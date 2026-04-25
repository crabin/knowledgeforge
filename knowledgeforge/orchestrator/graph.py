from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.models import AgentMessage, WorkflowStepEvent
from knowledgeforge.orchestrator.state import WorkflowState
from knowledgeforge.postprocess.pipeline import PostStoragePipeline
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.time import now_iso


class KnowledgeGraphWorkflow:
    def __init__(
        self,
        insight_engine: InsightEngine,
        query_engine: QueryEngine,
        media_engine: MediaEngine,
        evaluator: CompletenessEvaluator,
        writer: MarkdownKnowledgeWriter,
        post_storage_pipeline: PostStoragePipeline,
        workflow_event_callback: Callable[[str, WorkflowStepEvent], None] | None = None,
    ) -> None:
        self._insight_engine = insight_engine
        self._query_engine = query_engine
        self._media_engine = media_engine
        self._evaluator = evaluator
        self._writer = writer
        self._post_storage_pipeline = post_storage_pipeline
        self._workflow_event_callback = workflow_event_callback
        self._graph = self._build_graph()

    def run(self, initial_state: WorkflowState) -> WorkflowState:
        return self._graph.invoke(initial_state)

    def generate_plans(self, state: WorkflowState) -> WorkflowState:
        context = state["request_context"]
        round_number = state.get("round_number", 1)
        self._append_workflow_event(state, "planning", "三路计划生成", "active")
        plans = {}
        for name, engine in (
            ("InsightEngine", self._insight_engine),
            ("QueryEngine", self._query_engine),
            ("MediaEngine", self._media_engine),
        ):
            self._append_workflow_event(
                state,
                "planning",
                f"{name} 计划生成中",
                "active",
                {"agent": name},
            )
            try:
                plans[name] = engine.plan(context, round_number)
            except Exception as exc:
                raise RuntimeError(f"{name} plan generation failed: {exc}") from exc
        state["agent_plans"] = plans
        state["task_status"] = "awaiting_plan_confirmation"
        state["current_step"] = "awaiting_confirmation"
        state["current_action"] = "三路 Agent 执行计划已生成，等待用户确认。"
        self._append_workflow_event(state, "planning", "三路计划生成", "completed", {"agents": sorted(plans)})
        self._append_workflow_event(state, "awaiting_confirmation", "等待用户确认计划", "active")
        return state

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("collect_parallel", self._collect_parallel)
        graph.add_node("evaluate_completeness", self._evaluate_completeness)
        graph.add_node("write_markdown", self._write_markdown)
        graph.add_node("run_post_storage", self._run_post_storage)
        graph.add_node("finish_incomplete", self._finish_incomplete)
        graph.set_entry_point("collect_parallel")
        graph.add_edge("collect_parallel", "evaluate_completeness")
        graph.add_conditional_edges(
            "evaluate_completeness",
            self._route_after_evaluation,
            {
                "write_markdown": "write_markdown",
                "finish_incomplete": "finish_incomplete",
            },
        )
        graph.add_edge("write_markdown", "run_post_storage")
        graph.add_edge("run_post_storage", END)
        graph.add_edge("finish_incomplete", END)
        return graph.compile()

    def _collect_parallel(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        round_number = state.get("round_number", 1)
        plans = state.get("agent_plans", {})
        self._emit_workflow_event(state, "collecting", "三路并行采集", "active")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                "InsightEngine": executor.submit(self._insight_engine.run, context, round_number, plans.get("InsightEngine")),
                "QueryEngine": executor.submit(self._query_engine.run, context, round_number, plans.get("QueryEngine")),
                "MediaEngine": executor.submit(self._media_engine.run, context, round_number, plans.get("MediaEngine")),
            }
            outputs = {name: future.result() for name, future in futures.items()}

        messages = list(state.get("messages", []))
        messages.append(
            AgentMessage(
                role="assistant",
                content="三路采集已完成。",
                metadata={"timestamp": now_iso(), "round": round_number},
            )
        )
        return {
            "agent_outputs": outputs,
            "messages": messages,
            "task_status": "collected",
            "current_step": "collecting",
            "current_action": "三路采集已完成。",
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event("collecting", "三路并行采集", "completed"),
            ],
        }

    def _evaluate_completeness(self, state: WorkflowState) -> dict[str, Any]:
        self._emit_workflow_event(state, "evaluating", "完整性评估", "active")
        completeness = self._evaluator.evaluate(
            state["request_context"],
            state["agent_outputs"],
        )
        return {
            "completeness": completeness,
            "task_status": completeness.status,
            "current_step": "evaluating",
            "current_action": "完整性评估已完成。",
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event("evaluating", "完整性评估", "completed" if completeness.status == "pass" else "blocked"),
            ],
        }

    def _write_markdown(self, state: WorkflowState) -> dict[str, Any]:
        self._emit_workflow_event(state, "writing", "Markdown 落盘", "active")
        artifact = self._writer.write(
            context=state["request_context"],
            outputs=state["agent_outputs"],
            completeness=state["completeness"],
            round_number=state.get("round_number", 1),
        )
        return {
            "document_artifact": artifact,
            "task_status": "written",
            "current_step": "writing",
            "current_action": f"Markdown 文档已保存：{artifact.path}",
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event("writing", "Markdown 落盘", "completed", {"path": artifact.path}),
            ],
        }

    def _finish_incomplete(self, state: WorkflowState) -> dict[str, Any]:
        task_status = "max_rounds_reached" if state.get("round_number", 1) >= state.get("max_rounds", 1) else "supplement_required"
        return {
            "task_status": task_status,
            "current_step": "evaluating",
            "current_action": "完整性不足，等待补检索或恢复执行。",
        }

    def _run_post_storage(self, state: WorkflowState) -> dict[str, Any]:
        self._emit_workflow_event(state, "governing", "结构化治理与质量检测", "active")
        result = self._post_storage_pipeline.run(
            state["document_artifact"],
            state["request_context"],
            state["agent_outputs"],
        )
        if result.status == "passed":
            task_status = "verified"
        elif "research_flow" in result.remediation_flows:
            task_status = "research_required"
        else:
            task_status = "repair_required"
        return {
            "post_storage_result": result,
            "task_status": task_status,
            "current_step": "versioning" if task_status == "verified" else "governing",
            "current_action": "治理链路已完成。" if task_status == "verified" else f"治理链路需要回流：{task_status}",
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event("governing", "结构化治理与质量检测", "completed" if task_status == "verified" else "blocked"),
                self._make_workflow_event("versioning", "版本冻结与研报资格", "completed" if task_status == "verified" else "pending"),
            ],
        }

    def _emit_workflow_event(
        self,
        state: WorkflowState,
        step_id: str,
        label: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = self._make_workflow_event(step_id, label, status, details)
        if self._workflow_event_callback is not None:
            self._workflow_event_callback(state["task_id"], event)

    def _append_workflow_event(
        self,
        state: WorkflowState,
        step_id: str,
        label: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = self._make_workflow_event(step_id, label, status, details)
        state.setdefault("workflow_events", []).append(event)
        if self._workflow_event_callback is not None:
            self._workflow_event_callback(state["task_id"], event)

    @staticmethod
    def _make_workflow_event(
        step_id: str,
        label: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> WorkflowStepEvent:
        return WorkflowStepEvent(
            step_id=step_id,
            label=label,
            status=status,
            timestamp=now_iso(),
            details=details or {},
        )

    @staticmethod
    def _route_after_evaluation(state: WorkflowState) -> str:
        if state["completeness"].status == "pass":
            return "write_markdown"
        return "finish_incomplete"
