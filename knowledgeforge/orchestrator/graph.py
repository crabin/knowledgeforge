from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.evaluation.supplement_decision import SupplementDecisionPlanner
from knowledgeforge.models import AgentMessage, EngineRunResult, SourceRecord, WorkflowStepEvent
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
        supplement_planner: SupplementDecisionPlanner,
        writer: MarkdownKnowledgeWriter,
        post_storage_pipeline: PostStoragePipeline,
        workflow_event_callback: Callable[[str, WorkflowStepEvent], None] | None = None,
        state_update_callback: Callable[[str, WorkflowState], None] | None = None,
    ) -> None:
        self._insight_engine = insight_engine
        self._query_engine = query_engine
        self._media_engine = media_engine
        self._evaluator = evaluator
        self._supplement_planner = supplement_planner
        self._writer = writer
        self._post_storage_pipeline = post_storage_pipeline
        self._workflow_event_callback = workflow_event_callback
        self._state_update_callback = state_update_callback
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
                self._append_workflow_event(
                    state,
                    "planning",
                    f"{name} 计划已生成",
                    "completed",
                    {"agent": name},
                )
            except Exception as exc:
                raise RuntimeError(f"{name} plan generation failed: {exc}") from exc
        state["agent_plans"] = plans
        plan_document_paths = self._writer.write_agent_plan_documents(
            context=context,
            plans=plans,
            round_number=round_number,
        )
        state["plan_document_paths"] = plan_document_paths
        state["task_status"] = "awaiting_plan_confirmation"
        state["current_step"] = "awaiting_confirmation"
        state["current_action"] = "三路 Agent 执行计划已生成并保存，等待用户确认。"
        self._append_workflow_event(
            state,
            "planning",
            "三路计划生成",
            "completed",
            {"agents": sorted(plans), "plan_document_paths": plan_document_paths},
        )
        self._append_workflow_event(state, "awaiting_confirmation", "等待用户确认计划", "active")
        return state

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("collect_parallel", self._collect_parallel)
        graph.add_node("evaluate_completeness", self._evaluate_completeness)
        graph.add_node("query_supplement", self._query_supplement)
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
                "query_supplement": "query_supplement",
                "finish_incomplete": "finish_incomplete",
            },
        )
        graph.add_edge("query_supplement", "collect_parallel")
        graph.add_edge("write_markdown", "run_post_storage")
        graph.add_edge("run_post_storage", END)
        graph.add_edge("finish_incomplete", END)
        return graph.compile()

    def _collect_parallel(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        round_number = state.get("round_number", 1)
        plans = state.get("agent_plans", {})
        query_plan = state.get("pending_query_supplement_plan") or plans.get("QueryEngine")
        self._emit_workflow_event(state, "collecting", "三路并行采集", "active")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                "InsightEngine": executor.submit(self._insight_engine.run, context, round_number, plans.get("InsightEngine")),
                "QueryEngine": executor.submit(self._query_engine.run, context, round_number, query_plan),
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
        updates = {
            "agent_outputs": outputs,
            "messages": messages,
            "task_status": "collected",
            "current_step": "collecting",
            "current_action": "三路采集已完成。",
            "pending_query_supplement_plan": None,
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event("collecting", "三路并行采集", "completed"),
            ],
        }
        self._commit_state(state, updates)
        return updates

    def _evaluate_completeness(self, state: WorkflowState) -> dict[str, Any]:
        self._emit_workflow_event(state, "evaluating", "完整性评估", "active")
        completeness = self._evaluator.evaluate(
            state["request_context"],
            state["agent_outputs"],
        )
        previous_decision = state.get("completeness").supplement_decision if state.get("completeness") else {}
        if previous_decision and not completeness.supplement_decision:
            completeness.supplement_decision = previous_decision
        updates = {
            "completeness": completeness,
            "task_status": completeness.status,
            "current_step": "evaluating",
            "current_action": "完整性评估已完成。",
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event("evaluating", "完整性评估", "completed" if completeness.status == "pass" else "blocked"),
            ],
        }
        self._commit_state(state, updates)
        return updates

    def _write_markdown(self, state: WorkflowState) -> dict[str, Any]:
        self._emit_workflow_event(state, "writing", "Markdown 落盘", "active")
        artifact = self._writer.write(
            context=state["request_context"],
            outputs=state["agent_outputs"],
            completeness=state["completeness"],
            round_number=state.get("round_number", 1),
        )
        updates = {
            "document_artifact": artifact,
            "task_status": "written",
            "current_step": "writing",
            "current_action": f"Markdown 文档已保存：{artifact.path}",
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event("writing", "Markdown 落盘", "completed", {"path": artifact.path}),
            ],
        }
        self._commit_state(state, updates)
        return updates

    def _finish_incomplete(self, state: WorkflowState) -> dict[str, Any]:
        task_status = "max_rounds_reached" if state.get("round_number", 1) >= state.get("max_rounds", 1) else "supplement_required"
        updates = {
            "task_status": task_status,
            "current_step": "evaluating",
            "current_action": "完整性不足，等待补检索或恢复执行。",
        }
        self._commit_state(state, updates)
        return updates

    def _query_supplement(self, state: WorkflowState) -> dict[str, Any]:
        next_round = state.get("round_number", 1) + 1
        self._emit_workflow_event(state, "supplementing", "补充决策与 QueryEngine 定向补采", "active")
        plan = self._supplement_planner.plan(
            context=state["request_context"],
            completeness=state["completeness"],
            outputs=state["agent_outputs"],
            round_number=next_round,
        )
        if not plan.plan_items:
            updates = {
                "task_status": "supplement_required",
                "current_step": "supplementing",
                "current_action": "补充决策未生成可执行 QueryEngine 计划。",
            }
            self._commit_state(state, updates)
            return updates

        agent_plans = dict(state.get("agent_plans", {}))
        agent_plans[f"QueryEngineSupplement_R{next_round}"] = plan
        messages = list(state.get("messages", []))
        messages.append(
            AgentMessage(
                role="assistant",
                content="已根据实时知识 index 生成补充决策，下一轮将重新执行三路采集。",
                metadata={
                    "timestamp": now_iso(),
                    "round": next_round,
                    "supplement_plan_items": len(plan.plan_items),
                },
            )
        )
        updates = {
            "agent_plans": agent_plans,
            "pending_query_supplement_plan": plan,
            "messages": messages,
            "round_number": next_round,
            "task_status": "running",
            "current_step": "supplementing",
            "current_action": f"已生成第 {next_round} 轮补检索计划，等待三路 Agent 重新采集。",
            "workflow_events": [
                *state.get("workflow_events", []),
                self._make_workflow_event(
                    "supplementing",
                    "补充决策与下一轮三路采集准备",
                    "completed",
                    {
                        "round": next_round,
                        "plan_item_count": len(plan.plan_items),
                        "queries": [item.query_or_action for item in plan.plan_items],
                    },
                ),
            ],
        }
        self._commit_state(state, updates)
        return updates

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
        updates = {
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
        self._commit_state(state, updates)
        return updates

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
        if state.get("round_number", 1) < state.get("max_rounds", 1):
            return "query_supplement"
        return "finish_incomplete"

    def _commit_state(self, state: WorkflowState, updates: dict[str, Any]) -> None:
        state.update(updates)
        if self._state_update_callback is not None:
            self._state_update_callback(state["task_id"], state)

    @staticmethod
    def _merge_query_outputs(
        previous: EngineRunResult | None,
        supplement: EngineRunResult,
    ) -> EngineRunResult:
        if previous is None:
            return supplement
        return EngineRunResult(
            agent_name=supplement.agent_name,
            summary=supplement.summary,
            key_points=KnowledgeGraphWorkflow._dedupe_strings([*previous.key_points, *supplement.key_points]),
            raw_material=[*previous.raw_material, "补充检索结果：", *supplement.raw_material],
            coverage_topics=KnowledgeGraphWorkflow._dedupe_strings(
                [*previous.coverage_topics, *supplement.coverage_topics]
            ),
            sources=KnowledgeGraphWorkflow._dedupe_sources([*previous.sources, *supplement.sources]),
            collected_at=supplement.collected_at,
            round_number=supplement.round_number,
            execution_log=[*previous.execution_log, *supplement.execution_log],
        )

    @staticmethod
    def _dedupe_strings(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen = set()
        for item in items:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _dedupe_sources(sources: list[SourceRecord]) -> list[SourceRecord]:
        deduped: list[SourceRecord] = []
        seen = set()
        for source in sources:
            key = source.url.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(source)
        return deduped
