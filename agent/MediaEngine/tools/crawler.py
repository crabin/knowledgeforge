from __future__ import annotations

from collections import OrderedDict
from typing import Callable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from agent.MediaEngine.state.state import MediaCrawledDocument, MediaSearchHit
from agent.MediaEngine.utils.ranking import classify_platform_type, score_media_url
from agent.MediaEngine.utils.text_processing import extract_media_text
from knowledgeforge.tools.agent_browser_cli import AgentBrowserCLI


class MediaPerspectiveCrawler:
    def __init__(
        self,
        timeout: float = 3.0,
        user_agent: str = "KnowledgeForgeMediaBot/0.1",
        trace: Callable[[str], None] | None = None,
    ) -> None:
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}
        self._trace = trace
        self._browser = AgentBrowserCLI(timeout=max(timeout * 2, 12.0), trace=trace)

    def search(
        self,
        *,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int = 5,
    ) -> list[MediaSearchHit]:
        browser_hits = self._search_with_browser(
            query=query,
            platform_type=platform_type,
            is_technical=is_technical,
            max_results=max_results,
        )
        if browser_hits:
            return browser_hits

        http_hits = self._search_with_http_fallback(
            query=query,
            platform_type=platform_type,
            is_technical=is_technical,
            max_results=max_results,
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

    def _search_with_browser(
        self,
        *,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int,
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
                platform_type=classify_platform_type(result.url, requested_type=platform_type),
                score=score_media_url(
                    result.url,
                    platform_type=classify_platform_type(result.url, requested_type=platform_type),
                    requested_type=platform_type,
                    is_technical=is_technical,
                    snippet=result.snippet,
                ),
            )
            for result in browser_results
        ]
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
    ) -> list[MediaSearchHit]:
        providers = (
            ("duckduckgo", "https://html.duckduckgo.com/html/"),
            ("bing", "https://www.bing.com/search"),
        )
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for provider_name, url in providers:
                hits = self._search_http_provider(
                    client=client,
                    provider_name=provider_name,
                    url=url,
                    query=query,
                    platform_type=platform_type,
                    is_technical=is_technical,
                    max_results=max_results,
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
    ) -> list[MediaSearchHit]:
        try:
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] GET {url} params.q={query} timeout={self._timeout}")
            response = client.get(url, params={"q": query})
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] status={response.status_code} url={response.url}")
            response.raise_for_status()
        except Exception as exc:
            self._log(f"[MEDIA-SEARCH][httpx:{provider_name}] failed {exc.__class__.__name__}: {exc}")
            return []

        if provider_name == "duckduckgo":
            selectors = (".result",)
            anchor_selectors = (".result__title a", "a.result__a")
            snippet_selectors = (".result__snippet",)
        else:
            selectors = ("li.b_algo",)
            anchor_selectors = ("h2 a",)
            snippet_selectors = (".b_caption p", "p")

        soup = BeautifulSoup(response.text, "html.parser")
        hits: list[MediaSearchHit] = []
        for selector in selectors:
            for result in soup.select(selector):
                anchor = None
                for anchor_selector in anchor_selectors:
                    anchor = result.select_one(anchor_selector)
                    if anchor and anchor.get("href"):
                        break
                if not anchor or not anchor.get("href"):
                    continue
                snippet_node = None
                for snippet_selector in snippet_selectors:
                    snippet_node = result.select_one(snippet_selector)
                    if snippet_node:
                        break
                result_url = anchor.get("href", "").strip()
                title = " ".join(anchor.get_text(" ", strip=True).split())
                snippet = " ".join((snippet_node.get_text(" ", strip=True) if snippet_node else "").split())
                actual_platform_type = classify_platform_type(result_url, requested_type=platform_type)
                hits.append(
                    MediaSearchHit(
                        title=title,
                        url=result_url,
                        snippet=snippet,
                        platform_type=actual_platform_type,
                        score=score_media_url(
                            result_url,
                            platform_type=actual_platform_type,
                            requested_type=platform_type,
                            is_technical=is_technical,
                            snippet=snippet,
                        ),
                    )
                )
            if hits:
                break

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

    def _log(self, message: str) -> None:
        if self._trace:
            self._trace(message)
