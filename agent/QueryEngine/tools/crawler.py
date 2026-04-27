from __future__ import annotations

import base64
from collections import OrderedDict
from typing import Callable
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from agent.QueryEngine.state.state import CrawledDocument, SearchHit
from agent.QueryEngine.tools.supplemental_sources import build_supplemental_source_targets, probe_source_url
from agent.QueryEngine.tools.wikipedia_fetcher import WikipediaFetcher
from agent.QueryEngine.utils.ranking import is_result_relevant, score_url
from agent.QueryEngine.utils.text_processing import extract_main_text
from knowledgeforge.tools.agent_browser_cli import AgentBrowserCLI
from knowledgeforge.tools.crawl4ai_adapter import Crawl4AIAdapter


SEARCH_PROVIDERS: list[tuple[str, str]] = [
    ("google", "https://www.google.com/search"),
    ("bing", "https://www.bing.com/search"),
    ("duckduckgo", "https://html.duckduckgo.com/html/"),
    ("brave", "https://search.brave.com/search"),
]


def parse_google_results(soup: BeautifulSoup) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for block in soup.select("div.g"):
        anchor = block.select_one("a[href]")
        if not anchor:
            continue
        title_node = anchor.select_one("h3")
        snippet_node = block.select_one("div.VwiC3b, div.IsZvec, span.aCOpRe")
        url = anchor.get("href", "").strip()
        if not url.startswith("http"):
            continue
        hits.append(
            {
                "url": url,
                "title": " ".join((title_node.get_text(" ", strip=True) if title_node else "").split()),
                "snippet": " ".join((snippet_node.get_text(" ", strip=True) if snippet_node else "").split()),
            }
        )
    return hits


def parse_brave_results(soup: BeautifulSoup) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for block in soup.select("div.snippet, div[data-type='web']"):
        anchor = block.select_one("a.result-header, a[href]")
        if not anchor:
            continue
        title_node = anchor.select_one("span.title") or anchor
        snippet_node = block.select_one("p.snippet-description, .snippet-content")
        url = anchor.get("href", "").strip()
        if not url.startswith("http"):
            continue
        hits.append(
            {
                "url": url,
                "title": " ".join(title_node.get_text(" ", strip=True).split()),
                "snippet": " ".join((snippet_node.get_text(" ", strip=True) if snippet_node else "").split()),
            }
        )
    return hits


def resolve_bing_redirect_url(url: str) -> str:
    """Decode Bing /ck/a redirects to the real destination URL."""
    parsed = urlparse(url)
    if "bing.com" not in parsed.netloc or "/ck/a" not in parsed.path:
        return url
    raw = (parse_qs(parsed.query).get("u") or [""])[0]
    if not raw:
        return url
    if raw.startswith("a1a"):
        raw = raw[3:]
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw).decode("utf-8")
    except Exception:
        return url


