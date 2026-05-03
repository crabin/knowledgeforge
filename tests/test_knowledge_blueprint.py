from __future__ import annotations

from pathlib import Path

from knowledgeforge.config import AppConfig
from knowledgeforge.intake.context_builder import ContextBuilder
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.file_contract import parse_contract_block
from knowledgeforge.utils.structure_graph import (
    build_fallback_structure_graph,
    derive_context_from_structure_graph,
    normalize_structure_graph_payload,
)


def test_context_builder_defers_blueprint_until_structure_graph() -> None:
    context = ContextBuilder().build(
        {
            "domain": "Knowledge Engineering",
            "subdomains": ["workflow orchestration", "knowledge curation"],
            "focus_points": ["traceability"],
        }
    )

    assert context.structure_mode == "pending_structure_graph"
    assert context.completion_mode == "framework"
    assert context.knowledge_blueprint == []
    assert context.navigation_targets == []
    assert context.required_files == []


def test_structure_graph_derives_dynamic_blueprint_without_fixed_modules() -> None:
    graph = normalize_structure_graph_payload(
        payload={
            "root_node_id": "root",
            "nodes": [
                {
                    "node_id": "root",
                    "title": "Knowledge Engineering",
                    "node_type": "domain",
                    "relative_path": "README.md",
                    "doc_type": "summary",
                    "owner_engine_candidates": ["InsightEngine"],
                },
                {
                    "node_id": "workflow",
                    "title": "Workflow Orchestration",
                    "node_type": "subtopic",
                    "parent_node_id": "root",
                    "relative_path": "workflow/README.md",
                    "doc_type": "summary",
                    "owner_engine_candidates": ["InsightEngine", "QueryEngine"],
                    "required_query_tasks": 1,
                },
                {
                    "node_id": "workflow-state",
                    "title": "State Persistence",
                    "node_type": "article",
                    "parent_node_id": "workflow",
                    "relative_path": "workflow/state-persistence.md",
                    "doc_type": "article",
                    "owner_engine_candidates": ["QueryEngine"],
                    "required_query_tasks": 1,
                },
            ],
            "edges": [
                {"from_node_id": "root", "edge_type": "CONTAINS", "to_node_id": "workflow"},
                {"from_node_id": "workflow", "edge_type": "CONTAINS", "to_node_id": "workflow-state"},
            ],
        },
        domain="Knowledge Engineering",
        subdomains=["workflow orchestration"],
        focus_points=["traceability"],
        source_intent="Knowledge Engineering",
    )

    derived = derive_context_from_structure_graph(graph=graph, domain="Knowledge Engineering")
    relative_paths = {item["relative_path"] for item in derived["knowledge_blueprint"]}

    assert "README.md" in relative_paths
    assert "workflow/README.md" in relative_paths
    assert "workflow/state-persistence.md" in relative_paths
    assert "00_overview/README.md" not in relative_paths
    assert "02_core_topics/workflow orchestration/README.md" not in relative_paths
    assert derived["required_files"]
    assert all(path.startswith("save/") for path in derived["required_files"])


def test_context_builder_normalizes_legacy_completion_mode_to_framework() -> None:
    context = ContextBuilder().build(
        {
            "domain": "Knowledge Engineering",
            "completion_mode": "file_level",
        }
    )

    assert context.completion_mode == "framework"


def test_structure_graph_sanitizes_paths_and_dedupes() -> None:
    graph = normalize_structure_graph_payload(
        payload={
            "nodes": [
                {"node_id": "root", "title": "知识工程", "node_type": "domain", "relative_path": "/bad.md"},
                {"node_id": "a", "title": "A", "node_type": "article", "relative_path": "../bad.md"},
                {"node_id": "b", "title": "B", "node_type": "article", "relative_path": "../bad.md"},
            ],
            "edges": [],
        },
        domain="知识工程",
        subdomains=["工作流编排"],
        focus_points=[],
        source_intent="知识工程",
    )

    paths = [node.relative_path for node in graph.nodes]

    assert "README.md" in paths
    assert len(paths) == len(set(paths))
    assert all(not path.startswith("/") for path in paths)
    assert all(".." not in Path(path).parts for path in paths)
    assert all(path.endswith(".md") for path in paths)


def test_structure_graph_falls_back_when_payload_empty() -> None:
    graph = normalize_structure_graph_payload(
        payload={},
        domain="知识工程",
        subdomains=["工作流编排"],
        focus_points=[],
        source_intent="知识工程",
    )

    paths = {node.relative_path for node in graph.nodes}

    assert paths == {"README.md", "工作流编排/README.md", "工作流编排/overview.md"}


def test_writer_materializes_contract_backed_blueprint_files(tmp_path: Path) -> None:
    context = ContextBuilder().build(
        {
            "domain": "Knowledge Engineering",
            "subdomains": ["workflow orchestration"],
            "focus_points": ["traceability"],
        }
    )
    graph = build_fallback_structure_graph(
        domain=context.domain,
        subdomains=context.subdomains,
        source_intent=context.original_input,
    )
    derived = derive_context_from_structure_graph(graph=graph, domain=context.domain)
    context.structure_graph = graph.to_dict()
    context.structure_mode = derived["structure_mode"]
    context.knowledge_modules = derived["knowledge_modules"]
    context.core_topics = derived["core_topics"]
    context.navigation_targets = derived["navigation_targets"]
    context.knowledge_blueprint = derived["knowledge_blueprint"]
    context.required_files = derived["required_files"]
    writer = MarkdownKnowledgeWriter(AppConfig(save_root=tmp_path / "save"))

    states = writer.materialize_knowledge_base(context=context, round_number=1)

    assert states
    topic_readme = tmp_path / "save" / "Knowledge Engineering" / "workflow orchestration" / "README.md"
    assert topic_readme.exists()
    content = topic_readme.read_text(encoding="utf-8")
    contract = parse_contract_block(content)

    assert contract is not None
    assert contract["file_id"] == "subtopic_workflow_orchestration"
    assert contract["query_tasks"]
    assert contract["completion_status"]["state"] == "generated"
