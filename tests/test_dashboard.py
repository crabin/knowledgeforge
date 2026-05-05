from __future__ import annotations

import json
from pathlib import Path

from knowledgeforge.server import create_app
from knowledgeforge.config import AppConfig
from knowledgeforge.graph.client import Neo4jGraphClient
from knowledgeforge.models import RequestContext


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
    assert "flow-track" in body
    assert "Neo4j 实时知识图谱" in body
    assert "neo4j-graph" in body
    assert "neo4j-auto-follow" in body
    assert "refresh-neo4j-graph" in body
    assert "检查知识点" in (Path(app.static_folder) / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "https://cdn.jsdelivr.net/npm/@antv/x6/dist/index.js" in body
    assert "https://unpkg.com/neovis.js@2.1.0/dist/neovis.js" in body
    assert "生成与查询队列状态" in body
    assert "plan-full-panel" in body
    assert "trace-grid" in body
    assert "图谱补全" in body
    assert "架构Review" in body
    assert "补全文档" in body
    assert "查询填充" in body
    assert "写入证据链接、来源类型和 claim 到 Neo4j。" in body
    assert "可选：补全文档前写入证据链接、来源类型和 claim。" not in body
    assert "governing-flow-detail" in body
    assert body.count('class="flow-step-detail"') == 10
    assert body.count('tabindex="0" aria-describedby=') == 10
    assert "触发条件" in body
    assert "执行步骤" in body
    assert "intent-flow-detail" in body
    assert "versioning-flow-detail" in body
    assert body.index('data-step-id="governing"') < body.index('data-step-id="evidence_link_recorded"')
    assert body.index('data-step-id="evidence_link_recorded"') < body.index('data-step-id="document_completion"')
    assert "data-task-action=\"complete-documents\"" in body
    assert "data-task-action=\"fill-evidence\"" in body
    assert "产出模式" not in body
    dashboard_js = (Path(app.static_folder) / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "repair_required: \"待系统修复\"" in dashboard_js
    assert "图谱上下文进度" in dashboard_js
    assert "图谱上下文已准备" in dashboard_js
    assert "[\"get\", \"queue\", \"logs\", \"resume\", \"fill-evidence\"]" in dashboard_js
    assert "LLM 生成进度" not in dashboard_js
    assert "文件已生成" not in dashboard_js
    assert "timing.is_running ? \"运行中\" : \"已完成\"" not in dashboard_js
    assert "function normalizeStructureReviewRounds" in dashboard_js
    assert "`${rounds.length}/2" in dashboard_js
    assert "function focusNeo4jNode" in dashboard_js
    assert "data-focus-node-id" in dashboard_js
    assert "getNeo4jIssueNodeIds" in dashboard_js
    assert "neo4jShowCompressedEdges: false" in dashboard_js
    assert "data-toggle-compressed-edges" in dashboard_js
    assert "buildNeo4jCompressedEdges" in dashboard_js
    assert "neo4j-inspector-edge${focusNodeId ? \" is-clickable\" : \"\"}" in dashboard_js
    assert "renderNeo4jInspectorRelationGroup(\"来自\", incoming, node, nodes)" in dashboard_js
    assert "renderNeo4jInspectorRelationGroup(\"指向\", outgoing, node, nodes)" in dashboard_js
    assert "调用与执行日志" in body
    assert "Token 实时消耗" in body
    assert "token-float collapsed" in body
    assert "token-float-toggle" in body
    assert "任务列表" in body
    assert "查看队列" in body
    assert "原始响应 JSON" in body
    assert "查看任务列表" in body
    assert "初始化系统" in body
    assert "/static/css/dashboard.css" in body
    assert "/static/js/dashboard.js" in body
    dashboard_css = (Path(app.static_folder) / "css" / "dashboard.css").read_text(encoding="utf-8")
    assert ".neo4j-issue-item.is-selected" in dashboard_css
    assert ".neo4j-graph {" in dashboard_css
    assert ".neo4j-inspector-edge.is-clickable" in dashboard_css
    assert ".neo4j-inspector-relation-group" in dashboard_css
    assert ".neo4j-toggle-edges" in dashboard_css


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


def test_system_initialize_clears_runtime_artifacts_only(tmp_path: Path, monkeypatch) -> None:
    config = AppConfig(
        save_root=tmp_path / "save",
        task_state_root=tmp_path / "runtime" / "tasks",
        intake_session_root=tmp_path / "runtime" / "intake",
        audit_root=tmp_path / "runtime" / "audit",
        frozen_root=tmp_path / "runtime" / "frozen",
    )
    app = create_app(config)
    runtime_files = [
        config.task_state_root / "task.json",
        config.intake_session_root / "session.json",
        config.audit_root / "task.jsonl",
        config.frozen_root / "frozen.json",
        config.save_root / "Deep Learning" / "README.md",
    ]
    for path in runtime_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime data", encoding="utf-8")
    system_file = tmp_path / "system-data.md"
    system_file.write_text("must stay", encoding="utf-8")

    def fake_clear_graph(self):
        return {"status": "cleared", "deleted_nodes": 2, "deleted_relationships": 1}

    monkeypatch.setattr(Neo4jGraphClient, "clear_knowledgeforge_graph", fake_clear_graph)
    client = app.test_client()

    response = client.post("/system/initialize")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "initialized"
    assert payload["scope"] == "runtime_artifacts_only"
    assert payload["neo4j"] == {"status": "cleared", "deleted_nodes": 2, "deleted_relationships": 1}
    assert "source_code" in payload["preserved"]
    assert system_file.read_text(encoding="utf-8") == "must stay"
    for root in [
        config.task_state_root,
        config.intake_session_root,
        config.audit_root,
        config.frozen_root,
        config.save_root,
    ]:
        assert root.exists()
        assert list(root.iterdir()) == []


def test_system_initialize_stops_running_tasks_before_clearing(tmp_path: Path, monkeypatch) -> None:
    task_root = tmp_path / "runtime" / "tasks"
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=task_root,
            intake_session_root=tmp_path / "runtime" / "intake",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    def fake_clear_graph(self):
        return {"status": "cleared", "deleted_nodes": 0, "deleted_relationships": 0}

    monkeypatch.setattr(Neo4jGraphClient, "clear_knowledgeforge_graph", fake_clear_graph)
    running_task = task_root / "task-running.json"
    running_task.write_text(
        json.dumps({"task_id": "task-running", "task_status": "running"}),
        encoding="utf-8",
    )
    client = app.test_client()

    response = client.post("/system/initialize")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "initialized"
    assert payload["stopped_task_ids"] == ["task-running"]
    assert not running_task.exists()


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


def test_graph_issue_endpoints_inspect_delete_and_link(tmp_path: Path, monkeypatch) -> None:
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
    calls: list[dict] = []

    def fake_inspect(self, *, domain: str, task_id: str):
        calls.append({"method": "inspect", "domain": domain, "task_id": task_id})
        return {
            "count": 1,
            "issues": [
                {
                    "graph_id": "4:noise",
                    "title": "工作流编排",
                    "type": "SubTopic",
                    "reason": "duplicate_non_structure_knowledge_point",
                    "matching_structure_node_id": "topic-workflow",
                    "matching_structure_title": "工作流编排",
                }
            ],
        }

    def fake_delete(self, *, domain: str, task_id: str, graph_id: str):
        calls.append({"method": "delete", "domain": domain, "task_id": task_id, "graph_id": graph_id})
        return {"status": "deleted", "graph_id": graph_id, "deleted_nodes": 1, "deleted_relationships": 2}

    def fake_link(self, *, domain: str, task_id: str, graph_id: str, target_node_id: str, relationship_type: str = "RELATED_TO"):
        calls.append(
            {
                "method": "link",
                "domain": domain,
                "task_id": task_id,
                "graph_id": graph_id,
                "target_node_id": target_node_id,
                "relationship_type": relationship_type,
            }
        )
        return {"status": "linked", "graph_id": graph_id, "target_node_id": target_node_id, "relationship_type": relationship_type}

    def fake_snapshot(self, *, domain: str, node_limit: int = 300, relationship_limit: int = 600):
        return {"nodes": [{"id": "topic-workflow", "title": "工作流编排", "type": "KnowledgeStructureNode", "properties": {"id": "topic-workflow"}}], "edges": []}

    monkeypatch.setattr(Neo4jGraphClient, "inspect_domain_graph_issues", fake_inspect)
    monkeypatch.setattr(Neo4jGraphClient, "delete_domain_graph_issue_node", fake_delete)
    monkeypatch.setattr(Neo4jGraphClient, "link_domain_graph_issue_node", fake_link)
    monkeypatch.setattr(Neo4jGraphClient, "snapshot_domain_graph", fake_snapshot)
    client = app.test_client()

    inspect_response = client.get("/tasks/task-graph/graph/issues")
    delete_response = client.post("/tasks/task-graph/graph/issues/delete", json={"graph_id": "4:noise"})
    link_response = client.post("/tasks/task-graph/graph/issues/link", json={"graph_id": "4:noise", "target_node_id": "topic-workflow"})

    assert inspect_response.status_code == 200
    assert inspect_response.get_json()["issues"][0]["matching_structure_node_id"] == "topic-workflow"
    assert delete_response.status_code == 200
    assert delete_response.get_json()["result"]["status"] == "deleted"
    assert delete_response.get_json()["graph_snapshot"]["nodes"][0]["id"] == "topic-workflow"
    assert link_response.status_code == 200
    assert link_response.get_json()["result"]["status"] == "linked"
    assert [call["method"] for call in calls] == ["inspect", "delete", "link"]


def test_expand_graph_leaf_node_adds_children_and_refreshes_snapshot(tmp_path: Path, monkeypatch) -> None:
    task_root = tmp_path / "runtime" / "tasks"
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=task_root,
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    structure_graph = {
        "root_node_id": "domain-root",
        "source_intent": "知识工程",
        "nodes": [
            {
                "node_id": "domain-root",
                "title": "知识工程 Overview",
                "node_type": "domain",
                "relative_path": "README.md",
                "doc_type": "summary",
                "owner_engine_candidates": ["InsightEngine"],
                "required_query_tasks": 0,
            },
            {
                "node_id": "leaf-1",
                "title": "状态持久化",
                "node_type": "article",
                "parent_node_id": "domain-root",
                "relative_path": "状态持久化/overview.md",
                "doc_type": "article",
                "owner_engine_candidates": ["QueryEngine"],
                "required_query_tasks": 1,
            },
        ],
        "edges": [{"from_node_id": "domain-root", "edge_type": "CONTAINS", "to_node_id": "leaf-1"}],
    }
    context = RequestContext(
        domain="知识工程",
        subdomains=["工作流编排"],
        time_window="",
        focus_points=["状态恢复"],
        constraints=[],
        initial_strategy=[],
        original_input="知识工程",
        normalized_domain="知识工程",
        confirmed=True,
        task_id="task-expand",
        structure_graph=structure_graph,
    )
    task_root.mkdir(parents=True, exist_ok=True)
    task_root.joinpath("task-expand.json").write_text(
        json.dumps(
            {
                "task_id": "task-expand",
                "request_context": context.to_dict(),
                "structure_graph": structure_graph,
                "task_status": "verified",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    synced_graphs: list[dict] = []

    def fake_sync(self, *, domain: str, task_id: str, structure_graph: dict):
        assert domain == "知识工程"
        assert task_id == "task-expand"
        synced_graphs.append(structure_graph)

    monkeypatch.setattr(Neo4jGraphClient, "sync_structure_graph", fake_sync)
    client = app.test_client()

    response = client.post("/tasks/task-expand/graph/nodes/expand", json={"node_id": "leaf-1"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "expanded"
    assert payload["node_id"] == "leaf-1"
    assert len(payload["added_nodes"]) == 3
    assert all(node["parent_node_id"] == "leaf-1" for node in payload["added_nodes"])
    assert payload["graph_snapshot"]["nodes"]
    assert payload["structure_graph_sync"]["status"] == "passed"
    assert synced_graphs
    stored = json.loads(task_root.joinpath("task-expand.json").read_text(encoding="utf-8"))
    assert stored["graph_event"]["event_type"] == "graph_node_expanded"
    assert any(node["parent_node_id"] in {"leaf-1", "leaf_1"} for node in stored["structure_graph"]["nodes"])


def test_expand_graph_node_rejects_existing_child_without_force(tmp_path: Path, monkeypatch) -> None:
    task_root = tmp_path / "runtime" / "tasks"
    app = create_app(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=task_root,
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    structure_graph = {
        "root_node_id": "domain-root",
        "nodes": [
            {"node_id": "domain-root", "title": "知识工程", "node_type": "domain", "relative_path": "README.md"},
            {"node_id": "parent", "title": "父节点", "node_type": "subtopic", "parent_node_id": "domain-root", "relative_path": "parent/README.md"},
            {"node_id": "child", "title": "子节点", "node_type": "article", "parent_node_id": "parent", "relative_path": "parent/child.md"},
        ],
        "edges": [
            {"from_node_id": "domain-root", "edge_type": "CONTAINS", "to_node_id": "parent"},
            {"from_node_id": "parent", "edge_type": "CONTAINS", "to_node_id": "child"},
        ],
    }
    context = RequestContext(
        domain="知识工程",
        subdomains=["工作流编排"],
        time_window="",
        focus_points=[],
        constraints=[],
        initial_strategy=[],
        confirmed=True,
        task_id="task-expand",
        structure_graph=structure_graph,
    )
    task_root.mkdir(parents=True, exist_ok=True)
    task_root.joinpath("task-expand.json").write_text(
        json.dumps({"task_id": "task-expand", "request_context": context.to_dict(), "structure_graph": structure_graph, "task_status": "verified"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(Neo4jGraphClient, "sync_structure_graph", lambda *args, **kwargs: None)
    client = app.test_client()

    response = client.post("/tasks/task-expand/graph/nodes/expand", json={"node_id": "parent"})

    assert response.status_code == 400
    assert "already has child branches" in response.get_json()["error"]


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
