from __future__ import annotations

import json
from pathlib import Path

from knowledgeforge.api import create_app
from knowledgeforge.config import AppConfig


def test_task_workflow_writes_markdown(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
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
    assert payload["task_status"] == "verified"
    assert payload["document_artifact"]["path"].endswith(".md")
    assert payload["post_storage_result"]["status"] == "passed"
    assert payload["post_storage_result"]["quality_check"]["status"] == "passed"
    assert payload["post_storage_result"]["version_record"]["status"] == "verified"
    assert payload["post_storage_result"]["version_record"]["frozen"] is True
    assert payload["post_storage_result"]["version_record"]["report_eligible"] is True

    document_path = Path(payload["document_artifact"]["path"])
    assert document_path.exists()

    content = document_path.read_text(encoding="utf-8")
    assert "## 证据与来源" in content
    assert "source_type: mixed" in content


def test_post_storage_result_contains_graph_and_extraction(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    response = client.post("/tasks", json={"domain": "知识工程"})

    assert response.status_code == 201
    payload = response.get_json()
    governance = payload["post_storage_result"]
    assert governance["extraction"]["chunks"]
    assert governance["graph_sync"]["nodes"]
    assert governance["failure_category"] is None


def test_research_flow_resume_and_max_round_protection(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
        max_rounds=2,
    )
    app = create_app(config)
    client = app.test_client()

    response = client.post(
        "/tasks",
        json={"domain": "知识工程", "constraints": ["simulate_missing_citation"]},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["task_status"] == "research_required"
    assert payload["post_storage_result"]["status"] == "failed"
    assert "research_flow" in payload["post_storage_result"]["remediation_flows"]

    task_id = payload["task_id"]
    resumed = client.post(f"/tasks/{task_id}/resume")
    assert resumed.status_code == 200
    resumed_payload = resumed.get_json()
    assert resumed_payload["round_number"] == 2
    assert resumed_payload["task_status"] == "research_required"

    capped = client.post(f"/tasks/{task_id}/resume")
    assert capped.status_code == 200
    capped_payload = capped.get_json()
    assert capped_payload["task_status"] == "max_rounds_reached"


def test_task_state_persists_across_app_recreation(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()
    created = client.post("/tasks", json={"domain": "知识工程", "constraints": ["simulate_duplicate"]})
    task_id = created.get_json()["task_id"]

    recreated_app = create_app(config)
    recreated_client = recreated_app.test_client()
    restored = recreated_client.get(f"/tasks/{task_id}")

    assert restored.status_code == 200
    payload = restored.get_json()
    assert payload["task_id"] == task_id
    assert payload["task_status"] == "repair_required"

    audit_file = config.audit_root / f"{task_id}.jsonl"
    assert audit_file.exists()
    events = [json.loads(line)["event"] for line in audit_file.read_text(encoding="utf-8").splitlines()]
    assert "task_created" in events
    assert "task_completed" in events


def test_frozen_version_and_report_only_use_verified_knowledge(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()

    created = client.post("/tasks", json={"domain": "知识工程"})
    task_id = created.get_json()["task_id"]

    frozen = client.get(f"/tasks/{task_id}/frozen")
    assert frozen.status_code == 200
    frozen_payload = frozen.get_json()
    assert frozen_payload["report_eligible"] is True
    assert frozen_payload["source_snapshot"]

    report = client.post(f"/tasks/{task_id}/report")
    assert report.status_code == 200
    report_payload = report.get_json()
    assert report_payload["source"] == "frozen_version"
    assert report_payload["version"] == frozen_payload["version"]


def test_report_rejects_non_frozen_task(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()

    created = client.post("/tasks", json={"domain": "知识工程", "constraints": ["simulate_missing_citation"]})
    task_id = created.get_json()["task_id"]

    frozen = client.get(f"/tasks/{task_id}/frozen")
    report = client.post(f"/tasks/{task_id}/report")
    assert frozen.status_code == 404
    assert report.status_code == 404


def test_domain_is_required(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    response = client.post("/tasks", json={})

    assert response.status_code == 400
    assert response.get_json()["error"] == "`domain` is required."


def test_app_config_loads_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=openai",
                "OPENAI_API_KEY=test-key",
                "OPENAI_BASE_URL=http://localhost:8317/v1",
                "OPENAI_MODEL=gpt-5.2",
                "OPENAI_EMBEDDING_MODEL=bge-m3:latest",
                "OPENAI_EMBEDDING_DIMENSIONS=1024",
                "OPENAI_EMBEDDING_API_KEY=ollama",
                "OPENAI_EMBEDDING_BASE_URL=http://localhost:11434/v1",
                "CHROMADB_PATH=./chroma_db",
                "CHROMADB_COLLECTION_NAME=domain_knowledge",
                "CHROMADB_HNSW_M=32",
                "CHROMADB_HNSW_CONSTRUCTION_EF=200",
                "CHROMADB_HNSW_SEARCH_EF=100",
                "NEO4J_URI=bolt://localhost:7687",
                "NEO4J_USER=neo4j",
                "NEO4J_PASSWORD=password",
                "MYSQL_DATABASE_URL=mysql://root:password@localhost:3306/knowledgeforge",
                "LOG_LEVEL=INFO",
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env(env_file)

    assert config.llm_provider == "openai"
    assert config.openai.model == "gpt-5.2"
    assert config.openai.embedding_dimensions == 1024
    assert config.neo4j.user == "neo4j"
    assert config.database.mysql_database_url.startswith("mysql://")
    assert config.show_config_status()["openai_configured"] is True
