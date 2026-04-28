from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from knowledgeforge.config import AppConfig
from knowledgeforge.services.task_service import TaskService


def create_app(config: AppConfig | None = None) -> Flask:
    web_root = Path(__file__).resolve().parents[1] / "web"
    app = Flask(
        __name__,
        template_folder=str(web_root / "templates"),
        static_folder=str(web_root / "static"),
        static_url_path="/static",
    )
    service = TaskService(config or AppConfig.from_env())

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/config/status")
    def config_status():
        return jsonify(service.get_config_status()), 200

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

    @app.post("/tasks/<task_id>/report")
    def generate_report(task_id: str):
        report = service.generate_report(task_id)
        if report is None:
            return jsonify({"error": "frozen version not found"}), 404
        return jsonify(report), 200

    return app
