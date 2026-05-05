from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time

import json as _json

from flask import Flask, Response, g, jsonify, render_template, request, stream_with_context

from knowledgeforge.config import AppConfig
from knowledgeforge.services.task_service import TaskService


def create_app(config: AppConfig | None = None) -> Flask:
    active_config = config or AppConfig.from_env()
    web_root = Path(__file__).resolve().parents[1] / "web"
    app = Flask(
        __name__,
        template_folder=str(web_root / "templates"),
        static_folder=str(web_root / "static"),
        static_url_path="/static",
    )
    _configure_application_logger(app, active_config)
    service = TaskService(active_config)
    app.config["TASK_SERVICE"] = service

    @app.before_request
    def _start_request_timer() -> None:
        g.request_started_at = time.perf_counter()

    @app.after_request
    def _log_request_response(response):
        duration_ms = round((time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())) * 1000, 2)
        details = {
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        }
        task_id = request.view_args.get("task_id") if request.view_args else None
        if task_id:
            task = service.get_task(task_id)
            if task:
                generation = task.get("generation_progress", {}) or {}
                details.update(
                    {
                        "task_id": task_id,
                        "task_status": task.get("task_status", ""),
                        "current_step": task.get("current_step", ""),
                        "current_action": task.get("current_action", ""),
                        "generation_progress": generation,
                    }
                )
        if request.path.endswith("/logs") and task_id:
            logs_payload = service.get_task_logs(task_id)
            if logs_payload:
                queue_summary = logs_payload.get("queue_summary", {}) or {}
                counts = queue_summary.get("counts", {}) or {}
                llm_activity = logs_payload.get("llm_activity", {}) or {}
                latest_llm = (llm_activity.get("latest_event") or {}).get("details", {}) or {}
                details.update(
                    {
                        "log_events": logs_payload.get("log_summary", {}).get("total_events", 0),
                        "queue_round": queue_summary.get("current_round", 1),
                        "queue_counts": counts,
                        "latest_llm_operation": latest_llm.get("operation", ""),
                        "latest_llm_status": latest_llm.get("status", ""),
                        "latest_llm_attempt": latest_llm.get("attempt", ""),
                    }
                )
        if request.method == "GET" and task_id and not request.path.endswith("/logs"):
            app.logger.debug("request_trace %s", details)
        else:
            app.logger.info("request_trace %s", details)
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/config/status")
    def config_status():
        return jsonify(service.get_config_status()), 200

    @app.post("/system/initialize")
    def initialize_system():
        try:
            result = service.initialize_system()
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result), 200

    @app.get("/tasks")
    def list_tasks():
        return jsonify(service.list_tasks()), 200

    @app.post("/tasks")
    def run_task():
        payload = request.get_json(silent=True) or {}
        try:
            result = service.run_task(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result), 201

    @app.post("/tasks/async")
    def start_task():
        payload = request.get_json(silent=True) or {}
        try:
            result = service.start_task(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result), 202

    @app.post("/intake/sessions")
    def create_intake_session():
        payload = request.get_json(silent=True) or {}
        try:
            result = service.create_intake_session(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result), 201

    @app.post("/intake/sessions/<session_id>/messages")
    def append_intake_message(session_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            result = service.append_intake_message(session_id, payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "intake session not found"}), 404
        return jsonify(result), 200

    @app.post("/intake/sessions/<session_id>/confirm")
    def confirm_intake_session(session_id: str):
        try:
            result = service.confirm_intake_session(session_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "intake session not found"}), 404
        return jsonify(result), 201

    @app.get("/tasks/<task_id>")
    def get_task(task_id: str):
        task = service.get_task(task_id)
        if task is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task), 200

    @app.patch("/tasks/<task_id>")
    def update_task(task_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            task = service.update_task(task_id, payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if task is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task), 200

    @app.delete("/tasks/<task_id>")
    def delete_task(task_id: str):
        try:
            result = service.delete_task(task_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(result), 200

    @app.post("/tasks/<task_id>/resume")
    def resume_task(task_id: str):
        try:
            task = service.resume_task(task_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if task is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task), 200

    @app.get("/tasks/<task_id>/plan")
    def get_task_plan(task_id: str):
        plan = service.get_task_plan(task_id)
        if plan is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(plan), 200

    @app.patch("/tasks/<task_id>/plan/items/<agent_name>/<plan_item_id>")
    def update_plan_item(task_id: str, agent_name: str, plan_item_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            result = service.update_plan_item(task_id, agent_name, plan_item_id, payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(result), 200

    @app.delete("/tasks/<task_id>/plan/items/<agent_name>/<plan_item_id>")
    def delete_plan_item(task_id: str, agent_name: str, plan_item_id: str):
        try:
            result = service.delete_plan_item(task_id, agent_name, plan_item_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(result), 200

    @app.post("/tasks/<task_id>/plan/confirm")
    def confirm_task_plan(task_id: str):
        try:
            task = service.confirm_task_plan(task_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if task is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task), 202

    @app.get("/tasks/<task_id>/frozen")
    def get_frozen(task_id: str):
        frozen = service.get_frozen_version(task_id)
        if frozen is None:
            return jsonify({"error": "frozen version not found"}), 404
        return jsonify(frozen), 200

    @app.get("/tasks/<task_id>/logs")
    def get_task_logs(task_id: str):
        logs = service.get_task_logs(task_id)
        if logs is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(logs), 200

    @app.get("/tasks/<task_id>/graph")
    def get_task_graph(task_id: str):
        graph = service.get_task_graph_snapshot(task_id)
        if graph is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(graph), 200

    @app.get("/tasks/<task_id>/graph/issues")
    def inspect_task_graph_issues(task_id: str):
        try:
            result = service.inspect_graph_issues(task_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(result), 200

    @app.post("/tasks/<task_id>/graph/issues/delete")
    def delete_task_graph_issue(task_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            result = service.delete_graph_issue_node(task_id, payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(result), 200

    @app.post("/tasks/<task_id>/graph/issues/link")
    def link_task_graph_issue(task_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            result = service.link_graph_issue_node(task_id, payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(result), 200

    @app.post("/tasks/<task_id>/graph/nodes/expand")
    def expand_task_graph_node(task_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            result = service.expand_graph_node(task_id, payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(result), 200

    _TERMINAL_STATUSES = frozenset([
        "graph_ready", "verified", "research_required", "repair_required",
        "supplement_required", "max_rounds_reached", "failed", "plan_failed",
    ])

    @app.get("/tasks/<task_id>/stream")
    def stream_task(task_id: str):
        def generate():
            last_updated_at = None
            while True:
                task = service.get_task(task_id)
                if task is None:
                    yield f"data: {_json.dumps({'error': 'task not found'})}\n\n"
                    return
                updated_at = task.get("updated_at", "")
                if updated_at != last_updated_at:
                    last_updated_at = updated_at
                    logs = service.get_task_logs(task_id) or {}
                    payload = {**task, **logs}
                    yield f"data: {_json.dumps(payload, default=str)}\n\n"
                    if task.get("task_status") in _TERMINAL_STATUSES and task.get("finished_at"):
                        yield "event: done\ndata: {}\n\n"
                        return
                time.sleep(0.25)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/tasks/<task_id>/report")
    def generate_report(task_id: str):
        report = service.generate_report(task_id)
        if report is None:
            return jsonify({"error": "frozen version not found"}), 404
        return jsonify(report), 200

    @app.post("/tasks/<task_id>/evidence/fill")
    def fill_evidence(task_id: str):
        try:
            task = service.start_evidence_fill(task_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if task is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task), 202 if task.get("task_status") == "running" else 200

    @app.post("/tasks/<task_id>/documents/complete")
    def complete_documents(task_id: str):
        try:
            task = service.complete_documents(task_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if task is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task), 200

    return app


def _configure_application_logger(app: Flask, config: AppConfig) -> None:
    log_root = config.app_log_root
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "knowledgeforge-server.log"
    handler_id = f"knowledgeforge-server::{log_path.as_posix()}"
    if any(getattr(handler, "name", "") == handler_id for handler in app.logger.handlers):
        return
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.set_name(handler_id)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(handler)
