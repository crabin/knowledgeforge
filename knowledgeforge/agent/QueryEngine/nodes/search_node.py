from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
from pathlib import Path

from collections.abc import Callable
from typing import Any

from knowledgeforge.agent.QueryEngine.nodes.base_node import BaseQueryNode, QueryEventCallback
from knowledgeforge.agent.QueryEngine.prompts.prompts import SEARCH_PLAN_SYSTEM_PROMPT
from knowledgeforge.agent.QueryEngine.state.state import QueryEngineState, SearchPlan, SearchQuestion
from knowledgeforge.agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.agent.QueryEngine.utils.ranking import (
    PREFERRED_TECH_REFERENCE_DOMAINS,
    PREFERRED_TUTORIAL_DOMAINS,
    build_site_constrained_queries,
    detect_candidate_official_domains,
    domains_for_source_priority,
    evidence_match_reason,
    score_evidence_match,
)
from knowledgeforge.server.utils.query_normalization import normalize_query_term
from knowledgeforge.server.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)
from knowledgeforge.server.storage.realtime_reviewer import RealtimeReviewCandidate, RealtimeReviewResult
from knowledgeforge.server.utils.file_contract import parse_contract_block
from knowledgeforge.server.utils.knowledge_tree import module_labels_by_id, plan_path_for_role
from knowledgeforge.server.runtime.task_queue import QueuedTaskSpec, RetrievalTaskQueue
from knowledgeforge.server.utils.paths import sanitize_path_segment
from knowledgeforge.server.utils.time import now_iso

QueryRealtimeFileCallback = Callable[[str, RealtimeReviewCandidate], RealtimeReviewResult]


@dataclass(slots=True)
class SearchAttemptResult:
    query: str
    hits: list[Any]
    status: str
    error: str = ""


@dataclass(slots=True)
class QuestionTaskResult:
    question: SearchQuestion
    source_type: str
    hits: list[Any]
    attempts: list[SearchAttemptResult]


