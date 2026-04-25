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


def test_writer_saves_query_plan_document_in_subdomain_directory() -> None:
    writer = MarkdownKnowledgeWriter(_make_config())
    ctx = RequestContext(
        domain="Machine Learning",
        subdomains=["最新论文方向"],
        time_window="2026",
        focus_points=["papers"],
        constraints=[],
        initial_strategy=[],
    )
    output = EngineRunResult(
        agent_name="QueryEngine",
        summary="Query summary.",
        key_points=["point 1"],
        raw_material=[
            "搜索规划：plan",
            "查询计划：",
            "- ☑ Q1 [completed] Machine Learning 最新论文方向有哪些官方或权威来源？ | Google 查询：Machine Learning latest papers official",
            "  查询内容：论文列表; 官方来源",
            "  预期信息：论文列表; 官方来源",
            "  满足标准：命中权威来源",
            "反思结论：无",
        ],
        coverage_topics=["最新论文方向"],
        sources=[_make_source()],
        collected_at="2026-04-25T00:00:00+09:00",
        round_number=1,
        execution_log=[
            {
                "event": "query_plan_created",
                "timestamp": "2026-04-25T00:00:00+09:00",
                "node": "QuerySearchNode",
                "details": {"question_count": 1},
            }
        ],
    )
    completeness = CompletenessResult(
        status="pass", reasons=[], missing_topics=[], supplement_queries=[], failure_categories=[]
    )

    artifact = writer.write(ctx, {"QueryEngine": output}, completeness, round_number=1)
    article_content = Path(artifact.path).read_text(encoding="utf-8")
    query_docs = list(Path(artifact.path).parent.glob("*query*.md"))

    assert query_docs
    assert Path(artifact.path).parent.name == "最新论文方向"
    query_content = query_docs[0].read_text(encoding="utf-8")
    assert "Machine Learning QueryEngine 查询计划" in query_content
    assert "Google 查询：Machine Learning latest papers official" in query_content
    assert "query_plan_created" in query_content
    assert str(query_docs[0]) in article_content
