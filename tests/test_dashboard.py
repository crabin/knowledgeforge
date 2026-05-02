from __future__ import annotations

import json
from pathlib import Path

from knowledgeforge.server import create_app
from knowledgeforge.config import AppConfig
from knowledgeforge.graph.client import Neo4jGraphClient


def test_dashboard_index_renders_feature_workbench(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            intake_session_root=tmp_path / "runtime" / "intake",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "KnowledgeForge 功能工作台" in body
    assert "交互式输入" in body
    assert "任务操作" in body
    assert "实时流程图" in body
    assert "workflow-x6" in body
    assert "Neo4j 实时知识图谱" in body
    assert "neo4j-graph" in body
    assert "neo4j-auto-follow" in body
    assert "refresh-neo4j-graph" in body
    assert "https://cdn.jsdelivr.net/npm/@antv/x6/dist/index.js" in body
    assert "生成与查询队列状态" in body
    assert "plan-full-panel" in body
    assert "trace-grid" in body
    assert "LLM 生成" in body
    assert "调用与执行日志" in body
    assert "Token 实时消耗" in body
    assert "token-float collapsed" in body
    assert "token-float-toggle" in body
    assert "任务列表" in body
    assert "查看队列" in body
    assert "原始响应 JSON" in body
    assert "查看任务列表" in body
    assert "/static/css/dashboard.css" in body
    assert "/static/js/dashboard.js" in body


def test_dashboard_does_not_break_status_endpoints(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    health_response = client.get("/health")
    config_response = client.get("/config/status")

    assert health_response.status_code == 200
    assert health_response.get_json() == {"status": "ok"}
    assert config_response.status_code == 200
    payload = config_response.get_json()
    assert isinstance(payload, dict)
    assert payload["llm"]["provider"] == "openai"
    assert payload["llm"]["chat"]["model"] == "gpt-5.2"
    assert payload["llm"]["chat"]["base_url"] == "http://localhost:8317/v1"
    assert payload["llm"]["embedding"]["model"] == "bge-m3:latest"
    assert payload["llm"]["embedding"]["base_url"] == "http://localhost:11434/v1"
    assert payload["llm"]["chat"]["api_key_present"] is True
    assert "api_key" not in payload["llm"]["chat"]


def test_task_graph_endpoint_returns_404_for_missing_task(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    response = client.get("/tasks/missing-task/graph")

    assert response.status_code == 404
    assert response.get_json() == {"error": "task not found"}


def test_task_graph_endpoint_returns_neo4j_snapshot(tmp_path: Path, monkeypatch) -> None:
    task_root = tmp_path / "runtime" / "tasks"
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=task_root,
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    task_root.joinpath("task-graph.json").write_text(
        json.dumps({"task_id": "task-graph", "request_context": {"domain": "知识工程"}, "task_status": "verified"}),
        encoding="utf-8",
    )

    def fake_snapshot(self, *, domain: str, node_limit: int = 300, relationship_limit: int = 600):
        assert domain == "知识工程"
        assert node_limit == 300
        assert relationship_limit == 600
        return {
            "nodes": [
                {"id": "domain-1", "title": "知识工程", "type": "Domain", "labels": ["Domain"], "path": "", "properties": {"id": "知识工程"}},
                {"id": "article-1", "title": "文章", "type": "Article", "labels": ["Article"], "path": "save/知识工程/a.md", "properties": {"id": "a"}},
            ],
            "edges": [{"id": "rel-1", "source": "domain-1", "target": "article-1", "type": "HAS_ARTICLE", "properties": {}}],
        }

    monkeypatch.setattr(Neo4jGraphClient, "snapshot_domain_graph", fake_snapshot)
    client = app.test_client()

    response = client.get("/tasks/task-graph/graph")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["task_id"] == "task-graph"
    assert payload["domain"] == "知识工程"
    assert payload["status"] == "ok"
    assert payload["limits"] == {"nodes": 300, "edges": 600}
    assert payload["graph"]["nodes"][0]["type"] == "Domain"
    assert payload["graph"]["edges"][0]["type"] == "HAS_ARTICLE"


def test_task_graph_endpoint_hides_neo4j_connection_errors(tmp_path: Path, monkeypatch) -> None:
    task_root = tmp_path / "runtime" / "tasks"
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=task_root,
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
            neo4j=AppConfig().neo4j.__class__(
                uri="bolt://secret-host:7687",
                user="neo4j",
                password="super-secret-password",
            ),
        )
    )
    task_root.joinpath("task-graph.json").write_text(
        json.dumps({"task_id": "task-graph", "request_context": {"domain": "知识工程"}, "task_status": "running"}),
        encoding="utf-8",
    )

    def fake_snapshot(self, *, domain: str, node_limit: int = 300, relationship_limit: int = 600):
        raise RuntimeError("super-secret-password at bolt://secret-host:7687")

    monkeypatch.setattr(Neo4jGraphClient, "snapshot_domain_graph", fake_snapshot)
    client = app.test_client()

    response = client.get("/tasks/task-graph/graph")

    assert response.status_code == 200
    payload = response.get_json()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "unavailable"
    assert payload["graph"] == {"nodes": [], "edges": []}
    assert "super-secret-password" not in serialized
    assert "secret-host" not in serialized
