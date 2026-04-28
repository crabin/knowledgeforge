from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from langgraph.graph import END, StateGraph

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.QueryEngine.agent import QueryEngine
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
    build_validation_system_prompt,
)
from knowledgeforge.runtime.domain_task_queue_store import DomainTaskQueueStore
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.file_contract import parse_contract_block, render_contract_block, replace_contract_block
from knowledgeforge.utils.paths import sanitize_path_segment
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
        graph.add_node("generate_files", self._generate_files)
        graph.add_node("run_query_queue", self._run_query_queue)
        graph.add_node("validate_round", self._validate_round)
        graph.add_node("fill_evidence", self._fill_evidence)
        graph.add_node("run_post_storage", self._run_post_storage)
        graph.set_entry_point("generate_files")
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

    def _generate_files(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        context.prompt_profile_version = PROMPT_PROFILE_VERSION
        domain_dir = self._domain_dir(context)
        queue = self._queue_store.load(domain_dir) or self._queue_store.initialize(domain=context.domain, domain_dir=domain_dir)
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
            generated = self._generate_single_file(context, blueprint, spec, file_path)
            file_path.write_text(generated["markdown"], encoding="utf-8")
            query_tasks = self._extract_queue_tasks(generated["contract"], blueprint, file_path, queue.get("current_round", 1))
            queue["tasks"] = self._merge_queue_tasks(queue.get("tasks", []), query_tasks)
            generated_count += 1
            queue["generation_status"] = {
                "total_files": total_files,
                "completed_files": generated_count,
                "current_file": relative_path,
                "last_saved_path": file_path.as_posix(),
            }
            self._queue_store.save(domain_dir, queue)
            self._emit_workflow_event(
                state,
                "llm_generating",
                f"文件骨架已保存：{relative_path}",
                "completed",
                {"file_path": file_path.as_posix(), "enqueued_tasks": len(query_tasks)},
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
            self._queue_store.save(domain_dir, queue)
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
            self._queue_store.save(domain_dir, queue)
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
            "task_status": "filled",
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
        task_status = "verified" if result.status == "passed" else "repair_required"
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

    def _generate_single_file(self, context: RequestContext, blueprint: dict[str, Any], spec, file_path: Path) -> dict[str, Any]:
        chat_client = getattr(self._insight_engine, "_chat_client", None)
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
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception:
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
            "claims": [str(item) for item in payload.get("claims", []) if str(item).strip()] or [f"{spec.title} 需要形成可追溯知识说明。"],
            "evidence_needed": [str(item) for item in payload.get("evidence_needed", []) if str(item).strip()] or ["权威定义", "关键结论来源", "必要时的案例或趋势证据"],
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
                body.extend([f"- {item}" for item in contract["claims"]])
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
                return RoundValidationResult(
                    is_complete=bool(payload.get("is_complete")),
                    missing_evidence=[str(item) for item in payload.get("missing_evidence", []) if str(item).strip()],
                    new_tasks=[item for item in payload.get("new_tasks", []) if isinstance(item, dict)],
                    reasoning=str(payload.get("reasoning", "")).strip() or "LLM 已完成本轮验证。",
                    file_status_updates=[item for item in payload.get("file_status_updates", []) if isinstance(item, dict)],
                )
            except Exception:
                pass
        incomplete = [task for task in queue.get("tasks", []) if str(task.get("status", "")) != "completed"]
        if incomplete and int(queue.get("current_round", 1)) >= max_rounds:
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
        return RoundValidationResult(
            is_complete=not incomplete,
            missing_evidence=[str(task.get("claim_or_gap", "")) for task in incomplete],
            new_tasks=[],
            reasoning="当前轮次已根据队列状态完成验证。" if not incomplete else "仍有未完成的依据任务，需要继续补充。",
            file_status_updates=[
                {"file_path": str(task.get("target_file_path", "")), "status": "completed" if not incomplete else "partially_completed"}
                for task in queue.get("tasks", [])
            ],
        )

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
    def _route_after_validation(state: WorkflowState) -> str:
        queue = state.get("task_queue_snapshot", {})
        return "fill_evidence" if queue.get("final_status") == "ready_for_fill" else "run_query_queue"

    def _emit_workflow_event(self, state: WorkflowState, step_id: str, label: str, status: str, details: dict[str, Any] | None = None) -> None:
        event = self._make_workflow_event(step_id, label, status, details)
        if self._workflow_event_callback is not None:
            self._workflow_event_callback(state["task_id"], event)

    def _commit_state(self, state: WorkflowState, updates: dict[str, Any]) -> None:
        state.update(updates)
        if self._state_update_callback is not None:
            self._state_update_callback(state["task_id"], state)

    @staticmethod
    def _make_workflow_event(step_id: str, label: str, status: str, details: dict[str, Any] | None = None) -> WorkflowStepEvent:
        return WorkflowStepEvent(step_id=step_id, label=label, status=status, timestamp=now_iso(), details=details or {})

    def _domain_dir(self, context: RequestContext) -> Path:
        save_root = getattr(self._writer, "_config").save_root
        return save_root / sanitize_path_segment(context.domain, "domain")
