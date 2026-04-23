from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Role = Literal["user", "assistant", "system"]
CompletenessStatus = Literal["pass", "supplement_required"]


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources"] = [source.to_dict() for source in self.sources]
        return payload


@dataclass(slots=True)
class CompletenessResult:
    status: CompletenessStatus
    reasons: list[str]
    missing_topics: list[str]
    supplement_queries: list[str]

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
