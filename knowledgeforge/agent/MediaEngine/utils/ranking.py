from __future__ import annotations

from urllib.parse import urlparse


TECH_HINTS = (
    "deep learning",
    "machine learning",
    "深度学习",
    "llm",
    "langgraph",
    "langchain",
    "pytorch",
    "tensorflow",
    "agent",
    "workflow",
    "rag",
)
SOCIAL_DOMAINS = ("x.com", "twitter.com", "reddit.com")
COMMUNITY_DOMAINS = ("news.ycombinator.com", "github.com", "v2ex.com", "juejin.cn", "zhihu.com")
BLOG_HINTS = ("blog", "substack", "medium.com", "dev.to", "hashnode", "engineering")
LOW_QUALITY_HINTS = ("tag", "tags", "search", "directory", "listing", "archive")


def is_technical_context(domain: str, subdomains: list[str], focus_points: list[str]) -> bool:
    haystack = " ".join([domain, *subdomains, *focus_points]).lower()
    return any(hint in haystack for hint in TECH_HINTS)


def classify_platform_type(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    if any(domain in netloc for domain in SOCIAL_DOMAINS):
        return "social"
    if any(domain in netloc for domain in COMMUNITY_DOMAINS):
        return "community"
    if any(hint in netloc for hint in BLOG_HINTS):
        return "blog"
    return "unknown"


def score_media_url(
    url: str,
    *,
    platform_type: str,
    requested_type: str,
    is_technical: bool,
    snippet: str,
) -> float:
    netloc = urlparse(url).netloc.lower()
    lowered_url = url.lower()
    score = 0.0
    if platform_type == requested_type:
        score += 3.0
    if platform_type == "community":
        score += 3.5
    elif platform_type == "blog":
        score += 2.5
    elif platform_type == "social":
        score += 2.0

    if is_technical:
        if any(domain in netloc for domain in ("news.ycombinator.com", "github.com", "reddit.com", "v2ex.com", "juejin.cn")):
            score += 4.0
        if "zhihu.com" in netloc or "x.com" in netloc or "twitter.com" in netloc:
            score += 2.0
        if any(hint in netloc for hint in BLOG_HINTS):
            score += 3.0

    if any(hint in lowered_url for hint in ("discussion", "discussions", "thread", "post", "item")):
        score += 1.0
    if any(hint in snippet.lower() for hint in ("trend", "adoption", "opinion", "community", "debate", "best practice")):
        score += 1.0
    if any(hint in lowered_url for hint in LOW_QUALITY_HINTS):
        score -= 3.0
    return score


def reliability_for_platform_type(platform_type: str, content: str) -> str:
    cleaned = (content or "").strip()
    if not cleaned:
        return "unknown"
    if platform_type == "community":
        return "medium"
    if platform_type == "blog":
        return "medium" if len(cleaned) > 280 else "unknown"
    if platform_type == "social":
        return "medium" if len(cleaned) > 480 else "low"
    return "unknown"
