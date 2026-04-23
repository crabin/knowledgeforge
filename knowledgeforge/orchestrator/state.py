from __future__ import annotations

from typing import TypedDict

from knowledgeforge.models import (
    AgentMessage,
    CompletenessResult,
    DocumentArtifact,
    EngineRunResult,
    PostStorageResult,
    RequestContext,
)


class WorkflowState(TypedDict, total=False):
    task_id: str
    request_context: RequestContext
    messages: list[AgentMessage]
    round_number: int
    max_rounds: int
    agent_outputs: dict[str, EngineRunResult]
    completeness: CompletenessResult
    document_artifact: DocumentArtifact
    post_storage_result: PostStorageResult
    task_status: str
