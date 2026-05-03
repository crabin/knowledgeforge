from __future__ import annotations

from contextlib import suppress
import json
import shutil
from threading import Lock, Thread
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from knowledgeforge.agent.InsightEngine.agent import InsightEngine
from knowledgeforge.agent.MediaEngine.agent import MediaEngine
from knowledgeforge.agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from knowledgeforge.agent.QueryEngine.agent import QueryEngine
from knowledgeforge.agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.config import AppConfig
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.evaluation.supplement_decision import SupplementDecisionPlanner
from knowledgeforge.graph.client import Neo4jGraphClient
from knowledgeforge.graph.neo4j_adapter import Neo4jPathMapper
from knowledgeforge.intake.clarifier import IntakeClarifier
from knowledgeforge.intake.context_builder import ContextBuilder
from knowledgeforge.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)
from knowledgeforge.models import (
    AgentMessage,
    ClarificationResult,
    EnginePlan,
    EnginePlanItem,
    FrozenVersionRecord,
    IntakeSession,
    RequestContext,
    WorkflowStepEvent,
)
from knowledgeforge.orchestrator.graph import KnowledgeGraphWorkflow
from knowledgeforge.orchestrator.state import WorkflowState
from knowledgeforge.postprocess.extractor import StructuredExtractor
from knowledgeforge.postprocess.pipeline import PostStoragePipeline
from knowledgeforge.quality.checker import QualityChecker
from knowledgeforge.runtime.audit import AuditLogger
from knowledgeforge.runtime.frozen_store import FrozenVersionStore
from knowledgeforge.runtime.intake_session_store import IntakeSessionStore
from knowledgeforge.runtime.state_store import TaskStateStore
from knowledgeforge.runtime.task_queue import RetrievalTaskQueue
from knowledgeforge.runtime.token_usage import (
    TokenUsageRecord,
    summarize_token_usage,
    token_tracking_context,
)
from knowledgeforge.reporting.report_service import ReportService
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.storage.realtime_reviewer import (
    RealtimeFileReviewer,
    RealtimeReviewCandidate,
    RealtimeReviewResult,
)
from knowledgeforge.tools.crawl4ai_adapter import Crawl4AIAdapter
from knowledgeforge.utils.time import now_iso
from knowledgeforge.versioning.recorder import VersionRecorder


def _format_generation_prefix(details: dict[str, Any]) -> str:
    current_file = str(details.get("current_file", "") or "").strip()
    completed_files = details.get("completed_files")
    total_files = details.get("total_files")
    progress = ""
    if total_files not in {None, ""}:
        current_index = int(completed_files or 0) + 1
        progress = f"[{current_index}/{total_files}] "
    if current_file:
        return f"{progress}{current_file} · "
    return progress


