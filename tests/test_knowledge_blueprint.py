from __future__ import annotations

from pathlib import Path

from knowledgeforge.config import AppConfig
from knowledgeforge.intake.context_builder import ContextBuilder
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.file_contract import parse_contract_block


def test_context_builder_creates_full_knowledge_blueprint() -> None:
    context = ContextBuilder().build(
        {
            "domain": "Knowledge Engineering",
            "subdomains": ["workflow orchestration", "knowledge curation"],
            "focus_points": ["traceability"],
        }
    )

    blueprint = context.knowledge_blueprint
    relative_paths = {item["relative_path"] for item in blueprint}

    assert "README.md" in relative_paths
    assert "00_overview/README.md" in relative_paths
    assert "01_foundations/README.md" in relative_paths
    assert "02_core_topics/workflow orchestration/README.md" in relative_paths
    assert "07_review/09_next_learning_plan.md" in relative_paths
    assert context.required_files
    assert all(path.startswith("save/") for path in context.required_files)


def test_writer_materializes_contract_backed_blueprint_files(tmp_path: Path) -> None:
    context = ContextBuilder().build(
        {
            "domain": "Knowledge Engineering",
            "subdomains": ["workflow orchestration"],
            "focus_points": ["traceability"],
        }
    )
    writer = MarkdownKnowledgeWriter(AppConfig(save_root=tmp_path / "save"))

    states = writer.materialize_knowledge_base(context=context, round_number=1)

    assert states
    topic_readme = tmp_path / "save" / "Knowledge Engineering" / "02_core_topics" / "workflow orchestration" / "README.md"
    assert topic_readme.exists()
    content = topic_readme.read_text(encoding="utf-8")
    contract = parse_contract_block(content)

    assert contract is not None
    assert contract["file_id"].endswith("overview")
    assert contract["query_tasks"]
    assert contract["completion_status"]["state"] == "generated"
