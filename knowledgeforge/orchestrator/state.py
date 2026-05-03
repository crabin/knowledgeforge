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
    knowledge_file_states: list[dict]
    generation_progress: dict
    task_queue_path: str
    task_queue_snapshot: dict
    validation_round: int
    fill_progress: dict
    workflow_events: list[WorkflowStepEvent]
    structure_graph: dict
    graph_snapshot: dict
    graph_event: dict
    file_update: dict
    current_step: str
    current_action: str
    plan_approved_at: str
    agent_outputs: dict[str, EngineRunResult]
    pending_query_supplement_plan: EnginePlan
    completeness: CompletenessResult
    document_artifact: DocumentArtifact
    post_storage_result: PostStorageResult
    task_status: str