class TaskService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._context_builder = ContextBuilder()
        self._state_store = TaskStateStore(config.task_state_root)
        self._intake_store = IntakeSessionStore(config.intake_session_root)
        self._audit_logger = AuditLogger(config.audit_root)
        self._frozen_store = FrozenVersionStore(config.frozen_root)
        self._report_service = ReportService()
        self._realtime_file_reviewer = RealtimeFileReviewer(config)
        self._writer = MarkdownKnowledgeWriter(config)
        self._retrieval_task_queue = RetrievalTaskQueue(
            max_network_concurrency=config.max_network_task_concurrency,
            max_llm_concurrency=config.max_llm_task_concurrency,
        )
        crawl4ai_adapter = Crawl4AIAdapter(
            enabled=config.enable_crawl4ai,
            headless=config.crawl4ai_headless,
            verbose=config.crawl4ai_verbose,
            page_timeout_ms=config.crawl4ai_page_timeout_ms,
        )
        planning_chat_client = OpenAICompatibleChatClient(
            config.openai,
            timeout=config.plan_llm_timeout,
            operation="planning.chat_json",
            token_usage_callback=self._record_token_usage,
            llm_event_callback=self._log_llm_event,
            max_retries=config.plan_llm_max_retries,
        )
        generation_chat_client = OpenAICompatibleChatClient(
            config.openai,
            timeout=config.generation_llm_timeout,
            operation="generation.chat_json",
            token_usage_callback=self._record_token_usage,
            llm_event_callback=self._log_llm_event,
            max_retries=config.generation_llm_max_retries,
        )
        execution_chat_client = OpenAICompatibleChatClient(
            config.openai,
            timeout=config.execution_llm_timeout,
            operation="execution.chat_json",
            token_usage_callback=self._record_token_usage,
            llm_event_callback=self._log_llm_event,
            max_retries=config.execution_llm_max_retries,
        )
        query_embedding_client = OpenAICompatibleEmbeddingClient(
            config.openai,
            timeout=2.0,
            operation="query.embeddings",
            token_usage_callback=self._record_token_usage,
            llm_event_callback=self._log_llm_event,
        )
        self._intake_clarifier = IntakeClarifier(
            OpenAICompatibleChatClient(
                config.openai,
                timeout=1.0,
                operation="intake.clarify",
                token_usage_callback=self._record_token_usage,
                llm_event_callback=self._log_llm_event,
                max_retries=config.intake_llm_max_retries,
            )
        )
        self._graph_client = Neo4jGraphClient(config.neo4j)
        self._workflow = KnowledgeGraphWorkflow(
            insight_engine=InsightEngine(chat_client=planning_chat_client),
            query_engine=QueryEngine(
                chat_client=planning_chat_client,
                embedding_client=query_embedding_client,
                crawler=(
                    DomainKnowledgeCrawler(crawl4ai_adapter=crawl4ai_adapter)
                    if config.enable_live_crawlers
                    else _NoopQueryCrawler()
                ),
                event_callback=self._log_realtime_query_event,
                realtime_file_callback=self._review_realtime_file,
                max_concurrent_network_tasks=config.max_query_network_concurrency,
                task_queue=self._retrieval_task_queue,
                save_root=config.save_root,
            ),
            media_engine=MediaEngine(
                chat_client=execution_chat_client,
                planning_chat_client=planning_chat_client,
                crawler=(
                    MediaPerspectiveCrawler(crawl4ai_adapter=crawl4ai_adapter)
                    if config.enable_live_crawlers
                    else _NoopMediaCrawler()
                ),
                event_callback=self._log_realtime_media_event,
                realtime_file_callback=self._review_realtime_file,
                max_concurrent_network_tasks=config.max_network_task_concurrency,
                task_queue=self._retrieval_task_queue,
                save_root=config.save_root,
            ),
            evaluator=CompletenessEvaluator(),
            supplement_planner=SupplementDecisionPlanner(
                save_root=config.save_root,
                chat_client=planning_chat_client,
            ),
            writer=self._writer,
            post_storage_pipeline=PostStoragePipeline(
                extractor=StructuredExtractor(),
                graph_mapper=Neo4jPathMapper(client=self._graph_client),
                quality_checker=QualityChecker(),
                version_recorder=VersionRecorder(),
                strict_graph_sync=config.strict_graph_sync,
            ),
            workflow_event_callback=self._log_workflow_step_event,
            state_update_callback=self._persist_running_state_update,
            generation_chat_client=generation_chat_client,
        )
        self._tasks: dict[str, WorkflowState] = {}
        self._task_lock = Lock()

    def get_config_status(self) -> dict[str, Any]:
        return self._config.show_config_status()

    def run_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_context = self._build_confirmed_context_from_payload(payload)
        initial_state = self._create_initial_state(request_context, audit_source="api")
        with token_tracking_context(initial_state["task_id"]):
            final_state = self._workflow.run(initial_state)
        return self._persist_and_serialize(final_state, "task_completed")

    def start_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_context = self._build_confirmed_context_from_payload(payload)
        return self._start_task_from_context(request_context)

    def _build_confirmed_context_from_payload(self, payload: dict[str, Any]) -> RequestContext:
        message = str(payload.get("message") or payload.get("original_input") or payload.get("domain") or "").strip()
        if not message:
            raise ValueError("`domain` or `message` is required.")
        with token_tracking_context("direct-intake"):
            clarification = self._intake_clarifier.clarify([message])
        if clarification.intent != "knowledge_collection":
            raise ValueError("direct task input is not confirmed for knowledge collection; please clarify the intent first.")
        normalized_payload = dict(payload)
        normalized_payload["domain"] = clarification.normalized_domain
        normalized_payload["normalized_domain"] = clarification.normalized_domain
        normalized_payload["original_input"] = clarification.original_input
        normalized_payload["intent"] = clarification.intent
        normalized_payload["output_language"] = clarification.output_language
        normalized_payload["search_language"] = clarification.search_language
        normalized_payload["search_terms"] = clarification.search_terms
        normalized_payload["clarification_summary"] = clarification.clarification_summary
        normalized_payload["confirmed"] = True
        if not normalized_payload.get("subdomains"):
            normalized_payload["subdomains"] = clarification.subdomains
        if not normalized_payload.get("focus_points"):
            normalized_payload["focus_points"] = clarification.focus_points
        return self._context_builder.build(normalized_payload)

    def _start_task_from_context(self, request_context: RequestContext) -> dict[str, Any]:
        initial_state = self._create_initial_state(request_context, audit_source="api_async")
        task_id = initial_state["task_id"]
        with self._task_lock:
            self._tasks[task_id] = initial_state
        payload_dict = self._serialize_state(initial_state)
        self._state_store.save(task_id, payload_dict)
        self._audit_logger.log(
            task_id,
            "task_started_async",
            {"status": "running", "source": "api_async", "round": initial_state.get("round_number", 1)},
        )
        Thread(target=self._run_started_task, args=(initial_state,), daemon=True).start()
        return self._attach_runtime_observability(payload_dict)

    def _persist_plan_failed(self, state: WorkflowState, exc: Exception) -> dict[str, Any]:
        task_id = state["task_id"]
        message = str(exc)
        event = WorkflowStepEvent(
            step_id="planning",
            label="三路计划生成失败",
            status="blocked",
            timestamp=now_iso(),
            details={"error": message},
        )
        state["task_status"] = "plan_failed"
        state["current_step"] = "planning"
        state["current_action"] = f"计划生成失败：{message}"
        state.setdefault("workflow_events", []).append(event)
        with self._task_lock:
            self._tasks[task_id] = state
        payload_dict = self._serialize_state(state)
        self._state_store.save(task_id, payload_dict)
        self._audit_logger.log(
            task_id,
            "agent_plan_failed",
            {"status": "plan_failed", "error": message},
        )
        self._audit_logger.log(task_id, "workflow_step", event.to_dict())
        return self._attach_runtime_observability(payload_dict)

    def get_task_plan(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        self._refresh_task_queue_snapshot_from_path(task)
        return {
            "task_id": task_id,
            "task_status": task.get("task_status", "unknown"),
            "task_queue_path": task.get("task_queue_path", ""),
            "task_queue_snapshot": task.get("task_queue_snapshot", {}),
        }

    def update_plan_item(
        self,
        task_id: str,
        agent_name: str,
        plan_item_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        stored = self._state_store.load(task_id)
        if stored is None:
            return None
        raise ValueError("当前流程已改为直接执行，不再支持计划项编辑。")

    def delete_plan_item(
        self,
        task_id: str,
        agent_name: str,
        plan_item_id: str,
    ) -> dict[str, Any] | None:
        stored = self._state_store.load(task_id)
        if stored is None:
            return None
        raise ValueError("当前流程已改为直接执行，不再支持计划项删除。")

    def confirm_task_plan(self, task_id: str) -> dict[str, Any] | None:
        stored = self.get_task(task_id)
        if stored is None:
            return None
        raise ValueError("当前流程已改为直接执行，不再需要确认计划。")

    def list_tasks(self) -> dict[str, Any]:
        tasks = self._state_store.list()
        in_memory_ids = {task["task_id"] for task in tasks}
        for task_id, state in self._tasks.items():
            if task_id in in_memory_ids:
                continue
            tasks.append(self._summarize_state(self._serialize_state(state)))
        tasks = sorted(tasks, key=lambda item: item["updated_at"], reverse=True)
        return {"count": len(tasks), "tasks": tasks}

    def initialize_system(self) -> dict[str, Any]:
        running_task_ids = self._collect_running_task_ids()
        if running_task_ids:
            raise ValueError("cannot initialize system while tasks are running.")

        with self._task_lock:
            self._tasks.clear()

        storage_roots = [
            ("tasks", self._config.task_state_root),
            ("sessions", self._config.intake_session_root),
            ("audit", self._config.audit_root),
            ("frozen_versions", self._config.frozen_root),
            ("saved_files", self._config.save_root),
        ]
        storage_results = [self._clear_runtime_directory(name, path) for name, path in storage_roots]
        graph_result: dict[str, Any]
        try:
            graph_result = self._graph_client.clear_knowledgeforge_graph()
        except Exception as exc:  # pragma: no cover - depends on local Neo4j availability.
            graph_result = {
                "status": "unavailable",
                "error": self._sanitize_graph_error(str(exc)),
            }

        return {
            "status": "initialized",
            "initialized_at": now_iso(),
            "scope": "runtime_artifacts_only",
            "preserved": [
                "source_code",
                "configuration",
                "project_docs",
                "dependencies",
                "chroma_db",
                "mysql",
                "application_log_files",
            ],
            "storage": storage_results,
            "neo4j": graph_result,
        }

    def update_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        stored = self.get_task(task_id)
        if stored is None:
            return None
        if self._is_running_status(stored.get("task_status", "")):
            raise ValueError("running tasks cannot be updated.")

        request_updates = payload.get("request_context") if isinstance(payload.get("request_context"), dict) else payload
        request_context = dict(stored.get("request_context") or {})
        changed: dict[str, Any] = {}
        allowed_context_fields = {
            "domain",
            "normalized_domain",
            "subdomains",
            "time_window",
            "focus_points",
            "constraints",
            "initial_strategy",
            "original_input",
            "output_language",
            "search_language",
            "search_terms",
            "clarification_summary",
            "confirmed",
        }
        for field in allowed_context_fields:
            if field not in request_updates:
                continue
            value = request_updates[field]
            if field in {"subdomains", "focus_points", "constraints", "initial_strategy", "search_terms"}:
                if not isinstance(value, list):
                    raise ValueError(f"`{field}` must be a list.")
                value = [str(item).strip() for item in value if str(item).strip()]
            elif field == "confirmed":
                value = bool(value)
            else:
                value = str(value).strip()
            if request_context.get(field) != value:
                request_context[field] = value
                changed[f"request_context.{field}"] = value

        if "task_status" in payload:
            status = str(payload["task_status"]).strip()
            if not status:
                raise ValueError("`task_status` cannot be empty.")
            if stored.get("task_status") != status:
                stored["task_status"] = status
                changed["task_status"] = status

        metadata = stored.setdefault("management_metadata", {})
        if "management_note" in payload:
            note = str(payload["management_note"]).strip()
            metadata["note"] = note
            changed["management_metadata.note"] = note
        if changed:
            metadata["updated_at"] = now_iso()
            stored["request_context"] = request_context
            with self._task_lock:
                self._tasks[task_id] = stored
            self._state_store.save(task_id, stored)
            self._audit_logger.log(task_id, "task_updated", {"changed_fields": sorted(changed.keys())})
        return self._attach_runtime_observability(stored)

    def delete_task(self, task_id: str) -> dict[str, Any] | None:
        stored = self.get_task(task_id)
        if stored is None:
            return None
        if self._is_running_status(stored.get("task_status", "")):
            raise ValueError("running tasks cannot be deleted.")
        self._audit_logger.log(
            task_id,
            "task_deleted",
            {
                "status": stored.get("task_status", "unknown"),
                "domain": (stored.get("request_context") or {}).get("domain", ""),
            },
        )
        with self._task_lock:
            self._tasks.pop(task_id, None)
        state_deleted = self._state_store.delete(task_id)
        frozen_deleted = self._frozen_store.delete(task_id)
        return {
            "task_id": task_id,
            "deleted": True,
            "state_deleted": state_deleted,
            "frozen_deleted": frozen_deleted,
        }

    def _collect_running_task_ids(self) -> list[str]:
        task_ids: set[str] = set()
        for task in self._state_store.list():
            if self._is_running_status(task.get("task_status", "")):
                task_ids.add(str(task.get("task_id", "")))
        with self._task_lock:
            for task_id, state in self._tasks.items():
                if self._is_running_status(state.get("task_status", "")):
                    task_ids.add(task_id)
        return sorted(task_id for task_id in task_ids if task_id)

    def _clear_runtime_directory(self, name: str, path: Path) -> dict[str, Any]:
        root = self._validate_initialization_root(path)
        files_deleted = 0
        directories_deleted = 0
        if root.exists():
            for child in root.iterdir():
                if child.is_dir() and not child.is_symlink():
                    files_deleted += sum(1 for nested in child.rglob("*") if nested.is_file() or nested.is_symlink())
                    directories_deleted += sum(1 for nested in child.rglob("*") if nested.is_dir() and not nested.is_symlink())
                    directories_deleted += 1
                    shutil.rmtree(child)
                else:
                    with suppress(FileNotFoundError):
                        child.unlink()
                    files_deleted += 1
        root.mkdir(parents=True, exist_ok=True)
        return {
            "name": name,
            "path": root.as_posix(),
            "files_deleted": files_deleted,
            "directories_deleted": directories_deleted,
        }

    @staticmethod
    def _validate_initialization_root(path: Path) -> Path:
        root = path.resolve()
        cwd = Path.cwd().resolve()
        forbidden = {Path("/").resolve(), cwd, cwd.parent, Path.home().resolve()}
        if root in forbidden or cwd.is_relative_to(root):
            raise ValueError(f"refusing to initialize unsafe path: {root}")
        if root.is_symlink():
            raise ValueError(f"refusing to initialize symlink path: {root}")
        return root

    @staticmethod
    def _sanitize_graph_error(message: str) -> str:
        lowered = message.lower()
        if "authentication" in lowered or "password" in lowered or "credentials" in lowered:
            return "Neo4j authentication failed."
        if "bolt://" in message or "neo4j://" in message:
            return "Neo4j connection failed."
        return message[:200]

    def create_intake_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message", payload.get("domain", ""))).strip()
        if not message:
            raise ValueError("`message` is required.")
        session_id = uuid.uuid4().hex
        with token_tracking_context(session_id):
            clarification = self._intake_clarifier.clarify([message])
        now = now_iso()
        session = IntakeSession(
            session_id=session_id,
            status="draft",
            messages=[AgentMessage(role="user", content=message, metadata={"source": "api"})],
            candidate_context=clarification,
            created_at=now,
            updated_at=now,
        )
        payload_dict = session.to_dict()
        self._intake_store.save(session_id, payload_dict)
        self._audit_logger.log(
            session_id,
            "intake_session_created",
            {"intent": clarification.intent, "normalized_domain": clarification.normalized_domain},
        )
        self._audit_logger.log(
            session_id,
            "intake_clarified",
            {
                "needs_clarification": clarification.needs_clarification,
                "output_language": clarification.output_language,
            },
        )
        return self._attach_runtime_observability(payload_dict)

    def append_intake_message(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        stored = self._intake_store.load(session_id)
        if stored is None:
            return None
        message = str(payload.get("message", "")).strip()
        if not message:
            raise ValueError("`message` is required.")
        messages = self._deserialize_messages(stored.get("messages", []))
        messages.append(AgentMessage(role="user", content=message, metadata={"source": "api"}))
        with token_tracking_context(session_id):
            clarification = self._intake_clarifier.clarify([item.content for item in messages])
        stored["messages"] = [item.to_dict() for item in messages]
        stored["candidate_context"] = clarification.to_dict()
        stored["updated_at"] = now_iso()
        self._intake_store.save(session_id, stored)
        self._audit_logger.log(
            session_id,
            "intake_clarified",
            {
                "intent": clarification.intent,
                "needs_clarification": clarification.needs_clarification,
                "output_language": clarification.output_language,
            },
        )
        return self._attach_runtime_observability(stored)

    def confirm_intake_session(self, session_id: str) -> dict[str, Any] | None:
        stored = self._intake_store.load(session_id)
        if stored is None:
            return None
        clarification = ClarificationResult(**stored["candidate_context"])
        if clarification.intent != "knowledge_collection":
            raise ValueError("intake session is not confirmed for knowledge collection.")
        request_context = self._context_builder.build(
            {
                "domain": clarification.normalized_domain,
                "original_input": clarification.original_input,
                "normalized_domain": clarification.normalized_domain,
                "intent": clarification.intent,
                "output_language": clarification.output_language,
                "search_language": clarification.search_language,
                "search_terms": clarification.search_terms,
                "subdomains": clarification.subdomains,
                "focus_points": clarification.focus_points,
                "clarification_summary": clarification.clarification_summary,
                "confirmed": True,
            }
        )
        self._audit_logger.log(
            session_id,
            "intake_confirmed",
            {"domain": request_context.domain, "output_language": request_context.output_language},
        )
        task_payload = self._start_task_from_context(request_context)
        stored["status"] = "confirmed"
        stored["task_id"] = task_payload["task_id"]
        stored["updated_at"] = now_iso()
        self._intake_store.save(session_id, stored)
        self._audit_logger.log(
            task_payload["task_id"],
            "task_created_from_intake",
            {"session_id": session_id, "domain": request_context.domain},
        )
        return {"intake_session": stored, "task": task_payload}

    def _run_workflow(self, request_context: RequestContext, *, audit_source: str) -> dict[str, Any]:
        initial_state = self._create_initial_state(request_context, audit_source=audit_source)
        with token_tracking_context(initial_state["task_id"]):
            final_state = self._workflow.run(initial_state)
        return self._persist_and_serialize(final_state, "task_completed")

    def _approve_plans_in_state(self, state: WorkflowState) -> WorkflowState:
        approved_at = now_iso()
        for plan in state.get("agent_plans", {}).values():
            plan.status = "approved"
            plan.approved_at = approved_at
            for item in plan.plan_items:
                item.status = "approved"
        state["plan_approved_at"] = approved_at
        state["task_status"] = "running"
        state["current_step"] = "collecting"
        state["current_action"] = "用户已确认三路计划，开始并行执行。"
        state.setdefault("workflow_events", []).append(
            WorkflowStepEvent(
                step_id="awaiting_confirmation",
                label="等待用户确认计划",
                status="completed",
                timestamp=approved_at,
            )
        )
        return state

    def _create_initial_state(self, request_context: RequestContext, *, audit_source: str) -> WorkflowState:
        task_id = uuid.uuid4().hex
        request_context.task_id = task_id
        initial_state: WorkflowState = {
            "task_id": task_id,
            "request_context": request_context,
            "messages": [
                AgentMessage(
                    role="user",
                    content=f"为领域 {request_context.domain} 启动知识沉淀任务。",
                    metadata={"source": audit_source},
                )
            ],
            "round_number": 1,
            "max_rounds": self._config.max_rounds,
            "task_status": "running" if audit_source == "api_async" else "created",
            "current_step": "intent_recognition",
            "current_action": "真实意图与领域名称已确认，等待生成目录结构图谱。",
            "updated_at": now_iso(),
        }
        self._audit_logger.log(
            task_id,
            "task_created",
            {
                "domain": request_context.domain,
                "normalized_domain": request_context.normalized_domain,
                "round": 1,
                "source": audit_source,
            },
        )
        return initial_state

    def _run_started_task(self, initial_state: WorkflowState) -> None:
        task_id = initial_state["task_id"]
        try:
            with token_tracking_context(task_id):
                final_state = self._workflow.run(initial_state)
        except Exception as exc:
            failed_state = dict(initial_state)
            failed_state["task_status"] = "failed"
            with self._task_lock:
                self._tasks[task_id] = failed_state
            payload = self._serialize_state(failed_state)
            self._state_store.save(task_id, payload)
            self._audit_logger.log(task_id, "task_failed", {"error": str(exc)})
            return
        self._persist_and_serialize(final_state, "task_completed")

    def _sync_plan_document(self, stored: dict[str, Any], agent_name: str) -> None:
        plan_path = (stored.get("plan_document_paths") or {}).get(agent_name)
        if not plan_path:
            return
        plan_payload = (stored.get("agent_plans") or {}).get(agent_name)
        if not isinstance(plan_payload, dict):
            return
        try:
            context = self._deserialize_request_context(stored["request_context"])
            plan = self._deserialize_engine_plans({agent_name: plan_payload})[agent_name]
            synced_path = self._writer.write_agent_plan_document(
                context=context,
                plan=plan,
                round_number=int(stored.get("round_number", 1)),
                document_path=plan_path,
            )
        except Exception as exc:
            self._audit_logger.log(
                stored["task_id"],
                "plan_document_sync_failed",
                {"agent": agent_name, "path": plan_path, "error": str(exc)},
            )
            return
        stored.setdefault("plan_document_paths", {})[agent_name] = synced_path

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if task_id in self._tasks:
            return self._attach_runtime_observability(self._serialize_state(self._tasks[task_id]))
        stored = self._state_store.load(task_id)
        if stored is None:
            return None
        return self._attach_runtime_observability(stored)

    def get_frozen_version(self, task_id: str) -> dict[str, Any] | None:
        return self._frozen_store.load(task_id)

    def get_task_logs(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        audit_logs = self._audit_logger.read(task_id)
        self._backfill_audit_logs_from_task(task_id, task, audit_logs)
        refreshed_logs = self._audit_logger.read(task_id)
        queue_snapshot = task.get("task_queue_snapshot", {}) or {}
        return {
            "task_id": task_id,
            "task_status": task.get("task_status"),
            "current_step": task.get("current_step"),
            "current_action": task.get("current_action"),
            "round_number": task.get("round_number"),
            "agent_plans": task.get("agent_plans", {}),
            "workflow_events": task.get("workflow_events", []),
            "structure_graph": task.get("structure_graph", (task.get("request_context") or {}).get("structure_graph", {})),
            "graph_snapshot": task.get("graph_snapshot", {}),
            "graph_event": task.get("graph_event", {}),
            "file_update": task.get("file_update", {}),
            "generation_progress": task.get("generation_progress", {}),
            "task_queue_snapshot": queue_snapshot,
            "queue_summary": self._build_queue_summary(queue_snapshot),
            "log_summary": self._build_log_summary(refreshed_logs),
            "llm_activity": self._build_llm_activity(refreshed_logs),
            "recent_errors": self._collect_recent_errors(refreshed_logs),
            "log_files": {
                "audit_jsonl": self._audit_logger.path_for(task_id).as_posix(),
                "application_log": (self._config.app_log_root / "knowledgeforge-server.log").as_posix(),
            },
            "logs": refreshed_logs,
            "token_usage": summarize_token_usage(refreshed_logs),
        }

    def get_task_graph_snapshot(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        request_context = task.get("request_context") or {}
        domain = str(request_context.get("domain") or request_context.get("normalized_domain") or "").strip()
        limits = {"nodes": 300, "edges": 600}
        if not domain:
            return {
                "task_id": task_id,
                "domain": "",
                "status": "unavailable",
                "refreshed_at": now_iso(),
                "graph": {"nodes": [], "edges": []},
                "limits": limits,
                "error": "Task domain is unavailable.",
            }
        try:
            graph = self._graph_client.snapshot_domain_graph(
                domain=domain,
                node_limit=limits["nodes"],
                relationship_limit=limits["edges"],
            )
        except Exception:
            local_graph = task.get("graph_snapshot") or {}
            if local_graph.get("nodes") or local_graph.get("edges"):
                return {
                    "task_id": task_id,
                    "domain": domain,
                    "status": "local",
                    "refreshed_at": now_iso(),
                    "graph": local_graph,
                    "limits": limits,
                    "error": "Neo4j graph snapshot unavailable; using task-local graph snapshot.",
                }
            return {
                "task_id": task_id,
                "domain": domain,
                "status": "unavailable",
                "refreshed_at": now_iso(),
                "graph": {"nodes": [], "edges": []},
                "limits": limits,
                "error": "Neo4j graph snapshot unavailable.",
            }
        return {
            "task_id": task_id,
            "domain": domain,
            "status": "ok",
            "refreshed_at": now_iso(),
            "graph": graph,
            "limits": limits,
        }

    def generate_report(self, task_id: str) -> dict[str, Any] | None:
        frozen_payload = self._frozen_store.load(task_id)
        if frozen_payload is None:
            return None
        frozen_record = FrozenVersionRecord(**frozen_payload)
        report = self._report_service.build_report(frozen_record)
        self._audit_logger.log(
            task_id,
            "report_generated",
            {"version": frozen_record.version, "source": "frozen_version"},
        )
        return report.to_dict()

    def resume_task(self, task_id: str) -> dict[str, Any] | None:
        stored = self.get_task(task_id)
        if stored is None:
            return None

        round_number = int(stored.get("round_number", 1))
        if round_number >= self._config.max_rounds:
            stored["task_status"] = "max_rounds_reached"
            self._state_store.save(task_id, stored)
            self._audit_logger.log(
                task_id,
                "max_rounds_reached",
                {"round": round_number, "max_rounds": self._config.max_rounds},
            )
            return stored

        request_context = self._deserialize_request_context(stored["request_context"])
        request_context.task_id = task_id
        previous_status = str(stored.get("task_status", "unknown"))
        messages = self._deserialize_messages(stored.get("messages", []))
        messages.append(
            AgentMessage(
                role="system",
                content=f"任务因 {previous_status} 进入恢复执行。",
                metadata={"resume_from_status": previous_status, "next_round": round_number + 1},
            )
        )
        resumed_state: WorkflowState = {
            "task_id": task_id,
            "request_context": request_context,
            "messages": messages,
            "round_number": round_number + 1,
            "max_rounds": self._config.max_rounds,
            "task_status": "resumed",
        }
        self._audit_logger.log(
            task_id,
            "task_resumed",
            {"from_status": previous_status, "round": round_number + 1},
        )
        with token_tracking_context(task_id):
            final_state = self._workflow.run(resumed_state)
        return self._persist_and_serialize(final_state, "task_completed")

    def _persist_and_serialize(self, state: WorkflowState, audit_event: str) -> dict[str, Any]:
        task_id = state["task_id"]
        self._finalize_successful_plan_statuses(state)
        with self._task_lock:
            self._tasks[task_id] = state
        payload = self._serialize_state(state)
        self._freeze_version_if_eligible(task_id, payload)
        self._attach_runtime_observability(payload)
        self._state_store.save(task_id, payload)
        self._log_agent_execution(task_id, payload)
        self._audit_logger.log(
            task_id,
            audit_event,
            {
                "status": payload.get("task_status"),
                "round": payload.get("round_number"),
            },
        )
        return payload

    def _record_token_usage(self, record: TokenUsageRecord) -> None:
        self._audit_logger.log(record.task_id, "token_usage_recorded", record.to_dict())

    def _log_llm_event(self, payload: dict[str, Any]) -> None:
        from knowledgeforge.runtime.token_usage import current_token_task_id

        task_id = str(payload.get("task_id") or current_token_task_id() or "")
        if not task_id:
            return
        enriched_payload = dict(payload)
        task_snapshot = self.get_task(task_id)
        if task_snapshot is not None:
            generation = task_snapshot.get("generation_progress", {}) or {}
            if generation:
                enriched_payload.setdefault("current_file", generation.get("current_file", ""))
                enriched_payload.setdefault("completed_files", generation.get("completed_files", 0))
                enriched_payload.setdefault("total_files", generation.get("total_files", 0))
        status = str(payload.get("status", "unknown"))
        event = {
            "started": "llm_call_started",
            "completed": "llm_call_completed",
            "failed": "llm_call_failed",
        }.get(status, "llm_call_event")
        self._audit_logger.log(task_id, event, enriched_payload)
        self._refresh_running_task_snapshot(
            task_id,
            {
                "agent": "LLM",
                "event": event,
                "timestamp": now_iso(),
                "node": "OpenAICompatibleClient",
                "details": enriched_payload,
            },
        )

    def _attach_runtime_observability(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._refresh_task_queue_snapshot_from_path(payload)
        self._attach_execution_log(payload)
        task_id = str(payload.get("task_id") or payload.get("session_id") or "")
        if task_id:
            payload["token_usage"] = summarize_token_usage(self._audit_logger.read(task_id))
        return payload

    @staticmethod
    def _build_queue_summary(queue: dict[str, Any]) -> dict[str, Any]:
        tasks = queue.get("tasks", []) if isinstance(queue, dict) else []
        counts = {
            "total": len(tasks),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "insufficient": 0,
            "blocked": 0,
        }
        current_task = None
        for task in tasks:
            status = str(task.get("status", "pending"))
            if status in counts:
                counts[status] += 1
            if current_task is None and status == "running":
                current_task = {
                    "task_id": task.get("task_id"),
                    "task_type": task.get("task_type"),
                    "target_file_path": task.get("target_file_path"),
                    "target_section": task.get("target_section"),
                    "query_text": task.get("query_text"),
                    "attempts": task.get("attempts"),
                    "round_number": task.get("round_number"),
                }
        return {
            "final_status": queue.get("final_status") if isinstance(queue, dict) else "",
            "current_round": queue.get("current_round") if isinstance(queue, dict) else 1,
            "generation_status": queue.get("generation_status", {}) if isinstance(queue, dict) else {},
            "counts": counts,
            "current_task": current_task or {},
            "round_summaries": queue.get("round_summaries", []) if isinstance(queue, dict) else [],
        }

    @staticmethod
    def _build_log_summary(logs: list[dict[str, Any]]) -> dict[str, Any]:
        llm_events = [entry for entry in logs if str(entry.get("event", "")).startswith("llm_call_")]
        failed_events = [
            entry
            for entry in logs
            if "failed" in str(entry.get("event", "")).lower() or str(entry.get("details", {}).get("status", "")).lower() in {"failed", "blocked"}
        ]
        last_event = logs[-1] if logs else {}
        return {
            "total_events": len(logs),
            "workflow_steps": len([entry for entry in logs if entry.get("event") == "workflow_step"]),
            "llm_event_count": len(llm_events),
            "failed_event_count": len(failed_events),
            "last_event": {
                "event": last_event.get("event", ""),
                "timestamp": last_event.get("timestamp", ""),
            },
        }

    @staticmethod
    def _build_llm_activity(logs: list[dict[str, Any]]) -> dict[str, Any]:
        llm_events = [entry for entry in logs if str(entry.get("event", "")).startswith("llm_call_")]
        latest = llm_events[-1] if llm_events else {}
        in_flight = 0
        request_state: dict[str, str] = {}
        for entry in llm_events:
            details = entry.get("details", {}) or {}
            request_id = str(details.get("request_id", ""))
            if not request_id:
                continue
            request_state[request_id] = str(details.get("status", ""))
        for status in request_state.values():
            if status == "started":
                in_flight += 1
        return {
            "in_flight_requests": in_flight,
            "latest_event": latest,
            "recent_events": llm_events[-5:],
        }

    @staticmethod
    def _collect_recent_errors(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recent_errors: list[dict[str, Any]] = []
        for entry in reversed(logs):
            event = str(entry.get("event", ""))
            details = entry.get("details", {}) or {}
            error = str(details.get("error", "")).strip()
            if "failed" not in event and not error:
                continue
            recent_errors.append(
                {
                    "event": event,
                    "timestamp": entry.get("timestamp", ""),
                    "error": error,
                    "agent": details.get("agent", ""),
                    "operation": details.get("operation", ""),
                }
            )
            if len(recent_errors) >= 5:
                break
        return list(reversed(recent_errors))

    @staticmethod
    def _refresh_task_queue_snapshot_from_path(payload: dict[str, Any]) -> None:
        queue_path = str(payload.get("task_queue_path") or "").strip()
        if not queue_path:
            return
        path = Path(queue_path)
        if not path.exists():
            return
        try:
            queue = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        payload["task_queue_snapshot"] = queue
        if isinstance(queue.get("generation_status"), dict):
            payload["generation_progress"] = queue["generation_status"]

    @staticmethod
    def _finalize_successful_plan_statuses(state: WorkflowState) -> None:
        if state.get("task_status") != "verified":
            return
        for plan in state.get("agent_plans", {}).values():
            plan.status = "approved"
            for item in plan.plan_items:
                item.status = "completed"

    def _attach_execution_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        execution_log = payload.setdefault("execution_log", [])
        agent_outputs = payload.get("agent_outputs", {})
        for agent_name, output in agent_outputs.items():
            for entry in output.get("execution_log", []):
                record = {
                    "agent": agent_name,
                    "event": str(entry.get("event", "agent_execution_event")),
                    "timestamp": entry.get("timestamp"),
                    "node": entry.get("node"),
                    "details": entry.get("details", {}),
                }
                if record not in execution_log:
                    execution_log.append(record)
        return payload

    def _log_agent_execution(self, task_id: str, payload: dict[str, Any]) -> None:
        for entry in payload.get("execution_log", []):
            event = str(entry.get("event", "agent_execution_event"))
            if event.startswith("query_") and event != "query_engine_fallback_result":
                continue
            if event.startswith("media_"):
                continue
            details = dict(entry.get("details", {}))
            details["agent"] = entry.get("agent")
            details["node"] = entry.get("node")
            details["event_timestamp"] = entry.get("timestamp")
            self._audit_logger.log(task_id, event, details)

    def _log_realtime_query_event(self, task_id: str, entry: dict[str, Any]) -> None:
        details = dict(entry.get("details", {}))
        details["agent"] = "QueryEngine"
        details["node"] = entry.get("node")
        details["event_timestamp"] = entry.get("timestamp")
        event = str(entry.get("event", "query_execution_event"))
        self._audit_logger.log(task_id, event, details)
        self._refresh_running_task_snapshot(
            task_id,
            {
                "agent": "QueryEngine",
                "event": event,
                "timestamp": entry.get("timestamp"),
                "node": entry.get("node"),
                "details": entry.get("details", {}),
            },
        )

    def _log_realtime_media_event(self, task_id: str, entry: dict[str, Any]) -> None:
        details = dict(entry.get("details", {}))
        details["agent"] = "MediaEngine"
        details["node"] = entry.get("node")
        details["event_timestamp"] = entry.get("timestamp")
        event = str(entry.get("event", "media_execution_event"))
        self._audit_logger.log(task_id, event, details)
        self._refresh_running_task_snapshot(
            task_id,
            {
                "agent": "MediaEngine",
                "event": event,
                "timestamp": entry.get("timestamp"),
                "node": entry.get("node"),
                "details": entry.get("details", {}),
            },
        )

    def _review_realtime_file(
        self,
        task_id: str,
        candidate: RealtimeReviewCandidate,
    ) -> RealtimeReviewResult:
        result = self._realtime_file_reviewer.review_and_save(candidate)
        self._audit_logger.log(
            task_id,
            "realtime_file_reviewed",
            {
                "agent": candidate.agent,
                "round": candidate.round_number,
                "plan_item_id": candidate.plan_item_id,
                "query": candidate.query,
                "source_type": candidate.source_type,
                "platform_type": candidate.platform_type,
                **result.to_dict(),
            },
        )
        return result

    def _log_workflow_step_event(self, task_id: str, event: WorkflowStepEvent) -> None:
        payload = event.to_dict()
        self._audit_logger.log(task_id, "workflow_step", payload)
        with self._task_lock:
            state = self._tasks.get(task_id)
            if state is None:
                stored = self._state_store.load(task_id)
                if stored is None:
                    return
                events = stored.setdefault("workflow_events", [])
                if payload not in events:
                    events.append(payload)
                stored["current_step"] = event.step_id
                stored["current_action"] = event.label
                stored["updated_at"] = now_iso()
                self._state_store.save(task_id, stored)
                return
            events = state.setdefault("workflow_events", [])
            if event not in events:
                events.append(event)
            state["current_step"] = event.step_id
            state["current_action"] = event.label
            state["updated_at"] = now_iso()
            self._state_store.save(task_id, self._serialize_state(state))

    def _backfill_audit_logs_from_task(
        self,
        task_id: str,
        task: dict[str, Any],
        audit_logs: list[dict[str, Any]],
    ) -> None:
        existing = {
            self._audit_dedupe_key(entry.get("event"), entry.get("details", {}))
            for entry in audit_logs
        }
        for entry in task.get("execution_log", []):
            event = str(entry.get("event", "agent_execution_event"))
            if event.startswith("llm_call_"):
                continue
            details = dict(entry.get("details", {}))
            details["agent"] = entry.get("agent")
            details["node"] = entry.get("node")
            details["event_timestamp"] = entry.get("timestamp")
            key = self._audit_dedupe_key(event, details)
            if key in existing:
                continue
            self._audit_logger.log(task_id, event, details)
            existing.add(key)

    @staticmethod
    def _audit_dedupe_key(event: object, details: dict[str, Any]) -> tuple[str, str, str, str]:
        event_name = str(event or "")
        event_timestamp = str(details.get("event_timestamp") or "")
        node = str(details.get("node") or "")
        stable_details = {
            key: value
            for key, value in details.items()
            if key not in {"agent", "node", "event_timestamp"}
        }
        return (event_name, event_timestamp, node, str(sorted(stable_details.items())))

    def _refresh_running_task_snapshot(self, task_id: str, entry: dict[str, Any]) -> None:
        with self._task_lock:
            state = self._tasks.get(task_id)
            if state is None:
                stored = self._state_store.load(task_id)
                if stored is None or not self._is_running_status(stored.get("task_status", "")):
                    return
                execution_log = stored.setdefault("execution_log", [])
                if entry not in execution_log:
                    execution_log.append(entry)
                stored["current_action"] = self._describe_realtime_action(entry)
                stored["updated_at"] = now_iso()
                self._state_store.save(task_id, stored)
                return

            execution_log = state.setdefault("execution_log", [])
            if entry not in execution_log:
                execution_log.append(entry)
            state["current_action"] = self._describe_realtime_action(entry)
            state["updated_at"] = now_iso()
            payload = self._serialize_state(state)
            self._state_store.save(task_id, payload)

    def _persist_running_state_update(self, task_id: str, state: WorkflowState) -> None:
        with self._task_lock:
            state["updated_at"] = now_iso()
            self._tasks[task_id] = state
            self._state_store.save(task_id, self._serialize_state(state))

    @staticmethod
    def _describe_realtime_action(entry: dict[str, Any]) -> str:
        details = entry.get("details", {})
        event = entry.get("event", "")
        if event == "llm_call_started":
            prefix = _format_generation_prefix(details)
            return f"{prefix}LLM 调用开始：{details.get('operation', '')} 第 {details.get('attempt', 1)}/{details.get('max_attempts', 1)} 次"
        if event == "llm_call_completed":
            prefix = _format_generation_prefix(details)
            return f"{prefix}LLM 调用完成：{details.get('operation', '')}"
        if event == "llm_call_failed":
            prefix = _format_generation_prefix(details)
            return f"{prefix}LLM 调用失败：{details.get('operation', '')}"
        if event == "file_generation_started":
            prefix = _format_generation_prefix(details)
            return f"{prefix}正在生成文件：{details.get('file_path', '')}"
        if event == "file_generation_completed":
            prefix = _format_generation_prefix(details)
            return f"{prefix}文件生成完成：{details.get('file_path', '')}"
        if event == "queue_task_started":
            return f"正在执行队列任务：{details.get('task_id', '')}"
        if event == "queue_task_completed":
            return f"队列任务已完成：{details.get('task_id', '')}"
        if event == "queue_round_validation_started":
            return "正在进行本轮完整性验证"
        if event == "queue_round_validation_completed":
            return "本轮完整性验证已完成"
        if event == "evidence_fill_started":
            return "正在统一回填依据到知识文件"
        if event == "evidence_fill_completed":
            return "知识文件依据回填完成"
        if event == "query_plan_created":
            return f"QueryEngine 已生成 {details.get('question_count', 0)} 个查询计划项"
        if event == "query_plan_item_started":
            return f"QueryEngine 正在查询：{details.get('question', '')}"
        if event == "query_search_executed":
            return f"QueryEngine 已执行搜索：{details.get('query', '')}"
        if event == "query_question_completed":
            return f"QueryEngine 完成查询项：{details.get('question', '')}"
        if event == "query_documents_fetched":
            return f"QueryEngine 已抓取 {details.get('document_count', 0)} 篇候选文档"
        if event == "query_embeddings_completed":
            return "QueryEngine 已完成候选文档向量化"
        if event == "query_realtime_file_reviewed":
            return f"QueryEngine 实时文件审查完成：{len(details.get('saved_paths', []))} 个文件"
        if event == "query_realtime_file_failed":
            return f"QueryEngine 实时文件保存失败：{details.get('error', '')}"
        if event == "media_plan_item_started":
            return f"MediaEngine 正在查询：{details.get('query', '')}"
        if event == "media_search_executed":
            return f"MediaEngine 已执行搜索：{details.get('query', '')}"
        if event == "media_documents_fetched":
            return f"MediaEngine 已抓取 {details.get('document_count', 0)} 篇候选文档"
        if event == "media_realtime_file_reviewed":
            return f"MediaEngine 实时文件审查完成：{len(details.get('saved_paths', []))} 个文件"
        if event == "media_realtime_file_failed":
            return f"MediaEngine 实时文件保存失败：{details.get('error', '')}"
        return str(event)

    def _freeze_version_if_eligible(self, task_id: str, payload: dict[str, Any]) -> None:
        post_storage = payload.get("post_storage_result") or {}
        version_record = post_storage.get("version_record")
        if not version_record or not version_record.get("frozen"):
            return
        request_context = payload["request_context"]
        agent_outputs = payload.get("agent_outputs", {})
        frozen_record = FrozenVersionRecord(
            task_id=task_id,
            document_id=version_record["document_id"],
            version=version_record["version"],
            frozen_at=version_record["frozen_at"],
            file_paths=version_record["file_paths"],
            graph_nodes=version_record["graph_nodes"],
            knowledge_objects=version_record["knowledge_objects"],
            source_snapshot=[
                {
                    "agent": name,
                    "sources": output.get("sources", []),
                    "summary": output.get("summary", ""),
                }
                for name, output in agent_outputs.items()
            ]
            + [
                {
                    "agent": "request_context",
                    "sources": [],
                    "summary": f"{request_context['domain']} / {', '.join(request_context['subdomains'])}",
                }
            ],
            report_eligible=version_record["report_eligible"],
        )
        self._frozen_store.save(task_id, frozen_record.to_dict())
        self._audit_logger.log(
            task_id,
            "version_frozen",
            {"version": frozen_record.version, "document_id": frozen_record.document_id},
        )

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

    @staticmethod
    def _summarize_state(payload: dict[str, Any]) -> dict[str, Any]:
        request_context = payload.get("request_context") or {}
        post_storage = payload.get("post_storage_result") or {}
        version_record = post_storage.get("version_record") or {}
        document_artifact = payload.get("document_artifact") or {}
        return {
            "task_id": payload.get("task_id", ""),
            "task_status": payload.get("task_status", "unknown"),
            "domain": request_context.get("domain", ""),
            "normalized_domain": request_context.get("normalized_domain", ""),
            "subdomains": request_context.get("subdomains", []),
            "round_number": payload.get("round_number", 1),
            "document_path": document_artifact.get("path", ""),
            "version": version_record.get("version", ""),
            "report_eligible": version_record.get("report_eligible", False),
            "updated_at": version_record.get("updated_at") or version_record.get("frozen_at") or now_iso(),
        }

    @staticmethod
    def _deserialize_request_context(payload: dict[str, Any]) -> RequestContext:
        return RequestContext(**payload)

    @staticmethod
    def _deserialize_messages(payload: list[dict[str, Any]]) -> list[AgentMessage]:
        return [AgentMessage(**item) for item in payload]

    @staticmethod
    def _deserialize_engine_plans(payload: dict[str, Any]) -> dict[str, EnginePlan]:
        plans: dict[str, EnginePlan] = {}
        for agent_name, plan_payload in payload.items():
            if isinstance(plan_payload, EnginePlan):
                plans[agent_name] = plan_payload
                continue
            if not isinstance(plan_payload, dict):
                continue
            items = [
                EnginePlanItem(**item)
                for item in plan_payload.get("plan_items", [])
                if isinstance(item, dict)
            ]
            plan_data = dict(plan_payload)
            plan_data["plan_items"] = items
            plans[agent_name] = EnginePlan(**plan_data)
        return plans

    @staticmethod
    def _is_running_status(status: object) -> bool:
        return str(status) in {"running", "resumed", "supplementing", "filled"}


class _NoopQueryCrawler:
    def search(self, **kwargs):
        from knowledgeforge.agent.QueryEngine.state.state import SearchHit

        query = str(kwargs.get("query", "offline query"))
        source_type = str(kwargs.get("source_type", "reference"))
        return [
            SearchHit(
                title=f"Offline reference for {query}",
                url=f"https://example.com/offline?q={query.replace(' ', '+')}",
                snippet=f"Offline fixture covering {query}.",
                source_type=source_type,
                score=1.0,
            )
        ]

    def fetch_documents(self, hits, *, max_documents: int = 6):
        from knowledgeforge.agent.QueryEngine.state.state import CrawledDocument

        return [
            CrawledDocument(
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                content=f"{hit.title}. {hit.snippet}",
                source_type=hit.source_type,
                publisher=hit.publisher,
                score=hit.score,
            )
            for hit in hits[:max_documents]
        ]


class _NoopMediaCrawler:
    def search(self, **kwargs):
        return []

    def fetch_documents(self, hits, *, max_documents: int = 8):
        return []
