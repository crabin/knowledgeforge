from __future__ import annotations

import json
import time
from pathlib import Path

from knowledgeforge.api import create_app
from knowledgeforge.config import AppConfig
from knowledgeforge.services.task_service import TaskService


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
    assert all(
        item["status"] == "completed"
        for plan in payload["agent_plans"].values()
        for item in plan["plan_items"]
    )

    document_path = Path(payload["document_artifact"]["path"])
    assert document_path.exists()

    content = document_path.read_text(encoding="utf-8")
    assert "## 证据与来源" in content
    assert "source_type: mixed" in content


def test_intake_session_clarifies_ml_without_starting_task(tmp_path: Path) -> None:
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

    response = client.post("/intake/sessions", json={"message": "ML"})

    assert response.status_code == 201
    payload = response.get_json()
    candidate = payload["candidate_context"]
    assert payload["status"] == "draft"
    assert payload["task_id"] is None
    assert candidate["normalized_domain"] == "Machine Learning"
    assert candidate["intent"] == "knowledge_collection"
    assert candidate["output_language"] == "zh-CN"
    assert candidate["subdomains"] == ["基础概念", "核心方法", "应用场景"]


def test_intake_confirm_starts_task_with_normalized_domain(tmp_path: Path, monkeypatch) -> None:
    def fake_start_task_from_context(self, request_context):
        return {
            "task_id": "task-from-intake",
            "task_status": "running",
            "request_context": request_context.to_dict(),
        }

    monkeypatch.setattr(TaskService, "_start_task_from_context", fake_start_task_from_context)
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
    created = client.post("/intake/sessions", json={"message": "ML"}).get_json()

    confirmed = client.post(f"/intake/sessions/{created['session_id']}/confirm")

    assert confirmed.status_code == 201
    payload = confirmed.get_json()
    context = payload["task"]["request_context"]
    assert payload["intake_session"]["status"] == "confirmed"
    assert payload["intake_session"]["task_id"] == "task-from-intake"
    assert payload["task"]["task_status"] == "running"
    assert context["domain"] == "Machine Learning"
    assert context["normalized_domain"] == "Machine Learning"
    assert context["original_input"] == "ML"
    assert context["output_language"] == "zh-CN"
    assert context["confirmed"] is True


def test_intake_detects_english_language_preference(tmp_path: Path) -> None:
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

    response = client.post("/intake/sessions", json={"message": "用英文整理 ML 的最新论文方向"})

    assert response.status_code == 201
    candidate = response.get_json()["candidate_context"]
    assert candidate["normalized_domain"] == "Machine Learning"
    assert candidate["output_language"] == "en"
    assert "最新论文方向" in candidate["subdomains"]


def test_intake_append_message_reclarifies_from_full_history(tmp_path: Path) -> None:
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

    created = client.post("/intake/sessions", json={"message": "解释一下 ML 是什么"}).get_json()
    session_id = created["session_id"]

    appended = client.post(
        f"/intake/sessions/{session_id}/messages",
        json={"message": "我想整理成知识库，并且用英文输出最新论文方向"},
    )

    assert appended.status_code == 200
    payload = appended.get_json()
    candidate = payload["candidate_context"]
    assert len(payload["messages"]) == 2
    assert candidate["normalized_domain"] == "Machine Learning"
    assert candidate["intent"] == "knowledge_collection"
    assert candidate["output_language"] == "en"
    assert "最新论文方向" in candidate["subdomains"]


def test_intake_concept_explanation_does_not_start_collection(tmp_path: Path) -> None:
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
    created = client.post("/intake/sessions", json={"message": "解释一下 ML 是什么"}).get_json()

    assert created["candidate_context"]["intent"] == "concept_explanation"
    assert created["candidate_context"]["needs_clarification"] is True

    confirmed = client.post(f"/intake/sessions/{created['session_id']}/confirm")
    assert confirmed.status_code == 400


