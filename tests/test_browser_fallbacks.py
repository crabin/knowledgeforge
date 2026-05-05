from __future__ import annotations

import subprocess
from urllib.parse import urlparse

from knowledgeforge.agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from knowledgeforge.agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.server.tools.agent_browser_cli import AgentBrowserCLI
from knowledgeforge.server.tools.crawl4ai_adapter import Crawl4AIFetchResult


def test_agent_browser_marks_itself_unhealthy_after_timeout(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[1] == "open":
            raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout", 0))

        class Completed:
            stdout = ""

        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    browser = AgentBrowserCLI(timeout=0.1)
    browser._binary = "agent-browser"

    first = browser.search_google("machine learning", limit=3)
    second = browser.search_google("machine learning", limit=3)

    assert first == []
    assert second == []
    assert browser.healthy is False
    assert browser.last_failure_reason == "search:TimeoutExpired"
    open_calls = [args for args in calls if len(args) > 1 and args[1] == "open"]
    assert len(open_calls) == 1


def test_query_crawler_falls_back_to_second_http_provider(monkeypatch) -> None:
    crawler = DomainKnowledgeCrawler(timeout=0.1)
    crawler._browser = type("FakeBrowser", (), {"search_google": lambda self, query, limit=5: []})()
    provider_calls: list[str] = []

    def fake_provider(*, provider_name: str, **kwargs):
        provider_calls.append(provider_name)
        if provider_name == "google":
            return []
        state = __import__("knowledgeforge.agent.QueryEngine.state.state", fromlist=["SearchHit"])
        return [
            state.SearchHit(
                title="Fallback result",
                url="https://example.com/query-fallback",
                snippet="fallback hit",
                source_type="tutorial",
                score=3.0,
            )
        ]

    monkeypatch.setattr(crawler, "_search_http_provider", fake_provider)

    hits = crawler.search(
        query="machine learning tutorial",
        source_type="tutorial",
        official_domains=[],
        preferred_domains=["github.com"],
        max_results=3,
    )

    assert provider_calls == ["google", "bing"]
    assert hits
    assert hits[0].url == "https://example.com/query-fallback"


def test_media_crawler_falls_back_to_second_http_provider(monkeypatch) -> None:
    crawler = MediaPerspectiveCrawler(timeout=0.1)
    crawler._browser = type("FakeBrowser", (), {"search_bing": lambda self, query, limit=5: []})()
    provider_calls: list[str] = []

    def fake_provider(*, provider_name: str, **kwargs):
        provider_calls.append(provider_name)
        if provider_name == "google":
            return []
        state = __import__("knowledgeforge.agent.MediaEngine.state.state", fromlist=["MediaSearchHit"])
        return [
            state.MediaSearchHit(
                title="Fallback media result",
                url="https://example.com/media-fallback",
                snippet="fallback media hit",
                platform_type="blog",
                score=4.0,
            )
        ]

    monkeypatch.setattr(crawler, "_search_http_provider", fake_provider)

    hits = crawler.search(
        query="machine learning community trend",
        platform_type="community",
        is_technical=True,
        max_results=3,
    )

    assert provider_calls == ["google", "bing"]
    assert hits
    assert hits[0].url == "https://example.com/media-fallback"


def test_query_crawler_fetch_documents_falls_back_after_crawl4ai_failure(monkeypatch) -> None:
    crawler = DomainKnowledgeCrawler(timeout=0.1)
    monkeypatch.setattr(
        crawler._crawl4ai,
        "fetch_markdown",
        lambda url: Crawl4AIFetchResult(success=False, markdown="", error="crawl4ai failed"),
    )
    crawler._browser = type("FakeBrowser", (), {"fetch_text": lambda self, url: "browser fallback content"})()

    state = __import__("knowledgeforge.agent.QueryEngine.state.state", fromlist=["SearchHit"])
    documents = crawler.fetch_documents(
        [
            state.SearchHit(
                title="Fallback result",
                url="https://example.com/query-fallback",
                snippet="fallback hit",
                source_type="tutorial",
                score=3.0,
            )
        ]
    )

    assert documents
    assert documents[0].content == "browser fallback content"
    assert documents[0].publisher == urlparse(documents[0].url).netloc


def test_media_crawler_fetch_documents_prefers_crawl4ai_markdown(monkeypatch) -> None:
    crawler = MediaPerspectiveCrawler(timeout=0.1)
    monkeypatch.setattr(
        crawler._crawl4ai,
        "fetch_markdown",
        lambda url: Crawl4AIFetchResult(success=True, markdown="# title\n\ncrawl4ai content"),
    )
    crawler._browser = type("FakeBrowser", (), {"fetch_text": lambda self, url: "browser content"})()

    state = __import__("knowledgeforge.agent.MediaEngine.state.state", fromlist=["MediaSearchHit"])
    documents = crawler.fetch_documents(
        [
            state.MediaSearchHit(
                title="Media result",
                url="https://example.com/media-fallback",
                snippet="fallback media hit",
                platform_type="blog",
                score=4.0,
            )
        ]
    )

    assert documents
    assert documents[0].content == "# title\n\ncrawl4ai content"
