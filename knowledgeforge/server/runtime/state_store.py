from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from knowledgeforge.server.utils.paths import ensure_directory


class TaskStateStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        ensure_directory(self._root)

    def save(self, task_id: str, payload: dict[str, Any]) -> None:
        ensure_directory(self._root)
        path = self._root / f"{task_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, task_id: str) -> dict[str, Any] | None:
        path = self._root / f"{task_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, task_id: str) -> bool:
        path = self._root / f"{task_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    def list(self) -> list[dict[str, Any]]:
        if not self._root.exists():
            return []
        tasks: list[dict[str, Any]] = []
        for path in self._root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            tasks.append(self._summarize(path, payload))
        return sorted(tasks, key=lambda item: item["updated_at"], reverse=True)

    @staticmethod
    def _summarize(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        request_context = payload.get("request_context") or {}
        post_storage = payload.get("post_storage_result") or {}
        version_record = post_storage.get("version_record") or {}
        document_artifact = payload.get("document_artifact") or {}
        updated_at = (
            version_record.get("updated_at")
            or version_record.get("frozen_at")
            or datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        )
        return {
            "task_id": payload.get("task_id", path.stem),
            "task_status": payload.get("task_status", "unknown"),
            "domain": request_context.get("domain", ""),
            "normalized_domain": request_context.get("normalized_domain", ""),
            "subdomains": request_context.get("subdomains", []),
            "round_number": payload.get("round_number", 1),
            "started_at": payload.get("started_at", ""),
            "finished_at": payload.get("finished_at", ""),
            "document_path": document_artifact.get("path", ""),
            "completion_mode": request_context.get("completion_mode", "framework"),
            "full_document_status": payload.get("full_document_status", ""),
            "version": version_record.get("version", ""),
            "report_eligible": version_record.get("report_eligible", False),
            "updated_at": updated_at,
        }
