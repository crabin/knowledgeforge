from __future__ import annotations

from abc import ABC, abstractmethod

from knowledgeforge.models import EngineRunResult, RequestContext


class BaseEngine(ABC):
    name: str

    @abstractmethod
    def run(self, context: RequestContext, round_number: int) -> EngineRunResult:
        raise NotImplementedError
