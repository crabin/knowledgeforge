# Quality Pipeline Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent low-quality, irrelevant sources (e.g., Weblio noise from a "Machine Learning" query) from passing through crawling, completeness evaluation, quality checking, and reaching the frozen/report-eligible state.

**Architecture:** Six-layer defense: (0) multi-provider search + Wikipedia authoritative supplement, (1) crawler relevance filter + URL decoding, (2) source credibility reclassification, (3) completeness evaluator source-quality gate, (4) quality checker source checks + freeze guard, (5) writer dynamic status messaging. Regression tests validate the ML noisy-source scenario end-to-end.

**Tech Stack:** Python 3.12, pytest, httpx, BeautifulSoup, urllib.parse — no new dependencies required.

---

## File Map

| Action | File |
|--------|------|
| Modify | `agent/QueryEngine/utils/ranking.py` |
| Modify | `agent/MediaEngine/utils/ranking.py` |
| Modify | `agent/QueryEngine/tools/crawler.py` |
| Modify | `agent/MediaEngine/tools/crawler.py` |
| Modify | `knowledgeforge/evaluation/completeness.py` |
| Modify | `knowledgeforge/quality/checker.py` |
| Modify | `knowledgeforge/storage/markdown_writer.py` |
| Modify | `knowledgeforge/models.py` |
| Create | `agent/QueryEngine/tools/wikipedia_fetcher.py` |
| Create | `tests/test_source_relevance_filter.py` |
| Create | `tests/test_completeness_source_gate.py` |
| Create | `tests/test_quality_source_checks.py` |
| Create | `tests/test_writer_dynamic_status.py` |
| Create | `tests/test_ml_regression.py` |
| Create | `tests/test_multi_provider_search.py` |

---

## Phase 0 — Expand Search Coverage and Authoritative Sources

### Task 0a: Add Google and Brave Search to HTTP fallback providers

Currently `_search_with_http_fallback` tries DuckDuckGo then Bing. Add Google and Brave Search so the crawler has four providers. Try them in order: Google → Bing → DuckDuckGo → Brave. Stop at the first that returns hits.

**Files:**
- Modify: `agent/QueryEngine/tools/crawler.py`
- Modify: `agent/MediaEngine/tools/crawler.py`
- Test: `tests/test_multi_provider_search.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_multi_provider_search.py
from __future__ import annotations

from agent.QueryEngine.tools.crawler import (
    SEARCH_PROVIDERS,
    parse_google_results,
    parse_brave_results,
)
from bs4 import BeautifulSoup


GOOGLE_HTML = """
<html><body>
  <div class="g">
    <a href="https://scikit-learn.org/stable/"><h3>scikit-learn: Machine Learning in Python</h3></a>
    <div class="VwiC3b">Simple and efficient tools for machine learning.</div>
  </div>
  <div class="g">
    <a href="https://developers.google.com/machine-learning"><h3>Google ML Crash Course</h3></a>
    <div class="VwiC3b">Learn machine learning fundamentals from Google.</div>
  </div>
</body></html>
"""

BRAVE_HTML = """
<html><body>
  <div class="snippet">
    <a class="result-header" href="https://en.wikipedia.org/wiki/Machine_learning">
      <span class="title">Machine learning - Wikipedia</span>
    </a>
    <p class="snippet-description">Machine learning (ML) is a field of study in artificial intelligence.</p>
  </div>
</body></html>
"""


def test_google_provider_is_in_search_providers() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert "google" in names


def test_brave_provider_is_in_search_providers() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert "brave" in names


def test_parse_google_results_extracts_title_url_snippet() -> None:
    soup = BeautifulSoup(GOOGLE_HTML, "html.parser")
    hits = parse_google_results(soup)
    assert len(hits) == 2
    assert hits[0]["url"] == "https://scikit-learn.org/stable/"
    assert hits[0]["title"] == "scikit-learn: Machine Learning in Python"
    assert "machine learning" in hits[0]["snippet"].lower()


def test_parse_brave_results_extracts_title_url_snippet() -> None:
    soup = BeautifulSoup(BRAVE_HTML, "html.parser")
    hits = parse_brave_results(soup)
    assert len(hits) == 1
    assert "wikipedia.org" in hits[0]["url"]
    assert "Machine learning" in hits[0]["title"]


def test_provider_order_is_google_bing_duckduckgo_brave() -> None:
    names = [name for name, _ in SEARCH_PROVIDERS]
    assert names.index("google") < names.index("bing")
    assert names.index("bing") < names.index("duckduckgo")
    assert names.index("duckduckgo") < names.index("brave")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/lpb/workspace/myProjects/KnowledgeForge
uv run pytest tests/test_multi_provider_search.py -v
```
Expected: `ImportError` — `SEARCH_PROVIDERS`, `parse_google_results`, `parse_brave_results` not defined.

- [ ] **Step 3: Refactor provider list and add parsers in `agent/QueryEngine/tools/crawler.py`**

At the top of the file, after imports, add:

```python
# (url, name) pairs tried in order; stop at first with results
SEARCH_PROVIDERS: list[tuple[str, str]] = [
    ("google", "https://www.google.com/search"),
    ("bing", "https://www.bing.com/search"),
    ("duckduckgo", "https://html.duckduckgo.com/html/"),
    ("brave", "https://search.brave.com/search"),
]


def parse_google_results(soup: BeautifulSoup) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for block in soup.select("div.g"):
        anchor = block.select_one("a[href]")
        if not anchor:
            continue
        title_node = anchor.select_one("h3")
        snippet_node = block.select_one("div.VwiC3b, div.IsZvec, span.aCOpRe")
        url = anchor.get("href", "").strip()
        if not url.startswith("http"):
            continue
        hits.append({
            "url": url,
            "title": " ".join((title_node.get_text(" ", strip=True) if title_node else "").split()),
            "snippet": " ".join((snippet_node.get_text(" ", strip=True) if snippet_node else "").split()),
        })
    return hits


def parse_brave_results(soup: BeautifulSoup) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for block in soup.select("div.snippet, div[data-type='web']"):
        anchor = block.select_one("a.result-header, a[href]")
        if not anchor:
            continue
        title_node = anchor.select_one("span.title") or anchor
        snippet_node = block.select_one("p.snippet-description, .snippet-content")
        url = anchor.get("href", "").strip()
        if not url.startswith("http"):
            continue
        hits.append({
            "url": url,
            "title": " ".join(title_node.get_text(" ", strip=True).split()),
            "snippet": " ".join((snippet_node.get_text(" ", strip=True) if snippet_node else "").split()),
        })
    return hits
```

Replace the `providers` tuple in `_search_with_http_fallback`:

```python
# Before (original two-provider tuple):
providers = (
    ("duckduckgo", "https://html.duckduckgo.com/html/"),
    ("bing", "https://www.bing.com/search"),
)

# After:
providers = SEARCH_PROVIDERS
```

Update `_search_http_provider` to dispatch to the right parser:

