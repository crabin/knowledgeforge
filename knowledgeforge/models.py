from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Role = Literal["user", "assistant", "system"]
TaskIntent = Literal["knowledge_collection", "concept_explanation", "qa"]
CompletenessStatus = Literal["pass", "supplement_required"]
GovernanceStatus = Literal["passed", "failed"]
RemediationFlow = Literal["repair_flow", "research_flow"]
FailureCategory = Literal[
    "file_write_failed",
    "graph_write_failed",
    "path_association_failed",
    "quality_check_failed",
    "source_quality_failed",
]


@dataclass(slots=True)
class AgentMessage:
    role: Role
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceRecord:
    title: str
    url: str
    publisher: str
    retrieved_at: str
    reliability: Literal["high", "medium", "low", "unknown"]
    agent: str
    source_type: str = "reference"
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RequestContext:
    domain: str
    subdomains: list[str]
    time_window: str
    focus_points: list[str]
    constraints: list[str]
    initial_strategy: list[str]
    original_input: str = ""
    normalized_domain: str = ""
    intent: TaskIntent = "knowledge_collection"
    output_language: str = "zh-CN"
    search_language: str = "en"
    search_terms: list[str] = field(default_factory=list)
    clarification_summary: str = ""
    confirmed: bool = False
    task_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ClarificationResult:
    original_input: str
    normalized_domain: str
    intent: TaskIntent
    output_language: str
    search_language: str
    subdomains: list[str]
    focus_points: list[str]
    search_terms: list[str]
    needs_clarification: bool
    clarification_questions: list[str]
    clarification_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IntakeSession:
    session_id: str
    status: Literal["draft", "confirmed"]
    messages: list[AgentMessage]
    candidate_context: ClarificationResult
    created_at: str
    updated_at: str
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["messages"] = [message.to_dict() for message in self.messages]
        payload["candidate_context"] = self.candidate_context.to_dict()
        return payload


@dataclass(slots=True)
class EngineRunResult:
    agent_name: str
    summary: str
    key_points: list[str]
    raw_material: list[str]
    coverage_topics: list[str]
    sources: list[SourceRecord]
    collected_at: str
    round_number: int
    execution_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources"] = [source.to_dict() for source in self.sources]
        return payload


PlanItemStatus = Literal["planned", "approved", "in_progress", "completed", "insufficient"]
PlanStatus = Literal["draft", "awaiting_confirmation", "approved"]
WorkflowStepStatus = Literal["pending", "active", "completed", "blocked"]


@dataclass(slots=True)
class EnginePlanItem:
    plan_item_id: str
    title: str
    query_or_action: str
    targets: list[str]
    success_criteria: list[str]
    fallbacks: list[str] = field(default_factory=list)
    source_priority: list[str] = field(default_factory=list)
    status: PlanItemStatus = "planned"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EnginePlan:
    agent_name: str
    plan_items: list[EnginePlanItem]
    reasoning: str
    status: PlanStatus
    created_at: str
    approved_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["plan_items"] = [item.to_dict() for item in self.plan_items]
        return payload


@dataclass(slots=True)
class WorkflowStepEvent:
    step_id: str
    label: str
    status: WorkflowStepStatus
    timestamp: str
    agent: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CompletenessResult:
    status: CompletenessStatus
    reasons: list[str]
    missing_topics: list[str]
    supplement_queries: list[str]
    failure_categories: list[str] = field(default_factory=list)
    supplement_decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DocumentArtifact:
    document_id: str
    title: str
    domain: str
    subdomain: str
    path: str
    status: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StructuredExtractionResult:
    document_id: str
    document_path: str
    chunks: list[dict[str, Any]]
    metadata: dict[str, Any]
    entities: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    status: GovernanceStatus = "passed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GraphSyncResult:
    document_id: str
    article_path: str
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    status: GovernanceStatus = "passed"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QualityIssue:
    category: FailureCategory
    detail: str
    flow: RemediationFlow

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QualityCheckResult:
    document_id: str
    status: GovernanceStatus
    issues: list[QualityIssue]
    checks: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [issue.to_dict() for issue in self.issues]
        return payload


@dataclass(slots=True)
class VersionRecord:
    document_id: str
    version: str
    updated_at: str
    knowledge_objects: list[str]
    file_paths: list[str]
    graph_nodes: list[str]
    pending_issues: list[str]
    status: str
    frozen: bool = False
    frozen_at: str | None = None
    report_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PostStorageResult:
    extraction: StructuredExtractionResult
    graph_sync: GraphSyncResult
    quality_check: QualityCheckResult
    version_record: VersionRecord | None
    status: GovernanceStatus
    remediation_flows: list[RemediationFlow] = field(default_factory=list)
    next_round_queries: list[str] = field(default_factory=list)
    failure_category: FailureCategory | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "extraction": self.extraction.to_dict(),
            "graph_sync": self.graph_sync.to_dict(),
            "quality_check": self.quality_check.to_dict(),
            "version_record": self.version_record.to_dict() if self.version_record else None,
            "status": self.status,
            "remediation_flows": self.remediation_flows,
            "next_round_queries": self.next_round_queries,
            "failure_category": self.failure_category,
        }


@dataclass(slots=True)
class FrozenVersionRecord:
    task_id: str
    document_id: str
    version: str
    frozen_at: str
    file_paths: list[str]
    graph_nodes: list[str]
    knowledge_objects: list[str]
    source_snapshot: list[dict[str, Any]]
    report_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReportArtifact:
    task_id: str
    document_id: str
    version: str
    generated_at: str
    source: Literal["frozen_version"]
    sections: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
