from __future__ import annotations

from agent.MediaEngine.nodes.formatting_node import MediaFormattingNode
from agent.MediaEngine.nodes.reflection_node import MediaReflectionNode
from agent.MediaEngine.nodes.search_node import MediaEventCallback, MediaRealtimeFileCallback, MediaSearchNode
from agent.MediaEngine.nodes.summary_node import MediaSummaryNode
from agent.MediaEngine.state.state import MediaEngineState
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.base import BaseEngine
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.models import EnginePlan, EnginePlanItem, EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class MediaEngine(BaseEngine):
    name = "MediaEngine"

    def __init__(
        self,
        chat_client: OpenAICompatibleChatClient | None = None,
        planning_chat_client: OpenAICompatibleChatClient | None = None,
        crawler: MediaPerspectiveCrawler | None = None,
        event_callback: MediaEventCallback | None = None,
        realtime_file_callback: MediaRealtimeFileCallback | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._planning_chat_client = planning_chat_client or chat_client
        self._crawler = crawler or MediaPerspectiveCrawler()
        self._search_node = MediaSearchNode(
            chat_client=self._planning_chat_client,
            crawler=self._crawler,
            event_callback=event_callback,
            realtime_file_callback=realtime_file_callback,
        )
        self._reflection_node = MediaReflectionNode(chat_client=self._chat_client)
        self._summary_node = MediaSummaryNode(chat_client=self._chat_client)
        self._formatting_node = MediaFormattingNode()

    def plan(self, context: RequestContext, round_number: int) -> EnginePlan:
        state = MediaEngineState.from_context(context=context, round_number=round_number)
        search_plan = self._search_node._build_plan(state)
        return self._engine_plan_from_search_plan(search_plan)

    def run(
        self,
        context: RequestContext,
        round_number: int,
        approved_plan: EnginePlan | None = None,
    ) -> EngineRunResult:
        state = MediaEngineState.from_context(context=context, round_number=round_number)
        try:
            if approved_plan is not None:
                state = self._search_node.execute_plan(
                    state,
                    plan=self._search_plan_from_engine_plan(approved_plan),
                )
            else:
                state = self._search_node.run(state)
            state = self._reflection_node.run(state)
            if state.reflection_plan and (
                state.reflection_plan.supplementary_social_queries
                or state.reflection_plan.supplementary_community_queries
                or state.reflection_plan.supplementary_blog_queries
            ):
                state = self._search_node.supplement(
                    state,
                    social_queries=state.reflection_plan.supplementary_social_queries,
                    community_queries=state.reflection_plan.supplementary_community_queries,
                    blog_queries=state.reflection_plan.supplementary_blog_queries,
                    is_technical=state.search_plan.is_technical if state.search_plan else False,
                )
            state = self._summary_node.run(state)
            return self._formatting_node.run(state)
        except Exception:
            if approved_plan is None:
                raise
            return self._fallback_result(context, round_number)

    def _engine_plan_from_search_plan(self, plan) -> EnginePlan:
        timestamp = now_iso()
        items: list[EnginePlanItem] = []
        groups = [
            ("M-S", "社交媒体观点检索", plan.social_queries, "social", ["社交讨论", "实时观点", "采用信号"]),
            ("M-C", "技术社区讨论检索", plan.community_queries, "community", ["社区共识", "争议点", "实践反馈"]),
            ("M-B", "博客与长文趋势检索", plan.blog_queries, "blog", ["趋势分析", "落地案例", "未来方向"]),
        ]
        for prefix, title, queries, platform_type, targets in groups:
            for index, query in enumerate(queries, start=1):
                items.append(
                    EnginePlanItem(
                        plan_item_id=f"{prefix}{index}",
                        title=title,
                        query_or_action=query,
                        targets=targets,
                        success_criteria=[f"命中相关 {platform_type} 来源", "结果能补充观点或趋势语境"],
                        fallbacks=[],
                        source_priority=[platform_type],
                    )
                )
        return EnginePlan(
            agent_name=self.name,
            plan_items=items,
            reasoning=plan.reasoning,
            status="awaiting_confirmation",
            created_at=timestamp,
        )

    @staticmethod
    def _search_plan_from_engine_plan(plan: EnginePlan):
        from agent.MediaEngine.state.state import MediaSearchPlan

        social_queries = [item.query_or_action for item in plan.plan_items if "social" in item.source_priority]
        community_queries = [item.query_or_action for item in plan.plan_items if "community" in item.source_priority]
        blog_queries = [item.query_or_action for item in plan.plan_items if "blog" in item.source_priority]
        return MediaSearchPlan(
            social_queries=social_queries,
            community_queries=community_queries,
            blog_queries=blog_queries,
            reasoning=plan.reasoning,
            is_technical=True,
        )

    def _fallback_result(self, context: RequestContext, round_number: int) -> EngineRunResult:
        timestamp = now_iso()
        return EngineRunResult(
            agent_name=self.name,
            summary=f"为 {context.domain} 生成一组面向社区观点、技术博客和社交讨论的趋势观察结果。",
            key_points=[
                "MediaEngine 关注的是当下怎么看、怎么用、接下来怎么演化。",
                "技术领域默认优先混合中外技术社区、社交平台与技术博客。",
                "当前结果为最小趋势检索规划，仍保留可追溯来源入口。",
            ],
            raw_material=[
                "社交媒体：",
                *[f"- {context.domain} {topic} X Reddit 最新讨论" for topic in context.subdomains[:2]],
                "技术社区：",
                *[f"- {context.domain} {topic} Hacker News GitHub Discussions V2EX" for topic in context.subdomains[:2]],
                "博客/长文：",
                *[f"- {context.domain} {topic} engineering blog future trend" for topic in context.subdomains[:2]],
            ],
            coverage_topics=context.subdomains,
            sources=[
                SourceRecord(
                    title=f"{context.domain} 社区趋势检索规划",
                    url=f"https://example.com/{round_number}/{self.name.lower()}",
                    publisher="media-plan",
                    retrieved_at=timestamp,
                    reliability="medium",
                    agent=self.name,
                    source_type="community",
                    snippet=f"{context.domain} community trend outlook",
                )
            ],
            collected_at=timestamp,
            round_number=round_number,
        )
