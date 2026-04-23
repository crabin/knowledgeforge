from __future__ import annotations

from urllib.parse import urlparse


OFFICIAL_HINTS = ("docs.", "developer.", "official", "spec", "standards", "github.com")
TUTORIAL_HINTS = ("tutorial", "guide", "blog", "medium.com", "dev.to", "substack")


def score_url(url: str, source_type: str, official_domains: list[str]) -> float:
    netloc = urlparse(url).netloc.lower()
    score = 0.0
    if source_type == "official":
        score += 5.0
    if any(domain.lower() in netloc for domain in official_domains):
        score += 6.0
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
