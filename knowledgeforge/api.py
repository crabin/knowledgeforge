from __future__ import annotations

from flask import Flask, jsonify, request

from knowledgeforge.config import AppConfig
from knowledgeforge.services.task_service import TaskService


def create_app(config: AppConfig | None = None) -> Flask:
    app = Flask(__name__)
    service = TaskService(config or AppConfig.from_env())

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/config/status")
    def config_status():
        return jsonify(service.get_config_status()), 200

    @app.post("/tasks")
    def run_task():
        payload = request.get_json(silent=True) or {}
        try:
            result = service.run_task(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result), 201

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

    @app.post("/tasks/<task_id>/resume")
    def resume_task(task_id: str):
        task = service.resume_task(task_id)
        if task is None:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task), 200

    @app.get("/tasks/<task_id>/frozen")
    def get_frozen(task_id: str):
        frozen = service.get_frozen_version(task_id)
        if frozen is None:
            return jsonify({"error": "frozen version not found"}), 404
        return jsonify(frozen), 200

    @app.post("/tasks/<task_id>/report")
    def generate_report(task_id: str):
        report = service.generate_report(task_id)
        if report is None:
            return jsonify({"error": "frozen version not found"}), 404
        return jsonify(report), 200

    return app