```python
# After building soup, replace the provider-specific selector block:
if provider_name == "duckduckgo":
    raw_hits = self._parse_duckduckgo(soup)
elif provider_name == "bing":
    raw_hits = self._parse_bing(soup)
elif provider_name == "google":
    raw_hits = parse_google_results(soup)
elif provider_name == "brave":
    raw_hits = parse_brave_results(soup)
else:
    raw_hits = []
```

Extract the existing DuckDuckGo and Bing parsing into private methods `_parse_duckduckgo` and `_parse_bing` that each return `list[dict[str, str]]` with `url`, `title`, `snippet` keys. Then the main loop builds `SearchHit` objects from the raw dict list uniformly.

- [ ] **Step 4: Copy `SEARCH_PROVIDERS`, `parse_google_results`, `parse_brave_results` to `agent/MediaEngine/tools/crawler.py`**

Import from QueryEngine to avoid duplication:

```python
from agent.QueryEngine.tools.crawler import (
    SEARCH_PROVIDERS,
    parse_google_results,
    parse_brave_results,
    resolve_bing_redirect_url,
)
```

Apply the same `_search_with_http_fallback` and `_search_http_provider` refactor.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_multi_provider_search.py -v
uv run pytest tests/test_query_engine.py tests/test_media_engine.py -v
```
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add agent/QueryEngine/tools/crawler.py agent/MediaEngine/tools/crawler.py tests/test_multi_provider_search.py
git commit -m "feat(crawler): add Google and Brave Search to HTTP fallback provider list"
```

---

### Task 0b: Add Wikipedia authoritative supplement via direct API

Wikipedia's REST API returns structured summaries with no rate limit for reasonable usage. After the main search, QueryEngine performs a targeted Wikipedia lookup for the domain and uses it as a supplementary authoritative source (`reliability="medium"`).

Wikipedia is appropriate for ML topics: it provides definitions, history, and sub-topic structure. It is community-edited so capped at `medium`, not `high`.

**Files:**
- Create: `agent/QueryEngine/tools/wikipedia_fetcher.py`
- Modify: `agent/QueryEngine/tools/crawler.py`
- Modify: `agent/QueryEngine/utils/ranking.py`
- Test: `tests/test_multi_provider_search.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_multi_provider_search.py`:

```python
from agent.QueryEngine.tools.wikipedia_fetcher import WikipediaFetcher, WikipediaResult


def test_wikipedia_result_dataclass_has_required_fields() -> None:
    result = WikipediaResult(
        title="Machine learning",
        url="https://en.wikipedia.org/wiki/Machine_learning",
        summary="Machine learning (ML) is a field of study in artificial intelligence.",
        reliability="medium",
    )
    assert result.reliability == "medium"
    assert "wikipedia.org" in result.url


def test_wikipedia_fetcher_returns_none_on_http_error(monkeypatch) -> None:
    import httpx

    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("timeout")

    monkeypatch.setattr(httpx, "get", fake_get)
    fetcher = WikipediaFetcher(timeout=1.0)
    result = fetcher.fetch_summary("Machine learning")
    assert result is None


def test_wikipedia_fetcher_parses_valid_response(monkeypatch) -> None:
    import httpx

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "title": "Machine learning",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Machine_learning"}},
                "extract": "Machine learning (ML) is a field of study in artificial intelligence.",
            }

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: FakeResponse())
    fetcher = WikipediaFetcher(timeout=5.0)
    result = fetcher.fetch_summary("Machine learning")
    assert result is not None
    assert result.title == "Machine learning"
    assert result.reliability == "medium"
    assert "wikipedia.org" in result.url
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_multi_provider_search.py::test_wikipedia_result_dataclass_has_required_fields -v
```
Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create `agent/QueryEngine/tools/wikipedia_fetcher.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import httpx


@dataclass(slots=True)
class WikipediaResult:
    title: str
    url: str
    summary: str
    reliability: Literal["medium"] = "medium"


class WikipediaFetcher:
    """Fetch a Wikipedia page summary via the REST API (no API key required)."""

    _BASE = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout

    def fetch_summary(self, query: str) -> WikipediaResult | None:
        """Return a WikipediaResult for the closest matching Wikipedia article, or None on failure."""
        encoded = quote(query.replace(" ", "_"), safe="")
        url = self._BASE.format(title=encoded)
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
        except Exception:
            return None
        data = response.json()
        extract = data.get("extract", "").strip()
        if not extract:
            return None
        page_url = (
            data.get("content_urls", {}).get("desktop", {}).get("page", "")
            or f"https://en.wikipedia.org/wiki/{encoded}"
        )
        return WikipediaResult(
            title=data.get("title", query),
            url=page_url,
            summary=extract,
        )
```

- [ ] **Step 4: Wire Wikipedia supplement into `DomainKnowledgeCrawler`**

Add to `agent/QueryEngine/tools/crawler.py` imports:
```python
from agent.QueryEngine.tools.wikipedia_fetcher import WikipediaFetcher
```

Add `_wiki` to `__init__`:
```python
self._wiki = WikipediaFetcher(timeout=max(timeout * 2, 8.0))
```

Add a public method `fetch_wikipedia_supplement`:
```python
def fetch_wikipedia_supplement(
    self,
    domain: str,
    agent_name: str = "QueryEngine",
) -> CrawledDocument | None:
    """Fetch a Wikipedia summary for `domain` and return it as a CrawledDocument."""
    from knowledgeforge.utils.time import now_iso

    result = self._wiki.fetch_summary(domain)
    if result is None:
        self._log(f"[QUERY-WIKI] no result for domain={domain}")
        return None
    self._log(f"[QUERY-WIKI] fetched title={result.title} url={result.url}")
    return CrawledDocument(
        title=result.title,
        url=result.url,
        snippet=result.summary[:300],
        content=result.summary,
        source_type="reference",
        publisher="en.wikipedia.org",
        score=3.0,  # fixed moderate score; reliability is medium, not high
    )
```

- [ ] **Step 5: Update `reliability_for_source_type_and_url` whitelist in `agent/QueryEngine/utils/ranking.py`**

Add `AUTHORITATIVE_REFERENCE_DOMAINS` constant after existing constants:

```python
# Domains that are authoritative references but community-edited → medium reliability
AUTHORITATIVE_REFERENCE_DOMAINS = (
    "en.wikipedia.org",
    "zh.wikipedia.org",
)

# Domains that are peer-reviewed or official research outlets → high reliability
HIGH_AUTHORITY_DOMAINS = (
    "arxiv.org",
    "papers.nips.cc",
    "proceedings.mlr.press",
    "openreview.net",
    "dl.acm.org",
    "ieeexplore.ieee.org",
)
```

Update `reliability_for_source_type_and_url`:

```python
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
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_multi_provider_search.py -v
uv run pytest tests/test_query_engine.py -v
```
Expected: all PASSED.

- [ ] **Step 7: Commit**

