from __future__ import annotations

from agent.QueryEngine.nodes.base_node import BaseQueryNode
from agent.QueryEngine.state.state import QueryEngineState
from agent.QueryEngine.utils.ranking import reliability_for_source_type_and_url
from knowledgeforge.models import EngineRunResult, SourceRecord


class QueryFormattingNode(BaseQueryNode):
    def run(self, state: QueryEngineState, **kwargs) -> EngineRunResult:
        payload = state.summary_payload
        official_docs = [doc for doc in state.crawled_documents if doc.source_type == "official"]
        tutorial_docs = [doc for doc in state.crawled_documents if doc.source_type == "tutorial"]

        raw_material = [
            f"术语归一化：{state.request_context.domain} -> {state.normalized_domain or state.request_context.domain}",
            f"归一化说明：{state.normalization_reasoning or '无'}",
            f"搜索规划：{state.search_plan.reasoning if state.search_plan else '无'}",
            "查询计划：",
            *self._format_search_plan(state),
            f"反思结论：{state.reflection_plan.reasoning if state.reflection_plan else '无'}",
            f"候选官方域名：{', '.join(state.candidate_official_domains) if state.candidate_official_domains else '无'}",
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

        key_points = [str(item) for item in payload.get("key_points", []) if str(item).strip()]
        official_findings = [str(item) for item in payload.get("official_findings", []) if str(item).strip()]
        tutorial_findings = [str(item) for item in payload.get("tutorial_findings", []) if str(item).strip()]
        key_points.extend([f"官方文档：{item}" for item in official_findings[:2]])
        key_points.extend([f"教程补充：{item}" for item in tutorial_findings[:1]])

        return EngineRunResult(
            agent_name="QueryEngine",
            summary=str(payload.get("summary", "")).strip()
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
        )

    @staticmethod
    def _format_search_plan(state: QueryEngineState) -> list[str]:
        if not state.search_plan or not state.search_plan.questions:
            return ["- 无结构化查询问题。"]
        formatted: list[str] = []
        for index, question in enumerate(state.search_plan.questions, start=1):
            formatted.append(
                f"- Q{index} [{question.status}] {question.question} | Google 查询：{question.google_query}"
            )
            if question.expected_info:
                formatted.append(f"  预期信息：{'; '.join(question.expected_info)}")
            if question.success_criteria:
                formatted.append(f"  满足标准：{'; '.join(question.success_criteria)}")
            if question.fallback_queries:
                formatted.append(f"  补查查询：{'; '.join(question.fallback_queries)}")
        return formatted

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
