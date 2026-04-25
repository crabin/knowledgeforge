from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from agent.QueryEngine.state.state import QueryEngineState
from knowledgeforge.utils.time import now_iso


QueryEventCallback = Callable[[str, dict[str, Any]], None]


class BaseQueryNode(ABC):
    def __init__(self, *, event_callback: QueryEventCallback | None = None) -> None:
        self._event_callback = event_callback

    @abstractmethod
    def run(self, state: QueryEngineState, **kwargs) -> QueryEngineState:
        raise NotImplementedError

    def _record_event(self, state: QueryEngineState, event: str, details: dict[str, Any]) -> None:
        entry = {
            "event": event,
            "timestamp": now_iso(),
            "node": self.__class__.__name__,
            "details": details,
        }
        state.execution_log.append(entry)
        task_id = getattr(state.request_context, "task_id", "")
        if task_id and self._event_callback is not None:
            self._event_callback(task_id, entry)
