from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Literal

from knowledgeforge.server.models import RequestContext
from knowledgeforge.server.utils.time import now_iso


MediaItemStatus = Literal["planned", "in_progress", "completed", "insufficient", "skipped"]


@dataclass(slots=True)
class MediaPlanItem:
    query: str
    platform_type: str
    subdomain: str
    article_title: str
    candidate_url: str
    planned_path: str
    source_kind: str
    doc_type: str = "trend"
    doc_role: str = "topic_article"
    module_id: str = "review"
    module_label: str = "Review"
    plan_item_id: str = ""
    status: MediaItemStatus = "planned"
    skip_reason: str = ""
    existing_path: str = ""
    completed_at: str = ""


@dataclass(slots=True)
class MediaSearchPlan:
    social_queries: list[str]
    community_queries: list[str]
    blog_queries: list[str]
    reasoning: str
    is_technical: bool
    items: list[MediaPlanItem] = field(default_factory=list)


@dataclass(slots=True)
class MediaReflectionPlan:
    missing_aspects: list[str]
    supplementary_social_queries: list[str]
    supplementary_community_queries: list[str]
    supplementary_blog_queries: list[str]
    reasoning: str


@dataclass(slots=True)
class MediaSearchHit:
    title: str
    url: str
    snippet: str
    platform_type: str
    score: float
    subdomain: str = ""
    planned_path: str = ""
    plan_item_id: str = ""

    @property
    def publisher(self) -> str:
        return urlparse(self.url).netloc or "unknown"


@dataclass(slots=True)
class MediaCrawledDocument:
    title: str
    url: str
    snippet: str
    content: str
    platform_type: str
    publisher: str
    score: float
    subdomain: str = ""
    doc_type: str = "trend"
    planned_path: str = ""
    plan_item_id: str = ""


@dataclass(slots=True)
class MediaEngineState:
    request_context: RequestContext
    round_number: int
    normalized_domain: str = ""
    domain_aliases: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    normalization_reasoning: str = ""
    search_plan: MediaSearchPlan | None = None
    reflection_plan: MediaReflectionPlan | None = None
    search_hits: list[MediaSearchHit] = field(default_factory=list)
    crawled_documents: list[MediaCrawledDocument] = field(default_factory=list)
    summary_payload: dict[str, object] = field(default_factory=dict)
    search_history: list[dict[str, object]] = field(default_factory=list)
    execution_log: list[dict[str, object]] = field(default_factory=list)
    observation_notes: list[str] = field(default_factory=list)
    reflection_notes: list[str] = field(default_factory=list)
    iteration_count: int = 0
    collected_at: str = field(default_factory=now_iso)

    @classmethod
    def from_context(cls, context: RequestContext, round_number: int) -> "MediaEngineState":
        return cls(request_context=context, round_number=round_number)
