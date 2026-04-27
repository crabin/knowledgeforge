from __future__ import annotations

from pathlib import Path

from agent.MediaEngine.nodes.formatting_node import MediaFormattingNode
from agent.MediaEngine.nodes.reflection_node import MediaReflectionNode
from agent.MediaEngine.nodes.search_node import MediaEventCallback, MediaRealtimeFileCallback, MediaSearchNode
from agent.MediaEngine.nodes.summary_node import MediaSummaryNode
from agent.MediaEngine.state.state import MediaEngineState
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.base import BaseEngine
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.models import EnginePlan, EnginePlanItem, EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.runtime.task_queue import RetrievalTaskQueue
from knowledgeforge.utils.paths import sanitize_path_segment
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
        max_concurrent_network_tasks: int = 5,
        task_queue: RetrievalTaskQueue | None = None,
        save_root: Path | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._planning_chat_client = planning_chat_client or chat_client
        self._crawler = crawler or MediaPerspectiveCrawler()
        self._search_node = MediaSearchNode(
            chat_client=self._planning_chat_client,
            crawler=self._crawler,
            event_callback=event_callback,
            realtime_file_callback=realtime_file_callback,
            max_concurrent_network_tasks=max_concurrent_network_tasks,
            task_queue=task_queue,
            save_root=save_root,
        )
        self._reflection_node = MediaReflectionNode(chat_client=self._chat_client)
        self._summary_node = MediaSummaryNode(chat_client=self._chat_client)
        self._formatting_node = MediaFormattingNode()

    def plan(self, context: RequestContext, round_number: int) -> EnginePlan:
        state = MediaEngineState.from_context(context=context, round_number=round_number)
        search_plan = self._search_node._build_plan(state)
        search_plan.social_queries = self._search_node._dedupe_queries(
            search_plan.social_queries,
            limit=self._search_node.MAX_SOCIAL_QUERIES,
        )
        search_plan.community_queries = self._search_node._dedupe_queries(
            search_plan.community_queries,
            limit=self._search_node.MAX_COMMUNITY_QUERIES,
        )
        search_plan.blog_queries = self._search_node._dedupe_queries(
            search_plan.blog_queries,
            limit=self._search_node.MAX_BLOG_QUERIES,
        )
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
        for item in plan.items:
            items.append(
                EnginePlanItem(
                    plan_item_id=item.plan_item_id,
                    title=item.article_title or f"{item.platform_type} 候选资料",
                    query_or_action=item.query,
                    targets=self._targets_for_platform(item.platform_type),
                    success_criteria=[f"命中相关 {item.platform_type} 来源", "结果能补充观点或趋势语境"],
                    fallbacks=[],
                    source_priority=[item.platform_type],
                    status=item.status,
                    metadata={
                        "url": item.candidate_url,
                        "subdomain": item.subdomain,
                        "doc_type": item.doc_type,
                        "doc_role": item.doc_role,
                        "module_id": item.module_id,
                        "module_label": item.module_label,
                        "source_kind": item.source_kind,
                        "planned_path": item.planned_path,
                        "target_file_path": item.planned_path,
                        "target_section": "正文",
                        "article_title": item.article_title,
                        "skip_reason": item.skip_reason,
                        "existing_path": item.existing_path,
                    },
                )
            )
        return EnginePlan(
            agent_name=self.name,
            plan_items=items,
            reasoning=plan.reasoning,
            status="awaiting_confirmation",
            created_at=timestamp,
        )

    def _search_plan_from_engine_plan(self, plan: EnginePlan):
        from agent.MediaEngine.state.state import MediaSearchPlan

        deduped_items = MediaEngine._dedupe_plan_items(plan.plan_items)
        social_queries = self._search_node._dedupe_queries(
            [item.query_or_action for item in deduped_items if "social" in item.source_priority],
            limit=self._search_node.MAX_SOCIAL_QUERIES,
        )
        community_queries = self._search_node._dedupe_queries(
            [item.query_or_action for item in deduped_items if "community" in item.source_priority],
            limit=self._search_node.MAX_COMMUNITY_QUERIES,
        )
        blog_queries = self._search_node._dedupe_queries(
            [item.query_or_action for item in deduped_items if "blog" in item.source_priority],
            limit=self._search_node.MAX_BLOG_QUERIES,
        )
        media_items = self._search_node.items_from_engine_plan(deduped_items)
        return MediaSearchPlan(
            social_queries=social_queries,
            community_queries=community_queries,
            blog_queries=blog_queries,
            reasoning=plan.reasoning,
            is_technical=True,
            items=media_items,
        )

    @staticmethod
    def _dedupe_plan_items(items: list[EnginePlanItem]) -> list[EnginePlanItem]:
        deduped: list[EnginePlanItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            key = (
                str(item.metadata.get("url", "")).strip().lower() or MediaSearchNode._semantic_query_key(item.query_or_action),
                MediaSearchNode._semantic_query_key(item.query_or_action),
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
            artifacts=self._build_fallback_artifacts(context),
        )

    @staticmethod
    def _targets_for_platform(platform_type: str) -> list[str]:
        if platform_type == "social":
            return ["社交讨论", "实时观点", "采用信号"]
        if platform_type == "community":
            return ["社区共识", "争议点", "实践反馈"]
        return ["趋势分析", "落地案例", "未来方向"]

    @staticmethod
    def _build_fallback_artifacts(context: RequestContext) -> list[dict[str, object]]:
        artifacts: list[dict[str, object]] = []
        domain_segment = sanitize_path_segment(context.domain, "domain")
        for blueprint in context.knowledge_blueprint:
            owners = [str(item) for item in blueprint.get("owner_engine_candidates", [])]
            if "MediaEngine" not in owners:
                continue
            artifacts.append(
                {
                    "target_file_path": (Path("save") / domain_segment / str(blueprint.get("relative_path", ""))).as_posix(),
                    "target_section": "正文",
                    "state": "generated",
                    "content": f"MediaEngine 为 {blueprint.get('title', '')} 保留趋势、社区观点或案例补充位。",
                    "task_updates": [],
                }
            )
        return artifacts
