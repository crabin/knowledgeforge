from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from typing import Any

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.QueryEngine.agent import QueryEngine
from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.config import AppConfig
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.graph.client import Neo4jGraphClient
from knowledgeforge.graph.neo4j_adapter import Neo4jPathMapper
from knowledgeforge.intake.clarifier import IntakeClarifier
from knowledgeforge.intake.context_builder import ContextBuilder
from knowledgeforge.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)
from knowledgeforge.models import AgentMessage, ClarificationResult, FrozenVersionRecord, IntakeSession, RequestContext
from knowledgeforge.orchestrator.graph import KnowledgeGraphWorkflow
from knowledgeforge.orchestrator.state import WorkflowState
from knowledgeforge.postprocess.extractor import StructuredExtractor
from knowledgeforge.postprocess.pipeline import PostStoragePipeline
from knowledgeforge.quality.checker import QualityChecker
from knowledgeforge.runtime.audit import AuditLogger
from knowledgeforge.runtime.frozen_store import FrozenVersionStore
from knowledgeforge.runtime.intake_session_store import IntakeSessionStore
from knowledgeforge.runtime.state_store import TaskStateStore
from knowledgeforge.reporting.report_service import ReportService
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.time import now_iso
from knowledgeforge.versioning.recorder import VersionRecorder


class TaskService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._context_builder = ContextBuilder()
        self._state_store = TaskStateStore(config.task_state_root)
        self._intake_store = IntakeSessionStore(config.intake_session_root)
        self._audit_logger = AuditLogger(config.audit_root)
        self._frozen_store = FrozenVersionStore(config.frozen_root)
        self._report_service = ReportService()
        query_chat_client = OpenAICompatibleChatClient(config.openai, timeout=1.5)
        query_embedding_client = OpenAICompatibleEmbeddingClient(config.openai, timeout=2.0)
        media_chat_client = OpenAICompatibleChatClient(config.openai, timeout=1.5)
        self._intake_clarifier = IntakeClarifier(OpenAICompatibleChatClient(config.openai, timeout=1.0))
        graph_client = Neo4jGraphClient(config.neo4j)
        self._workflow = KnowledgeGraphWorkflow(
            insight_engine=InsightEngine(),
            query_engine=QueryEngine(
                chat_client=query_chat_client,
                embedding_client=query_embedding_client,
                crawler=DomainKnowledgeCrawler() if config.enable_live_crawlers else _NoopQueryCrawler(),
            ),
            media_engine=MediaEngine(
                chat_client=media_chat_client,
                crawler=MediaPerspectiveCrawler() if config.enable_live_crawlers else _NoopMediaCrawler(),
            ),
            evaluator=CompletenessEvaluator(),
            writer=MarkdownKnowledgeWriter(config),
            post_storage_pipeline=PostStoragePipeline(
                extractor=StructuredExtractor(),
                graph_mapper=Neo4jPathMapper(client=graph_client),
                quality_checker=QualityChecker(),
                version_recorder=VersionRecorder(),
                strict_graph_sync=config.strict_graph_sync,
            ),
        )
        self._tasks: dict[str, WorkflowState] = {}

    def get_config_status(self) -> dict[str, bool | str]:
        return self._config.show_config_status()

    def run_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_context = self._context_builder.build(payload)
        return self._run_workflow(request_context, audit_source="api")

    def create_intake_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message", payload.get("domain", ""))).strip()
        if not message:
            raise ValueError("`message` is required.")
        session_id = uuid.uuid4().hex
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
        return payload_dict

    def append_intake_message(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        stored = self._intake_store.load(session_id)
        if stored is None:
            return None
        message = str(payload.get("message", "")).strip()
        if not message:
            raise ValueError("`message` is required.")
        messages = self._deserialize_messages(stored.get("messages", []))
        messages.append(AgentMessage(role="user", content=message, metadata={"source": "api"}))
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
        return stored

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
        task_payload = self._run_workflow(request_context, audit_source="intake")
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
        task_id = uuid.uuid4().hex
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
            "task_status": "created",
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
        final_state = self._workflow.run(initial_state)
        return self._persist_and_serialize(final_state, "task_completed")

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if task_id in self._tasks:
            return self._serialize_state(self._tasks[task_id])
        return self._state_store.load(task_id)

    def get_frozen_version(self, task_id: str) -> dict[str, Any] | None:
        return self._frozen_store.load(task_id)

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
        final_state = self._workflow.run(resumed_state)
        return self._persist_and_serialize(final_state, "task_completed")

    def _persist_and_serialize(self, state: WorkflowState, audit_event: str) -> dict[str, Any]:
        task_id = state["task_id"]
        self._tasks[task_id] = state
        payload = self._serialize_state(state)
        self._state_store.save(task_id, payload)
        self._freeze_version_if_eligible(task_id, payload)
        self._audit_logger.log(
            task_id,
            audit_event,
            {
                "status": payload.get("task_status"),
                "round": payload.get("round_number"),
            },
        )
        return payload

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
    def _deserialize_request_context(payload: dict[str, Any]) -> RequestContext:
        return RequestContext(**payload)

    @staticmethod
    def _deserialize_messages(payload: list[dict[str, Any]]) -> list[AgentMessage]:
        return [AgentMessage(**item) for item in payload]


class _NoopQueryCrawler:
    def search(self, **kwargs):
        return []

    def fetch_documents(self, hits, *, max_documents: int = 6):
        return []


class _NoopMediaCrawler:
    def search(self, **kwargs):
        return []

    def fetch_documents(self, hits, *, max_documents: int = 8):
        return []
