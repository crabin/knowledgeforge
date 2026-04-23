from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from typing import Any

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.config import AppConfig
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.intake.context_builder import ContextBuilder
from knowledgeforge.models import AgentMessage
from knowledgeforge.orchestrator.graph import KnowledgeGraphWorkflow
from knowledgeforge.orchestrator.state import WorkflowState
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter


class TaskService:
    def __init__(self, config: AppConfig) -> None:
        self._context_builder = ContextBuilder()
        self._workflow = KnowledgeGraphWorkflow(
            insight_engine=InsightEngine(),
            query_engine=QueryEngine(),
            media_engine=MediaEngine(),
            evaluator=CompletenessEvaluator(),
            writer=MarkdownKnowledgeWriter(config),
        )
        self._tasks: dict[str, WorkflowState] = {}

    def run_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_context = self._context_builder.build(payload)
        task_id = uuid.uuid4().hex
        initial_state: WorkflowState = {
            "task_id": task_id,
            "request_context": request_context,
            "messages": [
                AgentMessage(
                    role="user",
                    content=f"为领域 {request_context.domain} 启动知识沉淀任务。",
                    metadata={"source": "api"},
                )
            ],
            "round_number": 1,
            "task_status": "created",
        }
        final_state = self._workflow.run(initial_state)
        self._tasks[task_id] = final_state
        return self._serialize_state(final_state)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        state = self._tasks.get(task_id)
        if state is None:
            return None
        return self._serialize_state(state)

    def _serialize_state(self, state: WorkflowState) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in state.items():
            payload[key] = self._serialize_value(value)
        return payload

    def _serialize_value(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize_value(item) for key, item in value.items()}
        return value
