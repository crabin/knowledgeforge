from __future__ import annotations

from agent.QueryEngine.nodes.base_node import QueryEventCallback
from agent.QueryEngine.nodes.formatting_node import QueryFormattingNode
from agent.QueryEngine.nodes.reflection_node import QueryReflectionNode
from agent.QueryEngine.nodes.search_node import QueryRealtimeFileCallback, QuerySearchNode
from agent.QueryEngine.nodes.summary_node import QuerySummaryNode
from agent.QueryEngine.state.state import QueryEngineState, SearchPlan, SearchQuestion
from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from agent.base import BaseEngine
from knowledgeforge.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)
from knowledgeforge.models import EnginePlan, EnginePlanItem, EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class QueryEngine(BaseEngine):
    name = "QueryEngine"

    def __init__(
        self,
        chat_client: OpenAICompatibleChatClient | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
        crawler: DomainKnowledgeCrawler | None = None,
        event_callback: QueryEventCallback | None = None,
        realtime_file_callback: QueryRealtimeFileCallback | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._embedding_client = embedding_client
        self._crawler = crawler or DomainKnowledgeCrawler()
        self._search_node = QuerySearchNode(
            chat_client=self._chat_client,
            crawler=self._crawler,
            event_callback=event_callback,
            realtime_file_callback=realtime_file_callback,
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

    def _engine_plan_from_search_plan(self, plan: SearchPlan) -> EnginePlan:
        timestamp = now_iso()
        return EnginePlan(
            agent_name=self.name,
            plan_items=[
                EnginePlanItem(
                    plan_item_id=question.plan_item_id,
                    title=question.question,
                    query_or_action=question.google_query,
                    targets=question.search_targets or question.expected_info,
                    success_criteria=question.success_criteria,
                    fallbacks=question.fallback_queries,
                    source_priority=question.source_priority,
                    status="planned",
                )
                for question in plan.questions
            ],
            reasoning=plan.reasoning,
            status="awaiting_confirmation",
            created_at=timestamp,
        )

    @staticmethod
    def _search_plan_from_engine_plan(plan: EnginePlan) -> SearchPlan:
        questions = [
            SearchQuestion(
                question=item.title,
                google_query=item.query_or_action,
                search_targets=item.targets,
                expected_info=item.targets,
                source_priority=item.source_priority,
                success_criteria=item.success_criteria,
                fallback_queries=item.fallbacks,
                status="planned",
                plan_item_id=item.plan_item_id,
            )
            for item in plan.plan_items
        ]
        official_queries = [
            item.query_or_action
            for item in plan.plan_items
            if not any(token in " ".join(item.source_priority).lower() for token in ["tutorial", "blog", "guide"])
        ]
        tutorial_queries = [
            item.query_or_action
            for item in plan.plan_items
            if any(token in " ".join(item.source_priority).lower() for token in ["tutorial", "blog", "guide"])
        ]
        return SearchPlan(
            official_queries=official_queries,
            tutorial_queries=tutorial_queries,
            official_domains=[],
            reasoning=plan.reasoning,
            questions=questions,
        )

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