def test_intake_empty_message_returns_400(tmp_path: Path) -> None:
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
    created = client.post("/intake/sessions", json={"message": "ML"}).get_json()

    append_response = client.post(
        f"/intake/sessions/{created['session_id']}/messages",
        json={"message": ""},
    )
    create_response = client.post("/intake/sessions", json={"message": ""})

    assert append_response.status_code == 400
    assert create_response.status_code == 400


def test_intake_message_and_confirm_missing_session_return_404(tmp_path: Path) -> None:
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

    appended = client.post("/intake/sessions/missing/messages", json={"message": "补充说明"})
    confirmed = client.post("/intake/sessions/missing/confirm")

    assert appended.status_code == 404
    assert confirmed.status_code == 404


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


def test_task_response_and_logs_include_query_execution_trace(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()

    response = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["工作流编排"]})

    assert response.status_code == 201
    payload = response.get_json()
    query_output = payload["agent_outputs"]["QueryEngine"]
    assert any(item == "查询计划：" for item in query_output["raw_material"])
    assert payload["execution_log"]
    assert any(entry["event"] == "query_plan_created" for entry in payload["execution_log"])
    assert any(entry["event"] == "query_search_executed" for entry in payload["execution_log"])

    logs = client.get(f"/tasks/{payload['task_id']}/logs")
    assert logs.status_code == 200
    events = [entry["event"] for entry in logs.get_json()["logs"]]
    assert "query_plan_created" in events
    assert "query_search_executed" in events


