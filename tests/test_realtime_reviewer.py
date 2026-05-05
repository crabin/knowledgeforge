from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledgeforge.server.config import AppConfig
from knowledgeforge.server.models import RequestContext
from knowledgeforge.server.storage.realtime_reviewer import RealtimeFileReviewer, RealtimeReviewCandidate


@dataclass(slots=True)
class ReviewDocument:
    title: str
    url: str
    snippet: str
    content: str
    source_type: str
    publisher: str
    score: float
    platform_type: str = ""


def _context(task_id: str = "task-1") -> RequestContext:
    return RequestContext(
        domain="Machine Learning",
        subdomains=["基础概念"],
        time_window="latest",
        focus_points=["官方文档"],
        constraints=[],
        initial_strategy=[],
        task_id=task_id,
    )


def test_realtime_reviewer_saves_query_plan_item_and_updates_readme(tmp_path: Path) -> None:
    reviewer = RealtimeFileReviewer(AppConfig(save_root=tmp_path / "save"))
    candidate = RealtimeReviewCandidate(
        agent="QueryEngine",
        round_number=1,
        plan_item_id="Q1",
        query="machine learning official documentation",
        source_type="official",
        context=_context(),
        documents=[
            ReviewDocument(
                title="ML Official Guide",
                url="https://example.com/ml",
                snippet="Official machine learning facts.",
                content="Official machine learning facts and definitions.",
                source_type="official",
                publisher="example.com",
                score=10.0,
            )
        ],
    )

    result = reviewer.review_and_save(candidate)

    assert result.status == "saved"
    assert len(result.saved_paths) == 1
    content = Path(result.saved_paths[0]).read_text(encoding="utf-8")
    assert "realtime_saved: true" in content
    assert "plan_item_id: Q1" in content
    assert "ML Official Guide" in content
    readme = Path(result.index_path).read_text(encoding="utf-8")
    assert "## 实时保存文档" in readme
    assert result.saved_paths[0] in readme


def test_realtime_reviewer_skips_invalid_and_duplicate_sources(tmp_path: Path) -> None:
    reviewer = RealtimeFileReviewer(AppConfig(save_root=tmp_path / "save"))
    first = RealtimeReviewCandidate(
        agent="QueryEngine",
        round_number=1,
        plan_item_id="Q1",
        query="machine learning official documentation",
        source_type="official",
        context=_context(),
        documents=[
            ReviewDocument(
                title="ML Official Guide",
                url="https://example.com/ml",
                snippet="Official machine learning facts.",
                content="Official machine learning facts and definitions.",
                source_type="official",
                publisher="example.com",
                score=10.0,
            )
        ],
    )
    reviewer.review_and_save(first)
    second = RealtimeReviewCandidate(
        agent="QueryEngine",
        round_number=1,
        plan_item_id="Q2",
        query="machine learning tutorial",
        source_type="tutorial",
        context=_context(),
        documents=[
            first.documents[0],
            ReviewDocument(
                title="No Content",
                url="https://example.com/empty",
                snippet="",
                content="",
                source_type="tutorial",
                publisher="example.com",
                score=4.0,
            ),
        ],
    )

    result = reviewer.review_and_save(second)

    assert result.status == "skipped"
    assert not result.saved_paths
    reasons = {item["reason"] for item in result.skipped_sources}
    assert {"duplicate_url", "missing_content"} <= reasons
