from __future__ import annotations

from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord


def _make_context(domain: str = "Machine Learning") -> RequestContext:
    return RequestContext(
        domain=domain,
        subdomains=["supervised learning", "unsupervised learning"],
        time_window="2024",
        focus_points=["applications"],
        constraints=[],
        initial_strategy=[],
    )


def _make_source(
    title: str = "ML Guide",
    url: str = "https://scikit-learn.org/",
    reliability: str = "high",
) -> SourceRecord:
    return SourceRecord(
        title=title,
        url=url,
        publisher="scikit-learn.org",
        retrieved_at="2024-01-01T00:00:00Z",
        reliability=reliability,  # type: ignore[arg-type]
        agent="QueryEngine",
    )


def _make_engine_result(sources: list[SourceRecord], topics: list[str]) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="summary",
        key_points=[],
        raw_material=[],
        coverage_topics=topics,
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def _make_engine_result_with_log(
    sources: list[SourceRecord],
    topics: list[str],
    execution_log: list[dict],
) -> EngineRunResult:
    result = _make_engine_result(sources, topics)
    result.execution_log.extend(execution_log)
    return result


def test_passes_with_high_reliability_source_and_full_coverage() -> None:
    ctx = _make_context()
    output = _make_engine_result(
        sources=[_make_source(reliability="high")],
        topics=["supervised learning", "unsupervised learning"],
    )
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    assert result.status == "pass"


def test_fails_when_all_sources_are_unknown_reliability() -> None:
    ctx = _make_context()
    output = _make_engine_result(
        sources=[_make_source(reliability="unknown")],
        topics=["supervised learning", "unsupervised learning"],
    )
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    assert result.status == "supplement_required"
    assert any("no_authoritative_source" in r for r in result.failure_categories)


def test_fails_when_sources_empty() -> None:
    ctx = _make_context()
    output = _make_engine_result(sources=[], topics=["supervised learning", "unsupervised learning"])
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    assert result.status == "supplement_required"


def test_supplement_queries_are_domain_specific() -> None:
    ctx = _make_context()
    output = _make_engine_result(sources=[], topics=[])
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    for query in result.supplement_queries:
        assert "machine learning" in query.lower() or "ml" in query.lower()


def test_fails_when_query_plan_has_insufficient_items() -> None:
    ctx = _make_context()
    output = _make_engine_result_with_log(
        sources=[_make_source(reliability="high")],
        topics=["supervised learning", "unsupervised learning"],
        execution_log=[
            {
                "event": "query_question_completed",
                "details": {
                    "status": "insufficient",
                    "question": "需要补充教程案例",
                },
            }
        ],
    )

    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})

    assert result.status == "supplement_required"
    assert "query_plan_incomplete" in result.failure_categories