```bash
git add agent/QueryEngine/tools/wikipedia_fetcher.py agent/QueryEngine/tools/crawler.py agent/QueryEngine/utils/ranking.py tests/test_multi_provider_search.py
git commit -m "feat(crawler): add Wikipedia authoritative supplement; HIGH_AUTHORITY_DOMAINS whitelist"
```

---

## Phase 1 — Stop Bad Sources at the Crawler

### Task 1: Decode Bing redirect URLs before scoring

Bing HTTP fallback returns URLs like `/ck/a?!&&p=...&u=a1aHR0c...` — the real destination is base64-encoded in the `u=` param. Scoring the redirect URL instead of the real URL means no signal from netloc.

**Files:**
- Modify: `agent/QueryEngine/tools/crawler.py`
- Modify: `agent/MediaEngine/tools/crawler.py`
- Test: `tests/test_source_relevance_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_source_relevance_filter.py
from __future__ import annotations

from agent.QueryEngine.tools.crawler import resolve_bing_redirect_url


def test_resolve_bing_redirect_decodes_base64_u_param() -> None:
    # Bing redirect: u= is base64url of actual URL
    import base64
    real = "https://scikit-learn.org/stable/index.html"
    encoded = base64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
    bing_redirect = f"https://www.bing.com/ck/a?!&&p=abc&u=a1a{encoded}&ntb=1"
    assert resolve_bing_redirect_url(bing_redirect) == real


def test_resolve_bing_redirect_returns_original_when_not_redirect() -> None:
    url = "https://scikit-learn.org/stable/"
    assert resolve_bing_redirect_url(url) == url


def test_resolve_bing_redirect_returns_original_on_malformed() -> None:
    url = "https://www.bing.com/ck/a?!&&p=abc&u=NOTBASE64!!!&ntb=1"
    assert resolve_bing_redirect_url(url) == url
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/lpb/workspace/myProjects/KnowledgeForge
uv run pytest tests/test_source_relevance_filter.py::test_resolve_bing_redirect_decodes_base64_u_param -v
```
Expected: `ImportError` or `AttributeError` — `resolve_bing_redirect_url` does not exist yet.

- [ ] **Step 3: Implement `resolve_bing_redirect_url` in QueryEngine crawler**

Add to `agent/QueryEngine/tools/crawler.py` after the imports, before class definition:

```python
import base64
from urllib.parse import parse_qs, urlparse as _urlparse


def resolve_bing_redirect_url(url: str) -> str:
    """Decode Bing /ck/a redirect to the real destination URL."""
    parsed = _urlparse(url)
    if "bing.com" not in parsed.netloc or "/ck/a" not in parsed.path:
        return url
    qs = parse_qs(parsed.query)
    u_values = qs.get("u", [])
    if not u_values:
        return url
    raw = u_values[0]
    # Bing prefixes the base64 with "a1a"
    if raw.startswith("a1a"):
        raw = raw[3:]
    # Restore base64 padding
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw).decode("utf-8")
    except Exception:
        return url
```

Then in `_search_http_provider`, before building the `SearchHit`, replace:
```python
result_url = anchor.get("href", "").strip()
```
with:
```python
result_url = resolve_bing_redirect_url(anchor.get("href", "").strip())
```

- [ ] **Step 4: Copy identical function to MediaEngine crawler**

Add the same `resolve_bing_redirect_url` function to `agent/MediaEngine/tools/crawler.py` (same location: after imports, before class). Apply the same one-line replacement in its `_search_http_provider`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_source_relevance_filter.py -v
```
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add agent/QueryEngine/tools/crawler.py agent/MediaEngine/tools/crawler.py tests/test_source_relevance_filter.py
git commit -m "feat(crawler): decode Bing redirect URLs before scoring"
```

---

### Task 2: Add domain relevance filter to QueryEngine crawler

After scoring and sorting hits, filter out results whose title + snippet + URL do not contain the full domain phrase or a recognized alias. A result matching only a sub-word (e.g., "machinery", "machine") must be discarded.

**Files:**
- Modify: `agent/QueryEngine/utils/ranking.py`
- Modify: `agent/QueryEngine/tools/crawler.py`
- Test: `tests/test_source_relevance_filter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_source_relevance_filter.py`:

```python
from agent.QueryEngine.utils.ranking import is_result_relevant


def test_relevant_result_passes_exact_phrase() -> None:
    assert is_result_relevant(
        title="Machine Learning Tutorial",
        snippet="An introduction to machine learning algorithms.",
        url="https://scikit-learn.org/stable/",
        domain_phrases=["machine learning", "ml"],
    )


def test_irrelevant_result_with_partial_word_is_rejected() -> None:
    # "machine" alone without "learning" must fail
    assert not is_result_relevant(
        title="Sewing Machine Parts Catalog",
        snippet="Find machine parts for all sewing models.",
        url="https://sewingmachineparts.example.com/",
        domain_phrases=["machine learning", "ml"],
    )


def test_irrelevant_result_weblio_dictionary_is_rejected() -> None:
    assert not is_result_relevant(
        title="machine - Weblio英和辞典",
        snippet="machineの日本語への翻訳。",
        url="https://ejje.weblio.jp/content/machine",
        domain_phrases=["machine learning", "ml"],
    )


def test_alias_match_passes() -> None:
    assert is_result_relevant(
        title="ML Ops Guide",
        snippet="Best practices for ML pipelines.",
        url="https://mlops.example.com/guide",
        domain_phrases=["machine learning", "ml"],
    )
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_source_relevance_filter.py::test_relevant_result_passes_exact_phrase -v
```
Expected: `ImportError` — `is_result_relevant` not defined yet.

- [ ] **Step 3: Implement `is_result_relevant` in `agent/QueryEngine/utils/ranking.py`**

Add after the existing constants:

```python
import re


def is_result_relevant(
    title: str,
    snippet: str,
    url: str,
    domain_phrases: list[str],
) -> bool:
    """Return True if at least one domain phrase appears as a whole phrase in title, snippet, or URL."""
    haystack = f"{title} {snippet} {url}".lower()
    for phrase in domain_phrases:
        # Match the phrase as a word-boundary sequence (handles multi-word phrases)
        pattern = r"(?<!\w)" + re.escape(phrase.lower()) + r"(?!\w)"
        if re.search(pattern, haystack):
            return True
    return False
```

- [ ] **Step 4: Wire relevance filter into `DomainKnowledgeCrawler._search_with_browser`**

In `agent/QueryEngine/tools/crawler.py`, update `_search_with_browser` to accept and apply `domain_phrases`:

Replace the method signature:
```python
def _search_with_browser(
    self,
    *,
    query: str,
    source_type: str,
    official_domains: list[str],
    preferred_domains: list[str] | None,
    max_results: int,
) -> list[SearchHit]:
```
with:
```python
def _search_with_browser(
    self,
    *,
    query: str,
    source_type: str,
    official_domains: list[str],
    preferred_domains: list[str] | None,
    max_results: int,
    domain_phrases: list[str] | None = None,
) -> list[SearchHit]:
```