def test_async_task_streams_query_progress_before_completion(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()

    response = client.post("/tasks/async", json={"domain": "知识工程", "subdomains": ["实时进度"]})

    assert response.status_code == 202
    started = response.get_json()
    task_id = started["task_id"]
    assert started["task_status"] == "awaiting_plan_confirmation"
    assert set(started["agent_plans"]) == {"InsightEngine", "QueryEngine", "MediaEngine"}
    assert "agent_outputs" not in started

    immediate_logs = client.get(f"/tasks/{task_id}/logs")
    assert immediate_logs.status_code == 200
    immediate_events = [entry["event"] for entry in immediate_logs.get_json()["logs"]]
    assert "agent_plans_created" in immediate_events

    plan_response = client.get(f"/tasks/{task_id}/plan")
    assert plan_response.status_code == 200
    assert plan_response.get_json()["task_status"] == "awaiting_plan_confirmation"

    confirmed = client.post(f"/tasks/{task_id}/plan/confirm")
    assert confirmed.status_code == 202
    assert confirmed.get_json()["task_status"] == "running"

    events: list[str] = []
    final_payload = {}
    for _ in range(40):
        logs_payload = client.get(f"/tasks/{task_id}/logs").get_json()
        events = [entry["event"] for entry in logs_payload["logs"]]
        final_payload = client.get(f"/tasks/{task_id}").get_json()
        if "query_plan_created" in events and final_payload.get("task_status") != "running":
            break
        time.sleep(0.05)

    assert "query_plan_created" in events
    assert "query_plan_item_started" in events
    assert "query_question_completed" in events
    assert final_payload["task_status"] != "running"


def test_async_task_detail_includes_realtime_query_action(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    service = TaskService(config)
    context = service._context_builder.build({"domain": "知识工程", "subdomains": ["实时动作"]})
    initial_state = service._create_initial_state(context, audit_source="api_async")
    task_id = initial_state["task_id"]
    service._tasks[task_id] = initial_state
    service._state_store.save(task_id, service._serialize_state(initial_state))

    service._log_realtime_query_event(
        task_id,
        {
            "event": "query_plan_item_started",
            "timestamp": "2026-04-25T16:00:00+09:00",
            "node": "QuerySearchNode",
            "details": {
                "plan_item_id": "Q1",
                "question": "知识工程如何实时展示动作？",
                "status": "in_progress",
            },
        },
    )

    task = service.get_task(task_id)
    logs = service.get_task_logs(task_id)

    assert task is not None
    assert "正在查询" in task["current_action"]
    assert any(entry["event"] == "query_plan_item_started" for entry in task["execution_log"])
    assert logs is not None
    assert "query_plan_item_started" in [entry["event"] for entry in logs["logs"]]


def test_task_logs_backfill_saved_execution_log_entries(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    service = TaskService(config)
    context = service._context_builder.build({"domain": "知识工程", "subdomains": ["日志保存"]})
    state = service._create_initial_state(context, audit_source="api_async")
    task_id = state["task_id"]
    payload = service._serialize_state(state)
    payload["execution_log"] = [
        {
            "agent": "QueryEngine",
            "event": "query_plan_created",
            "timestamp": "2026-04-25T16:05:00+09:00",
            "node": "QuerySearchNode",
            "details": {"question_count": 1, "questions": []},
        }
    ]
    service._state_store.save(task_id, payload)

    logs = service.get_task_logs(task_id)
    audit_file = config.audit_root / f"{task_id}.jsonl"

    assert logs is not None
    assert "query_plan_created" in [entry["event"] for entry in logs["logs"]]
    assert audit_file.exists()
    saved_events = [json.loads(line)["event"] for line in audit_file.read_text(encoding="utf-8").splitlines()]
    assert "query_plan_created" in saved_events


def test_task_list_returns_saved_task_summaries(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()

    created = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["任务列表"]}).get_json()
    listed = client.get("/tasks")

    assert listed.status_code == 200
    payload = listed.get_json()
    assert payload["count"] >= 1
    task = next(item for item in payload["tasks"] if item["task_id"] == created["task_id"])
    assert task["domain"] == "知识工程"
    assert task["task_status"] == created["task_status"]
    assert task["document_path"].endswith(".md")
    assert task["updated_at"]


def test_task_list_persists_across_app_recreation(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()
    created = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["持久化"]}).get_json()

    recreated_app = create_app(config)
    recreated_client = recreated_app.test_client()
    listed = recreated_client.get("/tasks")

    assert listed.status_code == 200
    task_ids = [item["task_id"] for item in listed.get_json()["tasks"]]
    assert created["task_id"] in task_ids


def test_task_management_updates_and_deletes_saved_task(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()
    created = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["任务管理"]}).get_json()
    task_id = created["task_id"]

    updated = client.patch(
        f"/tasks/{task_id}",
        json={
            "request_context": {
                "domain": "知识工程管理",
                "subdomains": ["删除", "修改"],
                "focus_points": ["任务状态"],
            },
            "management_note": "人工修正任务范围",
        },
    )

    assert updated.status_code == 200
    updated_payload = updated.get_json()
    assert updated_payload["request_context"]["domain"] == "知识工程管理"
    assert updated_payload["request_context"]["subdomains"] == ["删除", "修改"]
    assert updated_payload["management_metadata"]["note"] == "人工修正任务范围"

    logs = client.get(f"/tasks/{task_id}/logs").get_json()["logs"]
    assert "task_updated" in [entry["event"] for entry in logs]

    deleted = client.delete(f"/tasks/{task_id}")

    assert deleted.status_code == 200
    assert deleted.get_json()["deleted"] is True
    assert client.get(f"/tasks/{task_id}").status_code == 404
    listed = client.get("/tasks").get_json()
    assert task_id not in [item["task_id"] for item in listed["tasks"]]


def test_awaiting_plan_task_can_be_managed_but_not_resumed(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()
    started = client.post("/tasks/async", json={"domain": "知识工程", "subdomains": ["运行中"]}).get_json()
    task_id = started["task_id"]

    resume_before_confirmation = client.post(f"/tasks/{task_id}/resume")
    updated = client.patch(f"/tasks/{task_id}", json={"management_note": "不应允许"})
    deleted = client.delete(f"/tasks/{task_id}")

    assert resume_before_confirmation.status_code == 400
    assert updated.status_code == 200
    assert deleted.status_code == 200


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
    status = config.show_config_status()
    assert status["legacy"]["openai_configured"] is True
    assert status["llm"]["chat"]["model"] == "gpt-5.2"
    assert status["llm"]["chat"]["base_url"] == "http://localhost:8317/v1"