class QuerySearchNode(BaseQueryNode):
    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        crawler: DomainKnowledgeCrawler,
        event_callback: QueryEventCallback | None = None,
        realtime_file_callback: QueryRealtimeFileCallback | None = None,
        max_concurrent_network_tasks: int = 5,
        task_queue: RetrievalTaskQueue | None = None,
        save_root: Path | None = None,
    ) -> None:
        super().__init__(event_callback=event_callback)
        self._chat_client = chat_client
        self._crawler = crawler
        self._realtime_file_callback = realtime_file_callback
        self._max_concurrent_network_tasks = max(1, max_concurrent_network_tasks)
        self._task_queue = task_queue
        self._save_root = save_root

    def run(
        self,
        state: QueryEngineState,
        *,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> QueryEngineState:
        plan = self._build_plan(state)
        state.search_plan = plan
        self._append_search_results(
            state,
            questions=plan.questions,
            embedding_client=embedding_client,
        )
        return state

    def execute_plan(
        self,
        state: QueryEngineState,
        *,
        plan: SearchPlan,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> QueryEngineState:
        self._normalize_domain(state)
        state.search_plan = plan
        self._append_search_results(
            state,
            questions=plan.questions,
            embedding_client=embedding_client,
        )
        return state

    def supplement(
        self,
        state: QueryEngineState,
        *,
        official_queries: list[str],
        tutorial_queries: list[str],
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> QueryEngineState:
        self._append_search_results(
            state,
            questions=self._questions_from_supplemental_queries(
                state,
                official_queries=official_queries,
                tutorial_queries=tutorial_queries,
            ),
            official_queries=official_queries,
            tutorial_queries=tutorial_queries,
            embedding_client=embedding_client,
        )
        state.iteration_count += 1
        return state

    def _build_plan(self, state: QueryEngineState) -> SearchPlan:
        context = state.request_context
        self._normalize_domain(state)
        blueprint_questions = self._questions_from_file_contracts(state)
        if blueprint_questions:
            return SearchPlan(
                official_queries=[question.google_query for question in blueprint_questions],
                tutorial_queries=[],
                official_domains=[],
                reasoning="优先读取知识文件骨架中的 query_tasks，按文件级证据槽位执行查询。",
                questions=blueprint_questions,
            )
        if self._chat_client is None:
            raise RuntimeError("QueryEngine plan generation requires an LLM chat client.")
        user_prompt = json.dumps(
            {
                "domain": state.normalized_domain or context.domain,
                "original_domain": context.domain,
                "aliases": state.domain_aliases,
                "search_terms": state.search_terms,
                "subdomains": context.subdomains,
                "core_topics": context.core_topics,
                "knowledge_modules": context.knowledge_modules,
                "navigation_targets": context.navigation_targets,
                "time_window": context.time_window,
                "focus_points": context.focus_points,
                "constraints": context.constraints,
            },
            ensure_ascii=False,
        )
        payload = self._chat_client.complete_json(
            system_prompt=SEARCH_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        self._record_event(state, "query_plan_llm_completed", {"payload_keys": sorted(payload.keys())})
        question_templates = self._parse_questions(payload.get("questions", []), state)
        official_queries = [
            str(item).strip() for item in payload.get("official_queries", []) if str(item).strip()
        ]
        tutorial_queries = [
            str(item).strip() for item in payload.get("tutorial_queries", []) if str(item).strip()
        ]
        if not question_templates:
            raise RuntimeError("QueryEngine LLM did not return any valid search questions.")
        question_templates = self._prepend_structural_templates(state, question_templates)
        questions = self._expand_questions_to_article_plan(
            state,
            question_templates,
            official_domains=[str(item).strip() for item in payload.get("official_domains", []) if str(item).strip()],
        )
        if not questions:
            raise RuntimeError("QueryEngine could not expand search questions into article-level plan items.")
        return SearchPlan(
            official_queries=official_queries or [
                question.google_query
                for question in questions
                if self._question_source_type(question) == "official"
            ],
            tutorial_queries=tutorial_queries or [
                question.google_query
                for question in questions
                if self._question_source_type(question) == "tutorial"
            ],
            official_domains=[str(item).strip() for item in payload.get("official_domains", []) if str(item).strip()],
            reasoning=str(payload.get("reasoning", "")).strip() or "官方优先，教程补充。",
            questions=questions,
        )

    def _questions_from_file_contracts(self, state: QueryEngineState) -> list[SearchQuestion]:
        if self._save_root is None:
            return []
        context = state.request_context
        questions: list[SearchQuestion] = []
        counter = 0
        for blueprint in context.knowledge_blueprint:
            relative_path = str(blueprint.get("relative_path", "")).strip()
            if not relative_path:
                continue
            file_path = self._save_root / sanitize_path_segment(context.domain, "domain") / relative_path
            if not file_path.exists():
                continue
            contract = parse_contract_block(file_path.read_text(encoding="utf-8"))
            if contract is None:
                continue
            for task in contract.get("query_tasks", []):
                if str(task.get("status", "")).strip() == "completed":
                    continue
                question = str(task.get("claim_or_gap", "")).strip() or str(blueprint.get("title", file_path.stem))
                query = str(task.get("query_intent", "")).strip()
                if not query:
                    continue
                counter += 1
                expected_info = [
                    str(item).strip() for item in task.get("expected_evidence", []) if str(item).strip()
                ]
                source_priority = [
                    str(item).strip() for item in task.get("preferred_source_types", []) if str(item).strip()
                ] or ["official documentation", "standard"]
                success_criteria = [
                    str(item).strip() for item in task.get("acceptance_criteria", []) if str(item).strip()
                ] or ["补齐可追溯来源"]
                questions.append(
                    SearchQuestion(
                        question=question,
                        google_query=query,
                        expected_info=expected_info,
                        source_priority=source_priority,
                        success_criteria=success_criteria,
                        authority_queries=self._build_authority_queries(
                            query=query,
                            domain=context.normalized_domain or context.domain,
                            expected_info=expected_info,
                            source_priority=source_priority,
                        ),
                        fallback_queries=[],
                        status="planned",
                        plan_item_id=f"Q{counter}",
                        search_targets=expected_info,
                        subdomain=str(blueprint.get("subdomain", "")),
                        doc_type=str(blueprint.get("doc_type", "article")),
                        doc_role=str(blueprint.get("doc_role", "topic_article")),
                        module_id=str(blueprint.get("module_id", "core_topics")),
                        module_label=str(blueprint.get("module_label", "Core Topics")),
                        article_title=str(blueprint.get("title", question)),
                        planned_path=file_path.as_posix(),
                        existing_path=str(task.get("task_id", "")),
                    )
                )
        return questions

    @staticmethod
    def _dedupe_hits(hits):
        seen = set()
        deduped = []
        for hit in sorted(hits, key=lambda item: item.score, reverse=True):
            if hit.url in seen:
                continue
            seen.add(hit.url)
            deduped.append(hit)
        return deduped

    def _append_search_results(
        self,
        state: QueryEngineState,
        *,
        questions: list[SearchQuestion] | None = None,
        official_queries: list[str] | None = None,
        tutorial_queries: list[str] | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None,
    ) -> None:
        official_queries = official_queries or []
        tutorial_queries = tutorial_queries or []
        all_hits = list(state.search_hits)
        domain_phrases = self._domain_phrases(state)
        plan_questions = questions or self._questions_from_query_lists(
            state,
            official_queries=official_queries,
            tutorial_queries=tutorial_queries,
        )
        self._prepare_plan_questions(plan_questions)
        self._record_event(
            state,
            "query_plan_created",
            {
                "question_count": len(plan_questions),
                "max_concurrent_network_tasks": self._max_concurrent_network_tasks,
                "questions": [
                    {
                        "plan_item_id": question.plan_item_id,
                        "question": question.question,
                        "google_query": question.google_query,
                        "search_targets": question.search_targets,
                        "expected_info": question.expected_info,
                        "source_priority": question.source_priority,
                        "success_criteria": question.success_criteria,
                        "authority_queries": question.authority_queries,
                        "fallback_queries": question.fallback_queries,
                        "status": question.status,
                        "url": question.candidate_url,
                        "subdomain": question.subdomain,
                        "planned_path": question.planned_path,
                        "review_status": question.review_status,
                        "skip_reason": question.skip_reason,
                    }
                    for question in plan_questions
                ],
            },
        )
        if not plan_questions:
            return
        for question in plan_questions:
            if question.status == "skipped":
                self._record_event(
                    state,
                    "query_plan_item_skipped",
                    self._question_log_details(question, status=question.status),
                )
                continue
            question.status = "in_progress"
            self._record_event(
                state,
                "query_plan_item_started",
                self._question_log_details(question, status=question.status),
            )
        runnable_questions = [question for question in plan_questions if question.status != "skipped"]
        task_results = self._run_question_tasks(state, runnable_questions, domain_phrases)
        for task_result in task_results:
            question = task_result.question
            question_hits = task_result.hits
            for attempt in task_result.attempts:
                selected_hits = [hit for hit in attempt.hits if self._question_satisfied([hit])]
                rejected_hits = [hit for hit in attempt.hits if not self._question_satisfied([hit])]
                state.search_history.append(
                    {
                        "question": question.question,
                        "query": attempt.query,
                        "expected_info": question.expected_info,
                        "source_type": task_result.source_type,
                        "hits": len(attempt.hits),
                        "status": attempt.status,
                        "error": attempt.error,
                        "url": question.candidate_url,
                        "subdomain": question.subdomain,
                        "providers": sorted(
                            {
                                str(getattr(hit, "provider", ""))
                                for hit in attempt.hits
                                if getattr(hit, "provider", "")
                            }
                        ),
                        "selected": [
                            {
                                "url": getattr(hit, "url", ""),
                                "score": getattr(hit, "score", 0),
                                "reason": getattr(hit, "rank_reason", ""),
                            }
                            for hit in selected_hits[:3]
                        ],
                        "rejected": [
                            {
                                "url": getattr(hit, "url", ""),
                                "score": getattr(hit, "score", 0),
                                "reason": getattr(hit, "rank_reason", "") or "score_below_threshold",
                            }
                            for hit in rejected_hits[:3]
                        ],
                    }
                )
                event_name = "query_search_failed" if attempt.status == "failed" else "query_search_executed"
                details = {
                    "plan_item_id": question.plan_item_id,
                    "question": question.question,
                    "query": attempt.query,
                    "search_targets": question.search_targets,
                    "expected_info": question.expected_info,
                    "source_type": task_result.source_type,
                    "hits": len(attempt.hits),
                    "status": attempt.status,
                    "url": question.candidate_url,
                    "subdomain": question.subdomain,
                    "planned_path": question.planned_path,
                }
                if attempt.error:
                    details["error"] = attempt.error
                    details["failure_category"] = "network_query_failed"
                self._record_event(state, event_name, details)
            all_hits.extend(question_hits)
            question.status = "completed" if self._question_satisfied(question_hits) else "insufficient"
            if question.status == "completed":
                question.completed_at = now_iso()
                selected_hit = max(question_hits, key=lambda hit: getattr(hit, "score", 0), default=None)
                if selected_hit is not None:
                    question.candidate_url = getattr(selected_hit, "url", question.candidate_url)
                    question.article_title = getattr(selected_hit, "title", question.article_title)
                    question.publisher = getattr(selected_hit, "publisher", question.publisher)
                    question.candidate_score = float(getattr(selected_hit, "score", 0.0))
                    question.provider = str(getattr(selected_hit, "provider", ""))
                    question.evidence_match_reason = str(getattr(selected_hit, "rank_reason", ""))
            self._record_event(
                state,
                "query_question_completed",
                {
                    "plan_item_id": question.plan_item_id,
                    "question": question.question,
                    "query": question.google_query,
                    "search_targets": question.search_targets,
                    "status": question.status,
                    "total_hits": len(question_hits),
                    "completed_at": question.completed_at,
                    "url": question.candidate_url,
                    "subdomain": question.subdomain,
                    "module_id": question.module_id,
                    "doc_role": question.doc_role,
                    "planned_path": question.planned_path,
                },
            )
            self._save_realtime_question_documents(
                state,
                question=question,
                source_type=task_result.source_type,
                hits=question_hits,
            )
        deduped_hits = self._dedupe_hits(all_hits)
        evidence_hits = [hit for hit in deduped_hits if self._question_satisfied([hit])]
        state.search_hits = evidence_hits
        state.candidate_official_domains = self._merge_candidate_domains(
            state,
            detect_candidate_official_domains(state.request_context.domain, evidence_hits),
        )
        state.crawled_documents = self._crawler.fetch_documents(evidence_hits, max_documents=8)
        question_by_url = {question.candidate_url: question for question in plan_questions if question.candidate_url}
        for document in state.crawled_documents:
            matched_question = question_by_url.get(document.url)
            if matched_question is None:
                continue
            document.subdomain = matched_question.subdomain
            document.doc_type = matched_question.doc_type
            document.planned_path = matched_question.planned_path
            document.plan_item_id = matched_question.plan_item_id
        self._record_event(
            state,
            "query_documents_fetched",
            {
                "hit_count": len(deduped_hits),
                "evidence_hit_count": len(evidence_hits),
                "document_count": len(state.crawled_documents),
            },
        )

        if embedding_client is not None and state.crawled_documents:
            try:
                vectors = embedding_client.embed_texts(
                    [doc.content[:800] or doc.snippet or doc.title for doc in state.crawled_documents]
                )
                for doc, vector in zip(state.crawled_documents, vectors):
                    doc.embedding_dimensions = len(vector)
                self._record_event(
                    state,
                    "query_embeddings_completed",
                    {
                        "document_count": len(state.crawled_documents),
                        "dimensions": state.crawled_documents[0].embedding_dimensions,
                    },
                )
            except Exception:
                self._record_event(
                    state,
                    "query_embeddings_failed",
                    {"document_count": len(state.crawled_documents)},
                )

    def _run_question_tasks(
        self,
        state: QueryEngineState,
        questions: list[SearchQuestion],
        domain_phrases: list[str],
    ) -> list[QuestionTaskResult]:
        if self._task_queue is None:
            max_workers = min(self._max_concurrent_network_tasks, len(questions))
            futures = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for question in questions:
                    source_type = self._question_source_type(question)
                    futures[
                        executor.submit(
                            self._run_question_task,
                            state,
                            question=question,
                            source_type=source_type,
                            domain_phrases=domain_phrases,
                        )
                    ] = question.plan_item_id
                return [future.result() for future in as_completed(futures)]

        queued_tasks = [
            QueuedTaskSpec[QuestionTaskResult, None](
                task_id=question.plan_item_id,
                task_type="network_query_and_optional_llm_summary",
                payload={
                    "agent": "QueryEngine",
                    "question": question.question,
                    "query": question.google_query,
                    "round": state.round_number,
                },
                network_call=lambda question=question, source_type=self._question_source_type(question): self._run_question_task(
                    state,
                    question=question,
                    source_type=source_type,
                    domain_phrases=domain_phrases,
                ),
            )
            for question in questions
        ]
        queued_results = self._task_queue.run_tasks(queued_tasks)
        ordered_results: list[QuestionTaskResult] = []
        for queued_result in queued_results:
            if queued_result.network_result is None:
                raise RuntimeError(queued_result.error or f"Query task {queued_result.task_id} failed")
            ordered_results.append(queued_result.network_result)
        return ordered_results

    def _parse_questions(self, items: object, state: QueryEngineState) -> list[SearchQuestion]:
        questions: list[SearchQuestion] = []
        if not isinstance(items, list):
            return questions
        for item in items:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            google_query = str(item.get("google_query", "")).strip()
            if not question or not google_query:
                continue
            questions.append(
                SearchQuestion(
                    question=question,
                    google_query=google_query,
                    search_targets=[
                        str(value).strip()
                        for value in item.get("search_targets", item.get("expected_info", []))
                        if str(value).strip()
                    ],
                    expected_info=[
                        str(value).strip()
                        for value in item.get("expected_info", [])
                        if str(value).strip()
                    ],
                    source_priority=[
                        str(value).strip()
                        for value in item.get("source_priority", [])
                        if str(value).strip()
                    ],
                    success_criteria=[
                        str(value).strip()
                        for value in item.get("success_criteria", [])
                        if str(value).strip()
                    ],
                    fallback_queries=[
                        str(value).strip()
                        for value in item.get("fallback_queries", [])
                        if str(value).strip()
                    ],
                    authority_queries=[
                        str(value).strip()
                        for value in item.get("authority_queries", [])
                        if str(value).strip()
                    ],
                    status="planned",
                    subdomain=str(item.get("subdomain", "")).strip()
                    or (state.request_context.subdomains[0] if state.request_context.subdomains else "通用"),
                    doc_type=str(item.get("doc_type", "source")).strip() or "source",
                    doc_role=str(item.get("doc_role", "")).strip() or "topic_article",
                    module_id=str(item.get("module_id", "")).strip() or "core_topics",
                    module_label=module_labels_by_id().get(
                        str(item.get("module_id", "")).strip() or "core_topics",
                        "Core Topics",
                    ),
                )
            )
        return questions

    def _expand_questions_to_article_plan(
        self,
        state: QueryEngineState,
        question_templates: list[SearchQuestion],
        *,
        official_domains: list[str],
    ) -> list[SearchQuestion]:
        existing_urls = self._existing_source_urls()
        domain_phrases = self._domain_phrases(state)
        questions: list[SearchQuestion] = []
        seen_urls: set[str] = set()
        for template in question_templates:
            source_type = self._question_source_type(template)
            hits = self._search(
                query=template.google_query,
                source_type=source_type,
                official_domains=official_domains,
                preferred_domains=[] if source_type == "official" else self._preferred_domains(),
                max_results=3 if source_type == "official" else 2,
                domain_phrases=domain_phrases,
            )
            hits = self._rank_question_hits(template, template.google_query, hits)
            if not hits:
                questions.append(
                    SearchQuestion(
                        question=template.question,
                        google_query=template.google_query,
                        search_targets=list(template.search_targets),
                        expected_info=list(template.expected_info),
                        source_priority=list(template.source_priority),
                        success_criteria=list(template.success_criteria),
                        authority_queries=list(template.authority_queries),
                        fallback_queries=list(template.fallback_queries),
                        status="planned",
                        subdomain=template.subdomain,
                        doc_type=template.doc_type,
                        doc_role=template.doc_role,
                        module_id=template.module_id,
                        module_label=template.module_label,
                        article_title=template.question,
                        source_kind=source_type,
                        planned_path=self._planned_article_path(
                            state,
                            subdomain=template.subdomain,
                            title=template.question,
                            module_id=template.module_id,
                            doc_role=template.doc_role,
                        ),
                    )
                )
                continue
            for hit in hits:
                url = str(getattr(hit, "url", "")).strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                article_question = SearchQuestion(
                    question=template.question,
                    google_query=template.google_query,
                    search_targets=list(template.search_targets),
                    expected_info=list(template.expected_info),
                    source_priority=list(template.source_priority),
                    success_criteria=list(template.success_criteria),
                    authority_queries=list(template.authority_queries),
                    fallback_queries=list(template.fallback_queries),
                    status="planned",
                    subdomain=template.subdomain,
                    doc_type=template.doc_type,
                    doc_role=template.doc_role,
                    module_id=template.module_id,
                    module_label=template.module_label,
                        article_title=hit.title,
                        candidate_url=url,
                        publisher=getattr(hit, "publisher", ""),
                        source_kind=source_type,
                        candidate_score=float(getattr(hit, "score", 0.0)),
                        provider=str(getattr(hit, "provider", "")),
                        evidence_match_reason=str(getattr(hit, "rank_reason", "")),
                        planned_path=self._planned_article_path(
                        state,
                        subdomain=template.subdomain,
                        title=hit.title,
                        module_id=template.module_id,
                        doc_role=template.doc_role,
                    ),
                )
                if url in existing_urls:
                    article_question.status = "skipped"
                    article_question.review_status = "duplicate_url"
                    article_question.skip_reason = "duplicate_url"
                    article_question.existing_path = existing_urls[url]
                questions.append(article_question)
        self._prepare_plan_questions(questions)
        return questions

    def _existing_source_urls(self) -> dict[str, str]:
        if self._save_root is None or not self._save_root.exists():
            return {}
        existing: dict[str, str] = {}
        for path in self._save_root.glob("**/*.md"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if line.strip().startswith("url: "):
                    existing[line.split("url:", 1)[1].strip().strip('"').strip("'")] = path.as_posix()
        return existing

    def _planned_article_path(
        self,
        state: QueryEngineState,
        *,
        subdomain: str,
        title: str,
        module_id: str,
        doc_role: str,
    ) -> str:
        return plan_path_for_role(
            save_root=self._save_root or Path("save"),
            domain=state.request_context.domain,
            module_id=module_id,
            subdomain=subdomain,
            doc_role=doc_role,
            title=title,
            suffix="query",
        )

    def _questions_from_query_lists(
        self,
        state: QueryEngineState,
        *,
        official_queries: list[str],
        tutorial_queries: list[str],
    ) -> list[SearchQuestion]:
        questions = [
            SearchQuestion(
                question=f"需要确认 {state.normalized_domain or state.request_context.domain} 的官方事实：{query}",
                google_query=query,
                search_targets=["官方定义", "权威说明", "关键事实"],
                expected_info=["官方定义", "权威说明", "关键事实"],
                source_priority=["official documentation", "standard", "vendor docs", "official GitHub"],
                success_criteria=["命中相关官方或权威来源"],
                fallback_queries=[],
                authority_queries=self._build_authority_queries(
                    query=query,
                    domain=state.normalized_domain or state.request_context.domain,
                    expected_info=["官方定义", "权威说明", "关键事实"],
                    source_priority=["official documentation", "standard", "vendor docs", "official GitHub"],
                ),
                subdomain=state.request_context.core_topics[0] if state.request_context.core_topics else "通用",
                module_id="core_topics",
                module_label="Core Topics",
                doc_role="topic_article",
            )
            for query in official_queries
        ]
        questions.extend(
            SearchQuestion(
                question=f"需要补充 {state.normalized_domain or state.request_context.domain} 的实践资料：{query}",
                google_query=query,
                search_targets=["教程示例", "实践步骤", "注意事项"],
                expected_info=["教程示例", "实践步骤", "注意事项"],
                source_priority=["tutorial", "technical blog", "reference guide"],
                success_criteria=["命中相关教程或技术参考"],
                fallback_queries=self._expand_preferred_queries([query])[1:],
                authority_queries=self._build_authority_queries(
                    query=query,
                    domain=state.normalized_domain or state.request_context.domain,
                    expected_info=["教程示例", "实践步骤", "注意事项"],
                    source_priority=["tutorial", "technical blog", "reference guide"],
                ),
                subdomain=state.request_context.core_topics[0] if state.request_context.core_topics else "通用",
                module_id="core_topics",
                module_label="Core Topics",
                doc_role="topic_article",
            )
            for query in tutorial_queries
        )
        return questions

    @staticmethod
    def _questions_from_supplemental_queries(
        state: QueryEngineState,
        *,
        official_queries: list[str],
        tutorial_queries: list[str],
    ) -> list[SearchQuestion]:
        questions: list[SearchQuestion] = []
        insufficient_questions = [
            question
            for question in (state.search_plan.questions if state.search_plan else [])
            if question.status == "insufficient"
        ]
        for query in official_queries:
            base_question = insufficient_questions[0].question if insufficient_questions else query
            questions.append(
                SearchQuestion(
                    question=f"补检索：{base_question}",
                    google_query=query,
                    search_targets=["补齐官方或权威证据"],
                    expected_info=["补齐官方或权威证据"],
                    source_priority=["official documentation", "standard", "vendor docs"],
                    success_criteria=["补检索命中相关官方或权威来源"],
                    authority_queries=[],
                    fallback_queries=[],
                    subdomain=insufficient_questions[0].subdomain if insufficient_questions else (state.request_context.core_topics[0] if state.request_context.core_topics else "通用"),
                    module_id=insufficient_questions[0].module_id if insufficient_questions else "core_topics",
                    module_label=insufficient_questions[0].module_label if insufficient_questions else "Core Topics",
                    doc_role=insufficient_questions[0].doc_role if insufficient_questions else "topic_article",
                )
            )
        for query in tutorial_queries:
            base_question = insufficient_questions[0].question if insufficient_questions else query
            questions.append(
                SearchQuestion(
                    question=f"补检索：{base_question}",
                    google_query=query,
                    search_targets=["补齐教程、案例或最佳实践证据"],
                    expected_info=["补齐教程、案例或最佳实践证据"],
                    source_priority=["tutorial", "technical blog", "reference guide"],
                    success_criteria=["补检索命中相关实践资料"],
                    authority_queries=[],
                    fallback_queries=[],
                    subdomain=insufficient_questions[0].subdomain if insufficient_questions else (state.request_context.core_topics[0] if state.request_context.core_topics else "通用"),
                    module_id=insufficient_questions[0].module_id if insufficient_questions else "core_topics",
                    module_label=insufficient_questions[0].module_label if insufficient_questions else "Core Topics",
                    doc_role=insufficient_questions[0].doc_role if insufficient_questions else "topic_article",
                )
            )
        return questions

    @staticmethod
    def _prepare_plan_questions(questions: list[SearchQuestion]) -> None:
        for index, question in enumerate(questions, start=1):
            if not question.plan_item_id:
                question.plan_item_id = f"Q{index}"
            if not question.search_targets:
                question.search_targets = list(question.expected_info)
            if not question.authority_queries:
                question.authority_queries = QuerySearchNode._build_authority_queries(
                    query=question.google_query,
                    domain=question.subdomain or question.question,
                    expected_info=question.expected_info,
                    source_priority=question.source_priority,
                )
            if not question.module_label:
                question.module_label = module_labels_by_id().get(question.module_id, "Core Topics")

    @staticmethod
    def _question_log_details(question: SearchQuestion, *, status: str | None = None) -> dict:
        return {
            "plan_item_id": question.plan_item_id,
            "question": question.question,
            "google_query": question.google_query,
            "search_targets": question.search_targets,
            "expected_info": question.expected_info,
            "source_priority": question.source_priority,
            "success_criteria": question.success_criteria,
            "authority_queries": question.authority_queries,
            "fallback_queries": question.fallback_queries,
            "status": status or question.status,
            "completed_at": question.completed_at,
            "url": question.candidate_url,
            "provider": question.provider,
            "candidate_score": question.candidate_score,
            "evidence_match_reason": question.evidence_match_reason,
            "subdomain": question.subdomain,
            "module_id": question.module_id,
            "module_label": question.module_label,
            "doc_role": question.doc_role,
            "planned_path": question.planned_path,
            "review_status": question.review_status,
            "skip_reason": question.skip_reason,
        }

    @staticmethod
    def _question_source_type(question: SearchQuestion) -> str:
        if question.source_kind:
            return question.source_kind
        priority_text = " ".join(question.source_priority).lower()
        if any(token in priority_text for token in ["tutorial", "blog", "guide", "example", "practice"]):
            return "tutorial"
        return "official"

    @staticmethod
    def _question_satisfied(hits) -> bool:
        return any(getattr(hit, "score", 0) >= 2.0 for hit in hits)

    def _run_question_task(
        self,
        state: QueryEngineState,
        *,
        question: SearchQuestion,
        source_type: str,
        domain_phrases: list[str],
    ) -> QuestionTaskResult:
        attempts: list[SearchAttemptResult] = []
        question_hits: list[Any] = []
        if question.candidate_url:
            try:
                hits = self._fetch_direct_hit(question=question, source_type=source_type)
                status = "completed" if self._question_satisfied(hits) else "insufficient"
                attempts.append(SearchAttemptResult(query=question.google_query, hits=hits, status=status))
                question_hits.extend(hits)
            except Exception as exc:
                attempts.append(
                    SearchAttemptResult(
                        query=question.google_query,
                        hits=[],
                        status="failed",
                        error=str(exc),
                    )
                )
            return QuestionTaskResult(
                question=question,
                source_type=source_type,
                hits=question_hits,
                attempts=attempts,
            )
        executable_queries = self._dedupe_terms(
            [question.google_query, *question.authority_queries, *question.fallback_queries]
        )
        for index, query in enumerate(executable_queries):
            if index > 0 and self._question_satisfied(question_hits):
                break
            try:
                hits = self._search_for_question(
                    state,
                    question=question,
                    query=query,
                    source_type=source_type,
                    domain_phrases=domain_phrases,
                )
            except Exception as exc:
                attempts.append(
                    SearchAttemptResult(
                        query=query,
                        hits=[],
                        status="failed",
                        error=str(exc),
                    )
                )
                continue
            status = "completed" if self._question_satisfied(hits) else "insufficient"
            attempts.append(SearchAttemptResult(query=query, hits=hits, status=status))
            question_hits.extend(hits)
        return QuestionTaskResult(
            question=question,
            source_type=source_type,
            hits=question_hits,
            attempts=attempts,
        )

    def _fetch_direct_hit(self, *, question: SearchQuestion, source_type: str) -> list[Any]:
        from knowledgeforge.agent.QueryEngine.state.state import SearchHit

        return [
            SearchHit(
                title=question.article_title or question.question,
                url=question.candidate_url,
                snippet=question.question,
                source_type=source_type,
                score=question.candidate_score,
                provider=question.provider or "approved_plan",
                rank_reason=question.evidence_match_reason or "用户已确认的候选链接。",
            )
        ]

    def _search_for_question(
        self,
        state: QueryEngineState,
        *,
        question: SearchQuestion,
        query: str,
        source_type: str,
        domain_phrases: list[str],
    ):
        if source_type == "official":
            preferred_domains = domains_for_source_priority(
                question.source_priority,
                query=query,
                expected_info=question.expected_info,
                max_domains=4,
            )
            return self._rank_question_hits(
                question,
                query,
                self._search(
                    query=query,
                    source_type="official",
                    official_domains=state.candidate_official_domains
                    or (state.search_plan.official_domains if state.search_plan else []),
                    preferred_domains=preferred_domains,
                    max_results=4,
                    domain_phrases=domain_phrases,
                ),
            )
        return self._rank_question_hits(
            question,
            query,
            self._search(
                query=query,
                source_type="tutorial",
                official_domains=state.search_plan.official_domains if state.search_plan else [],
                preferred_domains=self._preferred_domains(),
                max_results=3,
                domain_phrases=domain_phrases,
            ),
        )

    @staticmethod
    def _rank_question_hits(question: SearchQuestion, query: str, hits):
        ranked = []
        for hit in hits:
            match_score = score_evidence_match(
                title=getattr(hit, "title", ""),
                snippet=getattr(hit, "snippet", ""),
                url=getattr(hit, "url", ""),
                expected_info=question.expected_info,
                success_criteria=question.success_criteria,
                query=query,
            )
            hit.score = float(getattr(hit, "score", 0.0)) + match_score
            hit.rank_reason = evidence_match_reason(
                title=getattr(hit, "title", ""),
                snippet=getattr(hit, "snippet", ""),
                expected_info=question.expected_info,
                success_criteria=question.success_criteria,
            )
            ranked.append(hit)
        ranked.sort(key=lambda item: getattr(item, "score", 0), reverse=True)
        return ranked

    def _normalize_domain(self, state: QueryEngineState) -> None:
        if state.normalized_domain:
            return
        context = state.request_context
        if context.normalized_domain:
            state.normalized_domain = context.normalized_domain
            state.domain_aliases = self._dedupe_terms([context.domain, context.normalized_domain])
            state.search_terms = self._dedupe_terms([context.normalized_domain, *context.search_terms, context.domain])
            state.normalization_reasoning = context.clarification_summary or "已使用 Intake 阶段确认的领域归一化结果。"
            return
        normalized = normalize_query_term(
            state.request_context.domain,
            chat_client=self._chat_client,
        )
        state.normalized_domain = normalized.normalized_domain
        state.domain_aliases = normalized.aliases
        state.search_terms = normalized.search_terms
        state.normalization_reasoning = normalized.reasoning

    @staticmethod
    def _dedupe_terms(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen = set()
        for item in items:
            cleaned = item.strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

    @staticmethod
    def _preferred_domains() -> list[str]:
        return [*PREFERRED_TUTORIAL_DOMAINS, *PREFERRED_TECH_REFERENCE_DOMAINS]

    @staticmethod
    def _build_authority_queries(
        *,
        query: str,
        domain: str,
        expected_info: list[str],
        source_priority: list[str] | None = None,
    ) -> list[str]:
        compact_query = " ".join(query.split())
        compact_domain = " ".join(domain.split())
        evidence_terms = " ".join(item for item in expected_info[:2] if item).strip()
        priority_domains = domains_for_source_priority(
            source_priority or [],
            query=compact_query,
            expected_info=expected_info,
            max_domains=3,
        )
        candidates = [
            compact_query,
            *build_site_constrained_queries(compact_query, priority_domains, max_domains=3),
            f"{compact_query} official documentation",
            f"{compact_query} standard specification project homepage",
            f"{compact_domain} {evidence_terms} official documentation".strip(),
            f"{compact_query} paper benchmark reference",
        ]
        return QuerySearchNode._dedupe_terms(candidates)[1:4]

    def _expand_preferred_queries(self, tutorial_queries: list[str]) -> list[str]:
        expanded: list[str] = []
        for query in tutorial_queries:
            expanded.append(query)
            expanded.extend(build_site_constrained_queries(query, self._preferred_domains()))
        deduped: list[str] = []
        seen = set()
        for query in expanded:
            if query in seen:
                continue
            seen.add(query)
            deduped.append(query)
        return deduped

    @staticmethod
    def _merge_candidate_domains(state: QueryEngineState, domains: list[str]) -> list[str]:
        merged = list(state.candidate_official_domains)
        for domain in state.search_plan.official_domains if state.search_plan else []:
            if domain not in merged:
                merged.append(domain)
        for domain in domains:
            if domain not in merged:
                merged.append(domain)
        return merged

    @staticmethod
    def _domain_phrases(state: QueryEngineState) -> list[str]:
        return QuerySearchNode._dedupe_terms(
            [
                state.normalized_domain or state.request_context.domain,
                state.request_context.domain,
                *state.domain_aliases,
                *state.search_terms,
            ]
        )

    def _search(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None,
        max_results: int,
        domain_phrases: list[str],
    ):
        try:
            return self._crawler.search(
                query=query,
                source_type=source_type,
                official_domains=official_domains,
                preferred_domains=preferred_domains,
                max_results=max_results,
                domain_phrases=domain_phrases,
            )
        except TypeError as exc:
            if "domain_phrases" not in str(exc):
                raise
            return self._crawler.search(
                query=query,
                source_type=source_type,
                official_domains=official_domains,
                preferred_domains=preferred_domains,
                max_results=max_results,
            )

    def _save_realtime_question_documents(
        self,
        state: QueryEngineState,
        *,
        question: SearchQuestion,
        source_type: str,
        hits: list[Any],
    ) -> None:
        task_id = getattr(state.request_context, "task_id", "")
        if not task_id or self._realtime_file_callback is None or not hits:
            return
        try:
            documents = self._crawler.fetch_documents(self._dedupe_hits(hits), max_documents=1)
            for document in documents:
                document.subdomain = question.subdomain
                document.doc_type = question.doc_type
                document.planned_path = question.planned_path
                document.plan_item_id = question.plan_item_id
            candidate = RealtimeReviewCandidate(
                agent="QueryEngine",
                round_number=state.round_number,
                plan_item_id=question.plan_item_id,
                query=question.google_query,
                source_type=source_type,
                documents=documents,
                context=state.request_context,
                subdomain=question.subdomain,
                doc_type=question.doc_type,
                module_id=question.module_id,
                module_label=question.module_label,
                doc_role=question.doc_role,
                planned_path=question.planned_path,
                article_title=question.article_title or question.question,
                url=question.candidate_url,
            )
            result = self._realtime_file_callback(task_id, candidate)
            self._record_event(
                state,
                "query_realtime_file_reviewed",
                {
                    "plan_item_id": question.plan_item_id,
                    "question": question.question,
                    "query": question.google_query,
                    "url": question.candidate_url,
                    "subdomain": question.subdomain,
                    "module_id": question.module_id,
                    "doc_role": question.doc_role,
                    "planned_path": question.planned_path,
                    "review_status": result.status,
                    **result.to_dict(),
                },
            )
        except Exception as exc:
            self._record_event(
                state,
                "query_realtime_file_failed",
                {
                    "plan_item_id": question.plan_item_id,
                    "question": question.question,
                    "query": question.google_query,
                    "error": str(exc),
                    "failure_category": "file_write_failed",
                },
            )

    def _prepend_structural_templates(
        self,
        state: QueryEngineState,
        questions: list[SearchQuestion],
    ) -> list[SearchQuestion]:
        context = state.request_context
        bootstrap = [
            SearchQuestion(
                question=f"建立 {context.domain} 的领域总览",
                google_query=f"{state.normalized_domain or context.domain} overview official documentation",
                search_targets=["领域定义", "核心问题", "重要性"],
                expected_info=["领域定义", "核心问题", "主要应用"],
                source_priority=["official documentation", "standard", "vendor docs"],
                success_criteria=["命中领域总览级权威来源"],
                fallback_queries=[f"{state.normalized_domain or context.domain} introduction authoritative source"],
                subdomain="领域总览",
                doc_type="summary",
                doc_role="domain_overview",
                module_id="overview",
                module_label="Overview",
            ),
            SearchQuestion(
                question=f"建立 {context.domain} 的基础知识导航",
                google_query=f"{state.normalized_domain or context.domain} fundamentals official guide",
                search_targets=["基础概念", "理论前置", "核心术语"],
                expected_info=["基础概念", "理论前置", "核心术语"],
                source_priority=["official documentation", "reference guide", "standard"],
                success_criteria=["命中基础知识权威或高可信资料"],
                fallback_queries=[f"{state.normalized_domain or context.domain} basics reference guide"],
                subdomain="基础知识",
                doc_type="article",
                doc_role="module_doc",
                module_id="foundations",
                module_label="Foundations",
            ),
            SearchQuestion(
                question=f"建立 {context.domain} 的论文脉络入口",
                google_query=f"{state.normalized_domain or context.domain} survey papers recent papers",
                search_targets=["综述论文", "最新研究方向", "代表论文"],
                expected_info=["综述论文", "最新研究方向", "代表论文"],
                source_priority=["survey paper", "official publication", "reference guide"],
                success_criteria=["命中论文脉络相关高可信资料"],
                fallback_queries=[f"{state.normalized_domain or context.domain} recent papers survey"],
                subdomain="论文阅读",
                doc_type="article",
                doc_role="module_doc",
                module_id="papers",
                module_label="Papers",
            ),
        ]
        for topic in context.core_topics:
            bootstrap.append(
                SearchQuestion(
                    question=f"建立 {topic} 的核心主题入口",
                    google_query=f"{state.normalized_domain or context.domain} {topic} official guide",
                    search_targets=["主题定义", "代表方法", "适用场景"],
                    expected_info=["主题定义", "代表方法", "适用场景"],
                    source_priority=["official documentation", "standard", "vendor docs", "official GitHub"],
                    success_criteria=["命中该主题的权威或高可信资料"],
                    fallback_queries=[f"{state.normalized_domain or context.domain} {topic} reference documentation"],
                    subdomain=topic,
                    doc_type="article",
                    doc_role="topic_overview",
                    module_id="core_topics",
                    module_label="Core Topics",
                )
            )
        return [*bootstrap, *questions]
