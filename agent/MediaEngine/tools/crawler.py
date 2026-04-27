from __future__ import annotations

from collections import OrderedDict
from typing import Callable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from agent.MediaEngine.state.state import MediaCrawledDocument, MediaSearchHit
from agent.MediaEngine.utils.ranking import classify_platform_type, score_media_url
from agent.MediaEngine.utils.text_processing import extract_media_text
from agent.QueryEngine.tools.crawler import (
    SEARCH_PROVIDERS,
    parse_brave_results,
    parse_google_results,
    resolve_bing_redirect_url,
)
from agent.QueryEngine.utils.ranking import is_result_relevant
from knowledgeforge.tools.agent_browser_cli import AgentBrowserCLI
from knowledgeforge.tools.crawl4ai_adapter import Crawl4AIAdapter


class MediaPerspectiveCrawler:
    def __init__(
        self,
        timeout: float = 3.0,
        user_agent: str = "KnowledgeForgeMediaBot/0.1",
        trace: Callable[[str], None] | None = None,
        crawl4ai_adapter: Crawl4AIAdapter | None = None,
    ) -> None:
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}
        self._trace = trace
        self._browser = AgentBrowserCLI(timeout=max(timeout * 2, 12.0), trace=trace)
        self._crawl4ai = crawl4ai_adapter or Crawl4AIAdapter(enabled=False)

    def search(
        self,
        *,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int = 5,
        domain_phrases: list[str] | None = None,
    ) -> list[MediaSearchHit]:
        browser_hits = self._search_with_browser(
            query=query,
            platform_type=platform_type,
            is_technical=is_technical,
            max_results=max_results,
            domain_phrases=domain_phrases,
        )
        if browser_hits:
            return browser_hits

        http_hits = self._search_with_http_fallback(
            query=query,
            platform_type=platform_type,
            is_technical=is_technical,
            max_results=max_results,
            domain_phrases=domain_phrases,
        )
        return http_hits

    def fetch_documents(
        self,
        hits: list[MediaSearchHit],
        *,
        max_documents: int = 8,
    ) -> list[MediaCrawledDocument]:
        documents: list[MediaCrawledDocument] = []
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for hit in hits[:max_documents]:
                crawl4ai_content = self._fetch_with_crawl4ai(hit.url)
                if crawl4ai_content:
                    documents.append(
                        MediaCrawledDocument(
                            title=hit.title,
                            url=hit.url,
                            snippet=hit.snippet,
                            content=crawl4ai_content,
                            platform_type=hit.platform_type,
                            publisher=urlparse(hit.url).netloc or "unknown",
                            score=hit.score,
                        )
                    )
                    continue
                browser_content = self._browser.fetch_text(hit.url)
                if browser_content:
                    documents.append(
                        MediaCrawledDocument(
                            title=hit.title,
                            url=hit.url,
                            snippet=hit.snippet,
                            content=browser_content,
                            platform_type=hit.platform_type,
                            publisher=urlparse(hit.url).netloc or "unknown",
                            score=hit.score,
                        )
                    )
                    continue
                try:
                    self._log(f"[MEDIA-FETCH][httpx] GET {hit.url} timeout={self._timeout}")
                    response = client.get(hit.url)
                    self._log(f"[MEDIA-FETCH][httpx] status={response.status_code} url={response.url}")
                    response.raise_for_status()
                    content = extract_media_text(response.text)
                except Exception as exc:
                    self._log(f"[MEDIA-FETCH][httpx] failed url={hit.url} {exc.__class__.__name__}: {exc}")
                    content = hit.snippet
                documents.append(
                    MediaCrawledDocument(
                        title=hit.title,
                        url=hit.url,
                        snippet=hit.snippet,
                        content=content,
                        platform_type=hit.platform_type,
                        publisher=urlparse(hit.url).netloc or "unknown",
                        score=hit.score,
                    )
                )
        return documents

    def _fetch_with_crawl4ai(self, url: str) -> str:
        result = self._crawl4ai.fetch_markdown(url)
        if result.success:
            self._log(f"[MEDIA-FETCH][crawl4ai] success url={url}")
            return result.markdown
        if result.error:
            self._log(f"[MEDIA-FETCH][crawl4ai] failed url={url} error={result.error}")
        return ""

    def _search_with_browser(
        self,
        *,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int,
        domain_phrases: list[str] | None = None,
    ) -> list[MediaSearchHit]:
        browser_results = self._browser.search_bing(query, limit=max_results)
        if not browser_results:
            self._log(f"[MEDIA-SEARCH][browser] no hits query={query}")
            return []
        hits = [
            MediaSearchHit(
                title=result.title,
                url=result.url,
                snippet=result.snippet,
                platform_type=classify_platform_type(result.url),
                score=score_media_url(
                    result.url,
                    platform_type=classify_platform_type(result.url),
                    requested_type=platform_type,
                    is_technical=is_technical,
                    snippet=result.snippet,
                ),
            )
            for result in browser_results
        ]
        hits = self._filter_relevant_hits(hits, domain_phrases or [])
        hits.sort(key=lambda item: item.score, reverse=True)
        self._log(f"[MEDIA-SEARCH][browser] hits={len(hits[:max_results])} query={query}")
        return hits[:max_results]

    def _search_with_http_fallback(
        self,
        *,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int,
        domain_phrases: list[str] | None = None,
    ) -> list[MediaSearchHit]:
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for provider_name, url in SEARCH_PROVIDERS:
                hits = self._search_http_provider(
                    client=client,
                    provider_name=provider_name,
                    url=url,
                    query=query,
                    platform_type=platform_type,
                    is_technical=is_technical,
                    max_results=max_results,
                    domain_phrases=domain_phrases,
                )
                if hits:
                    return hits
        return []

    def _search_http_provider(
        self,
        *,
        client: httpx.Client,
        provider_name: str,
        url: str,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int,
        domain_phrases: list[str] | None = None,
    ) -> list[MediaSearchHit]:
        try:
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] GET {url} params.q={query} timeout={self._timeout}")
            response = client.get(url, params={"q": query})
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] status={response.status_code} url={response.url}")
            response.raise_for_status()
        except Exception as exc:
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] failed {exc.__class__.__name__}: {exc}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        if provider_name == "duckduckgo":
            raw_hits = self._parse_duckduckgo(soup)
        elif provider_name == "bing":
            raw_hits = self._parse_bing(soup)
        elif provider_name == "google":
            raw_hits = parse_google_results(soup)
        elif provider_name == "brave":
            raw_hits = parse_brave_results(soup)
        else:
            raw_hits = []

        hits: list[MediaSearchHit] = []
        for raw_hit in raw_hits:
            result_url = resolve_bing_redirect_url(raw_hit["url"])
            actual_platform_type = classify_platform_type(result_url)
            hits.append(
                MediaSearchHit(
                    title=raw_hit["title"],
                    url=result_url,
                    snippet=raw_hit["snippet"],
                    platform_type=actual_platform_type,
                    score=score_media_url(
                        result_url,
                        platform_type=actual_platform_type,
                        requested_type=platform_type,
                        is_technical=is_technical,
                        snippet=raw_hit["snippet"],
                    ),
                )
            )

        hits = self._filter_relevant_hits(hits, domain_phrases or [])
        hits.sort(key=lambda item: item.score, reverse=True)
        deduped: OrderedDict[str, MediaSearchHit] = OrderedDict()
        for hit in hits:
            deduped.setdefault(hit.url, hit)
            if len(deduped) >= max_results:
                break
        if deduped:
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] hits={len(deduped)} query={query}")
        else:
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] no hits query={query}")
        return list(deduped.values())

    @staticmethod
    def _parse_duckduckgo(soup: BeautifulSoup) -> list[dict[str, str]]:
        from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler

        return DomainKnowledgeCrawler._parse_duckduckgo(soup)

    @staticmethod
    def _parse_bing(soup: BeautifulSoup) -> list[dict[str, str]]:
        from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler

        return DomainKnowledgeCrawler._parse_bing(soup)

    def _filter_relevant_hits(
        self,
        hits: list,
        domain_phrases: list[str],
    ) -> list:
        if not domain_phrases:
            return hits
        return [
            hit
            for hit in hits
            if is_result_relevant(
                getattr(hit, "title", ""),
                getattr(hit, "snippet", ""),
                getattr(hit, "url", ""),
                domain_phrases,
            )
        ]

    def _log(self, message: str) -> None:
        if self._trace:
            self._trace(message)
