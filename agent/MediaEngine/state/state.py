from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from knowledgeforge.models import RequestContext
from knowledgeforge.utils.time import now_iso


@dataclass(slots=True)
class MediaSearchPlan:
    social_queries: list[str]
    community_queries: list[str]
    blog_queries: list[str]
    reasoning: str
    is_technical: bool


@dataclass(slots=True)
class MediaSearchHit:
    title: str
    url: str
    snippet: str
    platform_type: str
    score: float

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


@dataclass(slots=True)
class MediaEngineState:
    request_context: RequestContext
    round_number: int
    search_plan: MediaSearchPlan | None = None
    search_hits: list[MediaSearchHit] = field(default_factory=list)
    crawled_documents: list[MediaCrawledDocument] = field(default_factory=list)
    summary_payload: dict[str, object] = field(default_factory=dict)
    collected_at: str = field(default_factory=now_iso)

    @classmethod
    def from_context(cls, context: RequestContext, round_number: int) -> "MediaEngineState":
        return cls(request_context=context, round_number=round_number)
