from __future__ import annotations

import json
import time
from pathlib import Path

from knowledgeforge.server import create_app
from knowledgeforge.config import AppConfig
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.models import GraphSyncResult
from knowledgeforge.orchestrator.graph import KnowledgeGraphWorkflow
from knowledgeforge.postprocess.pipeline import PostStoragePipeline
from knowledgeforge.services.task_service import TaskService


def test_task_workflow_updates_graph_without_markdown_by_default(tmp_path: Path) -> None:
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
    assert payload["request_context"]["completion_mode"] == "framework"
    assert payload["document_completion_status"] == "not_requested"
    assert payload["full_document_status"] == "not_requested"
    assert payload["document_artifact"]["path"].endswith(".md")
    assert not payload["document_artifact"]["path"].endswith("-mixed.md")
    assert ".knowledgeforge" not in payload["document_artifact"]["path"]
    assert "graph_governance" in payload["document_artifact"]["path"]
    assert payload["post_storage_result"]["status"] == "passed"
    assert payload["post_storage_result"]["quality_check"]["status"] == "passed"
    assert payload["post_storage_result"]["quality_check"]["checks"]["framework_graph_check"] is True
    assert payload["post_storage_result"]["version_record"]["status"] == "verified"
    assert payload["post_storage_result"]["version_record"]["frozen"] is True
    assert payload["post_storage_result"]["version_record"]["report_eligible"] is True
    assert payload["task_queue_snapshot"]["tasks"]
    assert payload["structure_graph"]["nodes"]
    assert payload["graph_snapshot"]["nodes"]
    assert payload["started_at"]
    assert payload["finished_at"]
    assert payload["task_timing"]["elapsed_seconds"] >= 0
    assert payload["task_timing"]["is_running"] is False
    assert len(payload["structure_review_rounds"]) == 2
    assert payload["structure_review_status"] == "passed"
    assert any(
        node["properties"].get("generation_state") in {"completion_ready", "link_verified"}
        for node in payload["graph_snapshot"]["nodes"]
    )
    assert payload["graph_event"]["event_type"] == "structure_node_status_changed"
    assert payload["file_update"]["status"] == "completed"
    assert any(event["step_id"] == "structure_graph_ready" for event in payload["workflow_events"])
    assert any(event["step_id"] == "structure_review" for event in payload["workflow_events"])
    assert any(event["step_id"] == "evidence_link_query" for event in payload["workflow_events"])
    assert not any(event["step_id"] == "evidence_link_recorded" for event in payload["workflow_events"])
    assert all(task["task_type"] == "query" for task in payload["task_queue_snapshot"]["tasks"])
    assert any(task.get("selected_link") for task in payload["task_queue_snapshot"]["tasks"])
    assert all("selected_link" not in node for node in payload["structure_graph"]["nodes"])

    knowledge_markdown = [
        path for path in (tmp_path / "save" / "知识工程").rglob("*.md")
        if path.name == "README.md" or path.parent.name != "graph_governance"
    ]
    assert knowledge_markdown == []

    content = Path(payload["document_artifact"]["path"]).read_text(encoding="utf-8")
    assert "## 证据与来源" in content
    assert "## 知识定位" in content
    assert "source_type: neo4j" in content

    graph_response = client.get(f"/tasks/{payload['task_id']}/graph")
    assert graph_response.status_code == 200
    graph_payload = graph_response.get_json()
    assert graph_payload["status"] in {"ok", "local"}
    assert graph_payload["graph"]["nodes"]


def test_task_workflow_ignores_full_document_mode_until_completion_button(tmp_path: Path) -> None:
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
            "completion_mode": "full_document",
            "subdomains": ["工作流编排", "知识沉淀"],
            "focus_points": ["状态恢复", "来源追溯"],
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["task_status"] == "verified"
    assert payload["request_context"]["completion_mode"] == "framework"
    assert payload["document_completion_status"] == "not_requested"
    assert payload["full_document_status"] == "not_requested"
    assert not payload["document_artifact"]["path"].endswith("-mixed.md")
    assert not list((tmp_path / "save" / "知识工程").rglob("*.md"))


