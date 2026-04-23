from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledgeforge.utils.paths import ensure_directory
from knowledgeforge.utils.time import now_iso


class AuditLogger:
    def __init__(self, root: Path) -> None:
        self._root = root
        ensure_directory(self._root)

    def log(self, task_id: str, event: str, details: dict[str, Any]) -> None:
        ensure_directory(self._root)
        audit_path = self._root / f"{task_id}.jsonl"
        entry = {
            "task_id": task_id,
            "event": event,
            "timestamp": now_iso(),
            "details": details,
        }
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
