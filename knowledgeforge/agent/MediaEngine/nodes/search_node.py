from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from collections.abc import Callable
from typing import Any

from knowledgeforge.agent.MediaEngine.nodes.base_node import BaseMediaNode
from knowledgeforge.agent.MediaEngine.prompts.prompts import MEDIA_SEARCH_PLAN_SYSTEM_PROMPT
from knowledgeforge.agent.MediaEngine.state.state import MediaEngineState, MediaPlanItem, MediaSearchPlan
from knowledgeforge.agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from knowledgeforge.agent.MediaEngine.utils.ranking import is_technical_context
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.runtime.task_queue import QueuedTaskSpec, RetrievalTaskQueue
from knowledgeforge.utils.query_normalization import normalize_query_term
from knowledgeforge.storage.realtime_reviewer import RealtimeReviewCandidate, RealtimeReviewResult
from knowledgeforge.utils.knowledge_tree import plan_path_for_role
from knowledgeforge.utils.paths import sanitize_path_segment, slugify_filename
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
    url: str = ""
    subdomain: str = ""
    planned_path: str = ""
    article_title: str = ""
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
        save_root: Path | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._crawler = crawler
        self._event_callback = event_callback
        self._realtime_file_callback = realtime_file_callback
        self._max_concurrent_network_tasks = max(1, max_concurrent_network_tasks)
        self._task_queue = task_queue
        self._save_root = save_root

    def run(self, state: MediaEngineState, **kwargs) -> MediaEngineState:
        plan = self._build_plan(state)
        state.search_plan = plan
        self._append_search_results(
            state,
            plan_items=plan.items,
            is_technical=plan.is_technical,
        )
        return state

    def execute_plan(self, state: MediaEngineState, *, plan: MediaSearchPlan) -> MediaEngineState:
        self._normalize_domain(state)
        state.search_plan = plan
        self._append_search_results(
            state,
            plan_items=plan.items,
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
            plan_items=self._expand_queries_to_items(
                state,
                social_queries=social_queries,
                community_queries=community_queries,
                blog_queries=blog_queries,
                is_technical=is_technical,
            ),
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
                "core_topics": context.core_topics,
                "knowledge_modules": context.knowledge_modules,
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
        plan = MediaSearchPlan(
            social_queries=social_queries,
            community_queries=community_queries,
            blog_queries=blog_queries,
            reasoning=str(payload.get("reasoning", "")).strip()
            or "优先聚合当前社区、社交媒体和技术博客对该主题的观点。",
            is_technical=bool(payload.get("is_technical", is_technical)),
        )
        plan.items = self._expand_queries_to_items(
            state,
            social_queries=plan.social_queries,
            community_queries=plan.community_queries,
            blog_queries=plan.blog_queries,
            is_technical=plan.is_technical,
        )
        return plan

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
        plan_items: list[MediaPlanItem],
        is_technical: bool,
    ) -> None:
        all_hits = list(state.search_hits)
        items_by_id = {item.plan_item_id: item for item in plan_items if item.plan_item_id}
        task_specs: list[tuple[MediaPlanItem, int]] = []
        for item in plan_items:
            if not item.plan_item_id:
                item.plan_item_id = self._default_plan_item_id(item.platform_type, len(task_specs) + 1)
            if item.status == "skipped":
                self._record_event(
                    state,
                    "media_plan_item_skipped",
                    self._item_log_details(item),
                )
                continue
            task_specs.append((item, self._default_max_results(item.platform_type)))
            self._record_event(
                state,
                "media_plan_item_started",
                self._item_log_details(item, status="in_progress"),
            )
        for task_result in self._run_media_tasks(
            state,
            task_specs=task_specs,
            is_technical=is_technical,
        ):
            if task_result.plan_item_id in items_by_id:
                items_by_id[task_result.plan_item_id].status = task_result.status
                if task_result.status == "completed":
                    items_by_id[task_result.plan_item_id].completed_at = now_iso()
            state.search_history.append(
                {
                    "query": task_result.query,
                    "platform_type": task_result.platform_type,
                    "hits": len(task_result.hits),
                    "status": task_result.status,
                    "error": task_result.error,
                    "url": task_result.url,
                    "subdomain": task_result.subdomain,
                }
            )
            event_name = "media_search_failed" if task_result.status == "failed" else "media_search_executed"
            details = {
                "plan_item_id": task_result.plan_item_id,
                "query": task_result.query,
                "platform_type": task_result.platform_type,
                "hits": len(task_result.hits),
                "status": task_result.status,
                "url": task_result.url,
                "subdomain": task_result.subdomain,
                "planned_path": task_result.planned_path,
            }
            if task_result.error:
                details["error"] = task_result.error
                details["failure_category"] = "network_query_failed"
            self._record_event(state, event_name, details)
            self._record_event(
                state,
                "media_plan_item_completed",
                {
                    "plan_item_id": task_result.plan_item_id,
                    "query": task_result.query,
                    "platform_type": task_result.platform_type,
                    "status": task_result.status,
                    "url": task_result.url,
                    "subdomain": task_result.subdomain,
                    "planned_path": task_result.planned_path,
                },
            )
            all_hits.extend(task_result.hits)
            self._save_realtime_query_documents(
                state,
                plan_item_id=task_result.plan_item_id,
                query=task_result.query,
                platform_type=task_result.platform_type,
                hits=task_result.hits,
                subdomain=task_result.subdomain,
                planned_path=task_result.planned_path,
                url=task_result.url,
                article_title=task_result.article_title,
            )

        state.search_hits = self._dedupe_hits(all_hits)
        state.crawled_documents = self._crawler.fetch_documents(state.search_hits, max_documents=10)
        hit_map = {hit.url: hit for hit in state.search_hits if getattr(hit, "url", "")}
        for doc in state.crawled_documents:
            hit = hit_map.get(doc.url)
            if hit is None:
                continue
            doc.subdomain = getattr(hit, "subdomain", "")
            doc.planned_path = getattr(hit, "planned_path", "")
            doc.plan_item_id = getattr(hit, "plan_item_id", "")
        self._record_event(
            state,
            "media_documents_fetched",
            {"hit_count": len(state.search_hits), "document_count": len(state.crawled_documents)},
        )

    def _run_media_tasks(
        self,
        state: MediaEngineState,
        *,
        task_specs: list[tuple[MediaPlanItem, int]],
        is_technical: bool,
    ) -> list[MediaQueryTaskResult]:
        if self._task_queue is None:
            max_workers = min(self._max_concurrent_network_tasks, len(task_specs))
            futures = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for item, max_results in task_specs:
                    futures.append(
                        executor.submit(
                            self._run_media_task,
                            item=item,
                            max_results=max_results,
                            is_technical=is_technical,
                        )
                    )
                return [future.result() for future in as_completed(futures)]

        queued_tasks = [
            QueuedTaskSpec[MediaQueryTaskResult, None](
                task_id=item.plan_item_id,
                task_type="network_query_and_optional_llm_summary",
                payload={
                    "agent": "MediaEngine",
                    "query": item.query,
                    "platform_type": item.platform_type,
                    "round": state.round_number,
                },
                network_call=lambda item=item, max_results=max_results: self._run_media_task(
                    item=item,
                    max_results=max_results,
                    is_technical=is_technical,
                ),
            )
            for item, max_results in task_specs
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
        item: MediaPlanItem,
        max_results: int,
        is_technical: bool,
    ) -> MediaQueryTaskResult:
        try:
            if item.candidate_url:
                from knowledgeforge.agent.MediaEngine.state.state import MediaSearchHit

                hits = [
                    MediaSearchHit(
                        title=item.article_title or item.query,
                        url=item.candidate_url,
                        snippet=item.query,
                        platform_type=item.platform_type,
                        score=1.0,
                        subdomain=item.subdomain,
                        planned_path=item.planned_path,
                        plan_item_id=item.plan_item_id,
                    )
                ]
            else:
                hits = self._search(
                    query=item.query,
                    platform_type=item.platform_type,
                    is_technical=is_technical,
                    max_results=max_results,
                    domain_phrases=self._domain_phrases_from_item(item),
                )
        except Exception as exc:
            return MediaQueryTaskResult(
                plan_item_id=item.plan_item_id,
                query=item.query,
                platform_type=item.platform_type,
                hits=[],
                status="failed",
                url=item.candidate_url,
                subdomain=item.subdomain,
                planned_path=item.planned_path,
                article_title=item.article_title,
                error=str(exc),
            )
        status = "completed" if hits else "insufficient"
        return MediaQueryTaskResult(
            plan_item_id=item.plan_item_id,
            query=item.query,
            platform_type=item.platform_type,
            hits=hits,
            status=status,
            url=item.candidate_url,
            subdomain=item.subdomain,
            planned_path=item.planned_path,
            article_title=item.article_title,
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

    def _expand_queries_to_items(
        self,
        state: MediaEngineState,
        *,
        social_queries: list[str],
        community_queries: list[str],
        blog_queries: list[str],
        is_technical: bool,
    ) -> list[MediaPlanItem]:
        existing_urls = self._existing_source_urls()
        seen_urls: set[str] = set()
        items: list[MediaPlanItem] = []
        grouped = [
            ("social", social_queries, self.MAX_SOCIAL_QUERIES, "M-S"),
            ("community", community_queries, self.MAX_COMMUNITY_QUERIES, "M-C"),
            ("blog", blog_queries, self.MAX_BLOG_QUERIES, "M-B"),
        ]
        domain_phrases = self._domain_phrases(state)
        default_subdomain = state.request_context.core_topics[0] if state.request_context.core_topics else "通用"
        for platform_type, queries, max_results, prefix in grouped:
            for query in queries:
                module_id, module_label = self._module_for_platform(platform_type)
                hits = self._search(
                    query=query,
                    platform_type=platform_type,
                    is_technical=is_technical,
                    max_results=max_results,
                    domain_phrases=domain_phrases,
                )
                if not hits:
                    items.append(
                        MediaPlanItem(
                            query=query,
                            platform_type=platform_type,
                            subdomain=default_subdomain,
                            article_title=query,
                            candidate_url="",
                            planned_path=self._planned_article_path(
                                state,
                                subdomain=default_subdomain,
                                title=query,
                                module_id=module_id,
                                doc_role="topic_article",
                            ),
                            source_kind=platform_type,
                            doc_role="topic_article",
                            module_id=module_id,
                            module_label=module_label,
                        )
                    )
                    continue
                for hit in hits:
                    if hit.url in seen_urls:
                        continue
                    seen_urls.add(hit.url)
                    item = MediaPlanItem(
                        query=query,
                        platform_type=platform_type,
                        subdomain=default_subdomain,
                        article_title=hit.title,
                        candidate_url=hit.url,
                        planned_path=self._planned_article_path(
                            state,
                            subdomain=default_subdomain,
                            title=hit.title,
                            module_id=module_id,
                            doc_role="topic_article",
                        ),
                        source_kind=platform_type,
                        doc_role="topic_article",
                        module_id=module_id,
                        module_label=module_label,
                    )
                    if hit.url in existing_urls:
                        item.status = "skipped"
                        item.skip_reason = "duplicate_url"
                        item.existing_path = existing_urls[hit.url]
                    items.append(item)
        for index, item in enumerate(items, start=1):
            if not item.plan_item_id:
                item.plan_item_id = self._default_plan_item_id(item.platform_type, index)
        return items

    @staticmethod
    def items_from_engine_plan(items: list[Any]) -> list[MediaPlanItem]:
        media_items: list[MediaPlanItem] = []
        for item in items:
            platform_type = next((priority for priority in item.source_priority if priority in {"social", "community", "blog"}), "community")
            media_items.append(
                MediaPlanItem(
                    query=item.query_or_action,
                    platform_type=platform_type,
                    subdomain=str(item.metadata.get("subdomain", "")),
                    article_title=str(item.metadata.get("article_title", item.title)),
                    candidate_url=str(item.metadata.get("url", "")),
                    planned_path=str(item.metadata.get("planned_path", "")),
                    source_kind=str(item.metadata.get("source_kind", platform_type)),
                    doc_type=str(item.metadata.get("doc_type", "trend")),
                    doc_role=str(item.metadata.get("doc_role", "topic_article")),
                    module_id=str(item.metadata.get("module_id", "review")),
                    module_label=str(item.metadata.get("module_label", "Review")),
                    plan_item_id=item.plan_item_id,
                    status=item.status if item.status != "approved" else "planned",
                    skip_reason=str(item.metadata.get("skip_reason", "")),
                    existing_path=str(item.metadata.get("existing_path", "")),
                )
            )
        return media_items

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

    @staticmethod
    def _domain_phrases_from_item(item: MediaPlanItem) -> list[str]:
        values = [item.article_title, item.subdomain, item.query]
        return [value for value in values if value]

    @staticmethod
    def _default_plan_item_id(platform_type: str, index: int) -> str:
        prefix = {"social": "M-S", "community": "M-C", "blog": "M-B"}.get(platform_type, "M-X")
        return f"{prefix}{index}"

    @staticmethod
    def _default_max_results(platform_type: str) -> int:
        return {"social": 3, "community": 4, "blog": 3}.get(platform_type, 3)

    def _existing_source_urls(self) -> dict[str, str]:
        if self._save_root is None or not self._save_root.exists():
            return {}
        existing: dict[str, str] = {}
        for path in self._save_root.glob("**/*.md"):
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                if line.strip().startswith("url: "):
                    existing[line.split("url:", 1)[1].strip().strip('"').strip("'")] = path.as_posix()
        return existing

    def _planned_article_path(
        self,
        state: MediaEngineState,
        *,
        subdomain: str,
        title: str,
        module_id: str,
        doc_role: str,
    ) -> str:
        return plan_path_for_role(
            save_root=self._save_root or Path("save"),
            domain=state.request_context.domain,
            module_id=module_id,
            subdomain=subdomain,
            doc_role=doc_role,
            title=title,
            suffix="media",
        )

    @staticmethod
    def _item_log_details(item: MediaPlanItem, status: str | None = None) -> dict[str, object]:
        return {
            "plan_item_id": item.plan_item_id,
            "query": item.query,
            "platform_type": item.platform_type,
            "status": status or item.status,
            "url": item.candidate_url,
            "subdomain": item.subdomain,
            "module_id": item.module_id,
            "module_label": item.module_label,
            "doc_role": item.doc_role,
            "planned_path": item.planned_path,
            "skip_reason": item.skip_reason,
        }

    def _save_realtime_query_documents(
        self,
        state: MediaEngineState,
        *,
        plan_item_id: str,
        query: str,
        platform_type: str,
        hits: list[Any],
        subdomain: str,
        planned_path: str,
        url: str,
        article_title: str,
    ) -> None:
        task_id = getattr(state.request_context, "task_id", "")
        if not task_id or self._realtime_file_callback is None or not hits:
            return
        try:
            documents = self._crawler.fetch_documents(self._dedupe_hits(hits), max_documents=1)
            for document in documents:
                document.subdomain = subdomain
                document.planned_path = planned_path
                document.plan_item_id = plan_item_id
            candidate = RealtimeReviewCandidate(
                agent="MediaEngine",
                round_number=state.round_number,
                plan_item_id=plan_item_id,
                query=query,
                source_type=platform_type,
                platform_type=platform_type,
                documents=documents,
                context=state.request_context,
                subdomain=subdomain,
                doc_type="trend",
                module_id=next((item.module_id for item in state.search_plan.items if item.plan_item_id == plan_item_id), "review") if state.search_plan else "review",
                module_label=next((item.module_label for item in state.search_plan.items if item.plan_item_id == plan_item_id), "Review") if state.search_plan else "Review",
                doc_role=next((item.doc_role for item in state.search_plan.items if item.plan_item_id == plan_item_id), "topic_article") if state.search_plan else "topic_article",
                planned_path=planned_path,
                article_title=article_title,
                url=url,
            )
            result = self._realtime_file_callback(task_id, candidate)
            self._record_event(
                state,
                "media_realtime_file_reviewed",
                {
                    "plan_item_id": plan_item_id,
                    "query": query,
                    "platform_type": platform_type,
                    "url": url,
                    "subdomain": subdomain,
                    "module_id": candidate.module_id,
                    "doc_role": candidate.doc_role,
                    "planned_path": planned_path,
                    "review_status": result.status,
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

    @staticmethod
    def _module_for_platform(platform_type: str) -> tuple[str, str]:
        if platform_type == "blog":
            return "projects", "Projects"
        if platform_type == "community":
            return "advanced_topics", "Advanced Topics"
        return "review", "Review"
