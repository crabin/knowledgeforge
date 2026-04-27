from __future__ import annotations

from bs4 import BeautifulSoup

from agent.QueryEngine.tools.crawler import (
    SEARCH_PROVIDERS,
    DomainKnowledgeCrawler,
    parse_brave_results,
    parse_google_results,
)
from agent.QueryEngine.tools.supplemental_sources import (
    build_supplemental_source_targets,
    is_it_tutorial_query,
    probe_source_url,
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


def test_build_supplemental_source_targets_includes_requested_urls() -> None:
    targets = build_supplemental_source_targets("GAN")
    by_key = {target.key: target for target in targets}
    assert by_key["tencent_cloud"].url == "https://cloud.tencent.com/developer/search/article-GAN"
    assert by_key["zhihu_search"].url == "https://www.zhihu.com/search?type=content&q=GAN"
    assert by_key["zh_wikipedia"].url.startswith("https://zh.wikipedia.org/")
    assert by_key["csdn_search"].url == "https://so.csdn.net/so/search?spm=1000.2115.3001.4498&q=GAN&t=&u="
    assert by_key["runoob_search"].url == "https://www.runoob.com/?s=GAN"


def test_build_supplemental_source_targets_skips_runoob_for_non_it_query() -> None:
    targets = build_supplemental_source_targets("历史人物")
    keys = {target.key for target in targets}
    assert "csdn_search" in keys
    assert "runoob_search" not in keys


def test_is_it_tutorial_query_matches_python_and_tutorial_terms() -> None:
    assert is_it_tutorial_query("python 教程")
    assert is_it_tutorial_query("LangGraph examples")
    assert not is_it_tutorial_query("世界历史")


def test_probe_source_url_marks_zhihu_block_page_unavailable() -> None:
    class FakeResponse:
        status_code = 200
        text = (
            '{"error":{"message":"您当前请求存在异常，暂时限制本次访问。'
            '如有疑问，您可以通过手机摇一摇或登录后私信知乎小管家反馈。3de246852f24ad64a3be8cc01a10dad8","code":40362}}'
        )
        url = "https://www.zhihu.com/search?type=content&q=GAN"

    class FakeClient:
        def get(self, url: str):
            return FakeResponse()

    target = next(item for item in build_supplemental_source_targets("GAN") if item.key == "zhihu_search")
    result = probe_source_url(target, client=FakeClient())
    assert result.available is False
    assert result.reason == "blocked_marker_detected"


def test_probe_source_url_uses_browser_fallback_for_zh_wikipedia_http_403() -> None:
    class FakeResponse:
        status_code = 403
        text = "Forbidden"
        url = "https://zh.wikipedia.org/w/index.php?search=GAN&title=Special%3ASearch&ns0=1"

    class FakeClient:
        def get(self, url: str):
            return FakeResponse()

    target = next(item for item in build_supplemental_source_targets("GAN") if item.key == "zh_wikipedia")
    result = probe_source_url(
        target,
        client=FakeClient(),
        browser_fetcher=lambda url: "搜索结果 生成对抗网络 Generative Adversarial Network 共 6 条结果",
    )
    assert result.available is True
    assert result.status_code is None
    assert result.http_status_code == 403
    assert result.probe_method == "browser_fallback"
    assert result.reason == "browser_fallback_ok"


def test_probe_source_url_keeps_zhihu_unavailable_on_http_403_without_browser_fallback() -> None:
    class FakeResponse:
        status_code = 403
        text = "Forbidden"
        url = "https://www.zhihu.com/search?type=content&q=GAN"

    class FakeClient:
        def get(self, url: str):
            return FakeResponse()

    target = next(item for item in build_supplemental_source_targets("GAN") if item.key == "zhihu_search")
    result = probe_source_url(
        target,
        client=FakeClient(),
        browser_fetcher=lambda url: "系统监测到您的网络环境存在异常",
    )
    assert result.available is False
    assert result.status_code == 403
    assert result.http_status_code == 403
    assert result.probe_method == "http"
    assert result.reason == "http_403"


def test_query_crawler_extends_with_supplemental_hits_when_zhihu_question_present(monkeypatch) -> None:
    state = __import__("agent.QueryEngine.state.state", fromlist=["SearchHit"])
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
    monkeypatch.setattr(
        crawler,
        "_discover_supplemental_hits",
        lambda **kwargs: [
            state.SearchHit(
                title="腾讯云开发者社区搜索 - GAN",
                url="https://cloud.tencent.com/developer/search/article-GAN",
                snippet="腾讯云开发者社区文章搜索结果页",
                source_type="tutorial",
                score=3.5,
            ),
            state.SearchHit(
                title="中文维基百科搜索 - GAN",
                url="https://zh.wikipedia.org/w/index.php?search=GAN&title=Special%3ASearch&ns0=1",
                snippet="中文维基百科搜索结果页",
                source_type="tutorial",
                score=4.0,
            ),
        ],
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
    assert "https://www.zhihu.com/question/63493495" in urls
    assert "https://cloud.tencent.com/developer/search/article-GAN" in urls
    assert any("zh.wikipedia.org" in url for url in urls)