After building `hits` and before `hits.sort(...)`, add:

```python
from agent.QueryEngine.utils.ranking import is_result_relevant

if domain_phrases:
    hits = [
        h for h in hits
        if is_result_relevant(h.title, h.snippet, h.url, domain_phrases)
    ]
```

Apply the same change to `_search_with_http_fallback` and `_search_http_provider` (pass `domain_phrases` through).

Also add `domain_phrases: list[str] | None = None` to the public `search()` method and pass it down to both private methods.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_source_relevance_filter.py -v
```
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add agent/QueryEngine/utils/ranking.py agent/QueryEngine/tools/crawler.py tests/test_source_relevance_filter.py
git commit -m "feat(crawler): add domain-phrase relevance filter to QueryEngine crawler"
```

---

### Task 3: Apply same relevance filter to MediaEngine crawler

**Files:**
- Modify: `agent/MediaEngine/tools/crawler.py`
- Test: `tests/test_source_relevance_filter.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_source_relevance_filter.py`:

```python
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.MediaEngine.state.state import MediaSearchHit


def test_media_crawler_filters_irrelevant_hits() -> None:
    noise_hit = MediaSearchHit(
        title="Sewing Machine Community Forum",
        url="https://sewingforum.example.com/",
        snippet="Discussion about sewing machine maintenance.",
        platform_type="community",
        score=5.0,
    )
    relevant_hit = MediaSearchHit(
        title="Machine Learning Reddit Discussion",
        url="https://reddit.com/r/MachineLearning/comments/abc",
        snippet="Best practices for machine learning in production.",
        platform_type="community",
        score=8.0,
    )
    # Use the internal filter directly
    crawler = MediaPerspectiveCrawler.__new__(MediaPerspectiveCrawler)
    result = crawler._filter_relevant_hits(
        [noise_hit, relevant_hit],
        domain_phrases=["machine learning", "ml"],
    )
    assert len(result) == 1
    assert result[0].url == relevant_hit.url
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_source_relevance_filter.py::test_media_crawler_filters_irrelevant_hits -v
```
Expected: `AttributeError` — `_filter_relevant_hits` not defined.

- [ ] **Step 3: Implement in MediaEngine crawler**

In `agent/MediaEngine/tools/crawler.py`, add import at top:
```python
from agent.QueryEngine.utils.ranking import is_result_relevant
```

Add method to `MediaPerspectiveCrawler`:
```python
def _filter_relevant_hits(
    self,
    hits: list,
    domain_phrases: list[str],
) -> list:
    if not domain_phrases:
        return hits
    return [
        h for h in hits
        if is_result_relevant(
            getattr(h, "title", ""),
            getattr(h, "snippet", ""),
            getattr(h, "url", ""),
            domain_phrases,
        )
    ]
```

Apply filter in `_search_with_browser` and `_search_http_provider` after building hits (same pattern as Task 2). Add `domain_phrases: list[str] | None = None` to public `search()` method.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_source_relevance_filter.py -v
```
Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add agent/MediaEngine/tools/crawler.py tests/test_source_relevance_filter.py
git commit -m "feat(crawler): add domain-phrase relevance filter to MediaEngine crawler"
```

---

### Task 4: Fix source credibility — `source_type=official` must not auto-grant `reliability=high`

Currently `reliability_for_source_type("official") == "high"` regardless of the actual domain. A Weblio URL tagged `source_type="official"` by the caller gets `reliability="high"`. Fix: `high` requires the URL's netloc to be in the verified `official_domains` list.

**Files:**
- Modify: `agent/QueryEngine/utils/ranking.py`
- Test: `tests/test_source_relevance_filter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_source_relevance_filter.py`:

```python
from agent.QueryEngine.utils.ranking import reliability_for_source_type_and_url


def test_official_source_type_with_verified_domain_gives_high() -> None:
    assert reliability_for_source_type_and_url(
        source_type="official",
        url="https://scikit-learn.org/stable/",
        official_domains=["scikit-learn.org"],
    ) == "high"


def test_official_source_type_with_unverified_domain_gives_medium() -> None:
    # Weblio is NOT in official_domains
    assert reliability_for_source_type_and_url(
        source_type="official",
        url="https://ejje.weblio.jp/content/machine+learning",
        official_domains=["scikit-learn.org"],
    ) == "medium"


def test_tutorial_source_type_always_medium() -> None:
    assert reliability_for_source_type_and_url(
        source_type="tutorial",
        url="https://medium.com/some-article",
        official_domains=[],
    ) == "medium"


def test_unknown_source_type_gives_unknown() -> None:
    assert reliability_for_source_type_and_url(
        source_type="reference",
        url="https://example.com/",
        official_domains=[],
    ) == "unknown"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_source_relevance_filter.py::test_official_source_type_with_verified_domain_gives_high -v
```
Expected: `ImportError` — `reliability_for_source_type_and_url` not defined.

- [ ] **Step 3: Add `reliability_for_source_type_and_url` to `agent/QueryEngine/utils/ranking.py`**

Add after `reliability_for_source_type`:

```python
def reliability_for_source_type_and_url(
    source_type: str,
    url: str,
    official_domains: list[str],
) -> str:
    """Assign reliability only after verifying the URL against official_domains."""
    if source_type == "official":
        netloc = urlparse(url).netloc.lower()
        if any(domain.lower() in netloc for domain in official_domains):
            return "high"
        return "medium"
    if source_type == "tutorial":
        return "medium"
    return "unknown"
```

Keep `reliability_for_source_type` for backward compatibility (it is still used in tests).

- [ ] **Step 4: Update callers in QueryEngine**

Search for all call sites of `reliability_for_source_type` in the QueryEngine agent:

```bash
grep -rn "reliability_for_source_type" agent/QueryEngine/
```

For each call site that has access to `url` and `official_domains`, replace with `reliability_for_source_type_and_url(source_type, url, official_domains)`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_source_relevance_filter.py -v
uv run pytest tests/test_query_engine.py -v
```
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add agent/QueryEngine/utils/ranking.py tests/test_source_relevance_filter.py
git commit -m "fix(ranking): require verified domain for official reliability=high"
```

---

### Task 5: Fix MediaEngine platform classification — no fallback to `requested_type`

Currently `classify_platform_type` returns `requested_type` when no known domain matches. This lets any unknown URL inherit `platform_type="community"` and `reliability="medium"`. Fix: return `"unknown"` instead and treat `"unknown"` as a low-quality signal.

**Files:**
- Modify: `agent/MediaEngine/utils/ranking.py`
- Test: `tests/test_source_relevance_filter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_source_relevance_filter.py`:

