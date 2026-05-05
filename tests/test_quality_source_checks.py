from __future__ import annotations

import tempfile

from knowledgeforge.server.models import (
    DocumentArtifact,
    EngineRunResult,
    GraphSyncResult,
    RequestContext,
    SourceRecord,
    StructuredExtractionResult,
)
from knowledgeforge.server.quality.checker import QualityChecker


def _make_artifact(content: str) -> DocumentArtifact:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return DocumentArtifact(
        document_id="test-doc-001",
        title="Test",
        domain="Machine Learning",
        subdomain="supervised learning",
        path=tmp.name,
        status="draft",
        version="v1",
    )


_VALID_CONTENT = (
    "---\nid: test\n---\n\n# Title\n\n## 证据与来源\n\n| 编号 | 来源 | 关键信息 | 可信度 | 备注 |\n"
    "|---|---|---|---|---|\n| S1 | Example | Info | high | Q |\n"
)

_VALID_EXTRACTION = StructuredExtractionResult(
    document_id="test-doc-001",
    document_path="/tmp/test.md",
    chunks=[],
    metadata={},
    entities=[{"name": "Machine Learning"}],
    relations=[],
)

_VALID_GRAPH = GraphSyncResult(
    document_id="test-doc-001",
    article_path="/tmp/test.md",
    nodes=[{"id": "n1"}],
    relationships=[],
)

_VALID_CONTEXT = RequestContext(
    domain="Machine Learning",
    subdomains=["supervised learning"],
    time_window="2024",
    focus_points=["applications"],
    constraints=[],
    initial_strategy=[],
    completion_mode="full_document",
)


def _engine_result(sources: list[SourceRecord]) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="summary",
        key_points=[],
        raw_material=[],
        coverage_topics=["supervised learning"],
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def _source(reliability: str, title: str = "ML Guide", url: str = "https://scikit-learn.org/") -> SourceRecord:
    return SourceRecord(
        title=title,
        url=url,
        publisher="scikit-learn.org",
        retrieved_at="2024-01-01T00:00:00Z",
        reliability=reliability,  # type: ignore[arg-type]
        agent="QueryEngine",
    )


def test_passes_with_authoritative_source() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([_source("high")])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    assert result.status == "passed"


def test_fails_with_only_unknown_reliability_sources() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([_source("unknown")])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    assert result.status == "failed"
    assert any("source_quality" in issue.category for issue in result.issues)


def test_fails_with_no_sources() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    assert result.status == "failed"


def test_source_quality_issue_uses_research_flow() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([_source("unknown")])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    quality_issues = [issue for issue in result.issues if "source_quality" in issue.category]
    assert all(issue.flow == "research_flow" for issue in quality_issues)
