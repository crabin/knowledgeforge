from __future__ import annotations

from typing import TypedDict

from knowledgeforge.models import (
    AgentMessage,
    CompletenessResult,
    DocumentArtifact,
    EnginePlan,
    EngineRunResult,
    PostStorageResult,
    RequestContext,
    WorkflowStepEvent,
)


class WorkflowState(TypedDict, total=False):
    task_id: str
    request_context: RequestContext
    messages: list[AgentMessage]
    round_number: int
    max_rounds: int
    agent_plans: dict[str, EnginePlan]
    plan_document_paths: dict[str, str]
    workflow_events: list[WorkflowStepEvent]
    current_step: str
    current_action: str
    plan_approved_at: str
    agent_outputs: dict[str, EngineRunResult]
    completeness: CompletenessResult
    document_artifact: DocumentArtifact
    post_storage_result: PostStorageResult
    task_status: str
