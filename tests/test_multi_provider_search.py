from __future__ import annotations

from bs4 import BeautifulSoup

from agent.QueryEngine.tools.crawler import (
    SEARCH_PROVIDERS,
    parse_brave_results,
    parse_google_results,
)
from agent.QueryEngine.tools.wikipedia_fetcher import WikipediaFetcher, WikipediaResult


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

BRAVE_HTML = """
<html><body>
  <div class="snippet">
    <a class="result-header" href="https://en.wikipedia.org/wiki/Machine_learning">
      <span class="title">Machine learning - Wikipedia</span>
    </a>
    <p class="snippet-description">Machine learning (ML) is a field of study in artificial intelligence.</p>
  </div>
</body></html>
"""


def test_google_provider_is_in_search_providers() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert "google" in names


def test_brave_provider_is_in_search_providers() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert "brave" in names


def test_provider_order_is_google_bing_duckduckgo_brave() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert names.index("google") < names.index("bing")
    assert names.index("bing") < names.index("duckduckgo")
    assert names.index("duckduckgo") < names.index("brave")


def test_parse_google_results_extracts_title_url_snippet() -> None:
    soup = BeautifulSoup(GOOGLE_HTML, "html.parser")
    hits = parse_google_results(soup)
    assert len(hits) == 2
    assert hits[0]["url"] == "https://scikit-learn.org/stable/"
    assert hits[0]["title"] == "scikit-learn: Machine Learning in Python"
    assert "machine learning" in hits[0]["snippet"].lower()


def test_parse_brave_results_extracts_title_url_snippet() -> None:
    soup = BeautifulSoup(BRAVE_HTML, "html.parser")
    hits = parse_brave_results(soup)
    assert len(hits) == 1
    assert "wikipedia.org" in hits[0]["url"]
    assert "Machine learning" in hits[0]["title"]


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
