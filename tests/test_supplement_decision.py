from __future__ import annotations

from pathlib import Path

from knowledgeforge.config import AppConfig
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.evaluation.supplement_decision import SupplementDecisionPlanner
from knowledgeforge.models import (
    CompletenessResult,
    DocumentArtifact,
    EngineRunResult,
    GraphSyncResult,
    PostStorageResult,
    QualityCheckResult,
    RequestContext,
    SourceRecord,
    StructuredExtractionResult,
    VersionRecord,
)
from knowledgeforge.orchestrator.graph import KnowledgeGraphWorkflow
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.paths import ensure_directory, sanitize_path_segment


class FakeSupplementChatClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        self.prompts.append(user_prompt)
        return {
            "defects": [
                {
                    "topic": "知识 index 索引",
                    "issue": "README 只记录了子主题，缺少索引文件实时维护策略。",
                    "priority": "high",
                    "query": "Knowledge graph markdown README index maintenance official documentation",
                    "expected_info": ["索引维护策略", "可引用来源"],
                    "source_priority": ["official documentation", "standard"],
                    "fallback_queries": ["Markdown knowledge base index best practices official"],
                    "success_criteria": ["命中权威来源"],
                }
            ],
            "reasoning": "基于 README 判断索引维护证据不足。",
        }


def _context() -> RequestContext:
    return RequestContext(
        domain="知识工程",
        subdomains=["工作流编排", "知识 index 索引"],
        time_window="latest",
        focus_points=["补充决策"],
        constraints=[],
        initial_strategy=[],
        task_id="task-supplement-test",
    )


def _source(title: str, reliability: str = "high") -> SourceRecord:
    return SourceRecord(
        title=title,
        url=f"https://example.com/{title}",
        publisher="example.com",
        retrieved_at="2026-04-25T00:00:00+09:00",
        reliability=reliability,  # type: ignore[arg-type]
        agent="QueryEngine",
        snippet=title,
    )


def _result(agent_name: str, topics: list[str], sources: list[SourceRecord] | None = None) -> EngineRunResult:
    return EngineRunResult(
        agent_name=agent_name,
        summary=f"{agent_name} summary",
        key_points=[f"{agent_name} point"],
        raw_material=[f"{agent_name} raw"],
        coverage_topics=topics,
        sources=sources or [],
        collected_at="2026-04-25T00:00:00+09:00",
        round_number=1,
    )


def test_supplement_planner_reads_domain_index_and_builds_query_plan(tmp_path: Path) -> None:
    context = _context()
    domain_dir = tmp_path / sanitize_path_segment(context.domain, "domain")
    ensure_directory(domain_dir)
    (domain_dir / "README.md").write_text("# 知识工程\n\n## 子主题\n\n- 工作流编排\n", encoding="utf-8")
    chat_client = FakeSupplementChatClient()

    planner = SupplementDecisionPlanner(save_root=tmp_path, chat_client=chat_client)
    completeness = CompletenessResult(
        status="supplement_required",
        reasons=["存在未覆盖的核心子主题。"],
        missing_topics=["知识 index 索引"],
        supplement_queries=["知识工程 知识 index 索引 官方资料"],
        failure_categories=["missing_topics"],
    )

    plan = planner.plan(
        context=context,
        completeness=completeness,
        outputs={"QueryEngine": _result("QueryEngine", ["工作流编排"])},
        round_number=2,
    )

    assert plan.agent_name == "QueryEngine"
    assert plan.plan_items[0].query_or_action == "Knowledge graph markdown README index maintenance official documentation"
    assert "README.md" in chat_client.prompts[0]
    assert completeness.supplement_decision["source"] == "llm_index_analysis"


class FakeInsightEngine:
    def run(self, context, round_number, approved_plan=None):
        return _result("InsightEngine", ["工作流编排"], [_source("insight", "medium")])


class FakeMediaEngine:
    def run(self, context, round_number, approved_plan=None):
        return _result("MediaEngine", ["工作流编排"], [_source("media", "medium")])


class SupplementingQueryEngine:
    def __init__(self) -> None:
        self.approved_queries: list[str] = []

    def run(self, context, round_number, approved_plan=None):
        if approved_plan is None:
            return _result("QueryEngine", ["工作流编排"], [_source("initial-query", "high")])
        self.approved_queries.extend(item.query_or_action for item in approved_plan.plan_items)
        result = _result(
            "QueryEngine",
            ["工作流编排", "知识 index 索引"],
            [_source("supplement-query", "high")],
        )
        result.execution_log.append(
            {
                "event": "query_question_completed",
                "timestamp": "2026-04-25T00:00:00+09:00",
                "node": "QueryEngine",
                "details": {
                    "status": "completed",
                    "question": approved_plan.plan_items[0].title,
                    "query": approved_plan.plan_items[0].query_or_action,
                },
            }
        )
        return result


class PassingPostStoragePipeline:
    def run(self, artifact: DocumentArtifact, context, outputs):
        return PostStorageResult(
            extraction=StructuredExtractionResult(
                document_id=artifact.document_id,
                document_path=artifact.path,
                chunks=[],
                metadata={},
                entities=[],
                relations=[],
            ),
            graph_sync=GraphSyncResult(
                document_id=artifact.document_id,
                article_path=artifact.path,
                nodes=[],
                relationships=[],
            ),
            quality_check=QualityCheckResult(
                document_id=artifact.document_id,
                status="passed",
                issues=[],
                checks={},
            ),
            version_record=VersionRecord(
                document_id=artifact.document_id,
                version="v1",
                updated_at="2026-04-25T00:00:00+09:00",
                knowledge_objects=[],
                file_paths=[artifact.path],
                graph_nodes=[],
                pending_issues=[],
                status="verified",
                frozen=True,
                report_eligible=True,
            ),
            status="passed",
        )


def test_workflow_uses_index_decision_to_dispatch_query_supplement(tmp_path: Path) -> None:
    config = AppConfig(save_root=tmp_path / "save")
    context = _context()
    domain_dir = config.save_root / sanitize_path_segment(context.domain, "domain")
    ensure_directory(domain_dir)
    (domain_dir / "README.md").write_text("# 知识工程\n\n已规划子主题：工作流编排。\n", encoding="utf-8")
    query_engine = SupplementingQueryEngine()

    workflow = KnowledgeGraphWorkflow(
        insight_engine=FakeInsightEngine(),  # type: ignore[arg-type]
        query_engine=query_engine,  # type: ignore[arg-type]
        media_engine=FakeMediaEngine(),  # type: ignore[arg-type]
        evaluator=CompletenessEvaluator(),
        supplement_planner=SupplementDecisionPlanner(
            save_root=config.save_root,
            chat_client=FakeSupplementChatClient(),
        ),
        writer=MarkdownKnowledgeWriter(config),
        post_storage_pipeline=PassingPostStoragePipeline(),  # type: ignore[arg-type]
    )

    final_state = workflow.run(
        {
            "task_id": context.task_id,
            "request_context": context,
            "messages": [],
            "round_number": 1,
            "max_rounds": 2,
            "task_status": "running",
        }
    )

    assert final_state["task_status"] == "verified"
    assert final_state["round_number"] == 2
    assert query_engine.approved_queries == ["Knowledge graph markdown README index maintenance official documentation"]
    assert final_state["completeness"].supplement_decision["index_paths"]
