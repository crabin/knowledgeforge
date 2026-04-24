from __future__ import annotations

from agent.QueryEngine.nodes.formatting_node import QueryFormattingNode
from agent.QueryEngine.nodes.reflection_node import QueryReflectionNode
from agent.QueryEngine.nodes.search_node import QuerySearchNode
from agent.QueryEngine.nodes.summary_node import QuerySummaryNode
from agent.QueryEngine.state.state import QueryEngineState
from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from agent.base import BaseEngine
from knowledgeforge.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class QueryEngine(BaseEngine):
    name = "QueryEngine"

    def __init__(
        self,
        chat_client: OpenAICompatibleChatClient | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
        crawler: DomainKnowledgeCrawler | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._embedding_client = embedding_client
        self._crawler = crawler or DomainKnowledgeCrawler()
        self._search_node = QuerySearchNode(chat_client=self._chat_client, crawler=self._crawler)
        self._reflection_node = QueryReflectionNode(chat_client=self._chat_client)
        self._summary_node = QuerySummaryNode(chat_client=self._chat_client)
        self._formatting_node = QueryFormattingNode()

    def run(self, context: RequestContext, round_number: int) -> EngineRunResult:
        state = QueryEngineState.from_context(context=context, round_number=round_number)
        try:
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
            return self._fallback_result(context, round_number)

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
        )
