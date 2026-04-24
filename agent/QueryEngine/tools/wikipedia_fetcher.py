from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import httpx


@dataclass(slots=True)
class WikipediaResult:
    title: str
    url: str
    summary: str
    reliability: Literal["medium"] = "medium"


class WikipediaFetcher:
    """Fetch a Wikipedia page summary via the REST API."""

    _BASE = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout

    def fetch_summary(self, query: str) -> WikipediaResult | None:
        encoded = quote(query.replace(" ", "_"), safe="")
        url = self._BASE.format(title=encoded)
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
        except Exception:
            return None

        data = response.json()
        extract = data.get("extract", "").strip()
        if not extract:
            return None
        page_url = (
            data.get("content_urls", {}).get("desktop", {}).get("page", "")
            or f"https://en.wikipedia.org/wiki/{encoded}"
        )
        return WikipediaResult(
            title=data.get("title", query),
            url=page_url,
            summary=extract,
        )
