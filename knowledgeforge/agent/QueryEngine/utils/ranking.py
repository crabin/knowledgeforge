from __future__ import annotations

import re
from urllib.parse import urlparse


OFFICIAL_HINTS = ("docs.", "developer.", "official", "spec", "standards", "github.com")
TUTORIAL_HINTS = ("tutorial", "guide", "blog", "medium.com", "dev.to", "substack")
PREFERRED_TUTORIAL_DOMAINS = (
    "github.com",
    "stackoverflow.com",
    "medium.com",
    "dev.to",
    "substack.com",
    "hashnode.dev",
)
PREFERRED_TECH_REFERENCE_DOMAINS = (
    "docs.python.org",
    "developer.mozilla.org",
    "arxiv.org",
    "github.com",
    "huggingface.co",
    "paperswithcode.com",
)
PRIORITY_SOURCE_DOMAINS = {
    "concept": ("en.wikipedia.org", "zh.wikipedia.org"),
    "technical": ("docs.python.org", "developer.mozilla.org", "arxiv.org", "github.com"),
    "ai_ml": ("arxiv.org", "paperswithcode.com", "huggingface.co"),
    "news": ("reuters.com", "bbc.com", "theguardian.com"),
    "academic": ("scholar.google.com", "semanticscholar.org"),
}
AUTHORITATIVE_REFERENCE_DOMAINS = (
    "en.wikipedia.org",
    "zh.wikipedia.org",
)
HIGH_AUTHORITY_DOMAINS = (
    "arxiv.org",
    "papers.nips.cc",
    "proceedings.mlr.press",
    "openreview.net",
    "dl.acm.org",
    "ieeexplore.ieee.org",
)

LOW_QUALITY_RESULT_HINTS = (
    "search",
    "tag",
    "tags",
    "login",
    "signup",
    "directory",
    "archive",
)


def score_url(
    url: str,
    source_type: str,
    official_domains: list[str],
    preferred_domains: list[str] | None = None,
) -> float:
    netloc = urlparse(url).netloc.lower()
    score = 0.0
    if source_type == "official":
        score += 1.0
    if any(domain.lower() in netloc for domain in official_domains):
        score += 6.0
    if preferred_domains and any(domain.lower() in netloc for domain in preferred_domains):
        score += 4.0 if source_type != "official" else 3.0
    if any(hint in netloc for hint in OFFICIAL_HINTS):
        score += 3.0
    if any(hint in url.lower() for hint in ("docs", "reference", "api", "manual")):
        score += 2.0
    if any(hint in netloc for hint in TUTORIAL_HINTS):
        score += 1.0 if source_type == "tutorial" else -1.0
    return score


def score_evidence_match(
    *,
    title: str,
    snippet: str,
    url: str,
    expected_info: list[str],
    success_criteria: list[str],
    query: str,
) -> float:
    haystack = f"{title} {snippet} {url}".lower()
    score = 0.0
    for phrase in [*expected_info, *success_criteria]:
        cleaned = " ".join(str(phrase).lower().split())
        if cleaned and cleaned in haystack:
            score += 1.5
    query_tokens = [
        token
        for token in re.split(r"\W+", query.lower())
        if len(token) >= 4 and token not in {"official", "documentation", "tutorial", "guide", "best", "practices"}
    ]
    if query_tokens:
        matched = sum(1 for token in query_tokens if token in haystack)
        score += min(3.0, matched / max(len(query_tokens), 1) * 3.0)
    parsed = urlparse(url)
    lowered_path = parsed.path.lower()
    if any(hint in lowered_path for hint in LOW_QUALITY_RESULT_HINTS):
        score -= 1.0
    return score


def evidence_match_reason(
    *,
    title: str,
    snippet: str,
    expected_info: list[str],
    success_criteria: list[str],
) -> str:
    haystack = f"{title} {snippet}".lower()
    matched = [
        item
        for item in [*expected_info, *success_criteria]
        if str(item).strip() and str(item).strip().lower() in haystack
    ]
    if matched:
        return "匹配预期证据：" + "、".join(str(item) for item in matched[:3])
    if title or snippet:
        return "标题或摘要与查询主题相关，需用作候选证据复核。"
    return "搜索结果缺少摘要，仅保留 URL 作为候选。"


