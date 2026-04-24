from __future__ import annotations

import base64

from agent.MediaEngine.state.state import MediaSearchHit
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.MediaEngine.utils.ranking import classify_platform_type, reliability_for_platform_type
from agent.QueryEngine.tools.crawler import resolve_bing_redirect_url
from agent.QueryEngine.utils.ranking import is_result_relevant, reliability_for_source_type_and_url


def test_resolve_bing_redirect_decodes_base64_u_param() -> None:
    real = "https://scikit-learn.org/stable/index.html"
    encoded = base64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
    bing_redirect = f"https://www.bing.com/ck/a?!&&p=abc&u=a1a{encoded}&ntb=1"
    assert resolve_bing_redirect_url(bing_redirect) == real


def test_resolve_bing_redirect_returns_original_when_not_redirect() -> None:
    url = "https://scikit-learn.org/stable/"
    assert resolve_bing_redirect_url(url) == url


def test_resolve_bing_redirect_returns_original_on_malformed() -> None:
    url = "https://www.bing.com/ck/a?!&&p=abc&u=NOTBASE64!!!&ntb=1"
    assert resolve_bing_redirect_url(url) == url


def test_relevant_result_passes_exact_phrase() -> None:
    assert is_result_relevant(
        title="Machine Learning Tutorial",
        snippet="An introduction to machine learning algorithms.",
        url="https://scikit-learn.org/stable/",
        domain_phrases=["machine learning", "ml"],
    )


def test_irrelevant_result_with_partial_word_is_rejected() -> None:
    assert not is_result_relevant(
        title="Sewing Machine Parts Catalog",
        snippet="Find machine parts for all sewing models.",
        url="https://sewingmachineparts.example.com/",
        domain_phrases=["machine learning", "ml"],
    )


def test_irrelevant_result_weblio_dictionary_is_rejected() -> None:
    assert not is_result_relevant(
        title="machine - Weblio英和辞典",
        snippet="machineの日本語への翻訳。",
        url="https://ejje.weblio.jp/content/machine",
        domain_phrases=["machine learning", "ml"],
    )


def test_alias_match_passes() -> None:
    assert is_result_relevant(
        title="ML Ops Guide",
        snippet="Best practices for ML pipelines.",
        url="https://mlops.example.com/guide",
        domain_phrases=["machine learning", "ml"],
    )


def test_media_crawler_filters_irrelevant_hits() -> None:
    noise_hit = MediaSearchHit(
        title="Sewing Machine Community Forum",
        url="https://sewingforum.example.com/",
        snippet="Discussion about sewing machine maintenance.",
        platform_type="community",
        score=5.0,
    )
    relevant_hit = MediaSearchHit(
        title="Machine Learning Reddit Discussion",
        url="https://reddit.com/r/MachineLearning/comments/abc",
        snippet="Best practices for machine learning in production.",
        platform_type="community",
        score=8.0,
    )
    crawler = MediaPerspectiveCrawler.__new__(MediaPerspectiveCrawler)
    result = crawler._filter_relevant_hits(
        [noise_hit, relevant_hit],
        domain_phrases=["machine learning", "ml"],
    )
    assert len(result) == 1
    assert result[0].url == relevant_hit.url


def test_official_source_type_with_verified_domain_gives_high() -> None:
    assert (
        reliability_for_source_type_and_url(
            source_type="official",
            url="https://scikit-learn.org/stable/",
            official_domains=["scikit-learn.org"],
        )
        == "high"
    )


def test_official_source_type_with_unverified_domain_gives_medium() -> None:
    assert (
        reliability_for_source_type_and_url(
            source_type="official",
            url="https://ejje.weblio.jp/content/machine+learning",
            official_domains=["scikit-learn.org"],
        )
        == "medium"
    )


def test_tutorial_source_type_always_medium() -> None:
    assert (
        reliability_for_source_type_and_url(
            source_type="tutorial",
            url="https://medium.com/some-article",
            official_domains=[],
        )
        == "medium"
    )


def test_unknown_source_type_gives_unknown() -> None:
    assert (
        reliability_for_source_type_and_url(
            source_type="reference",
            url="https://example.com/",
            official_domains=[],
        )
        == "unknown"
    )


def test_classify_unknown_domain_returns_unknown() -> None:
    assert classify_platform_type("https://ejje.weblio.jp/content/machine+learning") == "unknown"


def test_classify_reddit_returns_social() -> None:
    assert classify_platform_type("https://reddit.com/r/MachineLearning/") == "social"


def test_reliability_unknown_platform_type_returns_unknown() -> None:
    assert reliability_for_platform_type("unknown", "some content here") == "unknown"
