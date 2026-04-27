from __future__ import annotations

import asyncio
from dataclasses import dataclass

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
except Exception:  # pragma: no cover - optional dependency fallback
    AsyncWebCrawler = None
    BrowserConfig = None
    CacheMode = None
    CrawlerRunConfig = None
    DefaultMarkdownGenerator = None
    PruningContentFilter = None


@dataclass(slots=True)
class Crawl4AIFetchResult:
    success: bool
    markdown: str
    error: str = ""


class Crawl4AIAdapter:
    def __init__(
        self,
        *,
        headless: bool = True,
        verbose: bool = False,
        page_timeout_ms: int = 15000,
        enabled: bool = True,
    ) -> None:
        self._headless = headless
        self._verbose = verbose
        self._page_timeout_ms = page_timeout_ms
        self._enabled = enabled and AsyncWebCrawler is not None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def fetch_markdown(self, url: str) -> Crawl4AIFetchResult:
        if not self._enabled:
            return Crawl4AIFetchResult(success=False, markdown="", error="crawl4ai_disabled")
        try:
            markdown = asyncio.run(self._fetch_markdown_async(url))
        except Exception as exc:
            return Crawl4AIFetchResult(success=False, markdown="", error=str(exc))
        if not markdown:
            return Crawl4AIFetchResult(success=False, markdown="", error="crawl4ai_empty_content")
        return Crawl4AIFetchResult(success=True, markdown=markdown)

    async def _fetch_markdown_async(self, url: str) -> str:
        browser_config = BrowserConfig(headless=self._headless, verbose=self._verbose)
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=self._page_timeout_ms,
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(threshold=0.45, threshold_type="fixed")
            ),
        )
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
        if not getattr(result, "success", False):
            return ""
        markdown = getattr(result, "markdown", "")
        if isinstance(markdown, str):
            return markdown.strip()
        fit_markdown = getattr(markdown, "fit_markdown", "")
        if fit_markdown:
            return str(fit_markdown).strip()
        raw_markdown = getattr(markdown, "raw_markdown", "")
        if raw_markdown:
            return str(raw_markdown).strip()
        return str(markdown).strip()
