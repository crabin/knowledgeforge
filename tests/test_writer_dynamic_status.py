from __future__ import annotations

import tempfile
from pathlib import Path

from knowledgeforge.config import AppConfig
from knowledgeforge.models import (
    CompletenessResult,
    EngineRunResult,
    RequestContext,
    SourceRecord,
)
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter


def _make_config() -> AppConfig:
    return AppConfig(save_root=Path(tempfile.mkdtemp()))


def _make_context() -> RequestContext:
    return RequestContext(
        domain="Machine Learning",
        subdomains=["supervised learning"],
        time_window="2024",
        focus_points=["applications"],
        constraints=[],
        initial_strategy=[],
    )


def _make_source(snippet: str = "Key finding about ML.") -> SourceRecord:
    return SourceRecord(
        title="ML Guide",
        url="https://scikit-learn.org/",
        publisher="scikit-learn.org",
        retrieved_at="2024-01-01T00:00:00Z",
        reliability="high",
        agent="QueryEngine",
        snippet=snippet,
    )


def _make_engine_result(sources: list[SourceRecord]) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="This is the engine summary, not the snippet.",
        key_points=["point 1"],
        raw_material=["raw 1"],
        coverage_topics=["supervised learning"],
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def test_writer_pass_status_uses_positive_conclusion() -> None:
    writer = MarkdownKnowledgeWriter(_make_config())
    ctx = _make_context()
    outputs = {"QueryEngine": _make_engine_result([_make_source()])}
    completeness = CompletenessResult(
        status="pass",
        reasons=["ok"],
        missing_topics=[],
        supplement_queries=[],
        failure_categories=[],
    )
    artifact = writer.write(ctx, outputs, completeness, round_number=1)
    content = Path(artifact.path).read_text(encoding="utf-8")
    assert "可以进入治理流程" in content
    assert "首版知识结构已经形成" not in content


def test_writer_supplement_required_uses_draft_conclusion() -> None:
    writer = MarkdownKnowledgeWriter(_make_config())
    ctx = _make_context()
    outputs = {"QueryEngine": _make_engine_result([])}
    completeness = CompletenessResult(
        status="supplement_required",
        reasons=["缺少来源"],
        missing_topics=[],
        supplement_queries=["Machine Learning official docs"],
        failure_categories=["no_authoritative_source"],
    )
    artifact = writer.write(ctx, outputs, completeness, round_number=1)
    content = Path(artifact.path).read_text(encoding="utf-8")
    assert "草稿" in content
    assert "补检索" in content


def test_evidence_table_uses_source_snippet_not_engine_summary() -> None:
    writer = MarkdownKnowledgeWriter(_make_config())
    ctx = _make_context()
    snippet = "Specific finding from the actual source page."
    outputs = {"QueryEngine": _make_engine_result([_make_source(snippet=snippet)])}
    completeness = CompletenessResult(
        status="pass", reasons=[], missing_topics=[], supplement_queries=[], failure_categories=[]
    )
    artifact = writer.write(ctx, outputs, completeness, round_number=1)
    content = Path(artifact.path).read_text(encoding="utf-8")
    assert snippet in content
    assert "This is the engine summary, not the snippet." not in content.split("## 证据与来源")[1]
