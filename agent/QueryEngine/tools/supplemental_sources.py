from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx


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
        ),
    ]


def probe_source_url(
    target: SupplementalSourceTarget,
    *,
    timeout: float = 8.0,
    headers: dict[str, str] | None = None,
    client: httpx.Client | None = None,
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
