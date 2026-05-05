from __future__ import annotations

from knowledgeforge.graph.client import Neo4jGraphClient


class _FakeTx:
    def __init__(self, rows):
        self._rows = rows

    def run(self, query, **kwargs):
        return self._rows


def test_read_domain_graph_issues_deduplicates_same_noise_node() -> None:
    rows = [
        {
            "graph_id": "4:noise-a",
            "labels": ["SubTopic"],
            "properties": {"title": "基础概念"},
            "relationship_count": 1,
            "relationship_types": ["MENTIONS"],
            "matching_structure_node_id": "topic-a",
            "matching_structure_title": "基础概念",
            "matching_structure_type": "section",
            "matching_structure_path": "基础概念/README.md",
        },
        {
            "graph_id": "4:noise-a",
            "labels": ["SubTopic"],
            "properties": {"title": "基础概念"},
            "relationship_count": 1,
            "relationship_types": ["HAS_SUBTOPIC"],
            "matching_structure_node_id": "topic-b",
            "matching_structure_title": "基础概念",
            "matching_structure_type": "section",
            "matching_structure_path": "基础概念/overview.md",
        },
        {
            "graph_id": "4:noise-b",
            "labels": ["SubTopic"],
            "properties": {"title": "数学与工程前置"},
            "relationship_count": 1,
            "relationship_types": ["MENTIONS"],
            "matching_structure_node_id": "topic-c",
            "matching_structure_title": "数学与工程前置",
            "matching_structure_type": "subtopic",
            "matching_structure_path": "数学与工程前置/README.md",
        },
    ]

    result = Neo4jGraphClient._read_domain_graph_issues(_FakeTx(rows), "Deep Learning", "task-1")

    assert result["count"] == 2
    assert [issue["graph_id"] for issue in result["issues"]] == ["4:noise-a", "4:noise-b"]
    first_issue = result["issues"][0]
    assert first_issue["title"] == "基础概念"
    assert first_issue["relationship_types"] == ["HAS_SUBTOPIC", "MENTIONS"]
    assert len(first_issue["matching_candidates"]) == 2

