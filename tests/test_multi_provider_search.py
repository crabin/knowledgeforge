from __future__ import annotations

from bs4 import BeautifulSoup

from knowledgeforge.agent.QueryEngine.tools.crawler import (
    SEARCH_PROVIDERS,
    DomainKnowledgeCrawler,
    parse_google_results,
)
from knowledgeforge.agent.QueryEngine.tools.wikipedia_fetcher import WikipediaFetcher, WikipediaResult


GOOGLE_HTML = """
<html><body>
  <div class="g">
    <a href="https://scikit-learn.org/stable/"><h3>scikit-learn: Machine Learning in Python</h3></a>
    <div class="VwiC3b">Simple and efficient tools for machine learning.</div>
  </div>
  <div class="g">
    <a href="https://developers.google.com/machine-learning"><h3>Google ML Crash Course</h3></a>
    <div class="VwiC3b">Learn machine learning fundamentals from Google.</div>
  </div>
</body></html>
"""

def test_search_providers_are_only_google_and_bing() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert names == ["google", "bing"]


def test_provider_order_is_google_then_bing() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert names.index("google") < names.index("bing")


def test_parse_google_results_extracts_title_url_snippet() -> None:
    soup = BeautifulSoup(GOOGLE_HTML, "html.parser")
    hits = parse_google_results(soup)
    assert len(hits) == 2
    assert hits[0]["url"] == "https://scikit-learn.org/stable/"
    assert hits[0]["title"] == "scikit-learn: Machine Learning in Python"
    assert "machine learning" in hits[0]["snippet"].lower()


def test_wikipedia_result_dataclass_has_required_fields() -> None:
    result = WikipediaResult(
        title="Machine learning",
        url="https://en.wikipedia.org/wiki/Machine_learning",
        summary="Machine learning (ML) is a field of study in artificial intelligence.",
        reliability="medium",
    )
    assert result.reliability == "medium"
    assert "wikipedia.org" in result.url


def test_wikipedia_fetcher_returns_none_on_http_error(monkeypatch) -> None:
    import httpx

    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("timeout")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = WikipediaFetcher(timeout=1.0).fetch_summary("Machine learning")
    assert result is None


def test_wikipedia_fetcher_parses_valid_response(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "title": "Machine learning",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Machine_learning"}},
                "extract": "Machine learning (ML) is a field of study in artificial intelligence.",
            }

    monkeypatch.setattr("httpx.get", lambda *a, **kw: FakeResponse())
    result = WikipediaFetcher(timeout=5.0).fetch_summary("Machine learning")
    assert result is not None
    assert result.title == "Machine learning"
    assert result.reliability == "medium"
    assert "wikipedia.org" in result.url


def test_query_crawler_does_not_extend_with_supplemental_hits(monkeypatch) -> None:
    state = __import__("knowledgeforge.agent.QueryEngine.state.state", fromlist=["SearchHit"])
    crawler = DomainKnowledgeCrawler(timeout=0.1)
    zhihu_hit = state.SearchHit(
        title="如何形象又有趣的讲解对抗神经网络（GAN）是什么?",
        url="https://www.zhihu.com/question/63493495",
        snippet="知乎问题页",
        source_type="tutorial",
        score=2.0,
    )
    monkeypatch.setattr(
        crawler,
        "_search_with_browser",
        lambda **kwargs: [zhihu_hit],
    )

    hits = crawler.search(
        query="GAN",
        source_type="tutorial",
        official_domains=[],
        preferred_domains=["zh.wikipedia.org", "cloud.tencent.com"],
        max_results=5,
        domain_phrases=["gan"],
    )

    urls = [hit.url for hit in hits]
    assert urls == ["https://www.zhihu.com/question/63493495"]
