from __future__ import annotations

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
    "arxiv.org",
    "huggingface.co",
    "paperswithcode.com",
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
        score += 5.0
    if any(domain.lower() in netloc for domain in official_domains):
        score += 6.0
    if preferred_domains and any(domain.lower() in netloc for domain in preferred_domains):
        score += 4.0 if source_type != "official" else 1.0
    if any(hint in netloc for hint in OFFICIAL_HINTS):
        score += 3.0
    if any(hint in url.lower() for hint in ("docs", "reference", "api", "manual")):
        score += 2.0
    if any(hint in netloc for hint in TUTORIAL_HINTS):
        score += 1.0 if source_type == "tutorial" else -1.0
    return score


def reliability_for_source_type(source_type: str) -> str:
    if source_type == "official":
        return "high"
    if source_type == "tutorial":
        return "medium"
    return "unknown"


def build_site_constrained_queries(query: str, preferred_domains: list[str], max_domains: int = 3) -> list[str]:
    compact_query = " ".join(query.split())
    return [f"{compact_query} site:{domain}" for domain in preferred_domains[:max_domains]]


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
