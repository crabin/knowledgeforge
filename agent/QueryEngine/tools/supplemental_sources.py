from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

from knowledgeforge.tools.agent_browser_cli import AgentBrowserCLI


BLOCKED_ZHIHU_MARKERS = (
    "40362",
    "请求存在异常",
    "暂时限制本次访问",
    "知乎小管家",
)


@dataclass(frozen=True, slots=True)
class SupplementalSourceTarget:
    key: str
    label: str
    url: str
    publisher: str
    snippet: str
    blocked_markers: tuple[str, ...] = ()
    min_text_chars: int = 32
    allow_browser_fallback: bool = False


@dataclass(frozen=True, slots=True)
class SourceProbeResult:
    key: str
    url: str
    available: bool
    status_code: int | None
    final_url: str
    reason: str
    content_chars: int


def build_supplemental_source_targets(query: str) -> list[SupplementalSourceTarget]:
    encoded_query = quote_plus(" ".join(query.split()))
    return [
        SupplementalSourceTarget(
            key="tencent_cloud",
            label="腾讯云开发者社区搜索",
            url=f"https://cloud.tencent.com/developer/search/article-{encoded_query}",
            publisher="cloud.tencent.com",
            snippet="腾讯云开发者社区文章搜索结果页，可作为中文技术资料补源。",
        ),
        SupplementalSourceTarget(
            key="zhihu_search",
            label="知乎搜索",
            url=f"https://www.zhihu.com/search?type=content&q={encoded_query}",
            publisher="www.zhihu.com",
            snippet="知乎站内搜索页；若问题页被限制，可改从搜索结果页回溯相关内容。",
            blocked_markers=BLOCKED_ZHIHU_MARKERS,
        ),
        SupplementalSourceTarget(
            key="zh_wikipedia",
            label="中文维基百科搜索",
            url=f"https://zh.wikipedia.org/w/index.php?search={encoded_query}&title=Special%3ASearch&ns0=1",
            publisher="zh.wikipedia.org",
            snippet="中文维基百科搜索结果页，可补充概念定义与术语映射。",
            allow_browser_fallback=True,
        ),
    ]


def probe_source_url(
    target: SupplementalSourceTarget,
    *,
    timeout: float = 8.0,
    headers: dict[str, str] | None = None,
    client: httpx.Client | None = None,
    browser_fetcher: callable | None = None,
) -> SourceProbeResult:
    def build_result(
        *,
        available: bool,
        status_code: int | None,
        final_url: str,
        reason: str,
        content_chars: int,
    ) -> SourceProbeResult:
        return SourceProbeResult(
            key=target.key,
            url=target.url,
            available=available,
            status_code=status_code,
            final_url=final_url,
            reason=reason,
            content_chars=content_chars,
        )

    local_headers = headers or {"User-Agent": "KnowledgeForgeBot/0.1"}
    if browser_fetcher is None and target.allow_browser_fallback:
        browser = AgentBrowserCLI(timeout=max(timeout * 2, 12.0))
        if browser.available:
            browser_fetcher = browser.fetch_text
    try:
        if client is None:
            response = httpx.get(
                target.url,
                timeout=timeout,
                headers=local_headers,
                follow_redirects=True,
            )
        else:
            response = client.get(target.url)
    except Exception as exc:
        return build_result(
            available=False,
            status_code=None,
            final_url=target.url,
            reason=f"request_failed:{exc.__class__.__name__}",
            content_chars=0,
        )

    text = response.text or ""
    compact_text = " ".join(text.split())
    final_url = str(getattr(response, "url", target.url))
    if response.status_code >= 400:
        browser_result = _probe_with_browser_fallback(
            target,
            timeout=timeout,
            browser_fetcher=browser_fetcher,
            status_code=response.status_code,
            final_url=final_url,
        )
        if browser_result is not None:
            return browser_result
        return build_result(
            available=False,
            status_code=response.status_code,
            final_url=final_url,
            reason=f"http_{response.status_code}",
            content_chars=len(compact_text),
        )
    if any(marker in text for marker in target.blocked_markers):
        return build_result(
            available=False,
            status_code=response.status_code,
            final_url=final_url,
            reason="blocked_marker_detected",
            content_chars=len(compact_text),
        )
    if len(compact_text) < target.min_text_chars:
        return build_result(
            available=False,
            status_code=response.status_code,
            final_url=final_url,
            reason="content_too_short",
            content_chars=len(compact_text),
        )
    return build_result(
        available=True,
        status_code=response.status_code,
        final_url=final_url,
        reason="ok",
        content_chars=len(compact_text),
    )


def _probe_with_browser_fallback(
    target: SupplementalSourceTarget,
    *,
    timeout: float,
    browser_fetcher: callable | None,
    status_code: int | None,
    final_url: str,
) -> SourceProbeResult | None:
    del timeout
    if not target.allow_browser_fallback or browser_fetcher is None:
        return None
    try:
        browser_text = browser_fetcher(target.url) or ""
    except Exception as exc:
        return SourceProbeResult(
            key=target.key,
            url=target.url,
            available=False,
            status_code=status_code,
            final_url=final_url,
            reason=f"http_{status_code}_browser_failed:{exc.__class__.__name__}",
            content_chars=0,
        )
    compact_text = " ".join(browser_text.split())
    if any(marker in browser_text for marker in target.blocked_markers):
        return SourceProbeResult(
            key=target.key,
            url=target.url,
            available=False,
            status_code=status_code,
            final_url=final_url,
            reason="browser_blocked_marker_detected",
            content_chars=len(compact_text),
        )
    if len(compact_text) < target.min_text_chars:
        return SourceProbeResult(
            key=target.key,
            url=target.url,
            available=False,
            status_code=status_code,
            final_url=final_url,
            reason=f"http_{status_code}_browser_content_too_short",
            content_chars=len(compact_text),
        )
    return SourceProbeResult(
        key=target.key,
        url=target.url,
        available=True,
        status_code=status_code,
        final_url=target.url,
        reason="browser_fallback_ok",
        content_chars=len(compact_text),
    )
