from __future__ import annotations

import json

from agent.MediaEngine.nodes.base_node import BaseMediaNode
from agent.MediaEngine.prompts.prompts import MEDIA_SEARCH_PLAN_SYSTEM_PROMPT
from agent.MediaEngine.state.state import MediaEngineState, MediaSearchPlan
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.MediaEngine.utils.ranking import is_technical_context
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient


class MediaSearchNode(BaseMediaNode):
    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        crawler: MediaPerspectiveCrawler,
    ) -> None:
        self._chat_client = chat_client
        self._crawler = crawler

    def run(self, state: MediaEngineState, **kwargs) -> MediaEngineState:
        plan = self._build_plan(state)
        state.search_plan = plan

        all_hits = []
        for query in plan.social_queries:
            all_hits.extend(
                self._crawler.search(
                    query=query,
                    platform_type="social",
                    is_technical=plan.is_technical,
                    max_results=3,
                )
            )
        for query in plan.community_queries:
            all_hits.extend(
                self._crawler.search(
                    query=query,
                    platform_type="community",
                    is_technical=plan.is_technical,
                    max_results=4,
                )
            )
        for query in plan.blog_queries:
            all_hits.extend(
                self._crawler.search(
                    query=query,
                    platform_type="blog",
                    is_technical=plan.is_technical,
                    max_results=3,
                )
            )

        state.search_hits = self._dedupe_hits(all_hits)
        state.crawled_documents = self._crawler.fetch_documents(state.search_hits, max_documents=8)
        return state

    def _build_plan(self, state: MediaEngineState) -> MediaSearchPlan:
        if self._chat_client is None:
            return self._fallback_plan(state)

        context = state.request_context
        is_technical = is_technical_context(
            context.domain,
            context.subdomains,
            context.focus_points,
        )
        user_prompt = json.dumps(
            {
                "domain": context.domain,
                "subdomains": context.subdomains,
                "time_window": context.time_window,
                "focus_points": context.focus_points,
                "constraints": context.constraints,
                "is_technical": is_technical,
            },
            ensure_ascii=False,
        )
        try:
            payload = self._chat_client.complete_json(
                system_prompt=MEDIA_SEARCH_PLAN_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return MediaSearchPlan(
                social_queries=[str(item).strip() for item in payload.get("social_queries", []) if str(item).strip()],
                community_queries=[
                    str(item).strip() for item in payload.get("community_queries", []) if str(item).strip()
                ],
                blog_queries=[str(item).strip() for item in payload.get("blog_queries", []) if str(item).strip()],
                reasoning=str(payload.get("reasoning", "")).strip()
                or "优先聚合当前社区、社交媒体和技术博客对该主题的观点。",
                is_technical=bool(payload.get("is_technical", is_technical)),
            )
        except Exception:
            return self._fallback_plan(state)

    @staticmethod
    def _fallback_plan(state: MediaEngineState) -> MediaSearchPlan:
        context = state.request_context
        technical = is_technical_context(context.domain, context.subdomains, context.focus_points)
        main_topic = context.subdomains[0] if context.subdomains else context.domain
        if technical:
            social_queries = [
                f"{context.domain} {main_topic} site:x.com OR site:twitter.com opinion trend",
                f"{context.domain} {main_topic} site:reddit.com discussion adoption",
            ]
            community_queries = [
                f"{context.domain} {main_topic} site:news.ycombinator.com discussion",
                f"{context.domain} {main_topic} site:github.com discussions OR site:v2ex.com",
            ]
            blog_queries = [
                f"{context.domain} {main_topic} engineering blog future trend",
                f"{context.domain} {main_topic} site:juejin.cn OR site:zhihu.com blog analysis",
            ]
        else:
            social_queries = [f"{context.domain} {main_topic} social media discussion trend"]
            community_queries = [f"{context.domain} {main_topic} community discussion outlook"]
            blog_queries = [f"{context.domain} {main_topic} blog analysis future trend"]
        return MediaSearchPlan(
            social_queries=social_queries,
            community_queries=community_queries,
            blog_queries=blog_queries,
            reasoning="未拿到 LLM 规划结果，按社交媒体、技术社区、博客三类观点源生成默认计划。",
            is_technical=technical,
        )

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
