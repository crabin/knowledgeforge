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
    completion_mode: str
    document_completion_status: str
    full_document_status: str
    workflow_events: list[WorkflowStepEvent]
    structure_graph: dict
    structure_graph_sync: dict
    structure_review_rounds: list[dict]
    structure_review_status: str
    structure_repair_log: list[dict]
    graph_snapshot: dict
    graph_event: dict
    file_update: dict
    current_step: str
    current_action: str
    started_at: str
    finished_at: str
    updated_at: str
    plan_approved_at: str
    agent_outputs: dict[str, EngineRunResult]
    pending_query_supplement_plan: EnginePlan
    completeness: CompletenessResult
    document_artifact: DocumentArtifact
    post_storage_result: PostStorageResult
    task_status: str
