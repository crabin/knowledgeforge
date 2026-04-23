from __future__ import annotations

from abc import ABC, abstractmethod

from agent.QueryEngine.state.state import QueryEngineState


class BaseQueryNode(ABC):
    @abstractmethod
    def run(self, state: QueryEngineState, **kwargs) -> QueryEngineState:
        raise NotImplementedError