```python
from agent.MediaEngine.utils.ranking import classify_platform_type, reliability_for_platform_type


def test_classify_unknown_domain_returns_unknown() -> None:
    assert classify_platform_type("https://ejje.weblio.jp/content/machine+learning") == "unknown"


def test_classify_reddit_returns_community() -> None:
    assert classify_platform_type("https://reddit.com/r/MachineLearning/") == "community"


def test_reliability_unknown_platform_type_returns_unknown() -> None:
    assert reliability_for_platform_type("unknown", "some content here") == "unknown"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_source_relevance_filter.py::test_classify_unknown_domain_returns_unknown -v
```
Expected: FAIL — current code returns `"community"` (the default requested_type).

- [ ] **Step 3: Fix `classify_platform_type` in `agent/MediaEngine/utils/ranking.py`**

Change the last line of `classify_platform_type`:

```python
# Before:
return requested_type

# After:
return "unknown"
```

Remove the `requested_type` parameter entirely (it was only used for the fallback):

```python
def classify_platform_type(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    if any(domain in netloc for domain in SOCIAL_DOMAINS):
        return "social"
    if any(domain in netloc for domain in COMMUNITY_DOMAINS):
        return "community"
    if any(hint in netloc for hint in BLOG_HINTS):
        return "blog"
    return "unknown"
```

Update all callers of `classify_platform_type` in `agent/MediaEngine/tools/crawler.py` to remove the `requested_type` argument.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_source_relevance_filter.py -v
uv run pytest tests/test_media_engine.py -v
```
Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add agent/MediaEngine/utils/ranking.py agent/MediaEngine/tools/crawler.py tests/test_source_relevance_filter.py
git commit -m "fix(ranking): MediaEngine platform classification falls back to unknown, not requested_type"
```

---

## Phase 2 — Strengthen CompletenessEvaluator

### Task 6: Add source-relevance and authority checks to CompletenessEvaluator

Currently `has_authoritative_sources = bool(query_output and query_output.sources)` — any non-empty sources list passes. Fix: require at least one source with `reliability in ("high", "medium")`.

Also add structured failure categories to `CompletenessResult`.

**Files:**
- Modify: `knowledgeforge/models.py`
- Modify: `knowledgeforge/evaluation/completeness.py`
- Test: `tests/test_completeness_source_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_completeness_source_gate.py
from __future__ import annotations

from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord


def _make_context(domain: str = "Machine Learning") -> RequestContext:
    return RequestContext(
        domain=domain,
        subdomains=["supervised learning", "unsupervised learning"],
        time_window="2024",
        focus_points=["applications"],
        constraints=[],
        initial_strategy=[],
    )


def _make_source(
    title: str = "ML Guide",
    url: str = "https://scikit-learn.org/",
    reliability: str = "high",
) -> SourceRecord:
    return SourceRecord(
        title=title,
        url=url,
        publisher="scikit-learn.org",
        retrieved_at="2024-01-01T00:00:00Z",
        reliability=reliability,  # type: ignore[arg-type]
        agent="QueryEngine",
    )


def _make_engine_result(sources: list[SourceRecord], topics: list[str]) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="summary",
        key_points=[],
        raw_material=[],
        coverage_topics=topics,
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def test_passes_with_high_reliability_source_and_full_coverage() -> None:
    ctx = _make_context()
    output = _make_engine_result(
        sources=[_make_source(reliability="high")],
        topics=["supervised learning", "unsupervised learning"],
    )
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    assert result.status == "pass"


def test_fails_when_all_sources_are_unknown_reliability() -> None:
    ctx = _make_context()
    output = _make_engine_result(
        sources=[_make_source(reliability="unknown")],
        topics=["supervised learning", "unsupervised learning"],
    )
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    assert result.status == "supplement_required"
    assert any("no_authoritative_source" in r for r in result.failure_categories)


def test_fails_when_sources_empty() -> None:
    ctx = _make_context()
    output = _make_engine_result(sources=[], topics=["supervised learning", "unsupervised learning"])
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    assert result.status == "supplement_required"


def test_supplement_queries_are_domain_specific() -> None:
    ctx = _make_context()
    output = _make_engine_result(sources=[], topics=[])
    result = CompletenessEvaluator().evaluate(ctx, {"QueryEngine": output})
    for q in result.supplement_queries:
        assert "machine learning" in q.lower() or "ml" in q.lower()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_completeness_source_gate.py -v
```
Expected: multiple failures — `failure_categories` attribute doesn't exist yet, and reliability check is missing.

- [ ] **Step 3: Add `failure_categories` to `CompletenessResult` in `knowledgeforge/models.py`**

Update the `CompletenessResult` dataclass:

```python
@dataclass(slots=True)
class CompletenessResult:
    status: CompletenessStatus
    reasons: list[str]
    missing_topics: list[str]
    supplement_queries: list[str]
    failure_categories: list[str] = field(default_factory=list)
```

Also add `field` to the import at the top of `models.py` if not already present:
```python
from dataclasses import asdict, dataclass, field
```

- [ ] **Step 4: Update `CompletenessEvaluator` in `knowledgeforge/evaluation/completeness.py`**

Replace the entire `evaluate` method:

```python
def evaluate(
    self,
    context: RequestContext,
    outputs: dict[str, EngineRunResult],
) -> CompletenessResult:
    covered_topics = {
        topic
        for output in outputs.values()
        for topic in output.coverage_topics
    }
    missing_topics = [topic for topic in context.subdomains if topic not in covered_topics]

    query_output = outputs.get("QueryEngine")
    all_sources = [s for output in outputs.values() for s in output.sources]
    authoritative_sources = [
        s for s in all_sources if s.reliability in ("high", "medium")
    ]
    has_authoritative_sources = bool(authoritative_sources)

    reasons: list[str] = []
    failure_categories: list[str] = []

    if not all_sources:
        reasons.append("缺少 QueryEngine 提供的可引用来源。")
        failure_categories.append("no_authoritative_source")
    elif not has_authoritative_sources:
        reasons.append("来源存在但可信度均为 unknown，无法作为权威证据。")
        failure_categories.append("no_authoritative_source")

    if missing_topics:
        reasons.append("存在未覆盖的核心子主题。")
        failure_categories.append("missing_topics")

    if reasons:
        domain_lower = context.domain.lower()
        supplement_queries = [
            f"{context.domain} official introduction site:ibm.com OR site:scikit-learn.org",
            f"{context.domain} supervised unsupervised reinforcement learning authoritative source",
            f"{context.domain} applications official documentation",
        ] if not missing_topics else [
            f"{context.domain} {topic} 官方资料"
            for topic in missing_topics
        ]
        return CompletenessResult(
            status="supplement_required",
            reasons=reasons,
            missing_topics=missing_topics,
            supplement_queries=supplement_queries,
            failure_categories=failure_categories,
        )

    return CompletenessResult(
        status="pass",
        reasons=["核心子主题已覆盖，且存在可引用权威来源。"],
        missing_topics=[],
        supplement_queries=[],
        failure_categories=[],
    )
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_completeness_source_gate.py -v
uv run pytest tests/ -v --ignore=tests/test_agent_browser_live.py
```
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add knowledgeforge/models.py knowledgeforge/evaluation/completeness.py tests/test_completeness_source_gate.py
git commit -m "feat(completeness): require authoritative sources; add failure_categories"
```

---

## Phase 3 — Quality Checker Source Gate

### Task 7: Add source quality checks to QualityChecker and block freeze on weak sources

Currently `QualityChecker` only validates document structure, not source quality. Add five new checks. A document with irrelevant or no authoritative sources must not be `"passed"`.

**Files:**
- Modify: `knowledgeforge/quality/checker.py`
- Test: `tests/test_quality_source_checks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_quality_source_checks.py
from __future__ import annotations

