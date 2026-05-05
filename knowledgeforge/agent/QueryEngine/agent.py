from __future__ import annotations

from pathlib import Path

from knowledgeforge.agent.QueryEngine.nodes.base_node import QueryEventCallback
from knowledgeforge.agent.QueryEngine.nodes.formatting_node import QueryFormattingNode
from knowledgeforge.agent.QueryEngine.nodes.reflection_node import QueryReflectionNode
from knowledgeforge.agent.QueryEngine.nodes.search_node import QueryRealtimeFileCallback, QuerySearchNode
from knowledgeforge.agent.QueryEngine.nodes.summary_node import QuerySummaryNode
from knowledgeforge.agent.QueryEngine.state.state import QueryEngineState, SearchPlan, SearchQuestion
from knowledgeforge.agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.agent.base import BaseEngine
from knowledgeforge.server.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)
from knowledgeforge.server.models import EnginePlan, EnginePlanItem, EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.server.runtime.task_queue import RetrievalTaskQueue
from knowledgeforge.server.utils.time import now_iso


class QueryEngine(BaseEngine):
    name = "QueryEngine"

    def __init__(
        self,
        chat_client: OpenAICompatibleChatClient | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
        crawler: DomainKnowledgeCrawler | None = None,
        event_callback: QueryEventCallback | None = None,
        realtime_file_callback: QueryRealtimeFileCallback | None = None,
        max_concurrent_network_tasks: int = 5,
        task_queue: RetrievalTaskQueue | None = None,
        save_root: Path | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._embedding_client = embedding_client
        self._crawler = crawler or DomainKnowledgeCrawler()
        self._search_node = QuerySearchNode(
            chat_client=self._chat_client,
            crawler=self._crawler,
            event_callback=event_callback,
            realtime_file_callback=realtime_file_callback,
            max_concurrent_network_tasks=max_concurrent_network_tasks,
            task_queue=task_queue,
            save_root=save_root,
        )
        self._reflection_node = QueryReflectionNode(
            chat_client=self._chat_client,
            event_callback=event_callback,
        )
        self._summary_node = QuerySummaryNode(
            chat_client=self._chat_client,
            event_callback=event_callback,
        )
        self._formatting_node = QueryFormattingNode()

    def plan(self, context: RequestContext, round_number: int) -> EnginePlan:
        state = QueryEngineState.from_context(context=context, round_number=round_number)
        search_plan = self._search_node._build_plan(state)
        search_plan.questions = self._dedupe_search_questions(search_plan.questions)
        self._search_node._prepare_plan_questions(search_plan.questions)
        return self._engine_plan_from_search_plan(search_plan)

    def run(
        self,
        context: RequestContext,
        round_number: int,
        approved_plan: EnginePlan | None = None,
    ) -> EngineRunResult:
        state = QueryEngineState.from_context(context=context, round_number=round_number)
        try:
            if approved_plan is not None:
                state = self._search_node.execute_plan(
                    state,
                    plan=self._search_plan_from_engine_plan(approved_plan),
                    embedding_client=self._embedding_client,
                )
            else:
                state = self._search_node.run(state, embedding_client=self._embedding_client)
            state = self._reflection_node.run(state)
            if state.reflection_plan and (
                state.reflection_plan.supplementary_official_queries
                or state.reflection_plan.supplementary_tutorial_queries
            ):
                state = self._search_node.supplement(
                    state,
                    official_queries=state.reflection_plan.supplementary_official_queries,
                    tutorial_queries=state.reflection_plan.supplementary_tutorial_queries,
                    embedding_client=self._embedding_client,
                )
            state = self._summary_node.run(state)
            return self._formatting_node.run(state)
        except Exception:
            if approved_plan is None:
                raise
            return self._fallback_result(context, round_number)

    def _fallback_plan(self, context: RequestContext, round_number: int) -> EnginePlan:
        timestamp = now_iso()
        queries = list(context.initial_strategy) or [
            f"{context.domain} 官方文档",
            f"{context.domain} 最新进展",
        ]
        return EnginePlan(
            agent_name=self.name,
            plan_items=[
                EnginePlanItem(
                    plan_item_id=f"Q{i + 1}",
                    title=query,
                    query_or_action=query,
                    targets=list(context.subdomains) or [context.domain],
                    success_criteria=["命中官方或高可信来源"],
                    fallbacks=[],
                    source_priority=["official", "academic"],
                    status="planned",
                )
                for i, query in enumerate(queries[:5])
            ],
            reasoning="LLM 计划生成超时，已按初始策略生成回退计划。",
            status="awaiting_confirmation",
            created_at=timestamp,
        )

    def _engine_plan_from_search_plan(self, plan: SearchPlan) -> EnginePlan:
        timestamp = now_iso()
        questions = self._dedupe_search_questions(plan.questions)
        return EnginePlan(
            agent_name=self.name,
            plan_items=[
                EnginePlanItem(
                    plan_item_id=question.plan_item_id,
                    title=question.article_title or question.question,
                    query_or_action=question.google_query,
                    targets=question.search_targets or question.expected_info,
                    success_criteria=question.success_criteria,
                    fallbacks=question.fallback_queries,
                    source_priority=question.source_priority,
                    status=question.status,
                    metadata={
                        "url": question.candidate_url,
                        "subdomain": question.subdomain,
                        "doc_type": question.doc_type,
                        "doc_role": question.doc_role,
                        "module_id": question.module_id,
                        "module_label": question.module_label,
                        "publisher": question.publisher,
                        "source_kind": question.source_kind,
                        "authority_queries": question.authority_queries,
                        "candidate_score": question.candidate_score,
                        "provider": question.provider,
                        "evidence_match_reason": question.evidence_match_reason,
                        "planned_path": question.planned_path,
                        "target_file_path": question.planned_path,
                        "target_section": "证据与来源",
                        "article_title": question.article_title,
                        "review_status": question.review_status,
                        "skip_reason": question.skip_reason,
                        "existing_path": question.existing_path,
                        "question": question.question,
                    },
                )
                for question in questions
            ],
            reasoning=plan.reasoning,
            status="awaiting_confirmation",
            created_at=timestamp,
        )

    @staticmethod
    def _search_plan_from_engine_plan(plan: EnginePlan) -> SearchPlan:
        deduped_items = QueryEngine._dedupe_plan_items(plan.plan_items)
        questions = [
            SearchQuestion(
                question=item.title,
                google_query=item.query_or_action,
                search_targets=item.targets,
                expected_info=item.targets,
                source_priority=item.source_priority,
                success_criteria=item.success_criteria,
                fallback_queries=item.fallbacks,
                status=item.status if item.status != "approved" else "planned",
                plan_item_id=item.plan_item_id,
                subdomain=str(item.metadata.get("subdomain", "")),
                doc_type=str(item.metadata.get("doc_type", "source")),
                doc_role=str(item.metadata.get("doc_role", "topic_article")),
                module_id=str(item.metadata.get("module_id", "core_topics")),
                module_label=str(item.metadata.get("module_label", "Core Topics")),
                article_title=str(item.metadata.get("article_title", item.title)),
                candidate_url=str(item.metadata.get("url", "")),
                publisher=str(item.metadata.get("publisher", "")),
                source_kind=str(item.metadata.get("source_kind", "")),
                authority_queries=[str(value) for value in item.metadata.get("authority_queries", []) if str(value).strip()],
                candidate_score=float(item.metadata.get("candidate_score", 2.0 if item.metadata.get("url") else 0.0) or 0.0),
                provider=str(item.metadata.get("provider", "")),
                evidence_match_reason=str(item.metadata.get("evidence_match_reason", "")),
                planned_path=str(item.metadata.get("planned_path", "")),
                review_status=str(item.metadata.get("review_status", "")),
                skip_reason=str(item.metadata.get("skip_reason", "")),
                existing_path=str(item.metadata.get("existing_path", "")),
            )
            for item in deduped_items
        ]
        official_queries = [
            item.query_or_action
            for item in deduped_items
            if not any(token in " ".join(item.source_priority).lower() for token in ["tutorial", "blog", "guide"])
        ]
        tutorial_queries = [
            item.query_or_action
            for item in deduped_items
            if any(token in " ".join(item.source_priority).lower() for token in ["tutorial", "blog", "guide"])
        ]
        return SearchPlan(
            official_queries=official_queries,
            tutorial_queries=tutorial_queries,
            official_domains=[],
            reasoning=plan.reasoning,
            questions=questions,
        )

    @staticmethod
    def _dedupe_search_questions(questions: list[SearchQuestion]) -> list[SearchQuestion]:
        deduped: list[SearchQuestion] = []
        seen: set[tuple[str, str, str]] = set()
        for question in questions:
            key = (
                question.candidate_url.strip().lower(),
                " ".join(question.google_query.lower().split()),
                "|".join(sorted(" ".join(item.lower().split()) for item in question.search_targets)),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(question)
        return deduped

    @staticmethod
    def _dedupe_plan_items(items: list[EnginePlanItem]) -> list[EnginePlanItem]:
        deduped: list[EnginePlanItem] = []
        seen: set[tuple[str, str, str, str]] = set()
        for item in items:
            key = (
                str(item.metadata.get("url", "")).strip().lower(),
                " ".join(item.query_or_action.lower().split()),
                "|".join(sorted(" ".join(target.lower().split()) for target in item.targets)),
                "|".join(sorted(" ".join(priority.lower().split()) for priority in item.source_priority)),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _fallback_result(self, context: RequestContext, round_number: int) -> EngineRunResult:
        timestamp = now_iso()
        return EngineRunResult(
            agent_name=self.name,
            summary=f"为 {context.domain} 生成一组优先面向官方与权威来源的事实检索结果。",
            key_points=[
                f"优先覆盖 {', '.join(context.subdomains)} 的事实型资料。",
                "由于实时检索失败，当前结果回退为最小查询规划摘要。",
                "项目约束要求官方文档优先，教程类资料仅作为补充。",
            ],
            raw_material=[f"建议检索：{query}" for query in context.initial_strategy],
            coverage_topics=context.subdomains,
            sources=[
                SourceRecord(
                    title=f"{context.domain} 官方资料检索建议",
                    url=f"https://example.com/{round_number}/{self.name.lower()}",
                    publisher="query-plan",
                    retrieved_at=timestamp,
                    reliability="unknown",
                    agent=self.name,
                    source_type="query_plan",
                )
            ],
            collected_at=timestamp,
            round_number=round_number,
            execution_log=[
                {
                    "event": "query_engine_fallback_result",
                    "timestamp": timestamp,
                    "node": "QueryEngine",
                    "details": {"reason": "unhandled_query_engine_error"},
                }
            ],
        )

    def run_evidence_task(
        self,
        *,
        context: RequestContext,
        round_number: int,
        task: dict[str, object],
    ) -> EngineRunResult:
        rewritten = self._rewrite_evidence_task_queries(context, task)
        plan = EnginePlan(
            agent_name=self.name,
            plan_items=[
                EnginePlanItem(
                    plan_item_id=str(task.get("task_id", "Q1")),
                    title=str(task.get("claim_or_gap", task.get("query_text", "补充证据"))),
                    query_or_action=rewritten["primary_query"],
                    targets=[str(item) for item in task.get("expected_evidence", []) if str(item).strip()],
                    success_criteria=[str(item) for item in task.get("acceptance_criteria", []) if str(item).strip()],
                    fallbacks=rewritten["fallback_queries"],
                    source_priority=[str(item) for item in task.get("preferred_source_types", []) if str(item).strip()],
                    status="approved",
                    metadata={
                        "authority_queries": rewritten["authority_queries"],
                        "target_file_path": str(task.get("target_file_path", "")),
                        "planned_path": str(task.get("target_file_path", "")),
                        "target_section": str(task.get("target_section", "证据与来源")),
                        "subdomain": str(task.get("subdomain", "")),
                        "doc_role": str(task.get("doc_role", "module_doc")),
                        "module_id": str(task.get("module_id", "core_topics")),
                        "module_label": str(task.get("module_label", "Core Topics")),
                    },
                )
            ],
            reasoning="队列模式：执行单个文件级证据任务。",
            status="approved",
            created_at=now_iso(),
            approved_at=now_iso(),
        )
        result = self.run(context, round_number, plan)
        selected = next((source for source in result.sources if source.url.startswith(("http://", "https://"))), None)
        link_summary = (
            f"已为 {task.get('claim_or_gap', task.get('query_text', '目标知识点'))} 找到可信链接：{selected.url}"
            if selected
            else "未找到可用于主链路的可信链接。"
        )
        return EngineRunResult(
            agent_name=result.agent_name,
            summary=link_summary,
            key_points=[],
            raw_material=result.raw_material,
            coverage_topics=result.coverage_topics,
            sources=result.sources,
            collected_at=result.collected_at,
            round_number=result.round_number,
            execution_log=[
                *result.execution_log,
                {
                    "event": "evidence_link_selected" if selected else "evidence_link_missing",
                    "timestamp": now_iso(),
                    "node": "QueryEngine",
                    "details": {
                        "task_id": str(task.get("task_id", "")),
                        "selected_link": selected.url if selected else "",
                        "source_kind": selected.source_type if selected else "",
                    },
                },
            ],
            artifacts=[],
        )

    @staticmethod
    def _rewrite_evidence_task_queries(context: RequestContext, task: dict[str, object]) -> dict[str, list[str] | str]:
        domain = context.normalized_domain or context.domain
        query_text = QueryEngine._normalize_evidence_search_query(domain, str(task.get("query_text", "")).strip(), task)
        claim = QueryEngine._clean_evidence_search_text(str(task.get("claim_or_gap", "")).strip())
        expected = [
            cleaned
            for item in task.get("expected_evidence", [])
            if (cleaned := QueryEngine._clean_evidence_search_text(str(item).strip()))
        ]
        base = query_text or " ".join([domain, claim]).strip() or f"{domain} official documentation"
        evidence_terms = " ".join(expected[:2]).strip()
        candidates = [
            base,
            f"{domain} {claim} official documentation".strip() if claim else f"{base} official documentation",
            f"{base} standard specification project homepage",
            f"{base} paper benchmark reference",
            f"{domain} {evidence_terms} official documentation".strip() if evidence_terms else f"{base} reference guide",
        ]
        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            cleaned = " ".join(item.split())
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                deduped.append(cleaned)
        primary = deduped[0] if deduped else f"{domain} official documentation"
        return {
            "primary_query": primary,
            "authority_queries": deduped[1:4],
            "fallback_queries": deduped[4:],
        }

    @staticmethod
    def _normalize_evidence_search_query(domain: str, query_text: str, task: dict[str, object]) -> str:
        cleaned = QueryEngine._clean_evidence_search_text(query_text)
        boilerplate_terms = ("official documentation", "wikipedia", "standard", "paper", "project homepage")
        if cleaned and not any(term in cleaned.lower() for term in boilerplate_terms):
            return cleaned
        topic = cleaned
        for term in boilerplate_terms:
            topic = topic.replace(term, "")
            topic = topic.replace(term.title(), "")
        topic = " ".join(topic.split())
        if not topic:
            topic = str(task.get("subdomain", "") or task.get("target_node_title", "") or task.get("node_title", "")).strip()
        if topic and domain and domain.lower() not in topic.lower():
            return f"{domain} {topic}".strip()
        return topic or cleaned

    @staticmethod
    def _clean_evidence_search_text(text: str) -> str:
        cleaned = " ".join(text.split())
        if not cleaned:
            return ""
        noisy_markers = ("补充", "关键依据", "官方或高公信力链接", "与知识点最贴近")
        if any(marker in cleaned for marker in noisy_markers):
            return ""
        return cleaned
