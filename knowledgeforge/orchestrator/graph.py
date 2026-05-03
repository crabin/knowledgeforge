from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import yaml
from langgraph.graph import END, StateGraph

from knowledgeforge.agent.InsightEngine.agent import InsightEngine
from knowledgeforge.agent.MediaEngine.agent import MediaEngine
from knowledgeforge.agent.QueryEngine.agent import QueryEngine
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.evaluation.supplement_decision import SupplementDecisionPlanner
from knowledgeforge.models import (
    AgentMessage,
    CompletenessResult,
    DomainTaskQueueItem,
    EngineRunResult,
    RequestContext,
    RoundValidationResult,
    WorkflowStepEvent,
)
from knowledgeforge.orchestrator.state import WorkflowState
from knowledgeforge.postprocess.pipeline import PostStoragePipeline
from knowledgeforge.prompts.knowledge_file_generation import (
    PROMPT_PROFILE_VERSION,
    build_generation_system_prompt,
    build_prompt_spec,
    build_structure_graph_system_prompt,
    build_validation_system_prompt,
)
from knowledgeforge.runtime.domain_task_queue_store import DomainTaskQueueStore
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.file_contract import parse_contract_block, render_contract_block, replace_contract_block
from knowledgeforge.utils.paths import sanitize_path_segment
from knowledgeforge.utils.structure_graph import (
    build_fallback_structure_graph,
    derive_context_from_structure_graph,
    normalize_structure_graph_payload,
    structure_graph_summary,
)
from knowledgeforge.utils.time import now_iso


def _normalize_contract_items(items: Any) -> list[Any]:
    """保留 LLM 输出的结构：dict 原样保留，字符串去空白后保留，其他空值丢弃。"""
    if not isinstance(items, list):
        return []
    normalized: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            if item:
                normalized.append(item)
        elif isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append(text)
        elif item is not None:
            text = str(item).strip()
            if text:
                normalized.append(text)
    return normalized