from pathlib import Path
import tempfile

from knowledgeforge.models import (
    DocumentArtifact,
    EngineRunResult,
    GraphSyncResult,
    QualityCheckResult,
    RequestContext,
    SourceRecord,
    StructuredExtractionResult,
)
from knowledgeforge.quality.checker import QualityChecker


def _make_artifact(content: str) -> DocumentArtifact:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return DocumentArtifact(
        document_id="test-doc-001",
        title="Test",
        domain="Machine Learning",
        subdomain="supervised learning",
        path=tmp.name,
        status="draft",
        version="v1",
    )


_VALID_CONTENT = (
    "---\nid: test\n---\n\n# Title\n\n## 证据与来源\n\n| 编号 | 来源 | 关键信息 | 可信度 | 备注 |\n"
    "|---|---|---|---|---|\n| S1 | Example | Info | high | Q |\n"
)

_VALID_EXTRACTION = StructuredExtractionResult(
    document_id="test-doc-001",
    document_path="/tmp/test.md",
    chunks=[],
    metadata={},
    entities=[{"name": "Machine Learning"}],
    relations=[],
)

_VALID_GRAPH = GraphSyncResult(
    document_id="test-doc-001",
    article_path="/tmp/test.md",
    nodes=[{"id": "n1"}],
    relationships=[],
)

_VALID_CONTEXT = RequestContext(
    domain="Machine Learning",
    subdomains=["supervised learning"],
    time_window="2024",
    focus_points=["applications"],
    constraints=[],
    initial_strategy=[],
)


def _engine_result(sources: list[SourceRecord]) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="summary",
        key_points=[],
        raw_material=[],
        coverage_topics=["supervised learning"],
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def _source(reliability: str, title: str = "ML Guide", url: str = "https://scikit-learn.org/") -> SourceRecord:
    return SourceRecord(
        title=title,
        url=url,
        publisher="scikit-learn.org",
        retrieved_at="2024-01-01T00:00:00Z",
        reliability=reliability,  # type: ignore[arg-type]
        agent="QueryEngine",
    )


def test_passes_with_authoritative_source() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([_source("high")])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    assert result.status == "passed"


def test_fails_with_only_unknown_reliability_sources() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([_source("unknown")])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    assert result.status == "failed"
    assert any("source_quality" in issue.category for issue in result.issues)


def test_fails_with_no_sources() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    assert result.status == "failed"


def test_source_quality_issue_uses_research_flow() -> None:
    artifact = _make_artifact(_VALID_CONTENT)
    outputs = {"QueryEngine": _engine_result([_source("unknown")])}
    result = QualityChecker().check(artifact, _VALID_EXTRACTION, _VALID_GRAPH, _VALID_CONTEXT, outputs)
    quality_issues = [i for i in result.issues if "source_quality" in i.category]
    assert all(i.flow == "research_flow" for i in quality_issues)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_quality_source_checks.py::test_fails_with_only_unknown_reliability_sources -v
```
Expected: FAIL — result is currently `"passed"` for unknown-reliability sources.

- [ ] **Step 3: Update `FailureCategory` literal in `knowledgeforge/models.py`**

Add `"source_quality_failed"` to the `FailureCategory` literal:

```python
FailureCategory = Literal[
    "file_write_failed",
    "graph_write_failed",
    "path_association_failed",
    "quality_check_failed",
    "source_quality_failed",
]
```

- [ ] **Step 4: Add source quality checks to `QualityChecker`**

In `knowledgeforge/quality/checker.py`, extend the `check` method. After the existing `checks` dict, add:

```python
all_sources = [s for output in outputs.values() for s in output.sources]
authoritative_sources = [s for s in all_sources if s.reliability in ("high", "medium")]
has_authoritative = bool(authoritative_sources)

source_checks = {
    "source_relevance_check": has_authoritative,
    "authority_check": bool(all_sources) and has_authoritative,
    "evidence_support_check": bool(all_sources),
}
```

Then add issue generation for source failures, before the existing `status` line:

```python
if not source_checks["evidence_support_check"]:
    issues.append(
        QualityIssue(
            category="source_quality_failed",
            detail="缺少任何可引用来源，需要重新检索权威证据。",
            flow="research_flow",
        )
    )
elif not source_checks["authority_check"]:
    issues.append(
        QualityIssue(
            category="source_quality_failed",
            detail="来源不相关或可信度均为 unknown，需要重新检索权威证据。",
            flow="research_flow",
        )
    )

# merge check dicts
checks.update(source_checks)
status = "failed" if issues else "passed"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_quality_source_checks.py -v
uv run pytest tests/ -v --ignore=tests/test_agent_browser_live.py
```
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add knowledgeforge/models.py knowledgeforge/quality/checker.py tests/test_quality_source_checks.py
git commit -m "feat(quality): add source quality checks; block pass on unknown-reliability sources"
```

---

## Phase 4 — Writer Dynamic Status Messaging

### Task 8: MarkdownWriter produces status-aware summaries and uses source snippets in evidence table

Currently the writer unconditionally writes "首版知识结构已经形成" and uses `output.summary` in the evidence table's 关键信息 column. Fix: (1) vary key_conclusions by `completeness.status`, (2) use `source.snippet` (falling back to `output.summary`) in evidence rows.

