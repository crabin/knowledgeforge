from __future__ import annotations

from typing import TypedDict

from knowledgeforge.models import (
    AgentMessage,
    CompletenessResult,
    DocumentArtifact,
    EngineRunResult,
    RequestContext,
)


class WorkflowState(TypedDict, total=False):
    task_id: str
    request_context: RequestContext
    messages: list[AgentMessage]
    round_number: int
    agent_outputs: dict[str, EngineRunResult]
    completeness: CompletenessResult
    document_artifact: DocumentArtifact
    task_status: str
