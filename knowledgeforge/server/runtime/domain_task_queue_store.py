from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledgeforge.server.utils.paths import ensure_directory


class DomainTaskQueueStore:
    QUEUE_FILENAME = "knowledge_task_queue.json"
    QUEUE_VERSION = "v2-link-evidence"

    def queue_path(self, domain_dir: Path) -> Path:
        return domain_dir / self.QUEUE_FILENAME

    def initialize(self, *, domain: str, domain_dir: Path) -> dict[str, Any]:
        ensure_directory(domain_dir)
        payload = {
            "domain": domain,
            "queue_version": self.QUEUE_VERSION,
            "generation_status": {
                "total_files": 0,
                "completed_files": 0,
                "current_file": "",
                "last_saved_path": "",
            },
            "current_round": 1,
            "tasks": [],
            "round_summaries": [],
            "final_status": "pending",
        }
        self.save(domain_dir, payload)
        return payload

    def load(self, domain_dir: Path) -> dict[str, Any] | None:
        path = self.queue_path(domain_dir)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, domain_dir: Path, payload: dict[str, Any]) -> Path:
        path = self.queue_path(domain_dir)
        ensure_directory(path.parent)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
