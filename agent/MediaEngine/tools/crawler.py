from __future__ import annotations

from collections import OrderedDict
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from agent.MediaEngine.state.state import MediaCrawledDocument, MediaSearchHit
from agent.MediaEngine.utils.ranking import classify_platform_type, score_media_url
from agent.MediaEngine.utils.text_processing import extract_media_text


class MediaPerspectiveCrawler:
    def __init__(self, timeout: float = 3.0, user_agent: str = "KnowledgeForgeMediaBot/0.1") -> None:
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}

    def search(
        self,
        *,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int = 5,
    ) -> list[MediaSearchHit]:
        url = "https://html.duckduckgo.com/html/"
        try:
            with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
                response = client.get(url, params={"q": query})
                response.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        hits: list[MediaSearchHit] = []
        for result in soup.select(".result"):
            anchor = result.select_one(".result__title a") or result.select_one("a.result__a")
            snippet_node = result.select_one(".result__snippet")
            if not anchor or not anchor.get("href"):
                continue
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

        hits.sort(key=lambda item: item.score, reverse=True)
        deduped: OrderedDict[str, MediaSearchHit] = OrderedDict()
        for hit in hits:
            deduped.setdefault(hit.url, hit)
            if len(deduped) >= max_results:
                break
        return list(deduped.values())

    def fetch_documents(
        self,
        hits: list[MediaSearchHit],
        *,
        max_documents: int = 8,
    ) -> list[MediaCrawledDocument]:
        documents: list[MediaCrawledDocument] = []
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            for hit in hits[:max_documents]:
                try:
                    response = client.get(hit.url)
                    response.raise_for_status()
                    content = extract_media_text(response.text)
                except Exception:
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
