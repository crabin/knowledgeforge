from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from collections.abc import Callable
from typing import Any

from agent.MediaEngine.nodes.base_node import BaseMediaNode
from agent.MediaEngine.prompts.prompts import MEDIA_SEARCH_PLAN_SYSTEM_PROMPT
from agent.MediaEngine.state.state import MediaEngineState, MediaSearchPlan
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.MediaEngine.utils.ranking import is_technical_context
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.runtime.task_queue import QueuedTaskSpec, RetrievalTaskQueue
from knowledgeforge.utils.query_normalization import normalize_query_term
from knowledgeforge.storage.realtime_reviewer import RealtimeReviewCandidate, RealtimeReviewResult
from knowledgeforge.utils.time import now_iso

MediaEventCallback = Callable[[str, dict[str, Any]], None]
MediaRealtimeFileCallback = Callable[[str, RealtimeReviewCandidate], RealtimeReviewResult]


@dataclass(slots=True)
class MediaQueryTaskResult:
    plan_item_id: str
    query: str
    platform_type: str
    hits: list[Any]
    status: str
    error: str = ""


class MediaSearchNode(BaseMediaNode):
    MAX_SOCIAL_QUERIES = 2
    MAX_COMMUNITY_QUERIES = 3
    MAX_BLOG_QUERIES = 2
    _GENERIC_QUERY_TOKENS = {
        "and",
        "or",
        "site",
        "social",
        "media",
        "community",
        "discussion",
        "discussions",
        "forum",
        "forums",
        "blog",
        "blogs",
        "engineering",
        "analysis",
        "opinion",
        "opinions",
        "trend",
        "trends",
        "outlook",
        "future",
        "latest",
        "current",
        "view",
        "views",
        "debate",
        "debates",
        "adoption",
        "signal",
        "signals",
        "x",
        "twitter",
        "reddit",
        "hacker",
        "news",
        "github",
        "discussions",
        "v2ex",
        "juejin",
        "zhihu",
        "hn",
        "com",
        "cn",
        "io",
        "dev",
        "www",
        "http",
        "https",
    }

    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        crawler: MediaPerspectiveCrawler,
        event_callback: MediaEventCallback | None = None,
        realtime_file_callback: MediaRealtimeFileCallback | None = None,
        max_concurrent_network_tasks: int = 5,
        task_queue: RetrievalTaskQueue | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._crawler = crawler
        self._event_callback = event_callback
        self._realtime_file_callback = realtime_file_callback
        self._max_concurrent_network_tasks = max(1, max_concurrent_network_tasks)
        self._task_queue = task_queue

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
        social_queries = self._dedupe_queries(
            [str(item).strip() for item in payload.get("social_queries", []) if str(item).strip()],
            limit=self.MAX_SOCIAL_QUERIES,
        )
        community_queries = self._dedupe_queries(
            [str(item).strip() for item in payload.get("community_queries", []) if str(item).strip()],
            limit=self.MAX_COMMUNITY_QUERIES,
        )
        blog_queries = self._dedupe_queries(
            [str(item).strip() for item in payload.get("blog_queries", []) if str(item).strip()],
            limit=self.MAX_BLOG_QUERIES,
        )
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
        social_queries = self._dedupe_queries(
            social_queries,
            limit=self.MAX_SOCIAL_QUERIES,
            existing_queries=self._history_queries(state, platform_type="social"),
        )
        community_queries = self._dedupe_queries(
            community_queries,
            limit=self.MAX_COMMUNITY_QUERIES,
            existing_queries=self._history_queries(state, platform_type="community"),
        )
        blog_queries = self._dedupe_queries(
            blog_queries,
            limit=self.MAX_BLOG_QUERIES,
            existing_queries=self._history_queries(state, platform_type="blog"),
        )
        task_specs: list[tuple[str, str, str, int]] = []
        task_specs.extend((f"M-S{index}", query, "social", 3) for index, query in enumerate(social_queries, start=1))
        task_specs.extend(
            (f"M-C{index}", query, "community", 4) for index, query in enumerate(community_queries, start=1)
        )
        task_specs.extend((f"M-B{index}", query, "blog", 3) for index, query in enumerate(blog_queries, start=1))
        for plan_item_id, query, platform_type, _ in task_specs:
            self._record_event(
                state,
                "media_plan_item_started",
                {"plan_item_id": plan_item_id, "query": query, "platform_type": platform_type},
            )
        for task_result in self._run_media_tasks(
            state,
            task_specs=task_specs,
            is_technical=is_technical,
            domain_phrases=domain_phrases,
        ):
            state.search_history.append(
                {
                    "query": task_result.query,
                    "platform_type": task_result.platform_type,
                    "hits": len(task_result.hits),
                    "status": task_result.status,
                    "error": task_result.error,
                }
            )
            event_name = "media_search_failed" if task_result.status == "failed" else "media_search_executed"
            details = {
                "plan_item_id": task_result.plan_item_id,
                "query": task_result.query,
                "platform_type": task_result.platform_type,
                "hits": len(task_result.hits),
                "status": task_result.status,
            }
            if task_result.error:
                details["error"] = task_result.error
                details["failure_category"] = "network_query_failed"
            self._record_event(state, event_name, details)
            all_hits.extend(task_result.hits)
            self._save_realtime_query_documents(
                state,
                plan_item_id=task_result.plan_item_id,
                query=task_result.query,
                platform_type=task_result.platform_type,
                hits=task_result.hits,
            )

        state.search_hits = self._dedupe_hits(all_hits)
        state.crawled_documents = self._crawler.fetch_documents(state.search_hits, max_documents=10)
        self._record_event(
            state,
            "media_documents_fetched",
            {"hit_count": len(state.search_hits), "document_count": len(state.crawled_documents)},
        )

    def _run_media_tasks(
        self,
        state: MediaEngineState,
        *,
        task_specs: list[tuple[str, str, str, int]],
        is_technical: bool,
        domain_phrases: list[str],
    ) -> list[MediaQueryTaskResult]:
        if self._task_queue is None:
            max_workers = min(self._max_concurrent_network_tasks, len(task_specs))
            futures = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for plan_item_id, query, platform_type, max_results in task_specs:
                    futures.append(
                        executor.submit(
                            self._run_media_task,
                            plan_item_id=plan_item_id,
                            query=query,
                            platform_type=platform_type,
                            max_results=max_results,
                            is_technical=is_technical,
                            domain_phrases=domain_phrases,
                        )
                    )
                return [future.result() for future in as_completed(futures)]

        queued_tasks = [
            QueuedTaskSpec[MediaQueryTaskResult, None](
                task_id=plan_item_id,
                task_type="network_query_and_optional_llm_summary",
                payload={
                    "agent": "MediaEngine",
                    "query": query,
                    "platform_type": platform_type,
                    "round": state.round_number,
                },
                network_call=lambda plan_item_id=plan_item_id, query=query, platform_type=platform_type, max_results=max_results: self._run_media_task(
                    plan_item_id=plan_item_id,
                    query=query,
                    platform_type=platform_type,
                    max_results=max_results,
                    is_technical=is_technical,
                    domain_phrases=domain_phrases,
                ),
            )
            for plan_item_id, query, platform_type, max_results in task_specs
        ]
        queued_results = self._task_queue.run_tasks(queued_tasks)
        return [
            result.network_result
            if result.network_result is not None
            else MediaQueryTaskResult(
                plan_item_id=result.task_id,
                query=str(result.payload.get("query", "")),
                platform_type=str(result.payload.get("platform_type", "")),
                hits=[],
                status="failed",
                error=result.error or f"Media task {result.task_id} failed",
            )
            for result in queued_results
        ]

    def _run_media_task(
        self,
        *,
        plan_item_id: str,
        query: str,
        platform_type: str,
        max_results: int,
        is_technical: bool,
        domain_phrases: list[str],
    ) -> MediaQueryTaskResult:
        try:
            hits = self._search(
                query=query,
                platform_type=platform_type,
                is_technical=is_technical,
                max_results=max_results,
                domain_phrases=domain_phrases,
            )
        except Exception as exc:
            return MediaQueryTaskResult(
                plan_item_id=plan_item_id,
                query=query,
                platform_type=platform_type,
                hits=[],
                status="failed",
                error=str(exc),
            )
        status = "completed" if hits else "insufficient"
        return MediaQueryTaskResult(
            plan_item_id=plan_item_id,
            query=query,
            platform_type=platform_type,
            hits=hits,
            status=status,
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

    @staticmethod
    def _history_queries(state: MediaEngineState, *, platform_type: str) -> list[str]:
        return [
            str(item.get("query", "")).strip()
            for item in state.search_history
            if str(item.get("platform_type", "")).strip() == platform_type and str(item.get("query", "")).strip()
        ]

    @classmethod
    def _dedupe_queries(
        cls,
        queries: list[str],
        *,
        limit: int,
        existing_queries: list[str] | None = None,
    ) -> list[str]:
        deduped: list[str] = []
        seen_keys: set[str] = set()
        for query in existing_queries or []:
            seen_keys.add(cls._semantic_query_key(query))
        for query in queries:
            cleaned = " ".join(query.split())
            if not cleaned:
                continue
            key = cls._semantic_query_key(cleaned)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(cleaned)
            if len(deduped) >= limit:
                break
        return deduped

    @classmethod
    def _semantic_query_key(cls, query: str) -> str:
        lowered = query.lower()
        lowered = re.sub(r"site:[^\s)]+", " ", lowered)
        lowered = re.sub(r"https?://\S+", " ", lowered)
        lowered = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", lowered)
        tokens: list[str] = []
        seen = set()
        for token in lowered.split():
            if token in cls._GENERIC_QUERY_TOKENS:
                continue
            if len(token) == 1 and token.isascii():
                continue
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
        return " ".join(tokens) or " ".join(query.lower().split())

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
