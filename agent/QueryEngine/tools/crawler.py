from __future__ import annotations

from collections import OrderedDict
from typing import Callable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from agent.QueryEngine.state.state import CrawledDocument, SearchHit
from knowledgeforge.tools.agent_browser_cli import AgentBrowserCLI
from agent.QueryEngine.utils.ranking import score_url
from agent.QueryEngine.utils.text_processing import extract_main_text


class DomainKnowledgeCrawler:
    def __init__(
        self,
        timeout: float = 3.0,
        user_agent: str = "KnowledgeForgeBot/0.1",
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
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None = None,
        max_results: int = 5,
    ) -> list[SearchHit]:
        browser_hits = self._search_with_browser(
            query=query,
            source_type=source_type,
            official_domains=official_domains,
            preferred_domains=preferred_domains,
            max_results=max_results,
        )
        if browser_hits:
            return browser_hits

        url = "https://html.duckduckgo.com/html/"
        try:
            self._log(f"[QUERY-SEARCH][httpx] GET {url} params.q={query} timeout={self._timeout}")
            with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
                response = client.get(url, params={"q": query})
                self._log(f"[QUERY-SEARCH][httpx] status={response.status_code} url={response.url}")
                response.raise_for_status()
        except Exception as exc:
            self._log(f"[QUERY-SEARCH][httpx] failed {exc.__class__.__name__}: {exc}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        hits: list[SearchHit] = []
        for result in soup.select(".result"):
            anchor = result.select_one(".result__title a") or result.select_one("a.result__a")
            snippet_node = result.select_one(".result__snippet")
            if not anchor or not anchor.get("href"):
                continue
            result_url = anchor.get("href", "").strip()
            title = " ".join(anchor.get_text(" ", strip=True).split())
            snippet = " ".join((snippet_node.get_text(" ", strip=True) if snippet_node else "").split())
            hits.append(
                SearchHit(
                    title=title,
                    url=result_url,
                    snippet=snippet,
                    source_type=source_type,
                    score=score_url(result_url, source_type, official_domains, preferred_domains),
                )
            )

        hits.sort(key=lambda item: item.score, reverse=True)
        deduped: OrderedDict[str, SearchHit] = OrderedDict()
        for hit in hits:
            deduped.setdefault(hit.url, hit)
            if len(deduped) >= max_results:
                break
        return list(deduped.values())

    def fetch_documents(
        self,
        hits: list[SearchHit],
        *,
        max_documents: int = 6,
    ) -> list[CrawledDocument]:
        documents: list[CrawledDocument] = []
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for hit in hits[:max_documents]:
                browser_content = self._browser.fetch_text(hit.url)
                if browser_content:
                    documents.append(
                        CrawledDocument(
                            title=hit.title,
                            url=hit.url,
                            snippet=hit.snippet,
                            content=browser_content,
                            source_type=hit.source_type,
                            publisher=urlparse(hit.url).netloc or "unknown",
                            score=hit.score,
                        )
                    )
                    continue
                try:
                    self._log(f"[QUERY-FETCH][httpx] GET {hit.url} timeout={self._timeout}")
                    response = client.get(hit.url)
                    self._log(f"[QUERY-FETCH][httpx] status={response.status_code} url={response.url}")
                    response.raise_for_status()
                    content = extract_main_text(response.text)
                except Exception as exc:
                    self._log(f"[QUERY-FETCH][httpx] failed url={hit.url} {exc.__class__.__name__}: {exc}")
                    content = hit.snippet
                documents.append(
                    CrawledDocument(
                        title=hit.title,
                        url=hit.url,
                        snippet=hit.snippet,
                        content=content,
                        source_type=hit.source_type,
                        publisher=urlparse(hit.url).netloc or "unknown",
                        score=hit.score,
                    )
                )
        return documents

    def _search_with_browser(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None,
        max_results: int,
    ) -> list[SearchHit]:
        browser_results = self._browser.search_bing(query, limit=max_results)
        if not browser_results:
            self._log(f"[QUERY-SEARCH][browser] no hits query={query}")
            return []
        hits = [
            SearchHit(
                title=result.title,
                url=result.url,
                snippet=result.snippet,
                source_type=source_type,
                score=score_url(result.url, source_type, official_domains, preferred_domains),
            )
            for result in browser_results
        ]
        hits.sort(key=lambda item: item.score, reverse=True)
        self._log(f"[QUERY-SEARCH][browser] hits={len(hits[:max_results])} query={query}")
        return hits[:max_results]

    def _log(self, message: str) -> None:
        if self._trace:
            self._trace(message)