**Files:**
- Modify: `knowledgeforge/storage/markdown_writer.py`
- Test: `tests/test_writer_dynamic_status.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_writer_dynamic_status.py
from __future__ import annotations

import tempfile
from pathlib import Path

from knowledgeforge.config import AppConfig
from knowledgeforge.models import (
    CompletenessResult,
    EngineRunResult,
    RequestContext,
    SourceRecord,
)
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter


def _make_config() -> AppConfig:
    tmp_dir = Path(tempfile.mkdtemp())
    return AppConfig(save_root=tmp_dir)


def _make_context() -> RequestContext:
    return RequestContext(
        domain="Machine Learning",
        subdomains=["supervised learning"],
        time_window="2024",
        focus_points=["applications"],
        constraints=[],
        initial_strategy=[],
    )


def _make_source(snippet: str = "Key finding about ML.") -> SourceRecord:
    return SourceRecord(
        title="ML Guide",
        url="https://scikit-learn.org/",
        publisher="scikit-learn.org",
        retrieved_at="2024-01-01T00:00:00Z",
        reliability="high",
        agent="QueryEngine",
        snippet=snippet,
    )


def _make_engine_result(sources: list[SourceRecord]) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="This is the engine summary, not the snippet.",
        key_points=["point 1"],
        raw_material=["raw 1"],
        coverage_topics=["supervised learning"],
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def test_writer_pass_status_uses_positive_conclusion() -> None:
    writer = MarkdownKnowledgeWriter(_make_config())
    ctx = _make_context()
    outputs = {"QueryEngine": _make_engine_result([_make_source()])}
    completeness = CompletenessResult(
        status="pass",
        reasons=["ok"],
        missing_topics=[],
        supplement_queries=[],
        failure_categories=[],
    )
    artifact = writer.write(ctx, outputs, completeness, round_number=1)
    content = Path(artifact.path).read_text(encoding="utf-8")
    assert "可以进入治理流程" in content
    assert "首版知识结构已经形成" not in content


def test_writer_supplement_required_uses_draft_conclusion() -> None:
    writer = MarkdownKnowledgeWriter(_make_config())
    ctx = _make_context()
    outputs = {"QueryEngine": _make_engine_result([])}
    completeness = CompletenessResult(
        status="supplement_required",
        reasons=["缺少来源"],
        missing_topics=[],
        supplement_queries=["Machine Learning official docs"],
        failure_categories=["no_authoritative_source"],
    )
    artifact = writer.write(ctx, outputs, completeness, round_number=1)
    content = Path(artifact.path).read_text(encoding="utf-8")
    assert "草稿" in content
    assert "补检索" in content


def test_evidence_table_uses_source_snippet_not_engine_summary() -> None:
    writer = MarkdownKnowledgeWriter(_make_config())
    ctx = _make_context()
    snippet = "Specific finding from the actual source page."
    outputs = {"QueryEngine": _make_engine_result([_make_source(snippet=snippet)])}
    completeness = CompletenessResult(
        status="pass", reasons=[], missing_topics=[], supplement_queries=[], failure_categories=[]
    )
    artifact = writer.write(ctx, outputs, completeness, round_number=1)
    content = Path(artifact.path).read_text(encoding="utf-8")
    assert snippet in content
    assert "This is the engine summary, not the snippet." not in content.split("## 证据与来源")[1]
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_writer_dynamic_status.py -v
```
Expected: 3 FAILED — current writer uses hardcoded conclusions and engine summary in evidence table.

- [ ] **Step 3: Update `_render_document` in `knowledgeforge/storage/markdown_writer.py`**

Replace the `key_conclusions` block (lines 104–108):

```python
# Before:
key_conclusions = [
    f"{context.domain} 的首版知识结构已经形成，可进入后续治理流程。",
    "当前结果包含可引用来源，满足最小知识沉淀条件。",
    "后续可在质量闭环阶段继续细化实体、关系与冲突裁决。",
]
```

```python
# After:
if completeness.status == "pass":
    key_conclusions = [
        f"{context.domain} 已覆盖核心子主题，可以进入治理流程。",
        "来源包含可引用权威证据，满足知识沉淀最小条件。",
        "后续可在质量闭环阶段继续细化实体、关系与冲突裁决。",
    ]
else:
    failure_hints = "、".join(completeness.failure_categories) if completeness.failure_categories else "来源不足"
    key_conclusions = [
        f"{context.domain} 当前结果为草稿状态，尚不满足入库条件（{failure_hints}）。",
        "需要执行补检索任务，补充权威来源后重新评估。",
        "在来源质量通过前，不允许冻结或进入报告流程。",
    ]
```

Replace the evidence_rows building block (lines 129–136):

```python
# Before:
for source in output.sources:
    evidence_rows.append(
        f"| S{source_counter} | {source.title} | {output.summary} | {source.reliability} | {source.agent} |"
    )
```

```python
# After:
for source in output.sources:
    key_info = source.snippet if source.snippet.strip() else output.summary
    evidence_rows.append(
        f"| S{source_counter} | {source.title} | {key_info} | {source.reliability} | {source.agent} |"
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_writer_dynamic_status.py -v
uv run pytest tests/ -v --ignore=tests/test_agent_browser_live.py
```
Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add knowledgeforge/storage/markdown_writer.py tests/test_writer_dynamic_status.py
git commit -m "feat(writer): dynamic status conclusions; evidence table uses source snippet"
```

---

## Phase 5 — Regression Tests for Machine Learning

### Task 9: End-to-end regression: ML query rejects Weblio noise and triggers supplement

This task adds a full-pipeline regression test that uses fake crawlers to simulate the Weblio noisy-source scenario and verifies every defense layer fires correctly.

**Files:**
- Test: `tests/test_ml_regression.py`

- [ ] **Step 1: Write the regression test**

```python
# tests/test_ml_regression.py
"""Regression: 'Machine Learning' query must reject Weblio/dictionary noise."""
from __future__ import annotations

import tempfile
from pathlib import Path

from agent.QueryEngine.utils.ranking import is_result_relevant, reliability_for_source_type_and_url
from agent.MediaEngine.utils.ranking import classify_platform_type
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.quality.checker import QualityChecker
from knowledgeforge.models import (
    DocumentArtifact,
    GraphSyncResult,
    StructuredExtractionResult,
)


ML_CONTEXT = RequestContext(
    domain="Machine Learning",
    subdomains=["supervised learning", "unsupervised learning", "reinforcement learning"],
    time_window="2024",
    focus_points=["applications", "algorithms"],
    constraints=[],
    initial_strategy=[],
)

DOMAIN_PHRASES = ["machine learning", "ml"]

WEBLIO_SOURCE = SourceRecord(
    title="machine - Weblio英和辞典",
    url="https://ejje.weblio.jp/content/machine",
    publisher="ejje.weblio.jp",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="unknown",
    agent="QueryEngine",
    snippet="machineの日本語への翻訳。",
)

SEWING_SOURCE = SourceRecord(
    title="Sewing Machine Parts Catalog",
    url="https://sewingmachineparts.example.com/",
    publisher="sewingmachineparts.example.com",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="unknown",
    agent="QueryEngine",
    snippet="Find sewing machine parts for all models.",
)

AUTHORITATIVE_SOURCE = SourceRecord(
    title="Machine Learning - IBM Developer",
    url="https://developer.ibm.com/articles/cc-machine-learning-deep-learning-architectures/",
    publisher="developer.ibm.com",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="high",
    agent="QueryEngine",
    snippet="Machine learning is a subset of artificial intelligence that enables systems to learn.",
)

SKLEARN_SOURCE = SourceRecord(
    title="scikit-learn: machine learning in Python",
    url="https://scikit-learn.org/stable/",
    publisher="scikit-learn.org",
    retrieved_at="2024-01-01T00:00:00Z",
    reliability="high",
    agent="QueryEngine",
    snippet="Simple and efficient tools for predictive data analysis built on NumPy, SciPy, and matplotlib.",
)


# --- Relevance filter ---

