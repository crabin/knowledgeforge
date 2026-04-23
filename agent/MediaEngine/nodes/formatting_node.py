from __future__ import annotations

from agent.MediaEngine.nodes.base_node import BaseMediaNode
from agent.MediaEngine.state.state import MediaEngineState
from agent.MediaEngine.utils.ranking import reliability_for_platform_type
from knowledgeforge.models import EngineRunResult, SourceRecord


class MediaFormattingNode(BaseMediaNode):
    def run(self, state: MediaEngineState, **kwargs) -> EngineRunResult:
        payload = state.summary_payload
        social_docs = [doc for doc in state.crawled_documents if doc.platform_type == "social"]
        community_docs = [doc for doc in state.crawled_documents if doc.platform_type == "community"]
        blog_docs = [doc for doc in state.crawled_documents if doc.platform_type == "blog"]

        raw_material = [
            f"搜索规划：{state.search_plan.reasoning if state.search_plan else '无'}",
            "社交媒体：",
            *[f"- {doc.title} | {doc.url}" for doc in social_docs[:3]],
            "技术社区：",
            *[f"- {doc.title} | {doc.url}" for doc in community_docs[:4]],
            "博客/长文：",
            *[f"- {doc.title} | {doc.url}" for doc in blog_docs[:3]],
        ]
        sources = [
            SourceRecord(
                title=doc.title,
                url=doc.url,
                publisher=doc.publisher,
                retrieved_at=state.collected_at,
                reliability=reliability_for_platform_type(doc.platform_type, doc.content),
                agent="MediaEngine",
                source_type=doc.platform_type,
                snippet=doc.snippet[:240],
            )
            for doc in state.crawled_documents
        ]
        if not sources:
            sources = self._fallback_sources(state)
            raw_material.extend(
                [
                    "未抓到实时观点内容，已保留分平台趋势检索规划作为最小可追溯输出。",
                    *[
                        f"- 社交查询：{query}"
                        for query in (state.search_plan.social_queries if state.search_plan else [])
                    ],
                    *[
                        f"- 社区查询：{query}"
                        for query in (state.search_plan.community_queries if state.search_plan else [])
                    ],
                    *[
                        f"- 博客查询：{query}"
                        for query in (state.search_plan.blog_queries if state.search_plan else [])
                    ],
                ]
            )

        key_points: list[str] = []
        if payload.get("current_sentiment"):
            key_points.append(f"当前主流看法：{payload['current_sentiment']}")
        key_points.extend(f"社区共识：{item}" for item in payload.get("mainstream_views", [])[:2])
        key_points.extend(f"主要争议：{item}" for item in payload.get("debates", [])[:1])
        key_points.extend(f"采用信号：{item}" for item in payload.get("adoption_signals", [])[:1])
        key_points.extend(f"未来走向：{item}" for item in payload.get("future_directions", [])[:2])

        return EngineRunResult(
            agent_name="MediaEngine",
            summary=str(payload.get("summary", "")).strip()
            or f"{state.request_context.domain} 的社区观点和趋势观察已完成整理。",
            key_points=key_points[:6]
            or [
                "当前结果优先反映社区观点、采用信号和趋势走向。",
                "社交、社区、博客来源已分开整理并保留追溯信息。",
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
    def _fallback_sources(state: MediaEngineState) -> list[SourceRecord]:
        social_query = (
            state.search_plan.social_queries[0]
            if state.search_plan and state.search_plan.social_queries
            else f"{state.request_context.domain} social discussion"
        )
        community_query = (
            state.search_plan.community_queries[0]
            if state.search_plan and state.search_plan.community_queries
            else f"{state.request_context.domain} community discussion"
        )
        blog_query = (
            state.search_plan.blog_queries[0]
            if state.search_plan and state.search_plan.blog_queries
            else f"{state.request_context.domain} blog trend"
        )
        return [
            SourceRecord(
                title=f"{state.request_context.domain} 社交讨论检索规划",
                url=f"https://example.com/search?q={social_query.replace(' ', '+')}",
                publisher="media-plan",
                retrieved_at=state.collected_at,
                reliability="low",
                agent="MediaEngine",
                source_type="social",
                snippet=social_query,
            ),
            SourceRecord(
                title=f"{state.request_context.domain} 技术社区检索规划",
                url=f"https://example.com/search?q={community_query.replace(' ', '+')}",
                publisher="media-plan",
                retrieved_at=state.collected_at,
                reliability="medium",
                agent="MediaEngine",
                source_type="community",
                snippet=community_query,
            ),
            SourceRecord(
                title=f"{state.request_context.domain} 博客趋势检索规划",
                url=f"https://example.com/search?q={blog_query.replace(' ', '+')}",
                publisher="media-plan",
                retrieved_at=state.collected_at,
                reliability="medium",
                agent="MediaEngine",
                source_type="blog",
                snippet=blog_query,
            ),
        ]
