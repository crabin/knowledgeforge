from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from knowledgeforge.models import RequestContext
from knowledgeforge.utils.time import now_iso


QuestionStatus = Literal["planned", "in_progress", "completed", "insufficient"]


@dataclass(slots=True)
class SearchQuestion:
    question: str
    google_query: str
    expected_info: list[str]
    source_priority: list[str]
    success_criteria: list[str]
    fallback_queries: list[str]
    status: QuestionStatus = "planned"
    plan_item_id: str = ""
    search_targets: list[str] = field(default_factory=list)
    completed_at: str = ""


@dataclass(slots=True)
class SearchPlan:
    official_queries: list[str]
    tutorial_queries: list[str]
    official_domains: list[str]
    reasoning: str
    questions: list[SearchQuestion] = field(default_factory=list)


@dataclass(slots=True)
class ReflectionPlan:
    missing_aspects: list[str]
    supplementary_official_queries: list[str]
    supplementary_tutorial_queries: list[str]
    candidate_official_domains: list[str]
    reasoning: str


@dataclass(slots=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    source_type: str
    score: float

    @property
    def publisher(self) -> str:
        return urlparse(self.url).netloc or "unknown"


@dataclass(slots=True)
class CrawledDocument:
    title: str
    url: str
    snippet: str
    content: str
    source_type: str
    publisher: str
    score: float
    embedding_dimensions: int = 0


@dataclass(slots=True)
class QueryEngineState:
    request_context: RequestContext
    round_number: int
    normalized_domain: str = ""
    domain_aliases: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    normalization_reasoning: str = ""
    search_plan: SearchPlan | None = None
    reflection_plan: ReflectionPlan | None = None
    candidate_official_domains: list[str] = field(default_factory=list)
    search_hits: list[SearchHit] = field(default_factory=list)
    crawled_documents: list[CrawledDocument] = field(default_factory=list)
    summary_payload: dict[str, Any] = field(default_factory=dict)
    search_history: list[dict[str, Any]] = field(default_factory=list)
    execution_log: list[dict[str, Any]] = field(default_factory=list)
    observation_notes: list[str] = field(default_factory=list)
    reflection_notes: list[str] = field(default_factory=list)
    iteration_count: int = 0
    collected_at: str = field(default_factory=now_iso)

    @classmethod
    def from_context(cls, context: RequestContext, round_number: int) -> "QueryEngineState":
        return cls(request_context=context, round_number=round_number)