def test_structure_review_repairs_first_round_before_documents(tmp_path: Path, monkeypatch) -> None:
    original_complete_json = OpenAICompatibleChatClient.complete_json
    review_calls = {"count": 0}

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        if "知识架构审查器" in system_prompt:
            review_calls["count"] += 1
            if review_calls["count"] == 1:
                return {
                    "is_complete": False,
                    "status": "needs_repair",
                    "missing_topics": ["评估指标"],
                    "suggested_repairs": [{"type": "add_node", "title": "评估指标"}],
                    "reasoning": "缺少评估指标知识点。",
                }
            return {
                "is_complete": True,
                "status": "passed",
                "missing_topics": [],
                "suggested_repairs": [],
                "reasoning": "修补后结构完整。",
            }
        if "知识架构修补器" in system_prompt:
            return {}
        return original_complete_json(self, system_prompt=system_prompt, user_prompt=user_prompt)

    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", complete_json)
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    response = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["工作流编排"]})

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["task_status"] == "verified"
    assert [item["status"] for item in payload["structure_review_rounds"]] == ["needs_repair", "passed"]
    assert payload["structure_repair_log"]
    assert any(node["title"] == "评估指标" for node in payload["structure_graph"]["nodes"])
    assert payload["document_artifact"]["doc_role"] == "graph_governance"
    assert any(
        node.get("generation_state") in {"completion_ready", "link_verified"}
        for node in payload["structure_graph"]["nodes"]
    )


def test_structure_review_uses_neo4j_context_and_syncs_each_round(tmp_path: Path, monkeypatch) -> None:
    original_complete_json = OpenAICompatibleChatClient.complete_json
    review_prompts: list[dict] = []
    sync_states: list[str] = []

    def structure_review_context(self, *, domain: str, task_id: str, knowledge_id: str):
        return {
            "status": "ok",
            "domain": domain,
            "task_id": task_id,
            "knowledge_id": knowledge_id,
            "nodes": [
                {
                    "id": "neo4j-node-1",
                    "title": "Neo4j 里的结构节点",
                    "properties": {"id": knowledge_id, "generation_state": "reviewing"},
                }
            ],
            "edges": [{"source": "neo4j-node-1", "target": "neo4j-node-2", "type": "STRUCTURE_EDGE"}],
        }

    def sync_structure_graph(self, *, domain: str, task_id: str, structure_graph: dict):
        first_node = next((node for node in structure_graph.get("nodes", []) if isinstance(node, dict)), {})
        sync_states.append(str(first_node.get("generation_state", "")))
        return GraphSyncResult(
            document_id=f"{domain}-structure-graph",
            article_path="",
            nodes=[],
            relationships=[],
            status="passed",
        )

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        if "知识架构审查器" in system_prompt:
            prompt = json.loads(user_prompt)
            review_prompts.append(prompt)
            return {
                "is_complete": True,
                "status": "passed",
                "missing_topics": [],
                "suggested_repairs": [],
                "reasoning": "结合 Neo4j 上下文完成查漏补缺。",
            }
        return original_complete_json(self, system_prompt=system_prompt, user_prompt=user_prompt)

    monkeypatch.setattr(PostStoragePipeline, "structure_review_context", structure_review_context)
    monkeypatch.setattr(PostStoragePipeline, "sync_structure_graph", sync_structure_graph)
    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", complete_json)

    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    response = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["工作流编排"]})

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["task_status"] == "verified"
    assert len(review_prompts) == 2
    assert all(prompt["knowledge_id"] for prompt in review_prompts)
    assert all(prompt["neo4j_review_context"]["status"] == "ok" for prompt in review_prompts)
    assert review_prompts[0]["neo4j_review_context"]["nodes"][0]["title"] == "Neo4j 里的结构节点"
    assert review_prompts[1]["previous_review_rounds"][0]["neo4j_review_context"]["status"] == "ok"
    assert sync_states.count("approved") >= 2


