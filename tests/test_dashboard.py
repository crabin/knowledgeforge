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
    assert isinstance(config_response.get_json(), dict)
