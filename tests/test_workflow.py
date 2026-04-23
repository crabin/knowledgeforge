from __future__ import annotations

from pathlib import Path

from knowledgeforge.api import create_app
from knowledgeforge.config import AppConfig


def test_task_workflow_writes_markdown(tmp_path: Path) -> None:
    app = create_app(AppConfig(save_root=tmp_path / "save"))
    client = app.test_client()

    response = client.post(
        "/tasks",
        json={
            "domain": "知识工程",
            "subdomains": ["工作流编排", "知识沉淀"],
            "focus_points": ["状态恢复", "来源追溯"],
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["task_status"] == "written"
    assert payload["document_artifact"]["path"].endswith(".md")

    document_path = Path(payload["document_artifact"]["path"])
    assert document_path.exists()

    content = document_path.read_text(encoding="utf-8")
    assert "## 证据与来源" in content
    assert "source_type: mixed" in content


def test_domain_is_required(tmp_path: Path) -> None:
    app = create_app(AppConfig(save_root=tmp_path / "save"))
    client = app.test_client()

    response = client.post("/tasks", json={})

    assert response.status_code == 400
    assert response.get_json()["error"] == "`domain` is required."
