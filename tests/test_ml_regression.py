"""Regression: 'Machine Learning' query must reject Weblio/dictionary noise."""
from __future__ import annotations

import tempfile

from knowledgeforge.agent.MediaEngine.utils.ranking import classify_platform_type
from knowledgeforge.agent.QueryEngine.utils.ranking import is_result_relevant, reliability_for_source_type_and_url
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.models import (
    DocumentArtifact,
    EngineRunResult,
    GraphSyncResult,
    RequestContext,
    SourceRecord,
    StructuredExtractionResult,
)
from knowledgeforge.quality.checker import QualityChecker


ML_CONTEXT = RequestContext(
    domain="Machine Learning",
    subdomains=["supervised learning", "unsupervised learning", "reinforcement learning"],
    time_window="2024",
    focus_points=["applications", "algorithms"],
    constraints=[],
    initial_strategy=[],
    completion_mode="full_document",
)

DOMAIN_PHRASES = ["machine learning", "ml"]

WEBLIO_SOURCE = SourceRecord(
    title="machine - Weblio英和辞典",
    url="https://ejje.weblio.jp/content/machine",
    publisher="ejje.weblio.jp",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="unknown",
    agent="QueryEngine",
    snippet="machineの日本語への翻訳。",
)

SEWING_SOURCE = SourceRecord(
    title="Sewing Machine Parts Catalog",
    url="https://sewingmachineparts.example.com/",
    publisher="sewingmachineparts.example.com",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="unknown",
    agent="QueryEngine",
    snippet="Find sewing machine parts for all models.",
)

AUTHORITATIVE_SOURCE = SourceRecord(
    title="Machine Learning - IBM Developer",
    url="https://developer.ibm.com/articles/cc-machine-learning-deep-learning-architectures/",
    publisher="developer.ibm.com",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="high",
    agent="QueryEngine",
    snippet="Machine learning is a subset of artificial intelligence that enables systems to learn.",
)

SKLEARN_SOURCE = SourceRecord(
    title="scikit-learn: machine learning in Python",
    url="https://scikit-learn.org/stable/",
    publisher="scikit-learn.org",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="high",
    agent="QueryEngine",
    snippet="Simple and efficient tools for predictive data analysis built on NumPy, SciPy, and matplotlib.",
)


def test_weblio_url_is_rejected_by_relevance_filter() -> None:
    assert not is_result_relevant(
        title=WEBLIO_SOURCE.title,
        snippet=WEBLIO_SOURCE.snippet,
        url=WEBLIO_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


def test_sewing_machine_is_rejected_by_relevance_filter() -> None:
    assert not is_result_relevant(
        title=SEWING_SOURCE.title,
        snippet=SEWING_SOURCE.snippet,
        url=SEWING_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


def test_ibm_ml_source_passes_relevance_filter() -> None:
    assert is_result_relevant(
        title=AUTHORITATIVE_SOURCE.title,
        snippet=AUTHORITATIVE_SOURCE.snippet,
        url=AUTHORITATIVE_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


def test_sklearn_source_passes_relevance_filter() -> None:
    assert is_result_relevant(
        title=SKLEARN_SOURCE.title,
        snippet=SKLEARN_SOURCE.snippet,
        url=SKLEARN_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


def test_weblio_tagged_official_does_not_get_high_reliability() -> None:
    result = reliability_for_source_type_and_url(
        source_type="official",
        url=WEBLIO_SOURCE.url,
        official_domains=["scikit-learn.org", "developer.ibm.com"],
    )
    assert result != "high"


def test_sklearn_tagged_official_gets_high_reliability() -> None:
    result = reliability_for_source_type_and_url(
        source_type="official",
        url=SKLEARN_SOURCE.url,
        official_domains=["scikit-learn.org"],
    )
    assert result == "high"


def test_weblio_is_classified_as_unknown_platform() -> None:
    assert classify_platform_type(WEBLIO_SOURCE.url) == "unknown"


def _engine_result(sources: list[SourceRecord], topics: list[str] | None = None) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="summary",
        key_points=[],
        raw_material=[],
        coverage_topics=topics or ["supervised learning", "unsupervised learning", "reinforcement learning"],
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def test_only_weblio_sources_trigger_supplement_required() -> None:
    output = _engine_result(sources=[WEBLIO_SOURCE, SEWING_SOURCE])
    result = CompletenessEvaluator().evaluate(ML_CONTEXT, {"QueryEngine": output})
    assert result.status == "supplement_required"
    assert "no_authoritative_source" in result.failure_categories


def test_authoritative_sources_pass_completeness() -> None:
    output = _engine_result(sources=[AUTHORITATIVE_SOURCE, SKLEARN_SOURCE])
    result = CompletenessEvaluator().evaluate(ML_CONTEXT, {"QueryEngine": output})
    assert result.status == "pass"


def _make_valid_doc() -> DocumentArtifact:
    content = (
        "---\nid: test\n---\n\n# ML\n\n## 证据与来源\n\n"
        "| 编号 | 来源 | 关键信息 | 可信度 | 备注 |\n|---|---|---|---|---|\n"
        "| S1 | IBM | ML intro | high | Q |\n"
    )
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return DocumentArtifact(
        document_id="ml-regression-001",
        title="Machine Learning",
        domain="Machine Learning",
        subdomain="supervised learning",
        path=tmp.name,
        status="draft",
        version="v1",
    )


_EXTRACTION = StructuredExtractionResult(
    document_id="ml-regression-001",
    document_path="/tmp/ml.md",
    chunks=[],
    metadata={},
    entities=[{"name": "Machine Learning"}],
    relations=[],
)

_GRAPH = GraphSyncResult(
    document_id="ml-regression-001",
    article_path="/tmp/ml.md",
    nodes=[{"id": "n1"}],
    relationships=[],
)


def test_quality_checker_fails_on_weblio_only_sources() -> None:
    artifact = _make_valid_doc()
    outputs = {"QueryEngine": _engine_result(sources=[WEBLIO_SOURCE, SEWING_SOURCE])}
    result = QualityChecker().check(artifact, _EXTRACTION, _GRAPH, ML_CONTEXT, outputs)
    assert result.status == "failed"
    assert any("source_quality_failed" in issue.category for issue in result.issues)


def test_quality_checker_passes_on_authoritative_sources() -> None:
    artifact = _make_valid_doc()
    outputs = {"QueryEngine": _engine_result(sources=[AUTHORITATIVE_SOURCE, SKLEARN_SOURCE])}
    result = QualityChecker().check(artifact, _EXTRACTION, _GRAPH, ML_CONTEXT, outputs)
    assert result.status == "passed"
