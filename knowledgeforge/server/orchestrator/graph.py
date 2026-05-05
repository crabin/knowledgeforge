from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from langgraph.graph import END, StateGraph

from knowledgeforge.agent.InsightEngine.agent import InsightEngine
from knowledgeforge.agent.MediaEngine.agent import MediaEngine
from knowledgeforge.agent.QueryEngine.agent import QueryEngine
from knowledgeforge.server.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.server.evaluation.supplement_decision import SupplementDecisionPlanner
from knowledgeforge.server.models import (
    AgentMessage,
    CompletenessResult,
    DomainTaskQueueItem,
    EngineRunResult,
    RequestContext,
    RoundValidationResult,
    WorkflowStepEvent,
)
from knowledgeforge.server.orchestrator.state import WorkflowState
from knowledgeforge.server.postprocess.pipeline import PostStoragePipeline
from knowledgeforge.server.prompts.knowledge_file_generation import (
    PROMPT_PROFILE_VERSION,
    build_completion_readiness_review_system_prompt,
    build_generation_system_prompt,
    build_prompt_spec,
    build_structure_coverage_review_system_prompt,
    build_structure_depth_review_system_prompt,
    build_structure_graph_system_prompt,
    build_structure_repair_system_prompt,
    build_validation_system_prompt,
)
from knowledgeforge.server.runtime.domain_task_queue_store import DomainTaskQueueStore
from knowledgeforge.server.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.server.utils.file_contract import parse_contract_block, render_contract_block, replace_contract_block
from knowledgeforge.server.utils.paths import sanitize_path_segment
from knowledgeforge.server.utils.structure_graph import (
    build_fallback_structure_graph,
    derive_context_from_structure_graph,
    normalize_structure_graph_payload,
    structure_graph_summary,
)
from knowledgeforge.server.utils.time import now_iso

logger = logging.getLogger(__name__)


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


def _infer_source_kind(url: str) -> str:
    lowered = url.lower()
    if "wikipedia.org" in lowered:
        return "wikipedia"
    if "github.com" in lowered:
        return "project_homepage"
    if "arxiv.org" in lowered or "doi.org" in lowered:
        return "paper"
    if any(marker in lowered for marker in ("docs.", "/docs", "documentation", "developer.")):
        return "official_documentation"
    return "authoritative_link"