def test_structure_review_failure_stops_before_documents(tmp_path: Path, monkeypatch) -> None:
    original_complete_json = OpenAICompatibleChatClient.complete_json

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        if "知识架构审查器" in system_prompt:
            return {
                "is_complete": False,
                "status": "needs_repair",
                "missing_topics": ["核心边界"],
                "suggested_repairs": [{"type": "manual_review"}],
                "reasoning": "两轮后仍缺少核心边界。",
            }
        if "知识架构修补器" in system_prompt:
            return {}
        return original_complete_json(self, system_prompt=system_prompt, user_prompt=user_prompt)

    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", complete_json)
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()

    response = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["工作流编排"]})

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["task_status"] == "repair_required"
    assert len(payload["structure_review_rounds"]) == 2
    assert payload["structure_review_rounds"][-1]["suggested_repairs"] == []
    assert "人工" not in payload["current_action"]
    assert "系统后续修复流" in payload["current_action"]
    assert "document_artifact" not in payload
    domain_dir = tmp_path / "save" / "知识工程"
    assert not domain_dir.exists()


def test_resume_repair_required_continues_from_repaired_structure(tmp_path: Path, monkeypatch) -> None:
    original_complete_json = OpenAICompatibleChatClient.complete_json

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        if "知识架构审查器" in system_prompt:
            return {
                "is_complete": False,
                "status": "needs_repair",
                "missing_topics": ["恢复执行入口"],
                "suggested_repairs": [{"type": "add_nodes", "title": "恢复执行入口"}],
                "reasoning": "第二轮后仍需系统修补。",
            }
        if "知识架构修补器" in system_prompt:
            return {}
        return original_complete_json(self, system_prompt=system_prompt, user_prompt=user_prompt)

    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", complete_json)
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()
    created = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["工作流编排"]}).get_json()

    assert created["task_status"] == "repair_required"

    resumed = client.post(f"/tasks/{created['task_id']}/resume")

    assert resumed.status_code == 200
    payload = resumed.get_json()
    assert payload["task_status"] in {"verified", "research_required", "repair_required"}
    assert payload["current_step"] != "structure_review"
    assert payload["generation_progress"]["completed_files"] == payload["generation_progress"]["total_files"]
    assert payload["task_queue_path"].endswith("knowledge_task_queue.json")
    assert any(
        event["step_id"] == "structure_repair" and event["details"].get("resume_mode") == "continue_after_structure_repair"
        for event in payload["workflow_events"]
    )
    assert (tmp_path / "save" / "知识工程").exists()


def test_resume_repair_required_from_structure_repair_step_continues(tmp_path: Path, monkeypatch) -> None:
    original_complete_json = OpenAICompatibleChatClient.complete_json

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        if "知识架构审查器" in system_prompt:
            return {
                "is_complete": False,
                "status": "needs_repair",
                "missing_topics": ["恢复执行入口"],
                "suggested_repairs": [{"type": "add_nodes", "title": "恢复执行入口"}],
                "reasoning": "第二轮后仍需系统修补。",
            }
        if "知识架构修补器" in system_prompt:
            return {}
        return original_complete_json(self, system_prompt=system_prompt, user_prompt=user_prompt)

    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", complete_json)
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()
    created = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["工作流编排"]}).get_json()
    task_id = created["task_id"]
    created["current_step"] = "structure_repair"
    app.config["TASK_SERVICE"]._state_store.save(task_id, created)
    app.config["TASK_SERVICE"]._tasks.pop(task_id, None)

    resumed = client.post(f"/tasks/{task_id}/resume")

    assert resumed.status_code == 200
    payload = resumed.get_json()
    assert payload["current_step"] != "structure_review"
    assert payload["current_step"] != "structure_repair"
    assert payload["generation_progress"]["completed_files"] == payload["generation_progress"]["total_files"]