class DomainKnowledgeCrawler:
    def __init__(
        self,
        timeout: float = 3.0,
        user_agent: str = "KnowledgeForgeBot/0.1",
        trace: Callable[[str], None] | None = None,
        crawl4ai_adapter: Crawl4AIAdapter | None = None,
    ) -> None:
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}
        self._trace = trace
        self._browser = AgentBrowserCLI(timeout=max(timeout * 2, 12.0), trace=trace)
        self._wiki = WikipediaFetcher(timeout=max(timeout * 2, 8.0))
        self._crawl4ai = crawl4ai_adapter or Crawl4AIAdapter(enabled=False)

    def search(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None = None,
        max_results: int = 5,
        domain_phrases: list[str] | None = None,
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        try:
            browser_hits = self._search_with_browser(
                query=query,
                source_type=source_type,
                official_domains=official_domains,
                preferred_domains=preferred_domains,
                max_results=max_results,
                domain_phrases=domain_phrases,
            )
            if browser_hits:
                hits = browser_hits
        except Exception as exc:
            self._log(f"[QUERY-SEARCH][browser] unexpected failure {exc.__class__.__name__}: {exc}")

        if not hits:
            try:
                hits = self._search_with_http_fallback(
                    query=query,
                    source_type=source_type,
                    official_domains=official_domains,
                    preferred_domains=preferred_domains,
                    max_results=max_results,
                    domain_phrases=domain_phrases,
                )
            except Exception as exc:
                self._log(f"[QUERY-SEARCH][httpx] unexpected failure {exc.__class__.__name__}: {exc}")
                hits = []

        supplemental_hits = self._discover_supplemental_hits(
            query=query,
            source_type=source_type,
            official_domains=official_domains,
            preferred_domains=preferred_domains,
            domain_phrases=domain_phrases,
            existing_hits=hits,
            max_results=max_results,
        )
        merged = OrderedDict((hit.url, hit) for hit in hits)
        for hit in supplemental_hits:
            merged.setdefault(hit.url, hit)
            if len(merged) >= max_results:
                break
        final_hits = list(merged.values())
        final_hits.sort(key=lambda item: item.score, reverse=True)
        return final_hits[:max_results]

    def fetch_wikipedia_supplement(
        self,
        domain: str,
        agent_name: str = "QueryEngine",
    ) -> CrawledDocument | None:
        result = self._wiki.fetch_summary(domain)
        if result is None:
            self._log(f"[QUERY-WIKI] no result for domain={domain}")
            return None
        self._log(f"[QUERY-WIKI] fetched title={result.title} url={result.url}")
        return CrawledDocument(
            title=result.title,
            url=result.url,
            snippet=result.summary[:300],
            content=result.summary,
            source_type="reference",
            publisher=urlparse(result.url).netloc or "en.wikipedia.org",
            score=3.0,
        )

    def fetch_documents(
        self,
        hits: list[SearchHit],
        *,
        max_documents: int = 6,
    ) -> list[CrawledDocument]:
        documents: list[CrawledDocument] = []
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for hit in hits[:max_documents]:
                crawl4ai_content = self._fetch_with_crawl4ai(hit.url)
                if crawl4ai_content:
                    documents.append(
                        CrawledDocument(
                            title=hit.title,
                            url=hit.url,
                            snippet=hit.snippet,
                            content=crawl4ai_content,
                            source_type=hit.source_type,
                            publisher=urlparse(hit.url).netloc or "unknown",
                            score=hit.score,
                        )
                    )
                    continue
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

    def _fetch_with_crawl4ai(self, url: str) -> str:
        result = self._crawl4ai.fetch_markdown(url)
        if result.success:
            self._log(f"[QUERY-FETCH][crawl4ai] success url={url}")
            return result.markdown
        if result.error:
            self._log(f"[QUERY-FETCH][crawl4ai] failed url={url} error={result.error}")
        return ""

    def _search_with_browser(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None,
        max_results: int,
        domain_phrases: list[str] | None = None,
    ) -> list[SearchHit]:
        browser_results = self._browser.search_google(query, limit=max_results)
        if not browser_results:
            self._log(f"[QUERY-SEARCH][browser:google] no hits query={query}")
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
        hits = self._filter_relevant_hits(hits, domain_phrases)
        hits.sort(key=lambda item: item.score, reverse=True)
        self._log(f"[QUERY-SEARCH][browser:google] hits={len(hits[:max_results])} query={query}")
        return hits[:max_results]

    def _search_with_http_fallback(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None,
        max_results: int,
        domain_phrases: list[str] | None = None,
    ) -> list[SearchHit]:
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for provider_name, url in SEARCH_PROVIDERS:
                hits = self._search_http_provider(
                    client=client,
                    provider_name=provider_name,
                    url=url,
                    query=query,
                    source_type=source_type,
                    official_domains=official_domains,
                    preferred_domains=preferred_domains,
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
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None,
        max_results: int,
        domain_phrases: list[str] | None = None,
    ) -> list[SearchHit]:
        try:
            self._log(f"[QUERY-SEARCH][httpx:{provider_name}] GET {url} params.q={query} timeout={self._timeout}")
            response = client.get(url, params={"q": query})
            self._log(f"[QUERY-SEARCH][httpx:{provider_name}] status={response.status_code} url={response.url}")
            response.raise_for_status()
        except Exception as exc:
            self._log(f"[QUERY-SEARCH][httpx:{provider_name}] failed {exc.__class__.__name__}: {exc}")
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

        hits: list[SearchHit] = []
        for raw_hit in raw_hits:
            result_url = resolve_bing_redirect_url(raw_hit["url"])
            hits.append(
                SearchHit(
                    title=raw_hit["title"],
                    url=result_url,
                    snippet=raw_hit["snippet"],
                    source_type=source_type,
                    score=score_url(result_url, source_type, official_domains, preferred_domains),
                )
            )

        hits = self._filter_relevant_hits(hits, domain_phrases)
        hits.sort(key=lambda item: item.score, reverse=True)
        deduped: OrderedDict[str, SearchHit] = OrderedDict()
        for hit in hits:
            deduped.setdefault(hit.url, hit)
            if len(deduped) >= max_results:
                break
        if deduped:
            self._log(f"[QUERY-SEARCH][httpx:{provider_name}] hits={len(deduped)} query={query}")
        else:
            self._log(f"[QUERY-SEARCH][httpx:{provider_name}] no hits query={query}")
        return list(deduped.values())

    def _discover_supplemental_hits(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None,
        domain_phrases: list[str] | None,
        existing_hits: list[SearchHit],
        max_results: int,
    ) -> list[SearchHit]:
        if not self._should_expand_sources(existing_hits, max_results):
            return []
        existing_urls = {hit.url for hit in existing_hits}
        supplemental_hits: list[SearchHit] = []
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for target in build_supplemental_source_targets(query):
                if target.url in existing_urls:
                    continue
                probe = probe_source_url(target, client=client)
                self._log(
                    f"[QUERY-SEARCH][supplemental:{target.key}] "
                    f"available={probe.available} status={probe.status_code} reason={probe.reason}"
                )
                if not probe.available:
                    continue
                hit = SearchHit(
                    title=f"{target.label} - {query}",
                    url=target.url,
                    snippet=target.snippet,
                    source_type=source_type,
                    score=score_url(target.url, source_type, official_domains, preferred_domains)
                    + self._supplemental_source_bonus(target.url),
                )
                if domain_phrases and not is_result_relevant(hit.title, hit.snippet, hit.url, domain_phrases):
                    continue
                supplemental_hits.append(hit)
                if len(existing_hits) + len(supplemental_hits) >= max_results:
                    break
        supplemental_hits.sort(key=lambda item: item.score, reverse=True)
        return supplemental_hits

    @staticmethod
    def _should_expand_sources(existing_hits: list[SearchHit], max_results: int) -> bool:
        if len(existing_hits) < max_results:
            return True
        return any("zhihu.com/question/" in hit.url for hit in existing_hits)

    @staticmethod
    def _supplemental_source_bonus(url: str) -> float:
        if "zh.wikipedia.org" in url:
            return 2.0
        if "cloud.tencent.com" in url:
            return 1.5
        if "zhihu.com/search" in url:
            return 1.0
        return 0.0

    @staticmethod
    def _parse_duckduckgo(soup: BeautifulSoup) -> list[dict[str, str]]:
        return DomainKnowledgeCrawler._parse_search_blocks(
            soup,
            selectors=(".result",),
            anchor_selectors=(".result__title a", "a.result__a"),
            snippet_selectors=(".result__snippet",),
        )

    @staticmethod
    def _parse_bing(soup: BeautifulSoup) -> list[dict[str, str]]:
        return DomainKnowledgeCrawler._parse_search_blocks(
            soup,
            selectors=("li.b_algo",),
            anchor_selectors=("h2 a",),
            snippet_selectors=(".b_caption p", "p"),
        )

    @staticmethod
    def _parse_search_blocks(
        soup: BeautifulSoup,
        *,
        selectors: tuple[str, ...],
        anchor_selectors: tuple[str, ...],
        snippet_selectors: tuple[str, ...],
    ) -> list[dict[str, str]]:
        hits: list[dict[str, str]] = []
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
                hits.append(
                    {
                        "url": anchor.get("href", "").strip(),
                        "title": " ".join(anchor.get_text(" ", strip=True).split()),
                        "snippet": " ".join(
                            (snippet_node.get_text(" ", strip=True) if snippet_node else "").split()
                        ),
                    }
                )
            if hits:
                break
        return hits

    @staticmethod
    def _filter_relevant_hits(
        hits: list[SearchHit],
        domain_phrases: list[str] | None,
    ) -> list[SearchHit]:
        if not domain_phrases:
            return hits
        return [
            hit
            for hit in hits
            if is_result_relevant(hit.title, hit.snippet, hit.url, domain_phrases)
        ]

    def _log(self, message: str) -> None:
        if self._trace:
            self._trace(message)