def _render_contract_item(item: Any) -> str:
    """把 contract 条目（可能是 dict 或字符串）转换成 Markdown 列表里的人类可读文本。"""
    if isinstance(item, dict):
        for key in ("claim", "text", "description", "content", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                claim_id = item.get("claim_id") or item.get("id")
                section = item.get("section")
                prefix_parts = [str(p) for p in (claim_id, section) if p]
                prefix = f"[{' · '.join(prefix_parts)}] " if prefix_parts else ""
                return f"{prefix}{value.strip()}"
        return json.dumps(item, ensure_ascii=False)
    return str(item)


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
        generation_chat_client=None,
        workflow_event_callback=None,
        state_update_callback=None,
    ) -> None:
        self._insight_engine = insight_engine
        self._query_engine = query_engine
        self._media_engine = media_engine
        self._evaluator = evaluator
        self._supplement_planner = supplement_planner
        self._writer = writer
        self._post_storage_pipeline = post_storage_pipeline
        self._generation_chat_client = generation_chat_client
        self._workflow_event_callback = workflow_event_callback
        self._state_update_callback = state_update_callback
        self._queue_store = DomainTaskQueueStore()
        self._graph = self._build_graph()

    def run(self, initial_state: WorkflowState) -> WorkflowState:
        return self._graph.invoke(initial_state)

    def generate_plans(self, state: WorkflowState) -> WorkflowState:
        return state

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("generate_structure_graph", self._generate_structure_graph)
        graph.add_node("generate_files", self._generate_files)
        graph.add_node("run_query_queue", self._run_query_queue)
        graph.add_node("validate_round", self._validate_round)
        graph.add_node("fill_evidence", self._fill_evidence)
        graph.add_node("run_post_storage", self._run_post_storage)
        graph.set_entry_point("generate_structure_graph")
        graph.add_edge("generate_structure_graph", "generate_files")
        graph.add_edge("generate_files", "run_query_queue")
        graph.add_edge("run_query_queue", "validate_round")
        graph.add_conditional_edges(
            "validate_round",
            self._route_after_validation,
            {
                "run_query_queue": "run_query_queue",
                "fill_evidence": "fill_evidence",
            },
        )
        graph.add_edge("fill_evidence", "run_post_storage")
        graph.add_edge("run_post_storage", END)
        return graph.compile()

    def _generate_structure_graph(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        self._emit_workflow_event(state, "structure_graph_planning", "开始生成目录结构图谱", "active")
        chat_client = self._generation_chat_client or getattr(self._insight_engine, "_chat_client", None)
        payload: dict[str, Any] = {}
        if chat_client is not None:
            try:
                payload = chat_client.complete_json(
                    system_prompt=build_structure_graph_system_prompt(),
                    user_prompt=json.dumps(
                        {
                            "domain": context.domain,
                            "normalized_domain": context.normalized_domain,
                            "original_input": context.original_input,
                            "subdomains": context.subdomains,
                            "focus_points": context.focus_points,
                            "constraints": context.constraints,
                            "time_window": context.time_window,
                            "output_language": context.output_language,
                            "search_terms": context.search_terms,
                            "clarification_summary": context.clarification_summary,
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception as exc:
                logger.warning("Structure graph generation failed for %s: %s", context.domain, exc)
                payload = {}
        if payload:
            structure_graph = normalize_structure_graph_payload(
                payload=payload,
                domain=context.domain,
                subdomains=context.subdomains,
                focus_points=context.focus_points,
                source_intent=context.original_input or context.domain,
            )
        else:
            structure_graph = build_fallback_structure_graph(
                domain=context.domain,
                subdomains=context.subdomains,
                source_intent=context.original_input or context.domain,
            )
        derived_context = derive_context_from_structure_graph(graph=structure_graph, domain=context.domain)
        context.structure_graph = structure_graph.to_dict()
        self._initialize_structure_graph_status(context)
        context.structure_mode = str(derived_context["structure_mode"])
        context.knowledge_modules = derived_context["knowledge_modules"]
        context.core_topics = derived_context["core_topics"] or context.core_topics
        context.navigation_targets = derived_context["navigation_targets"]
        context.knowledge_blueprint = derived_context["knowledge_blueprint"]
        context.required_files = derived_context["required_files"]
        summary = structure_graph_summary(structure_graph)
        updates = {
            "request_context": context,
            "structure_graph": context.structure_graph,
            "structure_graph_sync": self._sync_structure_graph_for_generation(state["task_id"], context),
            "graph_snapshot": self._local_graph_snapshot(context),
            "graph_event": {
                "event_type": "structure_graph_initialized",
                "node_id": structure_graph.root_node_id,
                "status": "planned",
                "path": "",
                "timestamp": now_iso(),
            },
            "task_status": "running",
            "current_step": "structure_graph_ready",
            "current_action": f"目录结构图谱已生成：{summary['node_count']} 个节点，{summary['edge_count']} 条关系。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(state, "structure_graph_ready", "目录结构图谱已生成", "completed", summary)
        return updates

    def _generate_files(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        context.prompt_profile_version = PROMPT_PROFILE_VERSION
        if not context.knowledge_blueprint:
            structure_graph = build_fallback_structure_graph(
                domain=context.domain,
                subdomains=context.subdomains,
                source_intent=context.original_input or context.domain,
            )
            derived_context = derive_context_from_structure_graph(graph=structure_graph, domain=context.domain)
            context.structure_graph = structure_graph.to_dict()
            context.structure_mode = str(derived_context["structure_mode"])
            context.knowledge_modules = derived_context["knowledge_modules"]
            context.core_topics = derived_context["core_topics"] or context.core_topics
            context.navigation_targets = derived_context["navigation_targets"]
            context.knowledge_blueprint = derived_context["knowledge_blueprint"]
            context.required_files = derived_context["required_files"]
        domain_dir = self._domain_dir(context)
        queue = self._queue_store.initialize(domain=context.domain, domain_dir=domain_dir)
        context.generation_queue_path = self._queue_store.queue_path(domain_dir).as_posix()
        self._emit_workflow_event(state, "blueprint_ready", "知识文件蓝图已准备", "active")
        file_states = self._writer.materialize_knowledge_base(context=context, round_number=state.get("round_number", 1))
        total_files = len(context.knowledge_blueprint)
        generated_count = 0
        for blueprint in context.knowledge_blueprint:
            relative_path = str(blueprint.get("relative_path", "")).strip()
            if not relative_path:
                continue
            file_path = domain_dir / relative_path
            spec = build_prompt_spec(blueprint)
            self._emit_workflow_event(
                state,
                "llm_generating",
                f"开始生成文件：{relative_path}",
                "active",
                {
                    "event": "file_generation_started",
                    "file_path": file_path.as_posix(),
                    "relative_path": relative_path,
                    "completed_files": generated_count,
                    "total_files": total_files,
                    "current_file": relative_path,
                },
            )
            self._update_structure_node_status(
                state,
                context,
                blueprint,
                generation_state="generating",
                generated_path=file_path.as_posix(),
            )
            self._emit_workflow_event(
                state,
                "llm_generating",
                f"生成文件骨架：{relative_path}",
                "active",
                {"file_path": file_path.as_posix()},
            )
            queue["generation_status"] = {
                "total_files": total_files,
                "completed_files": generated_count,
                "current_file": relative_path,
                "last_saved_path": queue.get("generation_status", {}).get("last_saved_path", ""),
            }
            self._queue_store.save(domain_dir, queue)
            self._commit_queue_snapshot(
                state,
                domain_dir,
                queue,
                current_step="llm_generating",
                current_action=f"正在生成文件骨架：{relative_path}",
            )
            generated = self._generate_single_file(context, blueprint, spec, file_path)
            file_path.write_text(generated["markdown"], encoding="utf-8")
            query_tasks = self._extract_queue_tasks(generated["contract"], blueprint, file_path, queue.get("current_round", 1))
            graph_generation_sync = self._update_structure_node_status(
                state,
                context,
                blueprint,
                generation_state="evidence_pending" if query_tasks else "completed",
                generated_path=file_path.as_posix(),
                pending_task_count=len(query_tasks),
                completed_task_count=0,
            )
            queue["tasks"] = self._merge_queue_tasks(queue.get("tasks", []), query_tasks)
            generated_count += 1
            queue["generation_status"] = {
                "total_files": total_files,
                "completed_files": generated_count,
                "current_file": relative_path,
                "last_saved_path": file_path.as_posix(),
            }
            self._queue_store.save(domain_dir, queue)
            self._commit_queue_snapshot(
                state,
                domain_dir,
                queue,
                current_step="llm_generating",
                current_action=f"文件骨架已保存：{relative_path}",
                extra_updates={"latest_structure_node_sync": graph_generation_sync} if graph_generation_sync else None,
            )
            self._emit_workflow_event(
                state,
                "llm_generating",
                f"文件骨架已保存：{relative_path}",
                "completed",
                {
                    "event": "file_generation_completed",
                    "file_path": file_path.as_posix(),
                    "relative_path": relative_path,
                    "enqueued_tasks": len(query_tasks),
                    "completed_files": generated_count,
                    "total_files": total_files,
                    "current_file": relative_path,
                },
            )
        queue["final_status"] = "generated"
        queue_path = self._queue_store.save(domain_dir, queue)
        updates = {
            "knowledge_file_states": file_states,
            "generation_progress": queue["generation_status"],
            "task_queue_path": queue_path.as_posix(),
            "task_queue_snapshot": queue,
            "task_status": "running",
            "current_step": "llm_generating",
            "current_action": "文件骨架串行生成完成，准备进入查询队列。",
            "messages": [
                *state.get("messages", []),
                AgentMessage(role="assistant", content="文件骨架已串行生成，开始处理依据查询队列。"),
            ],
        }
        self._commit_state(state, updates)
        return updates

    def _sync_structure_graph_for_generation(self, task_id: str, context: RequestContext) -> dict[str, Any]:
        structure_graph = context.structure_graph or {}
        if not isinstance(structure_graph, dict) or not structure_graph.get("nodes"):
            return {"status": "skipped", "reason": "empty_structure_graph"}
        try:
            result = self._post_storage_pipeline.sync_structure_graph(
                domain=context.domain,
                task_id=task_id,
                structure_graph=structure_graph,
            )
        except Exception as exc:
            logger.warning("Structure graph Neo4j sync failed for %s: %s", context.domain, exc)
            return {"status": "failed", "error": str(exc)}
        if result is None:
            return {"status": "skipped", "reason": "graph_mapper_unavailable"}
        return result.to_dict()

    def _mark_structure_node_generated(
        self,
        task_id: str,
        context: RequestContext,
        blueprint: dict[str, Any],
        file_path: Path,
    ) -> dict[str, Any]:
        node_id = self._structure_node_id_for_blueprint(blueprint)
        if not node_id:
            return {"status": "skipped", "reason": "missing_structure_node_id", "path": file_path.as_posix()}
        try:
            result = self._post_storage_pipeline.mark_structure_node_generated(
                domain=context.domain,
                task_id=task_id,
                node_id=node_id,
                generated_path=file_path.as_posix(),
            )
        except Exception as exc:
            logger.warning("Structure node generation flag update failed for %s: %s", node_id, exc)
            return {"status": "failed", "node_id": node_id, "path": file_path.as_posix(), "error": str(exc)}
        if result is None:
            return {"status": "skipped", "reason": "graph_mapper_unavailable", "node_id": node_id, "path": file_path.as_posix()}
        return result.to_dict()

    def _update_structure_node_status(
        self,
        state: WorkflowState,
        context: RequestContext,
        blueprint: dict[str, Any],
        *,
        generation_state: str,
        generated_path: str = "",
        pending_task_count: int | None = None,
        completed_task_count: int | None = None,
    ) -> dict[str, Any]:
        node_id = self._structure_node_id_for_blueprint(blueprint)
        if not node_id:
            return {"status": "skipped", "reason": "missing_structure_node_id", "path": generated_path}
        return self._update_structure_node_status_by_id(
            state,
            context,
            node_id=node_id,
            generation_state=generation_state,
            generated_path=generated_path,
            pending_task_count=pending_task_count,
            completed_task_count=completed_task_count,
        )

    def _update_structure_node_status_for_task(
        self,
        state: WorkflowState,
        context: RequestContext,
        task: dict[str, Any],
        *,
        generation_state: str,
        pending_task_count: int | None = None,
        completed_task_count: int | None = None,
    ) -> dict[str, Any]:
        target_path = str(task.get("target_file_path", "")).strip()
        node_id = self._structure_node_id_for_file(context, target_path)
        if not node_id:
            return {"status": "skipped", "reason": "missing_structure_node_id", "path": target_path}
        return self._update_structure_node_status_by_id(
            state,
            context,
            node_id=node_id,
            generation_state=generation_state,
            generated_path=target_path,
            pending_task_count=pending_task_count,
            completed_task_count=completed_task_count,
        )

    def _update_structure_node_status_by_id(
        self,
        state: WorkflowState,
        context: RequestContext,
        *,
        node_id: str,
        generation_state: str,
        generated_path: str = "",
        pending_task_count: int | None = None,
        completed_task_count: int | None = None,
    ) -> dict[str, Any]:
        graph_sync = {"status": "skipped", "reason": "structure_graph_sync_not_available", "node_id": node_id, "path": generated_path}
        if (state.get("structure_graph_sync") or {}).get("status") == "passed":
            try:
                result = self._post_storage_pipeline.update_structure_node_status(
                    domain=context.domain,
                    task_id=state["task_id"],
                    node_id=node_id,
                    generation_state=generation_state,
                    generated_path=generated_path,
                    pending_task_count=pending_task_count,
                    completed_task_count=completed_task_count,
                )
                graph_sync = result.to_dict() if result is not None else graph_sync
            except Exception as exc:
                logger.warning("Structure node status update failed for %s: %s", node_id, exc)
                graph_sync = {"status": "failed", "node_id": node_id, "path": generated_path, "error": str(exc)}
        self._set_local_structure_node_status(
            context,
            node_id=node_id,
            generation_state=generation_state,
            generated_path=generated_path,
            pending_task_count=pending_task_count,
            completed_task_count=completed_task_count,
        )
        state["request_context"] = context
        state["structure_graph"] = context.structure_graph
        state["graph_snapshot"] = self._local_graph_snapshot(context)
        state["graph_event"] = {
            "event_type": "structure_node_status_changed",
            "node_id": node_id,
            "status": generation_state,
            "path": generated_path,
            "timestamp": now_iso(),
        }
        return graph_sync

    @staticmethod
    def _structure_node_id_for_blueprint(blueprint: dict[str, Any]) -> str:
        requirements = blueprint.get("completion_requirements", {})
        if isinstance(requirements, dict):
            return str(requirements.get("structure_node_id", "")).strip()
        return ""

    def _structure_node_id_for_file(self, context: RequestContext, file_path: str) -> str:
        if not file_path:
            return ""
        target = Path(file_path)
        domain_dir = self._domain_dir(context)
        try:
            relative = target.relative_to(domain_dir).as_posix()
        except ValueError:
            relative = target.as_posix()
            marker = f"{domain_dir.as_posix().rstrip('/')}/"
            if relative.startswith(marker):
                relative = relative[len(marker):]
        for blueprint in context.knowledge_blueprint:
            if str(blueprint.get("relative_path", "")).strip() == relative:
                return self._structure_node_id_for_blueprint(blueprint)
        graph = context.structure_graph or {}
        for node in graph.get("nodes", []) if isinstance(graph, dict) else []:
            if isinstance(node, dict) and str(node.get("relative_path", "")).strip() == relative:
                return str(node.get("node_id", "")).strip()
        return ""

    def _run_query_queue(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        domain_dir = self._domain_dir(context)
        queue = self._queue_store.load(domain_dir) or {}
        round_number = int(queue.get("current_round", 1))
        self._emit_workflow_event(state, "query_queue_running", f"第 {round_number} 轮查询队列执行", "active")
        outputs = dict(state.get("agent_outputs", {}))
        for index, task in enumerate(queue.get("tasks", [])):
            if str(task.get("round_number", 1)) != str(round_number):
                continue
            if str(task.get("status", "pending")) not in {"pending", "insufficient"}:
                continue
            queue["tasks"][index]["status"] = "running"
            queue["tasks"][index]["attempts"] = int(task.get("attempts", 0)) + 1
            running_node_sync = self._update_structure_node_status_for_task(
                state,
                context,
                queue["tasks"][index],
                generation_state="evidence_running",
            )
            self._queue_store.save(domain_dir, queue)
            self._commit_queue_snapshot(
                state,
                domain_dir,
                queue,
                current_step="query_queue_running",
                current_action=f"正在执行队列任务：{task.get('task_id', '')}",
                extra_updates={"latest_structure_node_sync": running_node_sync} if running_node_sync else None,
            )
            self._emit_workflow_event(
                state,
                "query_queue_running",
                f"执行队列任务：{task.get('task_id', '')}",
                "active",
                {"task_id": task.get("task_id", ""), "task_type": task.get("task_type", "")},
            )
            result = self._execute_queue_task(context, round_number, queue["tasks"][index])
            queue["tasks"][index].update(
                {
                    "status": result["status"],
                    "result_summary": result["result_summary"],
                    "citations": result["citations"],
                }
            )
            outputs[result["agent_name"]] = self._merge_engine_output(outputs.get(result["agent_name"]), result["engine_output"])
            self._writer.apply_output_artifacts(context, {result["agent_name"]: result["engine_output"]})
            file_update = self._build_file_update_from_task(queue["tasks"][index])
            self._emit_workflow_event(
                state,
                "evidence_realtime_write",
                f"证据已即时回写：{file_update.get('path', '')}",
                "completed" if result["status"] == "completed" else "blocked",
                file_update,
            )
            completed_count, pending_count = self._file_completion_counts(queue["tasks"][index])
            completed = result["status"] == "completed" and pending_count == 0
            completed_node_sync = self._update_structure_node_status_for_task(
                state,
                context,
                queue["tasks"][index],
                generation_state="completed" if completed else ("evidence_pending" if result["status"] == "completed" else "failed"),
                pending_task_count=pending_count,
                completed_task_count=completed_count,
            )
            self._queue_store.save(domain_dir, queue)
            self._commit_queue_snapshot(
                state,
                domain_dir,
                queue,
                current_step="query_queue_running",
                current_action=f"队列任务已完成：{task.get('task_id', '')}",
                extra_updates={
                    "agent_outputs": outputs,
                    "file_update": file_update,
                    **({"latest_structure_node_sync": completed_node_sync} if completed_node_sync else {}),
                },
            )
            self._emit_workflow_event(
                state,
                "query_queue_running",
                f"队列任务已完成：{task.get('task_id', '')}",
                "completed" if result["status"] == "completed" else "blocked",
                {"task_id": task.get("task_id", ""), "task_type": task.get("task_type", ""), "status": result["status"]},
            )
        updates = {
            "agent_outputs": outputs,
            "task_queue_snapshot": queue,
            "task_status": "running",
            "current_step": "query_queue_running",
            "current_action": f"第 {round_number} 轮查询队列执行完成。",
        }
        self._commit_state(state, updates)
        return updates

    def _validate_round(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        domain_dir = self._domain_dir(context)
        queue = self._queue_store.load(domain_dir) or {}
        round_number = int(queue.get("current_round", 1))
        self._emit_workflow_event(state, "round_validation", f"第 {round_number} 轮完整性验证", "active")
        validation = self._validate_queue_round(context, queue, state.get("max_rounds", 3))
        queue.setdefault("round_summaries", []).append(
            {
                "round_number": round_number,
                "is_complete": validation.is_complete,
                "reasoning": validation.reasoning,
                "missing_evidence": validation.missing_evidence,
            }
        )
        for item in validation.file_status_updates:
            self._apply_file_status_update(item)
        if validation.is_complete:
            queue["final_status"] = "ready_for_fill"
            completeness = CompletenessResult(
                status="pass",
                reasons=["文件级查询队列验证通过。"],
                missing_topics=[],
                supplement_queries=[],
                failure_categories=[],
            )
        else:
            queue["current_round"] = round_number + 1
            queue["final_status"] = "needs_more_evidence"
            queue["tasks"] = self._merge_queue_tasks(queue.get("tasks", []), validation.new_tasks)
            completeness = CompletenessResult(
                status="supplement_required",
                reasons=["文件级查询队列仍有证据缺口。"],
                missing_topics=[],
                supplement_queries=[str(item.get("query_text", "")) for item in validation.new_tasks if str(item.get("query_text", "")).strip()],
                failure_categories=["file_completion_incomplete"],
            )
        self._queue_store.save(domain_dir, queue)
        updates = {
            "task_queue_snapshot": queue,
            "validation_round": round_number,
            "completeness": completeness,
            "task_status": "running" if validation.is_complete else "supplementing",
            "current_step": "round_validation",
            "current_action": validation.reasoning,
        }
        self._commit_state(state, updates)
        return updates

    def _fill_evidence(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        queue = state.get("task_queue_snapshot", {})
        self._emit_workflow_event(state, "evidence_filling", "开始统一回填证据到知识文件", "active")
        outputs = dict(state.get("agent_outputs", {}))
        outputs["QueueFillPass"] = EngineRunResult(
            agent_name="QueueFillPass",
            summary="统一回填队列中的来源与结论。",
            key_points=[],
            raw_material=[],
            coverage_topics=context.subdomains,
            sources=[],
            collected_at=now_iso(),
            round_number=state.get("round_number", 1),
            artifacts=self._build_fill_artifacts(queue.get("tasks", [])),
        )
        self._writer.apply_output_artifacts(context, outputs)
        artifact = self._writer.write(
            context=context,
            outputs=outputs,
            completeness=state.get("completeness")
            or CompletenessResult(status="pass", reasons=["文件级回填完成。"], missing_topics=[], supplement_queries=[]),
            round_number=state.get("round_number", 1),
        )
        updates = {
            "agent_outputs": outputs,
            "document_artifact": artifact,
            "fill_progress": {
                "completed_tasks": len([task for task in queue.get("tasks", []) if str(task.get("status", "")) == "completed"]),
                "total_tasks": len(queue.get("tasks", [])),
            },
            "task_status": "running",
            "current_step": "evidence_filling",
            "current_action": "所有已验证依据已统一回填到知识文件。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(state, "evidence_filling", "证据回填完成", "completed")
        return updates

    def _run_post_storage(self, state: WorkflowState) -> dict[str, Any]:
        self._emit_workflow_event(state, "governing", "结构化治理与质量检测", "active")
        result = self._post_storage_pipeline.run(
            state["document_artifact"],
            state["request_context"],
            state.get("agent_outputs", {}),
        )
        task_status = self._task_status_from_post_storage(result)
        updates = {
            "post_storage_result": result,
            "task_status": task_status,
            "current_step": "versioning" if task_status == "verified" else "governing",
            "current_action": "治理链路已完成。" if task_status == "verified" else "治理链路需要修复。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(state, "governing", "结构化治理与质量检测", "completed" if task_status == "verified" else "blocked")
        self._emit_workflow_event(state, "versioning", "版本冻结与研报资格", "completed" if task_status == "verified" else "pending")
        return updates

    @staticmethod
    def _task_status_from_post_storage(result) -> str:
        if result.status == "passed":
            return "verified"
        flows = set(result.remediation_flows or [])
        if "research_flow" in flows and "repair_flow" not in flows:
            return "research_required"
        return "repair_required"

    def _generate_single_file(self, context: RequestContext, blueprint: dict[str, Any], spec, file_path: Path) -> dict[str, Any]:
        chat_client = self._generation_chat_client or getattr(self._insight_engine, "_chat_client", None)
        payload: dict[str, Any] = {}
        if chat_client is not None:
            try:
                payload = chat_client.complete_json(
                    system_prompt=build_generation_system_prompt(),
                    user_prompt=json.dumps(
                        {
                            "domain": context.domain,
                            "subdomain": blueprint.get("subdomain", ""),
                            "relative_path": file_path.as_posix(),
                            "doc_role": blueprint.get("doc_role", ""),
                            "module_id": blueprint.get("module_id", ""),
                            "title": blueprint.get("title", ""),
                            "required_sections": spec.required_sections,
                            "must_cover": spec.must_cover,
                            "query_hint_rules": spec.query_hint_rules,
                            "allowed_agent_tasks": spec.allowed_agent_tasks,
                            "structure_graph_context": self._structure_graph_context(context, blueprint),
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception as exc:
                logger.warning("LLM generation failed for %s: %s", file_path, exc)
                payload = {}
        return self._normalize_generated_payload(context, blueprint, spec, file_path, payload)

    def _normalize_generated_payload(
        self,
        context: RequestContext,
        blueprint: dict[str, Any],
        spec,
        file_path: Path,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        contract = {
            "file_id": str(blueprint.get("file_id", file_path.stem)),
            "file_path": file_path.as_posix(),
            "required_sections": list(spec.required_sections),
            "claims": _normalize_contract_items(payload.get("claims", [])) or [f"{spec.title} 需要形成可追溯知识说明。"],
            "evidence_needed": _normalize_contract_items(payload.get("evidence_needed", [])) or ["权威定义", "关键结论来源", "必要时的案例或趋势证据"],
            "query_tasks": payload.get("query_tasks", []) or self._default_query_tasks(blueprint, file_path, spec),
            "completion_status": payload.get("completion_status", {"state": "generated", "required": True}),
        }
        markdown = str(payload.get("markdown", "")).strip()
        if markdown and parse_contract_block(markdown) is None:
            markdown = f"{markdown}\n\n{render_contract_block(contract)}\n"
        if not markdown:
            markdown = self._fallback_markdown(context, blueprint, spec, file_path, contract)
        else:
            markdown = replace_contract_block(markdown, contract)
        return {"markdown": markdown, "contract": contract}

    @staticmethod
    def _structure_graph_context(context: RequestContext, blueprint: dict[str, Any]) -> dict[str, Any]:
        graph = context.structure_graph or {}
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges = graph.get("edges", []) if isinstance(graph, dict) else []
        structure_node_id = ""
        requirements = blueprint.get("completion_requirements", {})
        if isinstance(requirements, dict):
            structure_node_id = str(requirements.get("structure_node_id", ""))
        else:
            requirements = {}
        current = next((node for node in nodes if isinstance(node, dict) and str(node.get("node_id", "")) == structure_node_id), {})
        parent_id = str(current.get("parent_node_id") or requirements.get("parent_node_id", ""))
        parent = next((node for node in nodes if isinstance(node, dict) and str(node.get("node_id", "")) == parent_id), {})
        sibling_ids = {
            str(edge.get("to_node_id", ""))
            for edge in edges
            if isinstance(edge, dict)
            and str(edge.get("from_node_id", "")) == parent_id
            and str(edge.get("to_node_id", "")) != structure_node_id
        }
        siblings = [
            {"node_id": str(node.get("node_id", "")), "title": str(node.get("title", "")), "relative_path": str(node.get("relative_path", ""))}
            for node in nodes
            if isinstance(node, dict) and str(node.get("node_id", "")) in sibling_ids
        ][:8]
        return {
            "root_node_id": str(graph.get("root_node_id", "")) if isinstance(graph, dict) else "",
            "current_node": current,
            "parent_node": parent,
            "siblings": siblings,
        }

    def _fallback_markdown(
        self,
        context: RequestContext,
        blueprint: dict[str, Any],
        spec,
        file_path: Path,
        contract: dict[str, Any],
    ) -> str:
        front_matter = {
            "id": str(blueprint.get("file_id", file_path.stem)),
            "title": str(blueprint.get("title", file_path.stem)),
            "domain": context.domain,
            "subdomain": str(blueprint.get("subdomain", "")),
            "doc_type": str(blueprint.get("doc_type", "article")),
            "source_type": "mixed",
            "agent": "KnowledgeForge",
            "round": 1,
            "status": "draft",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "version": "v1",
            "path": file_path.as_posix(),
        }
        tasks = list(contract.get("query_tasks", [])) or self._default_query_tasks(blueprint, file_path, spec)
        contract["query_tasks"] = tasks
        contract["completion_status"] = {
            "state": "generated",
            "required": True,
            "completed_task_ids": [],
            "pending_task_ids": [item["task_id"] for item in tasks],
        }
        front_matter_text = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False).strip()
        body = [
            "---",
            front_matter_text,
            "---",
            "",
            f"# {spec.title}",
            "",
        ]
        for section in spec.required_sections:
            body.extend([f"## {section}", ""])
            if section == "摘要":
                body.append("该文件按固定模板生成，后续将结合队列中的依据任务补全。")
            elif section == "关键结论":
                body.extend([f"- {_render_contract_item(item)}" for item in contract["claims"]])
            elif section == "背景与上下文":
                body.extend([f"- {item}" for item in spec.must_cover])
            elif section == "证据与来源":
                body.extend(["| 编号 | 来源 | 关键信息 | 可信度 | 备注 |", "|---|---|---|---|---|", "| S0 | scaffold | 初始骨架 | unknown | 待补真实来源 |"])
            elif section == "后续动作":
                body.extend(["- 根据 JSON 合同中的 query_tasks 串行补充依据。"])
            else:
                body.append("待补充。")
            body.append("")
        body.extend([render_contract_block(contract), "", "## 变更记录", "", "| 版本 | 时间 | 变更说明 |", "|---|---|---|", f"| v1 | {now_iso()[:10]} | 初始生成 |", ""])
        return "\n".join(body)

    def _default_query_tasks(self, blueprint: dict[str, Any], file_path: Path, spec) -> list[dict[str, Any]]:
        requirements = blueprint.get("completion_requirements", {})
        required_query_tasks = 0
        if isinstance(requirements, dict):
            required_query_tasks = int(requirements.get("required_query_tasks", 0) or 0)
        if required_query_tasks <= 0:
            return []
        owners = [str(item) for item in blueprint.get("owner_engine_candidates", [])]
        task_type = "media" if "MediaEngine" in owners and "QueryEngine" not in owners else "query"
        return [
            {
                "task_id": f"{blueprint.get('file_id', file_path.stem)}-task-1",
                "task_type": task_type,
                "section": "证据与来源" if task_type == "query" else "正文",
                "claim_or_gap": f"补充 {blueprint.get('title', file_path.stem)} 的关键依据",
                "query_text": f"{blueprint.get('title', file_path.stem)} {'official documentation' if task_type == 'query' else 'community trend discussion'}",
                "expected_evidence": ["可追溯来源", "与结论对应的支撑信息"],
                "preferred_source_types": ["official documentation"] if task_type == "query" else ["community", "blog"],
                "acceptance_criteria": ["至少得到一条可回填的依据", "能写入对应文件章节"],
                "status": "pending",
            }
        ]

    def _extract_queue_tasks(self, contract: dict[str, Any], blueprint: dict[str, Any], file_path: Path, round_number: int) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for task in contract.get("query_tasks", []):
            if not isinstance(task, dict):
                continue
            queue_task = DomainTaskQueueItem(
                task_id=str(task.get("task_id", "")),
                task_type="media" if str(task.get("task_type", "query")) == "media" else "query",
                target_file_path=file_path.as_posix(),
                target_section=str(task.get("section", "正文")),
                claim_or_gap=str(task.get("claim_or_gap", "")),
                query_text=str(task.get("query_text", task.get("query_intent", ""))),
                expected_evidence=[str(item) for item in task.get("expected_evidence", []) if str(item).strip()],
                status="pending",
                round_number=round_number,
            ).to_dict()
            queue_task["preferred_source_types"] = [str(item) for item in task.get("preferred_source_types", []) if str(item).strip()]
            queue_task["acceptance_criteria"] = [str(item) for item in task.get("acceptance_criteria", []) if str(item).strip()]
            queue_task["module_id"] = str(blueprint.get("module_id", ""))
            queue_task["module_label"] = str(blueprint.get("module_label", ""))
            queue_task["doc_role"] = str(blueprint.get("doc_role", ""))
            queue_task["subdomain"] = str(blueprint.get("subdomain", ""))
            tasks.append(queue_task)
        return tasks

    @staticmethod
    def _merge_queue_tasks(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged = list(existing)
        existing_ids = {str(item.get("task_id", "")) for item in merged}
        for task in incoming:
            task_id = str(task.get("task_id", ""))
            if task_id in existing_ids:
                continue
            merged.append(task)
            existing_ids.add(task_id)
        return merged

    def _execute_queue_task(self, context: RequestContext, round_number: int, task: dict[str, Any]) -> dict[str, Any]:
        if str(task.get("task_type", "query")) == "media":
            result = self._media_engine.run_evidence_task(context=context, round_number=round_number, task=task)
        else:
            result = self._query_engine.run_evidence_task(context=context, round_number=round_number, task=task)
        citations = [
            {
                "title": source.title,
                "url": source.url,
                "publisher": source.publisher,
                "reliability": source.reliability,
            }
            for source in result.sources[:3]
        ]
        if not citations and result.summary:
            citations = [
                {
                    "title": str(task.get("claim_or_gap", "队列任务结果")),
                    "url": f"local://queue/{task.get('task_id', '')}",
                    "publisher": result.agent_name,
                    "reliability": "medium",
                }
            ]
        status = "completed" if citations else "insufficient"
        return {
            "status": status,
            "result_summary": result.summary,
            "citations": citations,
            "engine_output": result,
            "agent_name": result.agent_name,
        }

    @staticmethod
    def _merge_engine_output(existing: EngineRunResult | None, new_output: EngineRunResult) -> EngineRunResult:
        if existing is None:
            return new_output
        return EngineRunResult(
            agent_name=new_output.agent_name,
            summary=new_output.summary,
            key_points=[*existing.key_points, *new_output.key_points],
            raw_material=[*existing.raw_material, *new_output.raw_material],
            coverage_topics=list(dict.fromkeys([*existing.coverage_topics, *new_output.coverage_topics])),
            sources=[*existing.sources, *new_output.sources],
            collected_at=new_output.collected_at,
            round_number=new_output.round_number,
            execution_log=[*existing.execution_log, *new_output.execution_log],
            artifacts=[*existing.artifacts, *new_output.artifacts],
        )

    def _validate_queue_round(self, context: RequestContext, queue: dict[str, Any], max_rounds: int) -> RoundValidationResult:
        chat_client = getattr(self._insight_engine, "_chat_client", None)
        current_round = int(queue.get("current_round", 1))
        incomplete = [task for task in queue.get("tasks", []) if str(task.get("status", "")) != "completed"]
        current_round_incomplete = [
            task for task in incomplete if str(task.get("round_number", 1)) == str(current_round)
        ]
        if chat_client is not None:
            try:
                payload = chat_client.complete_json(
                    system_prompt=build_validation_system_prompt(),
                    user_prompt=json.dumps(
                        {
                            "domain": context.domain,
                            "current_round": queue.get("current_round", 1),
                            "tasks": queue.get("tasks", []),
                        },
                        ensure_ascii=False,
                    ),
                )
                is_complete = bool(payload.get("is_complete"))
                new_tasks = self._normalize_validation_tasks(
                    [item for item in payload.get("new_tasks", []) if isinstance(item, dict)],
                    next_round=current_round + 1,
                )
                if not is_complete and current_round >= max_rounds:
                    return self._max_round_validation(queue)
                if not is_complete and not new_tasks:
                    new_tasks = self._build_retry_tasks(current_round_incomplete, next_round=current_round + 1)
                return RoundValidationResult(
                    is_complete=is_complete,
                    missing_evidence=[str(item) for item in payload.get("missing_evidence", []) if str(item).strip()],
                    new_tasks=new_tasks,
                    reasoning=str(payload.get("reasoning", "")).strip() or "LLM 已完成本轮验证。",
                    file_status_updates=[item for item in payload.get("file_status_updates", []) if isinstance(item, dict)],
                )
            except Exception:
                pass
        if incomplete and current_round >= max_rounds:
            return self._max_round_validation(queue)
        retry_tasks = self._build_retry_tasks(current_round_incomplete, next_round=current_round + 1)
        return RoundValidationResult(
            is_complete=not incomplete,
            missing_evidence=[str(task.get("claim_or_gap", "")) for task in incomplete],
            new_tasks=retry_tasks,
            reasoning="当前轮次已根据队列状态完成验证。" if not incomplete else "仍有未完成的依据任务，需要继续补充。",
            file_status_updates=[
                {"file_path": str(task.get("target_file_path", "")), "status": "completed" if not incomplete else "partially_completed"}
                for task in queue.get("tasks", [])
            ],
        )

    @staticmethod
    def _max_round_validation(queue: dict[str, Any]) -> RoundValidationResult:
        incomplete = [task for task in queue.get("tasks", []) if str(task.get("status", "")) != "completed"]
        return RoundValidationResult(
            is_complete=True,
            missing_evidence=[str(task.get("claim_or_gap", "")) for task in incomplete],
            new_tasks=[],
            reasoning="已达到最大轮次，现有结果将进入统一回填并保留未决缺口说明。",
            file_status_updates=[
                {"file_path": str(task.get("target_file_path", "")), "status": "partially_completed"}
                for task in queue.get("tasks", [])
            ],
        )

    @staticmethod
    def _normalize_validation_tasks(tasks: list[dict[str, Any]], *, next_round: int) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, task in enumerate(tasks, start=1):
            query_text = str(task.get("query_text", task.get("query", ""))).strip()
            if not query_text:
                continue
            item = dict(task)
            item["task_id"] = str(item.get("task_id") or f"round-{next_round}-task-{index}")
            item["task_type"] = "media" if str(item.get("task_type", "query")) == "media" else "query"
            item["query_text"] = query_text
            item["status"] = "pending"
            item["attempts"] = 0
            item["round_number"] = next_round
            item.setdefault("expected_evidence", [])
            item.setdefault("citations", [])
            target_path = str(item.get("target_file_path", "")).strip()
            if not target_path:
                item["target_file_path"] = str(item.get("file_path", ""))
            item.setdefault("target_section", "证据与来源")
            item.setdefault("claim_or_gap", query_text)
            normalized.append(item)
        return normalized

    @staticmethod
    def _build_retry_tasks(incomplete: list[dict[str, Any]], *, next_round: int) -> list[dict[str, Any]]:
        retry_tasks: list[dict[str, Any]] = []
        for task in incomplete:
            base_id = str(task.get("task_id", "task")).strip() or "task"
            retry = dict(task)
            retry["task_id"] = f"{base_id}-r{next_round}"
            retry["status"] = "pending"
            retry["attempts"] = 0
            retry["round_number"] = next_round
            retry["result_summary"] = ""
            retry["citations"] = []
            retry_tasks.append(retry)
        return retry_tasks

    def _apply_file_status_update(self, update: dict[str, Any]) -> None:
        file_path = Path(str(update.get("file_path", "")).strip())
        if not file_path.exists():
            return
        text = file_path.read_text(encoding="utf-8")
        contract = parse_contract_block(text)
        if contract is None:
            return
        completion = dict(contract.get("completion_status", {}))
        completion["state"] = str(update.get("status", completion.get("state", "generated")))
        contract["completion_status"] = completion
        file_path.write_text(replace_contract_block(text, contract), encoding="utf-8")

    @staticmethod
    def _build_fill_artifacts(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}
        for task in tasks:
            file_path = str(task.get("target_file_path", "")).strip()
            if not file_path:
                continue
            artifact = artifacts.setdefault(
                file_path,
                {
                    "target_file_path": file_path,
                    "target_section": str(task.get("target_section", "正文")),
                    "state": "completed",
                    "content": "",
                    "task_updates": [],
                },
            )
            citations = task.get("citations", [])
            summary = str(task.get("result_summary", "")).strip()
            if summary:
                artifact["content"] += f"\n- {summary}"
            artifact["task_updates"].append(
                {
                    "task_id": str(task.get("task_id", "")),
                    "status": str(task.get("status", "completed")),
                    "citation": citations[0] if citations else {},
                }
            )
        return list(artifacts.values())

    @staticmethod
    def _build_file_update_from_task(task: dict[str, Any]) -> dict[str, Any]:
        citations = task.get("citations", [])
        return {
            "path": str(task.get("target_file_path", "")),
            "task_id": str(task.get("task_id", "")),
            "status": str(task.get("status", "")),
            "citations_count": len(citations) if isinstance(citations, list) else 0,
            "timestamp": now_iso(),
        }

    @staticmethod
    def _file_completion_counts(task: dict[str, Any]) -> tuple[int, int]:
        file_path = Path(str(task.get("target_file_path", "")).strip())
        if not file_path.exists():
            return (1 if str(task.get("status", "")) == "completed" else 0, 0 if str(task.get("status", "")) == "completed" else 1)
        try:
            contract = parse_contract_block(file_path.read_text(encoding="utf-8"))
        except OSError:
            contract = None
        if not contract:
            return (1 if str(task.get("status", "")) == "completed" else 0, 0 if str(task.get("status", "")) == "completed" else 1)
        tasks = contract.get("query_tasks", [])
        completed = len([item for item in tasks if str(item.get("status", "")) == "completed"])
        pending = len([item for item in tasks if str(item.get("status", "")) != "completed"])
        return completed, pending

    @staticmethod
    def _route_after_validation(state: WorkflowState) -> str:
        queue = state.get("task_queue_snapshot", {})
        return "fill_evidence" if queue.get("final_status") == "ready_for_fill" else "run_query_queue"

    def _emit_workflow_event(self, state: WorkflowState, step_id: str, label: str, status: str, details: dict[str, Any] | None = None) -> None:
        event = self._make_workflow_event(step_id, label, status, details)
        events = state.setdefault("workflow_events", [])
        if event not in events:
            events.append(event)
        if self._workflow_event_callback is not None:
            self._workflow_event_callback(state["task_id"], event)

    def _commit_state(self, state: WorkflowState, updates: dict[str, Any]) -> None:
        if "workflow_events" in state and "workflow_events" not in updates:
            updates["workflow_events"] = state["workflow_events"]
        for key in ("graph_snapshot", "graph_event", "file_update", "structure_graph"):
            if key in state and key not in updates:
                updates[key] = state[key]
        state.update(updates)
        if self._state_update_callback is not None:
            self._state_update_callback(state["task_id"], state)

    def _commit_queue_snapshot(
        self,
        state: WorkflowState,
        domain_dir: Path,
        queue: dict[str, Any],
        *,
        current_step: str,
        current_action: str,
        extra_updates: dict[str, Any] | None = None,
    ) -> None:
        updates = {
            "generation_progress": queue.get("generation_status", {}),
            "task_queue_path": self._queue_store.queue_path(domain_dir).as_posix(),
            "task_queue_snapshot": queue,
            "task_status": state.get("task_status", "running"),
            "current_step": current_step,
            "current_action": current_action,
        }
        if extra_updates:
            updates.update(extra_updates)
        self._commit_state(state, updates)

    @staticmethod
    def _make_workflow_event(step_id: str, label: str, status: str, details: dict[str, Any] | None = None) -> WorkflowStepEvent:
        return WorkflowStepEvent(step_id=step_id, label=label, status=status, timestamp=now_iso(), details=details or {})

    def _domain_dir(self, context: RequestContext) -> Path:
        save_root = getattr(self._writer, "_config").save_root
        return save_root / sanitize_path_segment(context.domain, "domain")

    @staticmethod
    def _initialize_structure_graph_status(context: RequestContext) -> None:
        graph = context.structure_graph or {}
        if not isinstance(graph, dict):
            return
        for node in graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node.setdefault("generation_state", "planned")
            node.setdefault("self_generation_state", "planned")
            node.setdefault("is_generated", False)
            node.setdefault("is_completed", False)
            node.setdefault("pending_task_count", 0)
            node.setdefault("completed_task_count", 0)

    def _set_local_structure_node_status(
        self,
        context: RequestContext,
        *,
        node_id: str,
        generation_state: str,
        generated_path: str = "",
        pending_task_count: int | None = None,
        completed_task_count: int | None = None,
    ) -> None:
        graph = context.structure_graph or {}
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        target = next((node for node in nodes if isinstance(node, dict) and str(node.get("node_id", "")) == node_id), None)
        if target is None:
            return
        target["self_generation_state"] = generation_state
        target["generation_state"] = generation_state
        target["is_generated"] = generation_state in {"generated", "evidence_pending", "evidence_running", "completed"}
        target["is_completed"] = generation_state == "completed"
        if generated_path:
            target["generated_path"] = generated_path
        if pending_task_count is not None:
            target["self_pending_task_count"] = max(0, int(pending_task_count))
            target["pending_task_count"] = max(0, int(pending_task_count))
        if completed_task_count is not None:
            target["self_completed_task_count"] = max(0, int(completed_task_count))
            target["completed_task_count"] = max(0, int(completed_task_count))
        target["updated_at"] = now_iso()
        if generation_state == "completed":
            target["completed_at"] = now_iso()
        self._aggregate_local_structure_graph(context)

    @staticmethod
    def _aggregate_local_structure_graph(context: RequestContext) -> None:
        graph = context.structure_graph or {}
        if not isinstance(graph, dict):
            return
        nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
        nodes_by_id = {str(node.get("node_id", "")): node for node in nodes}
        children_by_parent: dict[str, list[dict[str, Any]]] = {}
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            parent_id = str(edge.get("from_node_id", ""))
            child = nodes_by_id.get(str(edge.get("to_node_id", "")))
            if parent_id and child is not None:
                children_by_parent.setdefault(parent_id, []).append(child)

        def aggregate(node: dict[str, Any]) -> tuple[bool, str]:
            node_id = str(node.get("node_id", ""))
            children = children_by_parent.get(node_id, [])
            child_results = [aggregate(child) for child in children]
            own_state = str(node.get("self_generation_state") or node.get("generation_state") or "planned")
            own_required = str(node.get("node_type", "")) != "domain" or not children
            own_completed = own_state == "completed" or (own_state == "generated" and int(node.get("self_pending_task_count", node.get("pending_task_count", 0)) or 0) == 0)
            total = len(child_results) + (1 if own_required else 0)
            completed = len([item for item in child_results if item[0]]) + (1 if own_required and own_completed else 0)
            states = [own_state, *[item[1] for item in child_results]]
            if total and completed == total:
                aggregate_state = "completed"
            elif "evidence_running" in states:
                aggregate_state = "evidence_running"
            elif "evidence_pending" in states or "failed" in states:
                aggregate_state = "evidence_pending"
            elif "generating" in states:
                aggregate_state = "generating"
            elif "generated" in states:
                aggregate_state = "generated"
            else:
                aggregate_state = own_state
            if children:
                node["generation_state"] = aggregate_state
                node["is_generated"] = aggregate_state in {"generated", "evidence_pending", "evidence_running", "completed"}
                node["is_completed"] = bool(total and completed == total)
                node["completed_task_count"] = completed
                node["pending_task_count"] = max(0, total - completed)
                if node["is_completed"]:
                    node.setdefault("completed_at", now_iso())
            return bool(node.get("is_completed")), str(node.get("generation_state", "planned"))

        root_id = str(graph.get("root_node_id", ""))
        root = nodes_by_id.get(root_id)
        if root is not None:
            aggregate(root)
        else:
            for node in nodes:
                aggregate(node)

    @staticmethod
    def _local_graph_snapshot(context: RequestContext) -> dict[str, Any]:
        graph = context.structure_graph or {}
        if not isinstance(graph, dict):
            return {"nodes": [], "edges": []}
        nodes = []
        for node in graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("node_id", ""))
            label = {
                "domain": "Domain",
                "section": "KnowledgeSection",
                "subtopic": "SubTopic",
                "article": "Article",
                "index": "KnowledgeIndex",
            }.get(str(node.get("node_type", "")), "KnowledgeStructureNode")
            properties = dict(node)
            properties["id"] = node_id
            nodes.append(
                {
                    "id": node_id,
                    "title": str(node.get("title", node_id)),
                    "type": "KnowledgeStructureNode" if label != "Domain" else "Domain",
                    "labels": ["KnowledgeStructureNode", label] if label != "Domain" else ["Domain", "KnowledgeStructureNode"],
                    "path": str(node.get("generated_path") or node.get("relative_path", "")),
                    "properties": properties,
                }
            )
        edges = []
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from_node_id", ""))
            target = str(edge.get("to_node_id", ""))
            if not source or not target:
                continue
            edges.append(
                {
                    "id": f"{source}->{target}:{edge.get('edge_type', 'CONTAINS')}",
                    "source": source,
                    "target": target,
                    "type": "STRUCTURE_EDGE",
                    "properties": {"type": str(edge.get("edge_type", "CONTAINS"))},
                }
            )
        return {"nodes": nodes, "edges": edges}