def reliability_for_source_type(source_type: str) -> str:
    if source_type == "official":
        return "high"
    if source_type == "tutorial":
        return "medium"
    return "unknown"


def reliability_for_source_type_and_url(
    source_type: str,
    url: str,
    official_domains: list[str],
) -> str:
    netloc = urlparse(url).netloc.lower()
    if any(domain in netloc for domain in HIGH_AUTHORITY_DOMAINS):
        return "high"
    if any(domain in netloc for domain in AUTHORITATIVE_REFERENCE_DOMAINS):
        return "medium"
    if source_type == "official":
        if any(domain.lower() in netloc for domain in official_domains):
            return "high"
        return "medium"
    if source_type == "tutorial":
        return "medium"
    return "unknown"


def is_result_relevant(
    title: str,
    snippet: str,
    url: str,
    domain_phrases: list[str],
) -> bool:
    """Return True when a result mentions a whole domain phrase or alias."""
    haystack = f"{title} {snippet} {url}".lower()
    for phrase in domain_phrases:
        cleaned = phrase.strip().lower()
        if not cleaned:
            continue
        pattern = r"(?<!\w)" + re.escape(cleaned) + r"(?!\w)"
        if re.search(pattern, haystack):
            return True
    return False


def build_site_constrained_queries(query: str, preferred_domains: list[str], max_domains: int = 3) -> list[str]:
    compact_query = " ".join(query.split())
    return [f"{compact_query} site:{domain}" for domain in preferred_domains[:max_domains]]


def domains_for_source_priority(
    source_priority: list[str],
    *,
    query: str = "",
    expected_info: list[str] | None = None,
    max_domains: int = 4,
) -> list[str]:
    text = " ".join([query, *(expected_info or []), *source_priority]).lower()
    domains: list[str] = []

    def add(category: str) -> None:
        for domain in PRIORITY_SOURCE_DOMAINS[category]:
            if domain not in domains:
                domains.append(domain)

    if any(token in text for token in ("通用", "概念", "定义", "边界", "wikipedia", "百科", "overview", "definition")):
        add("concept")
    if any(token in text for token in ("技术", "编程", "python", "javascript", "web", "api", "sdk", "github", "developer")):
        add("technical")
    if any(token in text for token in ("ai", "ml", "machine learning", "deep learning", "模型", "论文", "paper", "huggingface")):
        add("ai_ml")
    if any(token in text for token in ("新闻", "时事", "趋势", "news", "recent", "trend")):
        add("news")
    if any(token in text for token in ("学术", "academic", "scholar", "survey", "citation", "semantic scholar")):
        add("academic")
    return domains[:max_domains]


def detect_candidate_official_domains(domain: str, hits: list[object], limit: int = 3) -> list[str]:
    candidates: list[str] = []
    domain_token = domain.lower().replace(" ", "").replace("-", "")
    for hit in hits:
        url = getattr(hit, "url", "")
        title = getattr(hit, "title", "")
        snippet = getattr(hit, "snippet", "")
        if not url:
            continue
        netloc = urlparse(url).netloc.lower()
        path = urlparse(url).path.lower()
        combined = f"{title} {snippet} {url}".lower()
        looks_official = (
            any(hint in netloc for hint in OFFICIAL_HINTS)
            or any(hint in path for hint in ("docs", "documentation", "reference", "manual"))
            or "official" in combined
            or domain_token in netloc.replace(".", "").replace("-", "")
        )
        looks_non_official = any(hint in netloc for hint in TUTORIAL_HINTS) or any(
            hint in netloc for hint in ("reddit.com", "stackoverflow.com", "medium.com", "dev.to", "substack.com")
        )
        if looks_official and not looks_non_official and netloc not in candidates:
            candidates.append(netloc)
        if len(candidates) >= limit:
            break
    return candidates
