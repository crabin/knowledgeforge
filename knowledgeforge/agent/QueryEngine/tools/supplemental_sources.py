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

IT_TUTORIAL_KEYWORDS = (
    "python",
    "java",
    "javascript",
    "typescript",
    "golang",
    "go ",
    "rust",
    "c++",
    "c#",
    "linux",
    "docker",
    "kubernetes",
    "mysql",
    "postgresql",
    "redis",
    "nginx",
    "flask",
    "django",
    "fastapi",
    "react",
    "vue",
    "node",
    "langgraph",
    "llm",
    "ai",
    "machine learning",
    "deep learning",
    "gan",
    "教程",
    "入门",
    "示例",
    "代码",
    "开发",
    "编程",
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
    http_status_code: int | None
    final_url: str
    probe_method: str
    reason: str
    content_chars: int


def build_supplemental_source_targets(query: str) -> list[SupplementalSourceTarget]:
    encoded_query = quote_plus(" ".join(query.split()))
    targets = [
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
        SupplementalSourceTarget(
            key="csdn_search",
            label="CSDN 搜索",
            url=f"https://so.csdn.net/so/search?spm=1000.2115.3001.4498&q={encoded_query}&t=&u=",
            publisher="so.csdn.net",
            snippet="CSDN 博客搜索结果页，可补充社区文章线索，但内容质量不稳定，需降权看待。",
        ),
    ]
    if is_it_tutorial_query(query):
        targets.append(
            SupplementalSourceTarget(
                key="runoob_search",
                label="菜鸟教程搜索",
                url=f"https://www.runoob.com/?s={encoded_query}",
                publisher="www.runoob.com",
                snippet="菜鸟教程搜索结果页，适合 IT 教程、语法与入门示例类查询。",
            )
        )
    return targets


def is_it_tutorial_query(query: str) -> bool:
    normalized = f" {query.strip().lower()} "
    return any(keyword in normalized for keyword in IT_TUTORIAL_KEYWORDS)


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
        http_status_code: int | None,
        final_url: str,
        probe_method: str,
        reason: str,
        content_chars: int,
    ) -> SourceProbeResult:
        return SourceProbeResult(
            key=target.key,
            url=target.url,
            available=available,
            status_code=status_code,
            http_status_code=http_status_code,
            final_url=final_url,
            probe_method=probe_method,
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
            http_status_code=None,
            final_url=target.url,
            probe_method="http",
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
            http_status_code=response.status_code,
            final_url=final_url,
            probe_method="http",
            reason=f"http_{response.status_code}",
            content_chars=len(compact_text),
        )
    if any(marker in text for marker in target.blocked_markers):
        return build_result(
            available=False,
            status_code=response.status_code,
            http_status_code=response.status_code,
            final_url=final_url,
            probe_method="http",
            reason="blocked_marker_detected",
            content_chars=len(compact_text),
        )
    if len(compact_text) < target.min_text_chars:
        return build_result(
            available=False,
            status_code=response.status_code,
            http_status_code=response.status_code,
            final_url=final_url,
            probe_method="http",
            reason="content_too_short",
            content_chars=len(compact_text),
        )
    return build_result(
        available=True,
        status_code=response.status_code,
        http_status_code=response.status_code,
        final_url=final_url,
        probe_method="http",
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
            status_code=None,
            http_status_code=status_code,
            final_url=final_url,
            probe_method="browser_fallback",
            reason=f"http_{status_code}_browser_failed:{exc.__class__.__name__}",
            content_chars=0,
        )
    compact_text = " ".join(browser_text.split())
    if any(marker in browser_text for marker in target.blocked_markers):
        return SourceProbeResult(
            key=target.key,
            url=target.url,
            available=False,
            status_code=None,
            http_status_code=status_code,
            final_url=final_url,
            probe_method="browser_fallback",
            reason="browser_blocked_marker_detected",
            content_chars=len(compact_text),
        )
    if len(compact_text) < target.min_text_chars:
        return SourceProbeResult(
            key=target.key,
            url=target.url,
            available=False,
            status_code=None,
            http_status_code=status_code,
            final_url=final_url,
            probe_method="browser_fallback",
            reason=f"http_{status_code}_browser_content_too_short",
            content_chars=len(compact_text),
        )
    return SourceProbeResult(
        key=target.key,
        url=target.url,
        available=True,
        status_code=None,
        http_status_code=status_code,
        final_url=target.url,
        probe_method="browser_fallback",
        reason="browser_fallback_ok",
        content_chars=len(compact_text),
    )
