from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledgeforge.utils.paths import ensure_directory


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