def test_weblio_url_is_rejected_by_relevance_filter() -> None:
    assert not is_result_relevant(
        title=WEBLIO_SOURCE.title,
        snippet=WEBLIO_SOURCE.snippet,
        url=WEBLIO_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


def test_sewing_machine_is_rejected_by_relevance_filter() -> None:
    assert not is_result_relevant(
        title=SEWING_SOURCE.title,
        snippet=SEWING_SOURCE.snippet,
        url=SEWING_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


def test_ibm_ml_source_passes_relevance_filter() -> None:
    assert is_result_relevant(
        title=AUTHORITATIVE_SOURCE.title,
        snippet=AUTHORITATIVE_SOURCE.snippet,
        url=AUTHORITATIVE_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


def test_sklearn_source_passes_relevance_filter() -> None:
    assert is_result_relevant(
        title=SKLEARN_SOURCE.title,
        snippet=SKLEARN_SOURCE.snippet,
        url=SKLEARN_SOURCE.url,
        domain_phrases=DOMAIN_PHRASES,
    )


# --- Credibility ---

def test_weblio_tagged_official_does_not_get_high_reliability() -> None:
    result = reliability_for_source_type_and_url(
        source_type="official",
        url=WEBLIO_SOURCE.url,
        official_domains=["scikit-learn.org", "developer.ibm.com"],
    )
    assert result != "high"


def test_sklearn_tagged_official_gets_high_reliability() -> None:
    result = reliability_for_source_type_and_url(
        source_type="official",
        url=SKLEARN_SOURCE.url,
        official_domains=["scikit-learn.org"],
    )
    assert result == "high"


# --- Media platform ---

def test_weblio_is_classified_as_unknown_platform() -> None:
    assert classify_platform_type(WEBLIO_SOURCE.url) == "unknown"


# --- Completeness ---

def _engine_result(sources: list[SourceRecord], topics: list[str] | None = None) -> EngineRunResult:
    return EngineRunResult(
        agent_name="QueryEngine",
        summary="summary",
        key_points=[],
        raw_material=[],
        coverage_topics=topics or ["supervised learning", "unsupervised learning", "reinforcement learning"],
        sources=sources,
        collected_at="2024-01-01T00:00:00Z",
        round_number=1,
    )


def test_only_weblio_sources_trigger_supplement_required() -> None:
    output = _engine_result(sources=[WEBLIO_SOURCE, SEWING_SOURCE])
    result = CompletenessEvaluator().evaluate(ML_CONTEXT, {"QueryEngine": output})
    assert result.status == "supplement_required"
    assert "no_authoritative_source" in result.failure_categories


def test_authoritative_sources_pass_completeness() -> None:
    output = _engine_result(sources=[AUTHORITATIVE_SOURCE, SKLEARN_SOURCE])
    result = CompletenessEvaluator().evaluate(ML_CONTEXT, {"QueryEngine": output})
    assert result.status == "pass"


# --- Quality Checker ---

def _make_valid_doc() -> DocumentArtifact:
    content = (
        "---\nid: test\n---\n\n# ML\n\n## 证据与来源\n\n"
        "| 编号 | 来源 | 关键信息 | 可信度 | 备注 |\n|---|---|---|---|---|\n"
        "| S1 | IBM | ML intro | high | Q |\n"
    )
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return DocumentArtifact(
        document_id="ml-regression-001",
        title="Machine Learning",
        domain="Machine Learning",
        subdomain="supervised learning",
        path=tmp.name,
        status="draft",
        version="v1",
    )


_EXTRACTION = StructuredExtractionResult(
    document_id="ml-regression-001",
    document_path="/tmp/ml.md",
    chunks=[],
    metadata={},
    entities=[{"name": "Machine Learning"}],
    relations=[],
)

_GRAPH = GraphSyncResult(
    document_id="ml-regression-001",
    article_path="/tmp/ml.md",
    nodes=[{"id": "n1"}],
    relationships=[],
)


def test_quality_checker_fails_on_weblio_only_sources() -> None:
    artifact = _make_valid_doc()
    outputs = {"QueryEngine": _engine_result(sources=[WEBLIO_SOURCE, SEWING_SOURCE])}
    result = QualityChecker().check(artifact, _EXTRACTION, _GRAPH, ML_CONTEXT, outputs)
    assert result.status == "failed"
    assert any("source_quality_failed" in i.category for i in result.issues)


def test_quality_checker_passes_on_authoritative_sources() -> None:
    artifact = _make_valid_doc()
    outputs = {"QueryEngine": _engine_result(sources=[AUTHORITATIVE_SOURCE, SKLEARN_SOURCE])}
    result = QualityChecker().check(artifact, _EXTRACTION, _GRAPH, ML_CONTEXT, outputs)
    assert result.status == "passed"
```

- [ ] **Step 2: Run to verify initial state**

```bash
uv run pytest tests/test_ml_regression.py -v
```
After all previous tasks are complete, expected: all PASSED.
If any fail, identify which task's implementation needs fixing before continuing.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --ignore=tests/test_agent_browser_live.py
```
Expected: all PASSED. Fix any regressions before committing.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ml_regression.py
git commit -m "test(regression): ML Weblio noise rejected across all pipeline layers"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task(s) |
|-----------------|---------|
| 多搜索引擎：Google、Brave 加入 HTTP fallback | Task 0a |
| Wikipedia 权威补充来源（medium 可信度） | Task 0b |
| arxiv / IEEE / ACM / NeurIPS 识别为 high | Task 0b |
| 标题、摘要、URL 命中完整领域短语 | Task 2, 3 |
| 过滤搜索引擎跳转域，解析 Bing /ck/a | Task 1 |
| source_type=official 不等于 high | Task 4 |
| Media 平台分类不 fallback 到 requested_type | Task 5 |
| CompletenessEvaluator 要求 1 个高相关来源 | Task 6 |
| 失败原因分类 | Task 6 |
| 失败时生成定向补检索 | Task 6 |
| QualityChecker source quality checks | Task 7 |
| 冻结规则：source quality 通过才允许 frozen | Task 7 |
| Writer 动态结论文案 | Task 8 |
| 证据表关键信息用 source snippet | Task 8 |
| ML 回归测试 | Task 9 |

### Placeholder scan
No TBD, TODO, or "similar to" references present.

### Type consistency
- `CompletenessResult.failure_categories: list[str]` — added in Task 6, used in Task 8 (`completeness.failure_categories`). ✓
- `SourceRecord.snippet: str` — already defined in `models.py:38`. ✓
- `reliability_for_source_type_and_url(source_type, url, official_domains)` — defined Task 4, used Task 9. ✓
- `is_result_relevant(title, snippet, url, domain_phrases)` — defined Task 2, used Tasks 3, 9. ✓
- `classify_platform_type(url)` — signature simplified in Task 5 (drops `requested_type`). Callers updated in Task 5. ✓
- `QualityIssue.category` accepts `"source_quality_failed"` — added to `FailureCategory` literal in Task 7. ✓