def test_resume_running_task_does_not_start_second_workflow(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    service = app.config["TASK_SERVICE"]
    initial_state = service._create_initial_state(
        service._context_builder.build({"domain": "知识工程", "subdomains": ["工作流编排"], "confirmed": True}),
        audit_source="api_async",
    )
    task_id = initial_state["task_id"]
    initial_state["current_step"] = "structure_repair"
    initial_state["current_action"] = "正在修补结构图谱。"
    service._tasks[task_id] = initial_state
    service._state_store.save(task_id, service._serialize_state(initial_state))

    response = app.test_client().post(f"/tasks/{task_id}/resume")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["task_status"] == "running"
    assert payload["current_step"] == "structure_repair"
    assert "task_resume_skipped" in [json.loads(line)["event"] for line in (service._config.audit_root / f"{task_id}.jsonl").read_text(encoding="utf-8").splitlines()]


def test_structure_review_rounds_are_replaced_not_appended() -> None:
    rounds = KnowledgeGraphWorkflow._merge_structure_review_round(
        [
            {"round": 1, "status": "needs_repair", "reasoning": "old round 1"},
            {"round": 2, "status": "needs_repair", "reasoning": "old round 2"},
            {"round": 1, "status": "needs_repair", "reasoning": "duplicate round 1"},
        ],
        {"round": 1, "status": "passed", "reasoning": "new round 1"},
    )

    assert len(rounds) == 2
    assert [round_item["round"] for round_item in rounds] == [1, 2]
    assert rounds[0]["reasoning"] == "new round 1"


def test_complete_documents_requires_finished_framework_then_expands_files(tmp_path: Path) -> None:
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    client = app.test_client()
    created = client.post("/tasks", json={"domain": "知识工程", "subdomains": ["工作流编排"]}).get_json()

    response = client.post(f"/tasks/{created['task_id']}/documents/complete")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["full_document_status"] == "generated"
    result = payload["document_completion_result"]
    assert result["completed_files"]
    workflow_step_ids = [event["step_id"] for event in payload["workflow_events"]]
    assert "evidence_link_recorded" in workflow_step_ids
    assert "document_completion" in workflow_step_ids
    assert workflow_step_ids.index("evidence_link_recorded") < workflow_step_ids.index("document_completion")
    assert payload["document_evidence_sync"]["total_tasks"] >= 1
    assert any("selected_link" in node for node in payload["request_context"]["structure_graph"]["nodes"])

    completed_path = Path(result["completed_files"][0])
    content = completed_path.read_text(encoding="utf-8")
    assert "## 正文" in content
    assert "## 知识定位" not in content
    assert "source_type: mixed" in content


def test_complete_documents_rejects_unverified_framework(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    config.task_state_root.joinpath("task-incomplete.json").write_text(
        json.dumps(
            {
                "task_id": "task-incomplete",
                "task_status": "running",
                "request_context": {"domain": "知识工程", "subdomains": ["工作流编排"]},
            }
        ),
        encoding="utf-8",
    )
    client = app.test_client()

    response = client.post("/tasks/task-incomplete/documents/complete")

    assert response.status_code == 400
    assert "running tasks cannot be completed" in response.get_json()["error"]


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
    assert context["completion_mode"] == "framework"


def test_direct_async_task_normalizes_domain_before_starting(tmp_path: Path) -> None:
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

    response = client.post("/tasks/async", json={"domain": "DL"})

    assert response.status_code == 202
    context = response.get_json()["request_context"]
    assert context["domain"] == "Deep Learning"
    assert context["normalized_domain"] == "Deep Learning"
    assert context["original_input"] == "DL"
    assert context["confirmed"] is True
    assert context["completion_mode"] == "framework"


def test_direct_async_task_normalizes_legacy_file_level_completion_mode(tmp_path: Path) -> None:
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

    response = client.post("/tasks/async", json={"domain": "DL", "completion_mode": "file_level"})

    assert response.status_code == 202
    context = response.get_json()["request_context"]
    assert context["completion_mode"] == "framework"


def test_direct_task_rejects_unconfirmed_concept_explanation(tmp_path: Path) -> None:
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

    response = client.post("/tasks/async", json={"domain": "解释一下 ML 是什么"})

    assert response.status_code == 400
    assert "not confirmed for knowledge collection" in response.get_json()["error"]


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
    assert any(item == "链接级采集计划：" for item in query_output["raw_material"])
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
    assert started["task_status"] == "running"
    assert started["current_step"] == "intent_recognition"

    immediate_logs = client.get(f"/tasks/{task_id}/logs")
    assert immediate_logs.status_code == 200
    immediate_events = [entry["event"] for entry in immediate_logs.get_json()["logs"]]
    assert "task_started_async" in immediate_events

    plan_response = client.get(f"/tasks/{task_id}/plan")
    assert plan_response.status_code == 200
    assert "task_queue_snapshot" in plan_response.get_json()

    events: list[str] = []
    final_payload = {}
    for _ in range(40):
        logs_payload = client.get(f"/tasks/{task_id}/logs").get_json()
        events = [entry["event"] for entry in logs_payload["logs"]]
        final_payload = client.get(f"/tasks/{task_id}").get_json()
        if final_payload.get("task_status") != "running":
            break
        time.sleep(0.05)

    assert "workflow_step" in events
    assert final_payload["task_status"] != "running"


def test_task_logs_include_rich_summary_and_application_log(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        app_log_root=tmp_path / "logs",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()

    response = client.post("/tasks/async", json={"domain": "知识工程", "subdomains": ["日志增强"]})

    assert response.status_code == 202
    task_id = response.get_json()["task_id"]
    logs_response = client.get(f"/tasks/{task_id}/logs")

    assert logs_response.status_code == 200
    payload = logs_response.get_json()
    assert "queue_summary" in payload
    assert "log_summary" in payload
    assert "llm_activity" in payload
    assert "log_files" in payload
    assert payload["log_files"]["application_log"].endswith("knowledgeforge-server.log")

    app_log = config.app_log_root / "knowledgeforge-server.log"
    assert app_log.exists()
    log_text = app_log.read_text(encoding="utf-8")
    assert "request_trace" in log_text
    assert f"/tasks/{task_id}/logs" in log_text


def test_async_task_falls_back_when_llm_generation_fails(tmp_path: Path, monkeypatch) -> None:
    def fail_plan(self, *, system_prompt: str, user_prompt: str):
        raise RuntimeError("planner llm down")

    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", fail_plan)
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()

    response = client.post("/tasks/async", json={"domain": "知识工程", "subdomains": ["计划失败"]})

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["task_status"] == "running"
    final = payload
    for _ in range(40):
        final = client.get(f"/tasks/{payload['task_id']}").get_json()
        if final.get("task_status") != "running":
            break
        time.sleep(0.05)
    assert final["task_status"] in {"verified", "repair_required", "research_required"}


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


def test_task_logs_do_not_backfill_duplicate_llm_events(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    service = TaskService(config)
    context = service._context_builder.build({"domain": "知识工程", "subdomains": ["日志去重"]})
    state = service._create_initial_state(context, audit_source="api_async")
    task_id = state["task_id"]
    payload = service._serialize_state(state)
    payload["execution_log"] = [
        {
            "agent": "LLM",
            "event": "llm_call_started",
            "timestamp": "2026-04-28T17:13:03+09:00",
            "node": "OpenAICompatibleClient",
            "details": {
                "request_id": "req-1",
                "operation": "generation.chat_json",
                "status": "started",
                "attempt": 1,
                "max_attempts": 1,
            },
        }
    ]
    service._state_store.save(task_id, payload)
    service._audit_logger.log(
        task_id,
        "llm_call_started",
        {
            "request_id": "req-1",
            "operation": "generation.chat_json",
            "status": "started",
            "attempt": 1,
            "max_attempts": 1,
        },
    )

    logs = service.get_task_logs(task_id)
    audit_file = config.audit_root / f"{task_id}.jsonl"

    assert logs is not None
    saved_events = [json.loads(line)["event"] for line in audit_file.read_text(encoding="utf-8").splitlines()]
    assert saved_events.count("llm_call_started") == 1


def test_task_logs_include_latest_runtime_snapshot(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    service = TaskService(config)
    context = service._context_builder.build({"domain": "知识工程", "subdomains": ["状态同步"]})
    state = service._create_initial_state(context, audit_source="api_async")
    task_id = state["task_id"]
    state["task_status"] = "running"
    state["current_step"] = "evaluating"
    state["current_action"] = "完整性评估已完成。"
    service._state_store.save(task_id, service._serialize_state(state))

    logs = service.get_task_logs(task_id)

    assert logs is not None
    assert logs["task_status"] == "running"
    assert logs["current_step"] == "evaluating"
    assert logs["current_action"] == "完整性评估已完成。"


def test_task_detail_refreshes_queue_snapshot_from_queue_file(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    service = TaskService(config)
    context = service._context_builder.build({"domain": "知识工程", "subdomains": ["队列状态"]})
    state = service._create_initial_state(context, audit_source="api_async")
    task_id = state["task_id"]
    queue_path = config.save_root / "知识工程" / "knowledge_task_queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps(
            {
                "domain": "知识工程",
                "queue_version": "v1",
                "generation_status": {
                    "total_files": 2,
                    "completed_files": 1,
                    "current_file": "module.md",
                    "last_saved_path": "save/知识工程/module.md",
                },
                "current_round": 1,
                "tasks": [{"task_id": "q1", "status": "running", "query_text": "状态显示"}],
                "round_summaries": [],
                "final_status": "generated",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state["task_queue_path"] = queue_path.as_posix()
    state["task_queue_snapshot"] = {"tasks": []}
    service._state_store.save(task_id, service._serialize_state(state))

    task = service.get_task(task_id)
    plan = service.get_task_plan(task_id)

    assert task is not None
    assert task["generation_progress"]["completed_files"] == 1
    assert task["task_queue_snapshot"]["tasks"][0]["status"] == "running"
    assert plan is not None
    assert plan["task_queue_snapshot"]["final_status"] == "generated"


def test_round_validation_creates_retry_tasks_instead_of_empty_loop(tmp_path: Path) -> None:
    service = TaskService(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    context = service._context_builder.build({"domain": "知识工程", "subdomains": ["流程控制"]})
    workflow = KnowledgeGraphWorkflow.__new__(KnowledgeGraphWorkflow)
    workflow._insight_engine = object()
    queue = {
        "current_round": 1,
        "tasks": [
            {
                "task_id": "q1",
                "task_type": "query",
                "target_file_path": "save/知识工程/a.md",
                "target_section": "证据与来源",
                "claim_or_gap": "缺少依据",
                "query_text": "知识工程 权威资料",
                "expected_evidence": ["权威来源"],
                "status": "insufficient",
                "attempts": 1,
                "round_number": 1,
                "citations": [],
            }
        ],
    }

    validation = workflow._validate_queue_round(context, queue, max_rounds=3)

    assert validation.is_complete is False
    assert validation.new_tasks
    assert validation.new_tasks[0]["task_id"] == "q1-r2"
    assert validation.new_tasks[0]["round_number"] == 2
    assert validation.new_tasks[0]["status"] == "pending"


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

    assert resume_before_confirmation.status_code in {200, 400}
    assert updated.status_code in {200, 400}
    assert deleted.status_code in {200, 400}


def test_plan_item_patch_is_disabled_in_direct_execution_flow(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()
    started = client.post("/tasks/async", json={"domain": "知识工程", "subdomains": ["计划同步"]}).get_json()
    task_id = started["task_id"]

    updated = client.patch(
        f"/tasks/{task_id}/plan/items/MediaEngine/M-S1",
        json={
            "title": "人工修正社交计划",
            "query_or_action": "knowledge engineering manually revised social query",
        },
    )

    assert updated.status_code == 400


def test_plan_item_delete_is_disabled_in_direct_execution_flow(tmp_path: Path) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    client = app.test_client()
    started = client.post("/tasks/async", json={"domain": "知识工程", "subdomains": ["计划删除同步"]}).get_json()
    task_id = started["task_id"]

    deleted = client.delete(f"/tasks/{task_id}/plan/items/QueryEngine/Q1")

    assert deleted.status_code == 400


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
    assert response.get_json()["error"] == "`domain` or `message` is required."


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
