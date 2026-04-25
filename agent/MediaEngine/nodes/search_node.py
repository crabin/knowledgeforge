from __future__ import annotations

import json

from collections.abc import Callable
from typing import Any

from agent.MediaEngine.nodes.base_node import BaseMediaNode
from agent.MediaEngine.prompts.prompts import MEDIA_SEARCH_PLAN_SYSTEM_PROMPT
from agent.MediaEngine.state.state import MediaEngineState, MediaSearchPlan
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.MediaEngine.utils.ranking import is_technical_context
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.utils.query_normalization import normalize_query_term
from knowledgeforge.storage.realtime_reviewer import RealtimeReviewCandidate, RealtimeReviewResult
from knowledgeforge.utils.time import now_iso

MediaEventCallback = Callable[[str, dict[str, Any]], None]
MediaRealtimeFileCallback = Callable[[str, RealtimeReviewCandidate], RealtimeReviewResult]


class MediaSearchNode(BaseMediaNode):
    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        crawler: MediaPerspectiveCrawler,
        event_callback: MediaEventCallback | None = None,
        realtime_file_callback: MediaRealtimeFileCallback | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._crawler = crawler
        self._event_callback = event_callback
        self._realtime_file_callback = realtime_file_callback

    def run(self, state: MediaEngineState, **kwargs) -> MediaEngineState:
        plan = self._build_plan(state)
        state.search_plan = plan
        self._append_search_results(
            state,
            social_queries=plan.social_queries,
            community_queries=plan.community_queries,
            blog_queries=plan.blog_queries,
            is_technical=plan.is_technical,
        )
        return state

    def execute_plan(self, state: MediaEngineState, *, plan: MediaSearchPlan) -> MediaEngineState:
        self._normalize_domain(state)
        state.search_plan = plan
        self._append_search_results(
            state,
            social_queries=plan.social_queries,
            community_queries=plan.community_queries,
            blog_queries=plan.blog_queries,
            is_technical=plan.is_technical,
        )
        return state

    def supplement(
        self,
        state: MediaEngineState,
        *,
        social_queries: list[str],
        community_queries: list[str],
        blog_queries: list[str],
        is_technical: bool,
    ) -> MediaEngineState:
        self._append_search_results(
            state,
            social_queries=social_queries,
            community_queries=community_queries,
            blog_queries=blog_queries,
            is_technical=is_technical,
        )
        state.iteration_count += 1
        return state

    def _build_plan(self, state: MediaEngineState) -> MediaSearchPlan:
        self._normalize_domain(state)
        if self._chat_client is None:
            raise RuntimeError("MediaEngine plan generation requires an LLM chat client.")

        context = state.request_context
        is_technical = is_technical_context(
            state.normalized_domain or context.domain,
            context.subdomains,
            context.focus_points,
        )
        user_prompt = json.dumps(
            {
                "domain": state.normalized_domain or context.domain,
                "original_domain": context.domain,
                "aliases": state.domain_aliases,
                "search_terms": state.search_terms,
                "subdomains": context.subdomains,
                "time_window": context.time_window,
                "focus_points": context.focus_points,
                "constraints": context.constraints,
                "is_technical": is_technical,
            },
            ensure_ascii=False,
        )
        payload = self._chat_client.complete_json(
            system_prompt=MEDIA_SEARCH_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        social_queries = [str(item).strip() for item in payload.get("social_queries", []) if str(item).strip()]
        community_queries = [
            str(item).strip() for item in payload.get("community_queries", []) if str(item).strip()
        ]
        blog_queries = [str(item).strip() for item in payload.get("blog_queries", []) if str(item).strip()]
        if not (social_queries or community_queries or blog_queries):
            raise RuntimeError("MediaEngine LLM did not return any valid media queries.")
        return MediaSearchPlan(
            social_queries=social_queries,
            community_queries=community_queries,
            blog_queries=blog_queries,
            reasoning=str(payload.get("reasoning", "")).strip()
            or "优先聚合当前社区、社交媒体和技术博客对该主题的观点。",
            is_technical=bool(payload.get("is_technical", is_technical)),
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

    def _append_search_results(
        self,
        state: MediaEngineState,
        *,
        social_queries: list[str],
        community_queries: list[str],
        blog_queries: list[str],
        is_technical: bool,
    ) -> None:
        all_hits = list(state.search_hits)
        domain_phrases = self._domain_phrases(state)
        for index, query in enumerate(social_queries, start=1):
            self._record_event(state, "media_plan_item_started", {"query": query, "platform_type": "social"})
            hits = self._search(
                query=query,
                platform_type="social",
                is_technical=is_technical,
                max_results=3,
                domain_phrases=domain_phrases,
            )
            state.search_history.append({"query": query, "platform_type": "social", "hits": len(hits)})
            self._record_event(
                state,
                "media_search_executed",
                {"query": query, "platform_type": "social", "hits": len(hits)},
            )
            all_hits.extend(hits)
            self._save_realtime_query_documents(
                state,
                plan_item_id=f"M-S{index}",
                query=query,
                platform_type="social",
                hits=hits,
            )
        for index, query in enumerate(community_queries, start=1):
            self._record_event(state, "media_plan_item_started", {"query": query, "platform_type": "community"})
            hits = self._search(
                query=query,
                platform_type="community",
                is_technical=is_technical,
                max_results=4,
                domain_phrases=domain_phrases,
            )
            state.search_history.append({"query": query, "platform_type": "community", "hits": len(hits)})
            self._record_event(
                state,
                "media_search_executed",
                {"query": query, "platform_type": "community", "hits": len(hits)},
            )
            all_hits.extend(hits)
            self._save_realtime_query_documents(
                state,
                plan_item_id=f"M-C{index}",
                query=query,
                platform_type="community",
                hits=hits,
            )
        for index, query in enumerate(blog_queries, start=1):
            self._record_event(state, "media_plan_item_started", {"query": query, "platform_type": "blog"})
            hits = self._search(
                query=query,
                platform_type="blog",
                is_technical=is_technical,
                max_results=3,
                domain_phrases=domain_phrases,
            )
            state.search_history.append({"query": query, "platform_type": "blog", "hits": len(hits)})
            self._record_event(
                state,
                "media_search_executed",
                {"query": query, "platform_type": "blog", "hits": len(hits)},
            )
            all_hits.extend(hits)
            self._save_realtime_query_documents(
                state,
                plan_item_id=f"M-B{index}",
                query=query,
                platform_type="blog",
                hits=hits,
            )

        state.search_hits = self._dedupe_hits(all_hits)
        state.crawled_documents = self._crawler.fetch_documents(state.search_hits, max_documents=10)
        self._record_event(
            state,
            "media_documents_fetched",
            {"hit_count": len(state.search_hits), "document_count": len(state.crawled_documents)},
        )

    def _record_event(self, state: MediaEngineState, event: str, details: dict[str, object]) -> None:
        entry = {
            "event": event,
            "timestamp": now_iso(),
            "node": "MediaSearchNode",
            "details": details,
        }
        state.execution_log.append(entry)
        task_id = getattr(state.request_context, "task_id", "")
        if task_id and self._event_callback is not None:
            self._event_callback(task_id, entry)

    def _normalize_domain(self, state: MediaEngineState) -> None:
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
    def _domain_phrases(state: MediaEngineState) -> list[str]:
        return MediaSearchNode._dedupe_terms(
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
        platform_type: str,
        is_technical: bool,
        max_results: int,
        domain_phrases: list[str],
    ):
        try:
            return self._crawler.search(
                query=query,
                platform_type=platform_type,
                is_technical=is_technical,
                max_results=max_results,
                domain_phrases=domain_phrases,
            )
        except TypeError as exc:
            if "domain_phrases" not in str(exc):
                raise
            return self._crawler.search(
                query=query,
                platform_type=platform_type,
                is_technical=is_technical,
                max_results=max_results,
            )

    def _save_realtime_query_documents(
        self,
        state: MediaEngineState,
        *,
        plan_item_id: str,
        query: str,
        platform_type: str,
        hits: list[Any],
    ) -> None:
        task_id = getattr(state.request_context, "task_id", "")
        if not task_id or self._realtime_file_callback is None or not hits:
            return
        try:
            documents = self._crawler.fetch_documents(self._dedupe_hits(hits), max_documents=4)
            candidate = RealtimeReviewCandidate(
                agent="MediaEngine",
                round_number=state.round_number,
                plan_item_id=plan_item_id,
                query=query,
                source_type=platform_type,
                platform_type=platform_type,
                documents=documents,
                context=state.request_context,
            )
            result = self._realtime_file_callback(task_id, candidate)
            self._record_event(
                state,
                "media_realtime_file_reviewed",
                {
                    "plan_item_id": plan_item_id,
                    "query": query,
                    "platform_type": platform_type,
                    **result.to_dict(),
                },
            )
        except Exception as exc:
            self._record_event(
                state,
                "media_realtime_file_failed",
                {
                    "plan_item_id": plan_item_id,
                    "query": query,
                    "platform_type": platform_type,
                    "error": str(exc),
                    "failure_category": "file_write_failed",
                },
            )
