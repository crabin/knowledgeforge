from __future__ import annotations

from abc import ABC, abstractmethod

from knowledgeforge.server.models import EnginePlan, EngineRunResult, RequestContext


class BaseEngine(ABC):
    name: str

    @abstractmethod
    def plan(self, context: RequestContext, round_number: int) -> EnginePlan:
        raise NotImplementedError

    @abstractmethod
    def run(
        self,
        context: RequestContext,
        round_number: int,
        approved_plan: EnginePlan | None = None,
    ) -> EngineRunResult:
        raise NotImplementedError