def _is_manual_review_suggestion(item: Any) -> bool:
    text = json.dumps(item, ensure_ascii=False).lower() if isinstance(item, (dict, list)) else str(item).lower()
    return any(
        marker in text
        for marker in (
            "manual_review",
            "human_intervention",
            "human_review",
            "code_review",
            "人工",
            "代码审核",
            "人工干预",
            "人工介入",
        )
    )


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

    def continue_after_structure_repair(self, initial_state: WorkflowState) -> WorkflowState:
        state: WorkflowState = dict(initial_state)
        self._emit_workflow_event(
            state,
            "structure_repair",
            "从已修补知识架构继续执行",
            "completed",
            {"resume_mode": "continue_after_structure_repair"},
        )
        self._commit_state(
            state,
            {
                "task_status": "running",
                "current_step": "graph_completion",
                "current_action": "已接续 repair flow，将基于当前修补后的知识架构继续补全图谱上下文与证据链接。",
            },
        )
        self._prepare_graph_completion_context(state)
        self._finalize_graph_for_completion(state)
        while True:
            self._run_query_queue(state)
            self._validate_round(state)
            if self._route_after_validation(state) == "run_post_storage":
                break
        self._run_post_storage(state)
        self._record_evidence_to_graph(state)
        return state

    def fill_evidence(self, initial_state: WorkflowState) -> WorkflowState:
        state: WorkflowState = dict(initial_state)
        self._emit_workflow_event(
            state,
            "evidence_link_query",
            "用户触发查询填充，开始联网补充图谱证据",
            "active",
            {"trigger": "manual_evidence_fill"},
        )
        self._commit_state(
            state,
            {
                "task_status": "running",
                "current_step": "evidence_link_query",
                "current_action": "查询填充已启动，正在为 Neo4j 知识图谱补充可信证据链接。",
            },
        )
        while True:
            self._run_query_queue(state)
            self._validate_round(state)
            if self._route_after_validation(state) == "run_post_storage":
                break
        self._run_post_storage(state)
        self._record_evidence_to_graph(state)
        return state

    def generate_plans(self, state: WorkflowState) -> WorkflowState:
        return state

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("generate_structure_graph", self._generate_structure_graph)
        graph.add_node("sync_structure_graph_to_neo4j", self._sync_structure_graph_to_neo4j)
        graph.add_node("review_structure_round_1", self._review_structure_round_1)
        graph.add_node("repair_structure_graph_round_1", self._repair_structure_graph_round_1)
        graph.add_node("review_structure_round_2", self._review_structure_round_2)
        graph.add_node("repair_structure_graph_round_2", self._repair_structure_graph_round_2)
        graph.add_node("review_structure_round_3", self._review_structure_round_3)
        graph.add_node("repair_structure_graph_round_3", self._repair_structure_graph_round_3)
        graph.add_node("finalize_structure_review_failure", self._finalize_structure_review_failure)
        graph.add_node("prepare_graph_completion_context", self._prepare_graph_completion_context)
        graph.add_node("finalize_graph_for_completion", self._finalize_graph_for_completion)
        graph.add_node("query_evidence_links", self._run_query_queue)
        graph.add_node("validate_round", self._validate_round)
        graph.add_node("record_evidence_to_graph", self._record_evidence_to_graph)
        graph.add_node("run_post_storage", self._run_post_storage)
        graph.set_entry_point("generate_structure_graph")
        graph.add_edge("generate_structure_graph", "sync_structure_graph_to_neo4j")
        graph.add_edge("sync_structure_graph_to_neo4j", "review_structure_round_1")
        graph.add_conditional_edges(
            "review_structure_round_1",
            self._route_after_structure_review,
            {
                "repair_structure_graph_round_1": "repair_structure_graph_round_1",
                "prepare_graph_completion_context": "prepare_graph_completion_context",
            },
        )
        graph.add_edge("repair_structure_graph_round_1", "prepare_graph_completion_context")
        graph.add_conditional_edges(
            "prepare_graph_completion_context",
            self._route_after_graph_completion_context,
            {
                "review_structure_round_2": "review_structure_round_2",
                "review_structure_round_3": "review_structure_round_3",
                "finalize_graph_for_completion": "finalize_graph_for_completion",
            },
        )
        graph.add_conditional_edges(
            "review_structure_round_2",
            self._route_after_final_structure_review,
            {
                "repair_structure_graph_round_2": "repair_structure_graph_round_2",
                "review_structure_round_3": "review_structure_round_3",
                "finalize_structure_review_failure": "finalize_structure_review_failure",
            },
        )
        graph.add_conditional_edges(
            "repair_structure_graph_round_2",
            self._route_after_final_structure_repair,
            {
                "prepare_graph_completion_context": "prepare_graph_completion_context",
                "finalize_structure_review_failure": "finalize_structure_review_failure",
            },
        )
        graph.add_conditional_edges(
            "review_structure_round_3",
            self._route_after_depth_structure_review,
            {
                "repair_structure_graph_round_3": "repair_structure_graph_round_3",
                "finalize_graph_for_completion": "finalize_graph_for_completion",
            },
        )
        graph.add_conditional_edges(
            "repair_structure_graph_round_3",
            self._route_after_final_structure_repair,
            {
                "prepare_graph_completion_context": "prepare_graph_completion_context",
                "finalize_structure_review_failure": "finalize_structure_review_failure",
            },
        )
        graph.add_edge("finalize_graph_for_completion", END)
        graph.add_edge("query_evidence_links", "validate_round")
        graph.add_conditional_edges(
            "validate_round",
            self._route_after_validation,
            {
                "run_query_queue": "query_evidence_links",
                "run_post_storage": "run_post_storage",
            },
        )
        graph.add_edge("finalize_structure_review_failure", END)
        graph.add_edge("run_post_storage", "record_evidence_to_graph")
        graph.add_edge("record_evidence_to_graph", END)
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
            "graph_snapshot": self._local_graph_snapshot(context),
            "graph_event": {
                "event_type": "structure_graph_initialized",
                "node_id": structure_graph.root_node_id,
                "status": "planned",
                "path": "",
                "timestamp": now_iso(),
            },
            "task_status": "running",
            "current_step": "structure_graph_planning",
            "current_action": f"目录结构图谱已生成：{summary['node_count']} 个节点，{summary['edge_count']} 条关系。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(state, "structure_graph_ready", "目录结构图谱已生成", "completed", summary)
        return updates

    def _sync_structure_graph_to_neo4j(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        self._emit_workflow_event(state, "neo4j_structure_sync", "同步知识架构图谱到 Neo4j", "active")
        sync_result = self._sync_structure_graph_for_generation(state["task_id"], context)
        updates = {
            "structure_graph_sync": sync_result,
            "graph_snapshot": self._local_graph_snapshot(context),
            "graph_event": {
                "event_type": "structure_graph_synced_to_neo4j",
                "node_id": (context.structure_graph or {}).get("root_node_id", ""),
                "status": sync_result.get("status", "unknown"),
                "path": "",
                "timestamp": now_iso(),
            },
            "task_status": "running",
            "current_step": "neo4j_structure_sync",
            "current_action": "知识架构图谱已优先同步到 Neo4j，准备进入两轮架构审查。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(state, "neo4j_structure_sync", "Neo4j 知识架构图谱已同步", "completed", sync_result)
        return updates

    def _review_structure_round_1(self, state: WorkflowState) -> dict[str, Any]:
        return self._review_structure_round(state, 1)

    def _review_structure_round_2(self, state: WorkflowState) -> dict[str, Any]:
        return self._review_structure_round(state, 2)

    def _review_structure_round_3(self, state: WorkflowState) -> dict[str, Any]:
        return self._review_structure_round(state, 3)

    def _review_structure_round(self, state: WorkflowState, round_number: int) -> dict[str, Any]:
        context = state["request_context"]
        review_type = self._structure_review_type(round_number)
        review_label = self._structure_review_label(review_type)
        self._emit_workflow_event(
            state,
            "structure_review",
            f"{review_label}开始",
            "active",
            {"round": round_number, "review_type": review_type},
        )
        if review_type == "structure_coverage":
            self._set_all_structure_nodes_status(context, "reviewing")
        review = self._run_structure_review(state, context, round_number)
        review["round"] = round_number
        review["review_type"] = review_type
        review["reviewed_at"] = now_iso()
        rounds = self._merge_structure_review_round(state.get("structure_review_rounds", []), review)
        status = "passed" if review.get("is_complete") else "needs_repair"
        state_status = "auto_repaired" if status == "passed" and state.get("structure_review_status") == "auto_repaired" else status
        if status == "passed" and review_type == "structure_coverage":
            self._set_all_structure_nodes_status(context, "approved")
        review_sync_after = self._sync_structure_graph_after_review(state, context)
        review["neo4j_sync_after_review"] = review_sync_after
        updates = {
            "request_context": context,
            "structure_graph": context.structure_graph,
            "structure_graph_sync": review_sync_after,
            "structure_review_rounds": rounds,
            "structure_review_status": state_status,
            "graph_snapshot": self._local_graph_snapshot(context),
            "graph_event": {
                "event_type": "structure_review_completed",
                "node_id": (context.structure_graph or {}).get("root_node_id", ""),
                "status": state_status,
                "review_type": review_type,
                "path": "",
                "timestamp": now_iso(),
            },
            "task_status": "running",
            "current_step": "structure_review",
            "current_action": review.get("reasoning") or f"第 {round_number} 轮知识架构审查完成。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(
            state,
            "structure_review",
            f"{review_label}{'通过' if status == 'passed' else '发现缺口'}",
            "completed" if status == "passed" else "blocked",
            review,
        )
        return updates

    @staticmethod
    def _structure_review_type(round_number: int) -> str:
        return {
            1: "structure_coverage",
            2: "completion_readiness",
            3: "structure_depth",
        }.get(round_number, "completion_readiness")

    @staticmethod
    def _structure_review_label(review_type: str) -> str:
        return {
            "structure_coverage": "结构覆盖审查",
            "completion_readiness": "执行准备度审查",
            "structure_depth": "结构深化审查",
        }.get(review_type, "知识架构审查")

    @staticmethod
    def _merge_structure_review_round(rounds: list[dict[str, Any]], review: dict[str, Any]) -> list[dict[str, Any]]:
        current_round = int(review.get("round", 0) or 0)
        merged: dict[int, dict[str, Any]] = {}
        for item in rounds:
            if not isinstance(item, dict):
                continue
            try:
                round_number = int(item.get("round", 0) or 0)
            except (TypeError, ValueError):
                continue
            if round_number in {1, 2, 3}:
                merged[round_number] = item
        if current_round in {1, 2, 3}:
            merged[current_round] = review
        return [merged[round_number] for round_number in sorted(merged)]

    def _repair_structure_graph_round_1(self, state: WorkflowState) -> dict[str, Any]:
        return self._repair_structure_graph(state, 1)

    def _repair_structure_graph_round_2(self, state: WorkflowState) -> dict[str, Any]:
        return self._repair_structure_graph(state, 2)

    def _repair_structure_graph_round_3(self, state: WorkflowState) -> dict[str, Any]:
        return self._repair_structure_graph(state, 3)

    def _repair_structure_graph(self, state: WorkflowState, round_number: int) -> dict[str, Any]:
        context = state["request_context"]
        review = (state.get("structure_review_rounds") or [{}])[-1]
        review_type = str(review.get("review_type") or self._structure_review_type(round_number))
        repair_label = {
            "structure_coverage": "结构覆盖修补",
            "completion_readiness": "执行准备度修补",
            "structure_depth": "结构深化修补",
        }.get(review_type, "知识架构修补")
        self._emit_workflow_event(
            state,
            "structure_repair",
            f"{repair_label}开始",
            "active",
            {"round": round_number, "review_type": review_type},
        )
        self._set_all_structure_nodes_status(context, "repairing")
        repaired_graph, applied_changes = self._run_structure_repair(context, review)
        context.structure_graph = repaired_graph
        derived_context = derive_context_from_structure_graph(
            graph=normalize_structure_graph_payload(
                payload=repaired_graph,
                domain=context.domain,
                subdomains=context.subdomains,
                focus_points=context.focus_points,
                source_intent=context.original_input or context.domain,
            ),
            domain=context.domain,
        )
        normalized = normalize_structure_graph_payload(
            payload=context.structure_graph,
            domain=context.domain,
            subdomains=context.subdomains,
            focus_points=context.focus_points,
            source_intent=context.original_input or context.domain,
        )
        context.structure_graph = normalized.to_dict()
        self._initialize_structure_graph_status(context)
        review_status = "auto_repaired" if round_number >= 2 else state.get("structure_review_status", "needs_repair")
        if round_number >= 2:
            self._set_all_structure_nodes_status(context, "approved")
        context.structure_mode = str(derived_context["structure_mode"])
        context.knowledge_modules = derived_context["knowledge_modules"]
        context.core_topics = derived_context["core_topics"] or context.core_topics
        context.navigation_targets = derived_context["navigation_targets"]
        context.knowledge_blueprint = derived_context["knowledge_blueprint"]
        context.required_files = derived_context["required_files"]
        sync_result = self._sync_structure_graph_for_generation(state["task_id"], context)
        repair_entry = {
            "round": round_number,
            "review_type": review_type,
            "applied_changes": applied_changes,
            "synced_to_neo4j": sync_result,
            "repaired_at": now_iso(),
        }
        updates = {
            "request_context": context,
            "structure_graph": context.structure_graph,
            "structure_graph_sync": sync_result,
            "structure_review_status": review_status,
            "readiness_repair_completed": round_number >= 2,
            "structure_repair_log": [*state.get("structure_repair_log", []), repair_entry],
            "graph_snapshot": self._local_graph_snapshot(context),
            "graph_event": {
                "event_type": "structure_graph_repaired",
                "node_id": context.structure_graph.get("root_node_id", ""),
                "status": "repairing",
                "review_type": review_type,
                "path": "",
                "timestamp": now_iso(),
            },
            "task_status": "running",
            "current_step": "structure_repair",
            "current_action": f"{repair_label}已自动完成并同步 Neo4j，应用 {len(applied_changes)} 项变更。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(state, "structure_repair", f"{repair_label}已完成", "completed", repair_entry)
        return updates

    def _enrich_graph_for_completion(self, state: WorkflowState) -> dict[str, Any]:
        updates = self._prepare_graph_completion_context(state)
        final_updates = self._finalize_graph_for_completion(state)
        return {**updates, **final_updates}

    def _prepare_graph_completion_context(self, state: WorkflowState) -> dict[str, Any]:
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
        self._emit_workflow_event(state, "graph_completion", "图谱补全文档上下文已准备", "active")
        total_files = len(context.knowledge_blueprint)
        prepared_count = 0
        for blueprint in context.knowledge_blueprint:
            relative_path = str(blueprint.get("relative_path", "")).strip()
            if not relative_path:
                continue
            spec = build_prompt_spec(blueprint, completion_mode=context.completion_mode)
            suggested_path = (domain_dir / relative_path).as_posix()
            self._emit_workflow_event(
                state,
                "graph_completion",
                f"补全图谱节点上下文：{relative_path}",
                "active",
                {
                    "event": "graph_completion_started",
                    "suggested_relative_path": relative_path,
                    "relative_path": relative_path,
                    "completed_files": prepared_count,
                    "total_files": total_files,
                    "current_file": relative_path,
                },
            )
            contract = self._build_graph_completion_contract(context, blueprint, spec, suggested_path)
            query_tasks = self._extract_queue_tasks(contract, blueprint, Path(suggested_path), queue.get("current_round", 1))
            node_sync = self._update_structure_node_status(
                state,
                context,
                blueprint,
                generation_state="completion_ready",
                pending_task_count=len(query_tasks),
                completed_task_count=0,
                extra_properties={
                    "suggested_relative_path": relative_path,
                    "document_completion_status": "not_requested",
                    "review_status": state.get("structure_review_status", ""),
                    "repair_log": state.get("structure_repair_log", []),
                    "claim_or_gap": "; ".join(str(task.get("claim_or_gap", "")) for task in query_tasks if str(task.get("claim_or_gap", "")).strip()),
                    "expected_evidence": [
                        str(item)
                        for task in query_tasks
                        for item in task.get("expected_evidence", [])
                        if str(item).strip()
                    ],
                },
            )
            queue["tasks"] = self._merge_queue_tasks(queue.get("tasks", []), query_tasks)
            prepared_count += 1
            queue["generation_status"] = {
                "total_files": total_files,
                "completed_files": prepared_count,
                "current_file": relative_path,
                "last_saved_path": suggested_path,
            }
            self._queue_store.save(domain_dir, queue)
            self._commit_queue_snapshot(
                state,
                domain_dir,
                queue,
                current_step="graph_completion",
                current_action=f"图谱补全文档上下文已写入：{relative_path}",
                extra_updates={"latest_structure_node_sync": node_sync} if node_sync else None,
            )
            self._emit_workflow_event(
                state,
                "graph_completion",
                f"图谱补全文档上下文已写入：{relative_path}",
                "completed",
                {
                    "event": "graph_completion_completed",
                    "suggested_relative_path": relative_path,
                    "relative_path": relative_path,
                    "enqueued_tasks": len(query_tasks),
                    "completed_files": prepared_count,
                    "total_files": total_files,
                    "current_file": relative_path,
                },
            )
        queue["final_status"] = "generated"
        queue_path = self._queue_store.save(domain_dir, queue)
        updates = {
            "request_context": context,
            "structure_graph": context.structure_graph,
            "graph_snapshot": self._local_graph_snapshot(context),
            "knowledge_file_states": [],
            "generation_progress": queue["generation_status"],
            "task_queue_path": queue_path.as_posix(),
            "task_queue_snapshot": queue,
            "task_status": "running",
            "current_step": "graph_completion",
            "current_action": "图谱补全文档上下文已准备，准备执行可查询与可治理准备度审查。",
            "document_completion_status": state.get("document_completion_status", "not_requested"),
            "full_document_status": state.get("full_document_status", "not_requested"),
            "readiness_repair_completed": state.get("readiness_repair_completed", False),
        }
        self._commit_state(state, updates)
        return updates

    def _finalize_graph_for_completion(self, state: WorkflowState) -> dict[str, Any]:
        queue = state.get("task_queue_snapshot") or {}
        updates = {
            "task_status": "graph_ready",
            "current_step": "graph_completion",
            "current_action": "Neo4j 知识图谱已生成，等待点击“查询填充”联网补充证据。",
            "document_completion_status": state.get("document_completion_status", "not_requested"),
            "full_document_status": state.get("full_document_status", "not_requested"),
            "generation_progress": state.get("generation_progress", queue.get("generation_status", {})),
            "messages": [
                *state.get("messages", []),
                AgentMessage(role="assistant", content="Neo4j 知识图谱已生成，下一步可点击“查询填充”补充可信证据链接。"),
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
        extra_properties: dict[str, Any] | None = None,
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
            extra_properties=extra_properties,
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
        extra_properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_path = str(task.get("target_file_path") or task.get("suggested_relative_path") or "").strip()
        node_id = str(task.get("target_node_id", "")).strip() or self._structure_node_id_for_file(context, target_path)
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
            extra_properties=extra_properties,
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
        extra_properties: dict[str, Any] | None = None,
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
                    extra_properties=extra_properties or {},
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
            extra_properties=extra_properties,
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
        self._emit_workflow_event(state, "evidence_link_query", f"第 {round_number} 轮可信证据链接查询", "active")
        outputs = dict(state.get("agent_outputs", {}))
        for index, task in enumerate(queue.get("tasks", [])):
            if str(task.get("round_number", 1)) != str(round_number):
                continue
            if str(task.get("status", "pending")) not in {"pending", "insufficient"}:
                continue
            if str(task.get("task_type", "query")) != "query":
                queue["tasks"][index]["status"] = "skipped"
                queue["tasks"][index]["result_summary"] = "主链路证据阶段仅执行 QueryEngine 可信链接查询，Media 任务留给后续文档补全或扩展材料。"
                continue
            queue["tasks"][index]["status"] = "running"
            queue["tasks"][index]["attempts"] = int(task.get("attempts", 0)) + 1
            running_node_sync = self._update_structure_node_status_for_task(
                state,
                context,
                queue["tasks"][index],
                generation_state="link_querying",
            )
            self._queue_store.save(domain_dir, queue)
            self._commit_queue_snapshot(
                state,
                domain_dir,
                queue,
                current_step="evidence_link_query",
                current_action=f"正在查询可信证据链接：{task.get('task_id', '')}",
                extra_updates={"latest_structure_node_sync": running_node_sync} if running_node_sync else None,
            )
            self._emit_workflow_event(
                state,
                "evidence_link_query",
                f"查询可信证据链接：{task.get('task_id', '')}",
                "active",
                {"task_id": task.get("task_id", ""), "task_type": task.get("task_type", "")},
            )
            result = self._execute_queue_task(context, round_number, queue["tasks"][index])
            queue["tasks"][index].update(
                {
                    "status": result["status"],
                    "result_summary": result["result_summary"],
                    "citations": result["citations"],
                    "selected_link": result["selected_link"],
                    "source_kind": result["source_kind"],
                    "reachable": result["reachable"],
                    "relevance_reason": result["relevance_reason"],
                    "checked_at": result["checked_at"],
                }
            )
            outputs[result["agent_name"]] = self._merge_engine_output(outputs.get(result["agent_name"]), result["engine_output"])
            file_update = self._build_file_update_from_task(queue["tasks"][index])
            self._emit_workflow_event(
                state,
                "evidence_link_query",
                f"可信证据链接已选择：{result['selected_link'] or file_update.get('path', '')}",
                "completed" if result["status"] == "completed" else "blocked",
                file_update,
            )
            completed_count, pending_count = self._file_completion_counts(queue["tasks"][index])
            completed_node_sync = self._update_structure_node_status_for_task(
                state,
                context,
                queue["tasks"][index],
                generation_state="link_verified" if result["status"] == "completed" else "link_failed",
                pending_task_count=pending_count,
                completed_task_count=completed_count,
            )
            self._queue_store.save(domain_dir, queue)
            self._commit_queue_snapshot(
                state,
                domain_dir,
                queue,
                current_step="evidence_link_query",
                current_action=f"证据链接任务已完成：{task.get('task_id', '')}",
                extra_updates={
                    "agent_outputs": outputs,
                    "file_update": file_update,
                    **({"latest_structure_node_sync": completed_node_sync} if completed_node_sync else {}),
                },
            )
            self._emit_workflow_event(
                state,
                "evidence_link_query",
                f"证据链接任务已完成：{task.get('task_id', '')}",
                "completed" if result["status"] == "completed" else "blocked",
                {"task_id": task.get("task_id", ""), "task_type": task.get("task_type", ""), "status": result["status"]},
            )
        updates = {
            "agent_outputs": outputs,
            "task_queue_snapshot": queue,
            "task_status": "running",
            "current_step": "evidence_link_query",
            "current_action": f"第 {round_number} 轮可信证据链接查询完成。",
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
            queue["final_status"] = "ready_for_governance"
            completeness = CompletenessResult(
                status="pass",
                reasons=["图谱级查询队列验证通过。"],
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
                reasons=["图谱级查询队列仍有证据缺口。"],
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
        self._emit_workflow_event(
            state,
            "evidence_filling",
            "开始收尾图谱证据任务",
            "active",
            {"completion_mode": context.completion_mode},
        )
        outputs = dict(state.get("agent_outputs", {}))
        outputs["QueueFillPass"] = EngineRunResult(
            agent_name="QueueFillPass",
            summary="可信证据链接队列已完成收尾，正文补全留给后置文档补全任务。",
            key_points=[],
            raw_material=[],
            coverage_topics=context.subdomains,
            sources=[],
            collected_at=now_iso(),
            round_number=state.get("round_number", 1),
            artifacts=self._build_fill_artifacts(queue.get("tasks", [])),
        )
        artifact = self._writer.build_graph_governance_artifact(context=context, queue=queue, outputs=outputs)
        full_document_status = "not_requested"
        current_action = "知识框架图谱与证据链接已完成，本地知识 Markdown 按需后置生成。"
        updates = {
            "agent_outputs": outputs,
            "document_artifact": artifact,
            "completion_mode": context.completion_mode,
            "full_document_status": full_document_status,
            "document_completion_status": "not_requested",
            "fill_progress": {
                "completed_tasks": len([task for task in queue.get("tasks", []) if str(task.get("status", "")) == "completed"]),
                "total_tasks": len(queue.get("tasks", [])),
            },
            "task_status": "running",
            "current_step": "evidence_filling",
            "current_action": current_action,
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(
            state,
            "evidence_filling",
            "图谱证据任务已收尾",
            "completed",
            {"completion_mode": context.completion_mode, "full_document_status": full_document_status},
        )
        return updates

    def _record_evidence_to_graph(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        queue = state.get("task_queue_snapshot", {})
        tasks = [task for task in queue.get("tasks", []) if isinstance(task, dict)]
        graph = context.structure_graph if isinstance(context.structure_graph, dict) else {}
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        synced: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        self._emit_workflow_event(
            state,
            "evidence_link_recorded",
            "写入 Neo4j 图谱证据",
            "active",
            {"total_tasks": len(tasks)},
        )
        for task in tasks:
            node_id = str(task.get("target_node_id", "")).strip()
            task_id = str(task.get("task_id", "")).strip()
            if not node_id:
                skipped.append({"task_id": task_id, "reason": "missing_target_node_id"})
                continue
            selected_link = str(task.get("selected_link", "")).strip()
            task_status = str(task.get("status", ""))
            extra_properties = {
                "evidence_links": [selected_link] if selected_link else [],
                "selected_link": selected_link,
                "source_kind": str(task.get("source_kind", "")),
                "reachable": bool(task.get("reachable", False)),
                "relevance_reason": str(task.get("relevance_reason", "")),
                "checked_at": str(task.get("checked_at", "")),
                "claim_or_gap": str(task.get("claim_or_gap", "")),
                "expected_evidence": task.get("expected_evidence", []),
                "document_completion_status": state.get("document_completion_status", "not_requested"),
            }
            for node in nodes:
                if isinstance(node, dict) and str(node.get("node_id", "")) == node_id:
                    node.update(extra_properties)
            try:
                result = self._post_storage_pipeline.update_structure_node_status(
                    domain=context.domain,
                    task_id=state["task_id"],
                    node_id=node_id,
                    generation_state="link_verified" if task_status == "completed" else "link_failed",
                    generated_path="",
                    pending_task_count=0 if task_status == "completed" else 1,
                    completed_task_count=1 if task_status == "completed" else 0,
                    extra_properties=extra_properties,
                )
            except Exception as exc:
                skipped.append({"task_id": task_id, "node_id": node_id, "reason": str(exc)})
                continue
            if result is None:
                skipped.append({"task_id": task_id, "node_id": node_id, "reason": "graph_mapper_unavailable"})
                continue
            if result.status == "failed":
                skipped.append({"task_id": task_id, "node_id": node_id, "reason": result.error or "graph_write_failed"})
                continue
            synced.append({"task_id": task_id, "node_id": node_id, "selected_link": selected_link})
        evidence_sync = {
            "status": "completed",
            "synced_tasks": synced,
            "skipped_tasks": skipped,
            "total_tasks": len(tasks),
            "synced_at": now_iso(),
        }
        updates = {
            "request_context": context,
            "document_evidence_sync": evidence_sync,
            "task_status": state.get("task_status", "running"),
            "current_step": "evidence_link_recorded",
            "current_action": f"Neo4j 图谱证据写入完成：{len(synced)}/{len(tasks)}。",
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(
            state,
            "evidence_link_recorded",
            "Neo4j 图谱证据已写入",
            "completed",
            evidence_sync,
        )
        return updates

    def _run_post_storage(self, state: WorkflowState) -> dict[str, Any]:
        self._emit_workflow_event(state, "governing", "结构化治理与质量检测", "active")
        artifact = state.get("document_artifact")
        if artifact is None:
            artifact = self._writer.build_graph_governance_artifact(
                context=state["request_context"],
                queue=state.get("task_queue_snapshot", {}),
                outputs=state.get("agent_outputs", {}),
            )
        result = self._post_storage_pipeline.run(
            artifact,
            state["request_context"],
            state.get("agent_outputs", {}),
        )
        task_status = self._task_status_from_post_storage(result)
        updates = {
            "post_storage_result": result,
            "document_artifact": artifact,
            "task_status": task_status,
            "current_step": "versioning" if task_status == "verified" else "governing",
            "current_action": "治理链路已完成。" if task_status == "verified" else "治理链路需要修复。",
            "document_completion_status": state.get("document_completion_status", "not_requested"),
            "full_document_status": state.get("full_document_status", "not_requested"),
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
                    system_prompt=build_generation_system_prompt(context.completion_mode),
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
                            "completion_mode": context.completion_mode,
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
            "doc_type": "note" if context.completion_mode == "framework" else str(blueprint.get("doc_type", "article")),
            "source_type": "query" if context.completion_mode == "framework" else "mixed",
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
            elif section == "知识定位":
                body.extend(
                    [
                        f"- 节点：{blueprint.get('title', file_path.stem)}",
                        f"- 领域：{context.domain}",
                        f"- 子领域：{blueprint.get('subdomain', '') or '领域总览'}",
                        "- 作用：记录该知识点在整体框架中的位置、证据入口和后续补全依据。",
                    ]
                )
            elif section == "学习角色与路径":
                body.extend(
                    [
                        f"- 学习角色：{self._framework_learning_role(blueprint)}",
                        f"- 建议顺序：{self._framework_learning_order(context, blueprint)}",
                        "- 后续完整文档应基于本文件证据和结构图谱补全。",
                    ]
                )
            elif section == "知识关系":
                graph_context = self._structure_graph_context(context, blueprint)
                parent = graph_context.get("parent_node", {}) or {}
                siblings = graph_context.get("siblings", []) or []
                body.append(f"- 上级节点：{parent.get('title') or '无'}")
                if siblings:
                    body.extend([f"- 相关节点：{item.get('title')}（{item.get('relative_path')}）" for item in siblings[:5]])
                else:
                    body.append("- 相关节点：暂无。")
            elif section == "关键结论":
                body.extend([f"- {_render_contract_item(item)}" for item in contract["claims"]])
            elif section == "背景与上下文":
                body.extend([f"- {item}" for item in spec.must_cover])
            elif section == "证据与来源":
                body.extend(["| 编号 | 来源 | 关键信息 | 可信度 | 备注 |", "|---|---|---|---|---|", "| S0 | scaffold | 初始骨架 | unknown | 待补真实来源 |"])
            elif section == "后续动作":
                body.extend(["- 根据 JSON 合同中的 query_tasks 串行补充官方或权威依据。"])
                body.append("- 证据完成后等待用户点击补全文档生成本地知识 Markdown。")
            else:
                body.append("待补充。")
            body.append("")
        body.extend([render_contract_block(contract), "", "## 变更记录", "", "| 版本 | 时间 | 变更说明 |", "|---|---|---|", f"| v1 | {now_iso()[:10]} | 初始生成 |", ""])
        return "\n".join(body)

    @staticmethod
    def _framework_learning_role(blueprint: dict[str, Any]) -> str:
        requirements = blueprint.get("completion_requirements", {})
        node_type = str(requirements.get("structure_node_type", "")) if isinstance(requirements, dict) else ""
        return {
            "domain": "领域总览与学习地图",
            "section": "阶段模块",
            "subtopic": "主题单元",
            "index": "导航索引",
            "article": "具体知识点",
        }.get(node_type, "知识节点")

    @staticmethod
    def _framework_learning_order(context: RequestContext, blueprint: dict[str, Any]) -> str:
        graph = context.structure_graph or {}
        node_id = ""
        requirements = blueprint.get("completion_requirements", {})
        if isinstance(requirements, dict):
            node_id = str(requirements.get("structure_node_id", ""))
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        for index, node in enumerate(nodes, start=1):
            if isinstance(node, dict) and str(node.get("node_id", "")) == node_id:
                metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
                order = metadata.get("learning_order")
                if order:
                    return str(order)
                return f"图谱顺序第 {index} 个节点"
        return "按结构图谱父子关系学习"

    def _default_query_tasks(self, blueprint: dict[str, Any], file_path: Path, spec) -> list[dict[str, Any]]:
        requirements = blueprint.get("completion_requirements", {})
        required_query_tasks = 0
        if isinstance(requirements, dict):
            required_query_tasks = int(requirements.get("required_query_tasks", 0) or 0)
        if required_query_tasks <= 0:
            return []
        return [
            {
                "task_id": f"{blueprint.get('file_id', file_path.stem)}-task-1",
                "task_type": "query",
                "section": "证据与来源",
                "claim_or_gap": f"补充 {blueprint.get('title', file_path.stem)} 的关键依据",
                "query_text": f"{blueprint.get('title', file_path.stem)} official documentation wikipedia",
                "expected_evidence": ["官方或高公信力链接", "与知识点最贴近的说明入口"],
                "preferred_source_types": ["official documentation", "standard", "paper", "project homepage", "wikipedia"],
                "acceptance_criteria": ["至少得到一条可访问链接", "链接能解释对应知识点"],
                "status": "pending",
            }
        ]

    def _build_graph_completion_contract(self, context: RequestContext, blueprint: dict[str, Any], spec, suggested_path: str) -> dict[str, Any]:
        file_path = Path(suggested_path)
        tasks = self._default_query_tasks(blueprint, file_path, spec)
        return {
            "file_id": str(blueprint.get("file_id", file_path.stem)),
            "file_path": suggested_path,
            "required_sections": list(spec.required_sections),
            "claims": [f"{spec.title} 需要形成可追溯知识说明。"],
            "evidence_needed": ["官方定义", "官方文档或标准来源", "关键关系与学习路径依据"],
            "query_tasks": tasks,
            "completion_status": {
                "state": "completion_ready",
                "required": True,
                "completed_task_ids": [],
                "pending_task_ids": [str(item.get("task_id", "")) for item in tasks],
                "document_completion_status": "not_requested",
            },
        }

    def _extract_queue_tasks(self, contract: dict[str, Any], blueprint: dict[str, Any], file_path: Path, round_number: int) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        node_id = self._structure_node_id_for_blueprint(blueprint)
        suggested_relative_path = str(blueprint.get("relative_path", "")).strip()
        for task in contract.get("query_tasks", []):
            if not isinstance(task, dict):
                continue
            queue_task = DomainTaskQueueItem(
                task_id=str(task.get("task_id", "")),
                task_type="query",
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
            queue_task["target_node_id"] = node_id
            queue_task["suggested_relative_path"] = suggested_relative_path
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
        result = self._query_engine.run_evidence_task(context=context, round_number=round_number, task=task)
        selected = self._select_evidence_link(result)
        citations = [selected["citation"]] if selected["citation"] else []
        status = "completed" if selected["reachable"] and selected["url"] else "insufficient"
        return {
            "status": status,
            "result_summary": selected["relevance_reason"],
            "citations": citations,
            "selected_link": selected["url"],
            "source_kind": selected["source_kind"],
            "reachable": selected["reachable"],
            "relevance_reason": selected["relevance_reason"],
            "checked_at": selected["checked_at"],
            "engine_output": result,
            "agent_name": result.agent_name,
        }

    @staticmethod
    def _select_evidence_link(result: EngineRunResult) -> dict[str, Any]:
        preferred_order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
        candidates = sorted(
            [source for source in result.sources if str(source.url).startswith(("http://", "https://"))],
            key=lambda source: preferred_order.get(source.reliability, 4),
        )
        if not candidates:
            checked_at = now_iso()
            return {
                "url": "",
                "source_kind": "",
                "reachable": False,
                "relevance_reason": "未找到可访问的官方或高公信力链接。",
                "checked_at": checked_at,
                "citation": {},
            }
        source = candidates[0]
        checked_at = now_iso()
        source_kind = source.source_type or _infer_source_kind(source.url)
        return {
            "url": source.url,
            "source_kind": source_kind,
            "reachable": True,
            "relevance_reason": f"已选择 {source.publisher or source_kind} 的可信链接，用于解释目标知识点。",
            "checked_at": checked_at,
            "citation": {
                "title": source.title,
                "url": source.url,
                "publisher": source.publisher,
                "reliability": source.reliability,
                "source_kind": source_kind,
                "checked_at": checked_at,
            },
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

    def _run_structure_review(self, state: WorkflowState, context: RequestContext, round_number: int) -> dict[str, Any]:
        chat_client = self._generation_chat_client or getattr(self._insight_engine, "_chat_client", None)
        knowledge_id = self._current_review_knowledge_id(context)
        review_type = self._structure_review_type(round_number)
        neo4j_context = self._structure_review_context_from_neo4j(
            state=state,
            task_id=state["task_id"],
            context=context,
            knowledge_id=knowledge_id,
        )
        previous_reviews = state.get("structure_review_rounds", [])
        system_prompt = {
            "structure_coverage": build_structure_coverage_review_system_prompt,
            "completion_readiness": build_completion_readiness_review_system_prompt,
            "structure_depth": build_structure_depth_review_system_prompt,
        }.get(review_type, build_completion_readiness_review_system_prompt)()
        review_payload: dict[str, Any] = {
            "domain": context.domain,
            "round": round_number,
            "review_type": review_type,
            "knowledge_id": knowledge_id,
            "neo4j_review_context": neo4j_context,
            "structure_graph": context.structure_graph,
            "subdomains": context.subdomains,
            "focus_points": context.focus_points,
            "previous_review_rounds": previous_reviews,
        }
        if review_type == "structure_coverage":
            review_payload["instruction"] = (
                "基于当前知识 ID 的 Neo4j 相关节点/关系、本地结构图谱和上一轮 review 记录进行结构覆盖查漏补缺。"
                "只输出 LLM 可继续自动补全的结构修补建议。"
            )
        elif review_type == "completion_readiness":
            review_payload.update(
                {
                    "knowledge_blueprint": context.knowledge_blueprint,
                    "task_queue_snapshot": state.get("task_queue_snapshot", {}),
                    "generation_progress": state.get("generation_progress", {}),
                    "instruction": (
                        "基于已准备的图谱补全文档上下文、证据队列、建议路径和 Neo4j 节点状态进行执行准备度审查。"
                        "优先输出证据需求、query 任务、路径、学习目标、来源优先级或 flow 分类相关的修补建议。"
                    ),
                }
            )
        else:
            review_payload.update(
                {
                    "depth_review_context": self._structure_depth_review_context(context),
                    "instruction": (
                        "基于倒数第二级节点和末级子节点数量进行结构深化审查。"
                        "只在分支确实过薄、方法族未展开或末级节点过宽时提出补充或拆分建议。"
                    ),
                }
            )
        if chat_client is not None:
            try:
                payload = chat_client.complete_json(
                    system_prompt=system_prompt,
                    user_prompt=json.dumps(review_payload, ensure_ascii=False),
                )
                if payload:
                    review = self._normalize_structure_review(payload)
                    review["review_type"] = review_type
                    review["knowledge_id"] = knowledge_id
                    review["neo4j_review_context"] = neo4j_context
                    return review
            except Exception as exc:
                logger.warning("Structure review round %s failed for %s: %s", round_number, context.domain, exc)
        review = self._fallback_structure_review(context)
        review["review_type"] = review_type
        review["knowledge_id"] = knowledge_id
        review["neo4j_review_context"] = neo4j_context
        return review

    def _sync_structure_graph_after_review(self, state: WorkflowState, context: RequestContext) -> dict[str, Any]:
        previous_sync = state.get("structure_graph_sync") or {}
        if previous_sync.get("status") in {"failed", "skipped"}:
            return {
                "status": "skipped",
                "reason": "previous_neo4j_sync_unavailable",
                "previous_sync": previous_sync,
            }
        return self._sync_structure_graph_for_generation(state["task_id"], context)

    @staticmethod
    def _normalize_structure_review(payload: dict[str, Any]) -> dict[str, Any]:
        is_complete = bool(payload.get("is_complete") or str(payload.get("status", "")).lower() == "passed")
        missing_topics = [str(item).strip() for item in payload.get("missing_topics", []) if str(item).strip()]
        suggested_repairs = payload.get("suggested_repairs", [])
        if isinstance(suggested_repairs, dict):
            normalized_repairs: list[Any] = [] if _is_manual_review_suggestion(suggested_repairs) else [suggested_repairs]
        elif isinstance(suggested_repairs, list):
            normalized_repairs = [item for item in suggested_repairs if not _is_manual_review_suggestion(item)]
        elif suggested_repairs:
            normalized_repairs = [] if _is_manual_review_suggestion(suggested_repairs) else [str(suggested_repairs)]
        else:
            normalized_repairs = []
        normalized = {
            "is_complete": is_complete,
            "status": "passed" if is_complete else "needs_repair",
            "missing_topics": missing_topics,
            "suggested_repairs": normalized_repairs,
            "reasoning": str(payload.get("reasoning", "")).strip() or ("知识架构审查通过。" if is_complete else "知识架构仍存在缺口。"),
        }
        for key in (
            "findings",
            "readiness_score",
            "missing_evidence_requirements",
            "weak_query_targets",
            "path_conflicts",
            "document_context_gaps",
            "source_priority_requirements",
            "depth_findings",
            "thin_penultimate_nodes",
            "leaf_split_candidates",
        ):
            if key in payload:
                normalized[key] = payload[key]
        return normalized

    @staticmethod
    def _structure_depth_review_context(context: RequestContext) -> dict[str, Any]:
        graph = context.structure_graph if isinstance(context.structure_graph, dict) else {}
        nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
        nodes_by_id = {str(node.get("node_id", "")): node for node in nodes if str(node.get("node_id", "")).strip()}
        children_by_parent: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            if str(edge.get("edge_type", "CONTAINS")) not in {"CONTAINS", "INDEXES"}:
                continue
            parent_id = str(edge.get("from_node_id", "")).strip()
            child = nodes_by_id.get(str(edge.get("to_node_id", "")).strip())
            if parent_id and child is not None:
                children_by_parent.setdefault(parent_id, []).append(child)

        candidates: list[dict[str, Any]] = []
        for node_id, node in nodes_by_id.items():
            children = children_by_parent.get(node_id, [])
            if not children or str(node.get("node_type", "")) in {"domain", "index"}:
                continue
            grandchildren = [
                grandchild
                for child in children
                for grandchild in children_by_parent.get(str(child.get("node_id", "")), [])
            ]
            if grandchildren:
                continue
            child_summaries = [
                {
                    "node_id": str(child.get("node_id", "")),
                    "title": str(child.get("title", "")),
                    "node_type": str(child.get("node_type", "")),
                    "relative_path": str(child.get("relative_path", "")),
                }
                for child in children
            ]
            candidates.append(
                {
                    "node_id": node_id,
                    "title": str(node.get("title", "")),
                    "node_type": str(node.get("node_type", "")),
                    "relative_path": str(node.get("relative_path", "")),
                    "child_count": len(children),
                    "children": child_summaries,
                    "looks_thin": len(children) <= 1,
                    "metadata": node.get("metadata", {}),
                }
            )
        return {
            "candidate_penultimate_nodes": candidates,
            "thin_penultimate_nodes": [item for item in candidates if item["looks_thin"]],
            "guidance": "Only expand method families, technical branches, application groups, evaluation groups, or broad leaves that need systematic study.",
        }

    def _structure_review_context_from_neo4j(self, *, state: WorkflowState, task_id: str, context: RequestContext, knowledge_id: str) -> dict[str, Any]:
        if not knowledge_id:
            return {"status": "skipped", "reason": "missing_knowledge_id", "nodes": [], "edges": []}
        previous_sync = state.get("structure_graph_sync") or {}
        if previous_sync.get("status") in {"failed", "skipped"}:
            fallback = self._local_structure_review_context(context, knowledge_id, status="local_fallback")
            fallback["neo4j_lookup"] = {
                "status": "skipped",
                "reason": "previous_neo4j_sync_unavailable",
                "previous_sync": previous_sync,
            }
            return fallback
        try:
            payload = self._post_storage_pipeline.structure_review_context(
                domain=context.domain,
                task_id=task_id,
                knowledge_id=knowledge_id,
            )
        except Exception as exc:
            logger.warning("Structure review Neo4j context lookup failed for %s: %s", knowledge_id, exc)
            return self._local_structure_review_context(context, knowledge_id, status="failed", error=str(exc))
        if not payload or payload.get("status") in {"skipped", "failed"}:
            fallback = self._local_structure_review_context(context, knowledge_id, status=str((payload or {}).get("status", "local_fallback")))
            if isinstance(payload, dict):
                fallback["neo4j_lookup"] = payload
            return fallback
        return payload

    @staticmethod
    def _current_review_knowledge_id(context: RequestContext) -> str:
        graph = context.structure_graph if isinstance(context.structure_graph, dict) else {}
        root_id = str(graph.get("root_node_id", "")).strip()
        if root_id:
            return root_id
        for node in graph.get("nodes", []):
            if isinstance(node, dict) and str(node.get("node_id", "")).strip():
                return str(node["node_id"]).strip()
        return sanitize_path_segment(context.domain, "domain")

    @staticmethod
    def _local_structure_review_context(
        context: RequestContext,
        knowledge_id: str,
        *,
        status: str = "local_fallback",
        error: str | None = None,
    ) -> dict[str, Any]:
        graph = context.structure_graph if isinstance(context.structure_graph, dict) else {}
        nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
        related_ids = {knowledge_id}
        for edge in edges:
            source = str(edge.get("from_node_id", ""))
            target = str(edge.get("to_node_id", ""))
            if source == knowledge_id and target:
                related_ids.add(target)
            if target == knowledge_id and source:
                related_ids.add(source)
        related_nodes = [node for node in nodes if str(node.get("node_id", "")) in related_ids]
        related_edges = [
            edge
            for edge in edges
            if str(edge.get("from_node_id", "")) in related_ids and str(edge.get("to_node_id", "")) in related_ids
        ]
        payload: dict[str, Any] = {
            "status": status,
            "source": "local_structure_graph",
            "domain": context.domain,
            "knowledge_id": knowledge_id,
            "nodes": related_nodes,
            "edges": related_edges,
        }
        if error:
            payload["error"] = error
        return payload

    @staticmethod
    def _fallback_structure_review(context: RequestContext) -> dict[str, Any]:
        graph = context.structure_graph if isinstance(context.structure_graph, dict) else {}
        nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
        has_root = any(str(node.get("node_type", "")) == "domain" for node in nodes)
        has_knowledge_nodes = any(str(node.get("node_type", "")) in {"subtopic", "article", "section"} for node in nodes)
        missing_topics: list[str] = []
        if not has_root:
            missing_topics.append("领域根节点")
        if not has_knowledge_nodes:
            missing_topics.append("核心知识节点")
        if not edges and len(nodes) > 1:
            missing_topics.append("知识层级关系")
        is_complete = not missing_topics
        return {
            "is_complete": is_complete,
            "status": "passed" if is_complete else "needs_repair",
            "missing_topics": missing_topics,
            "suggested_repairs": [{"missing_topics": missing_topics}] if missing_topics else [],
            "reasoning": "根据结构节点、知识节点和关系完整性完成 fallback 审查。",
        }

    def _run_structure_repair(self, context: RequestContext, review: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        chat_client = self._generation_chat_client or getattr(self._insight_engine, "_chat_client", None)
        if chat_client is not None:
            try:
                payload = chat_client.complete_json(
                    system_prompt=build_structure_repair_system_prompt(),
                    user_prompt=json.dumps(
                        {
                            "domain": context.domain,
                            "structure_graph": context.structure_graph,
                            "review": review,
                        },
                        ensure_ascii=False,
                    ),
                )
                if isinstance(payload, dict) and payload.get("nodes"):
                    return payload, [{"type": "llm_repaired_graph", "node_count": len(payload.get("nodes", []))}]
            except Exception as exc:
                logger.warning("Structure repair failed for %s: %s", context.domain, exc)
        return self._fallback_repair_structure_graph(context, review)

    @staticmethod
    def _fallback_repair_structure_graph(context: RequestContext, review: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        graph = json.loads(json.dumps(context.structure_graph or {}, ensure_ascii=False))
        nodes = graph.setdefault("nodes", [])
        edges = graph.setdefault("edges", [])
        root_id = str(graph.get("root_node_id", "")).strip()
        if not root_id:
            root_id = f"domain-{sanitize_path_segment(context.domain, 'domain')}"
            graph["root_node_id"] = root_id
        if not any(isinstance(node, dict) and str(node.get("node_id", "")) == root_id for node in nodes):
            nodes.insert(
                0,
                {
                    "node_id": root_id,
                    "title": f"{context.domain} Overview",
                    "node_type": "domain",
                    "relative_path": "README.md",
                    "doc_type": "summary",
                    "owner_engine_candidates": ["InsightEngine"],
                    "required_query_tasks": 0,
                },
            )
        existing_titles = {str(node.get("title", "")).strip().lower() for node in nodes if isinstance(node, dict)}
        missing = [str(item).strip() for item in review.get("missing_topics", []) if str(item).strip()]
        if not missing:
            missing = ["核心知识节点"] if not any(isinstance(node, dict) and str(node.get("node_type", "")) in {"subtopic", "article", "section"} for node in nodes) else []
        applied: list[dict[str, Any]] = []
        for index, title in enumerate(missing, start=1):
            if title.lower() in existing_titles:
                continue
            slug = sanitize_path_segment(title, f"topic-{index}")
            node_id = f"review_added_{slug}"
            nodes.append(
                {
                    "node_id": node_id,
                    "title": title,
                    "node_type": "subtopic",
                    "parent_node_id": root_id,
                    "relative_path": f"{slug}/README.md",
                    "description": "架构 review 自动补充的知识节点。",
                    "doc_type": "summary",
                    "owner_engine_candidates": ["InsightEngine", "QueryEngine"],
                    "required_query_tasks": 1,
                    "metadata": {"review_added": True, "subdomain": title},
                }
            )
            edges.append({"from_node_id": root_id, "edge_type": "CONTAINS", "to_node_id": node_id})
            applied.append({"type": "add_node", "node_id": node_id, "title": title})
        graph.setdefault("source_intent", context.original_input or context.domain)
        return graph, applied or [{"type": "noop", "reason": "review had no concrete missing topics"}]

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
            "selected_link": str(task.get("selected_link", "")),
            "source_kind": str(task.get("source_kind", "")),
            "reachable": bool(task.get("reachable", False)),
            "timestamp": now_iso(),
        }

    @staticmethod
    def _file_completion_counts(task: dict[str, Any]) -> tuple[int, int]:
        if any(key in task for key in ("selected_link", "reachable", "checked_at")):
            return (1 if str(task.get("status", "")) == "completed" else 0, 0 if str(task.get("status", "")) == "completed" else 1)
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
        return "run_post_storage" if queue.get("final_status") == "ready_for_governance" else "run_query_queue"

    @staticmethod
    def _route_after_structure_review(state: WorkflowState) -> str:
        return "prepare_graph_completion_context" if state.get("structure_review_status") == "passed" else "repair_structure_graph_round_1"

    @staticmethod
    def _route_after_graph_completion_context(state: WorkflowState) -> str:
        repair_log = state.get("structure_repair_log") or []
        rounds = state.get("structure_review_rounds") or []
        has_readiness_review = any(isinstance(item, dict) and item.get("round") == 2 for item in rounds)
        has_depth_review = any(isinstance(item, dict) and item.get("round") == 3 for item in rounds)
        has_depth_repair = any(
            isinstance(item, dict) and (item.get("round") == 3 or item.get("review_type") == "structure_depth")
            for item in repair_log
        )
        if has_depth_repair:
            return "finalize_graph_for_completion"
        if not has_readiness_review:
            return "review_structure_round_2"
        if not has_depth_review:
            return "review_structure_round_3"
        return "finalize_graph_for_completion"

    @staticmethod
    def _route_after_final_structure_review(state: WorkflowState) -> str:
        return "review_structure_round_3" if state.get("structure_review_status") == "passed" else "repair_structure_graph_round_2"

    @staticmethod
    def _route_after_depth_structure_review(state: WorkflowState) -> str:
        return "finalize_graph_for_completion" if state.get("structure_review_status") in {"passed", "auto_repaired"} else "repair_structure_graph_round_3"

    @staticmethod
    def _route_after_final_structure_repair(state: WorkflowState) -> str:
        return "prepare_graph_completion_context"

    def _finalize_structure_review_failure(self, state: WorkflowState) -> dict[str, Any]:
        review = (state.get("structure_review_rounds") or [{}])[-1]
        updates = {
            "task_status": "repair_required",
            "current_step": "structure_review",
            "current_action": "知识架构已执行自动修补并同步 Neo4j；治理仍需系统修复流继续处理。",
            "completeness": CompletenessResult(
                status="supplement_required",
                reasons=[str(review.get("reasoning", "知识架构审查未通过。"))],
                missing_topics=[str(item) for item in review.get("missing_topics", [])],
                supplement_queries=[],
                failure_categories=["structure_review_incomplete"],
            ),
        }
        self._commit_state(state, updates)
        self._emit_workflow_event(
            state,
            "structure_review",
            "两轮知识架构审查未通过",
            "blocked",
            {"missing_topics": review.get("missing_topics", [])},
        )
        return updates

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

    @staticmethod
    def _set_all_structure_nodes_status(context: RequestContext, generation_state: str) -> None:
        graph = context.structure_graph or {}
        if not isinstance(graph, dict):
            return
        is_generated = generation_state in {"completion_ready", "document_generating", "documented", "link_querying", "link_verified", "approved"}
        is_completed = generation_state in {"completion_ready", "documented", "link_verified", "approved"}
        for node in graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node["generation_state"] = generation_state
            node["self_generation_state"] = generation_state
            node["is_generated"] = is_generated
            node["is_completed"] = is_completed
            node["updated_at"] = now_iso()
            if is_completed:
                node["completed_at"] = now_iso()

    def _set_local_structure_node_status(
        self,
        context: RequestContext,
        *,
        node_id: str,
        generation_state: str,
        generated_path: str = "",
        pending_task_count: int | None = None,
        completed_task_count: int | None = None,
        extra_properties: dict[str, Any] | None = None,
    ) -> None:
        graph = context.structure_graph or {}
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        target = next((node for node in nodes if isinstance(node, dict) and str(node.get("node_id", "")) == node_id), None)
        if target is None:
            return
        target["self_generation_state"] = generation_state
        target["generation_state"] = generation_state
        target["is_generated"] = generation_state in {"completion_ready", "document_generating", "documented", "link_querying", "link_verified", "approved"}
        target["is_completed"] = generation_state in {"completion_ready", "documented", "link_verified", "approved"}
        if generated_path:
            target["generated_path"] = generated_path
        if extra_properties:
            for key, value in extra_properties.items():
                if value is not None:
                    target[key] = value
        if pending_task_count is not None:
            target["self_pending_task_count"] = max(0, int(pending_task_count))
            target["pending_task_count"] = max(0, int(pending_task_count))
        if completed_task_count is not None:
            target["self_completed_task_count"] = max(0, int(completed_task_count))
            target["completed_task_count"] = max(0, int(completed_task_count))
        target["updated_at"] = now_iso()
        if target["is_completed"]:
            target["completed_at"] = now_iso()

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
