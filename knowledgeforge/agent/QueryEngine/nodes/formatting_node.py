from __future__ import annotations

from knowledgeforge.agent.QueryEngine.nodes.base_node import BaseQueryNode
from knowledgeforge.agent.QueryEngine.state.state import QueryEngineState
from knowledgeforge.agent.QueryEngine.utils.ranking import reliability_for_source_type_and_url
from knowledgeforge.server.models import EngineRunResult, SourceRecord


class QueryFormattingNode(BaseQueryNode):
    def run(self, state: QueryEngineState, **kwargs) -> EngineRunResult:
        payload = state.summary_payload
        official_docs = [doc for doc in state.crawled_documents if doc.source_type == "official"]
        tutorial_docs = [doc for doc in state.crawled_documents if doc.source_type == "tutorial"]
        source_cross_check_lines = [
            f"- {item.get('title', '')} | {item.get('url', '')}"
            for item in state.source_cross_check
        ] or ["- 无"]

        raw_material = [
            f"术语归一化：{state.request_context.domain} -> {state.normalized_domain or state.request_context.domain}",
            f"归一化说明：{state.normalization_reasoning or '无'}",
            f"搜索规划：{state.search_plan.reasoning if state.search_plan else '无'}",
            f"搜索意图：{state.search_intent}",
            f"宽泛搜索：{'; '.join(state.broad_queries) if state.broad_queries else '无'}",
            f"验证搜索：{'; '.join(state.verification_queries[:12]) if state.verification_queries else '无'}",
            "链接级采集计划：",
            *self._format_search_plan(state),
            "候选概念池：",
            *self._format_candidate_concepts(state),
            "验证矩阵：",
            *self._format_verification_matrix(state),
            "剔除项：",
            *self._format_excluded_concepts(state),
            f"反思结论：{state.reflection_plan.reasoning if state.reflection_plan else '无'}",
            f"候选官方域名：{', '.join(state.candidate_official_domains) if state.candidate_official_domains else '无'}",
            "来源交叉验证：",
            *source_cross_check_lines,
            "官方文档优先：",
            *[
                f"- {doc.title} | {doc.url}"
                for doc in official_docs[:4]
            ],
            "教程/补充资料：",
            *[
                f"- {doc.title} | {doc.url}"
                for doc in tutorial_docs[:3]
            ],
        ]
        if any(doc.embedding_dimensions for doc in state.crawled_documents):
            raw_material.append(
                f"Embedding 已生成：{len(state.crawled_documents)} 个文档向量，维度示例 {state.crawled_documents[0].embedding_dimensions}。"
            )
        if state.reflection_plan and state.reflection_plan.missing_aspects:
            raw_material.extend([f"- 缺口：{item}" for item in state.reflection_plan.missing_aspects])
        sources = [
            SourceRecord(
                title=doc.title,
                url=doc.url,
                publisher=doc.publisher,
                retrieved_at=state.collected_at,
                reliability=reliability_for_source_type_and_url(
                    doc.source_type,
                    doc.url,
                    state.candidate_official_domains or (state.search_plan.official_domains if state.search_plan else []),
                ),
                agent="QueryEngine",
                source_type=doc.source_type,
                snippet=doc.snippet[:240],
            )
            for doc in state.crawled_documents
        ]
        sources.sort(key=lambda item: (0 if item.source_type == "official" else 1, item.title.lower()))
        if not sources:
            sources = self._fallback_sources(state)
            raw_material.extend(
                [
                    "未抓到实时网页内容，已保留官方优先的查询规划作为最小可追溯输出。",
                    *[f"- 官方查询：{query}" for query in (state.search_plan.official_queries if state.search_plan else [])],
                    *[f"- 教程查询：{query}" for query in (state.search_plan.tutorial_queries if state.search_plan else [])],
                ]
            )
        if state.search_history:
            raw_material.extend(
                [
                    f"检索轨迹：{len(state.search_history)} 次查询，补检索轮次 {state.iteration_count}。",
                    *[
                        f"- {item.get('status', 'unknown')} | {item.get('source_type', 'unknown')} | {item.get('query', '')}"
                        for item in state.search_history[:8]
                    ],
                ]
            )

        structured_answer = payload.get("structured_answer") if isinstance(payload.get("structured_answer"), list) else []
        structured_key_points: list[str] = []
        for section in structured_answer:
            if not isinstance(section, dict):
                continue
            for item in section.get("items", []):
                if isinstance(item, dict) and item.get("name") and item.get("role"):
                    structured_key_points.append(f"{item['name']}：{item['role']}")
        key_points = [
            *structured_key_points,
            *[str(item) for item in payload.get("key_points", []) if str(item).strip()],
        ]
        official_findings = [str(item) for item in payload.get("official_findings", []) if str(item).strip()]
        tutorial_findings = [str(item) for item in payload.get("tutorial_findings", []) if str(item).strip()]
        key_points.extend([f"官方文档：{item}" for item in official_findings[:2]])
        key_points.extend([f"教程补充：{item}" for item in tutorial_findings[:1]])
        artifacts = self._build_file_artifacts(state)

        return EngineRunResult(
            agent_name="QueryEngine",
            summary=str(payload.get("summary", "")).strip()
            or str(payload.get("short_summary", "")).strip()
            or state.short_summary
            or f"{state.request_context.domain} 的查询结果已按官方文档优先策略完成整理。",
            key_points=key_points[:6] or [
                "官方文档优先，教程补充。",
                "已保留来源链接与出版方。",
            ],
            raw_material=raw_material,
            coverage_topics=[
                str(item) for item in payload.get("coverage_topics", state.request_context.subdomains)
            ],
            sources=sources,
            collected_at=state.collected_at,
            round_number=state.round_number,
            execution_log=state.execution_log,
            artifacts=artifacts,
        )

    @staticmethod
    def _format_search_plan(state: QueryEngineState) -> list[str]:
        if not state.search_plan or not state.search_plan.questions:
            return ["- 无结构化链接级计划项。"]
        formatted: list[str] = []
        for question in state.search_plan.questions:
            marker = "☑" if question.status == "completed" else "☐"
            formatted.append(
                f"- {marker} {question.plan_item_id or 'Q?'} [{question.status}] {question.article_title or question.question} | URL：{question.candidate_url or '待解析'}"
            )
            formatted.append(f"  子领域：{question.subdomain or '通用'}")
            formatted.append(f"  查询：{question.google_query}")
            if question.search_targets:
                formatted.append(f"  查询内容：{'; '.join(question.search_targets)}")
            if question.expected_info:
                formatted.append(f"  预期信息：{'; '.join(question.expected_info)}")
            if question.success_criteria:
                formatted.append(f"  满足标准：{'; '.join(question.success_criteria)}")
            if question.planned_path:
                formatted.append(f"  计划保存路径：{question.planned_path}")
            if question.skip_reason:
                formatted.append(f"  跳过原因：{question.skip_reason}")
            if question.fallback_queries:
                formatted.append(f"  补查查询：{'; '.join(question.fallback_queries)}")
            if question.authority_queries:
                formatted.append(f"  权威改写查询：{'; '.join(question.authority_queries)}")
            if question.provider:
                formatted.append(f"  搜索来源：{question.provider}")
            if question.evidence_match_reason:
                formatted.append(f"  匹配原因：{question.evidence_match_reason}")
        return formatted

    @staticmethod
    def _format_candidate_concepts(state: QueryEngineState) -> list[str]:
        if not state.candidate_concepts:
            return ["- 无"]
        return [
            f"- {concept.canonical_name} | mentions={concept.mentions} | category={concept.preliminary_category} | sources={len(concept.source_urls)}"
            for concept in state.candidate_concepts[:12]
        ]

    @staticmethod
    def _format_verification_matrix(state: QueryEngineState) -> list[str]:
        if not state.verification_matrix:
            return ["- 无"]
        return [
            f"- {'纳入' if item.included else '剔除'} | {item.canonical_name} | {item.category} | support={item.support_count} | reliable={item.reliable_support_count} | {item.reason}"
            for item in state.verification_matrix[:12]
        ]

    @staticmethod
    def _format_excluded_concepts(state: QueryEngineState) -> list[str]:
        if not state.excluded_concepts:
            return ["- 无"]
        return [
            f"- {item.get('name', '')}：{item.get('reason', '')}"
            for item in state.excluded_concepts[:8]
        ]

    @staticmethod
    def _fallback_sources(state: QueryEngineState) -> list[SourceRecord]:
        if state.search_plan and state.search_plan.questions:
            official_query = state.search_plan.questions[0].google_query
        elif state.search_plan and state.search_plan.official_queries:
            official_query = state.search_plan.official_queries[0]
        else:
            official_query = f"{state.request_context.domain} official documentation"
        tutorial_query = (
            state.search_plan.tutorial_queries[0]
            if state.search_plan and state.search_plan.tutorial_queries
            else f"{state.request_context.domain} tutorial"
        )
        return [
            SourceRecord(
                title=f"{state.request_context.domain} 官方文档检索规划",
                url=f"https://example.com/search?q={official_query.replace(' ', '+')}",
                publisher="query-plan",
                retrieved_at=state.collected_at,
                reliability="unknown",
                agent="QueryEngine",
                source_type="query_plan",
                snippet=official_query,
            ),
            SourceRecord(
                title=f"{state.request_context.domain} 教程检索规划",
                url=f"https://example.com/search?q={tutorial_query.replace(' ', '+')}",
                publisher="query-plan",
                retrieved_at=state.collected_at,
                reliability="unknown",
                agent="QueryEngine",
                source_type="query_plan",
                snippet=tutorial_query,
            ),
        ]

    @staticmethod
    def _build_file_artifacts(state: QueryEngineState) -> list[dict[str, object]]:
        by_path: dict[str, list] = {}
        for question in (state.search_plan.questions if state.search_plan else []):
            if not question.planned_path:
                continue
            by_path.setdefault(question.planned_path, []).append(question)
        artifacts: list[dict[str, object]] = []
        for path, questions in by_path.items():
            completed = [question for question in questions if question.status == "completed"]
            pending = [question for question in questions if question.status != "completed"]
            task_updates = []
            for question in questions:
                citation = None
                for doc in state.crawled_documents:
                    if doc.plan_item_id == question.plan_item_id or doc.planned_path == question.planned_path:
                        citation = {"title": doc.title, "url": doc.url, "publisher": doc.publisher}
                        break
                task_updates.append(
                    {
                        "task_id": question.existing_path or question.plan_item_id,
                        "status": question.status,
                        "citation": citation,
                    }
                )
            artifacts.append(
                {
                    "target_file_path": path,
                    "target_section": "证据与来源",
                    "state": "completed" if questions and not pending else ("partially_completed" if completed else "insufficient"),
                    "task_updates": task_updates,
                    "resolved_claims": [question.question for question in completed],
                    "remaining_gaps": [question.question for question in pending],
                    "content": "；".join([question.question for question in completed[:3]]) or "待继续补充权威来源。",
                    "query_hint": pending[0].google_query if pending else (questions[0].google_query if questions else ""),
                }
            )
        return artifacts
