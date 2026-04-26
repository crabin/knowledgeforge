from __future__ import annotations

from pathlib import Path

from knowledgeforge.api import create_app
from knowledgeforge.config import AppConfig


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
    assert "https://cdn.jsdelivr.net/npm/@antv/x6/dist/index.js" in body
    assert "三路 Agent 执行计划" in body
    assert "plan-full-panel" in body
    assert "trace-grid" in body
    assert "确认计划" in body
    assert "调用与执行日志" in body
    assert "任务列表" in body
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
