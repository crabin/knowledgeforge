from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Literal

from knowledgeforge.utils.time import now_iso


TokenUsageStatus = Literal["completed", "failed"]
TokenUsageKind = Literal["chat", "embedding"]


@dataclass(slots=True)
class TokenUsageRecord:
    task_id: str
    request_id: str
    kind: TokenUsageKind
    operation: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    status: TokenUsageStatus
    timestamp: str
    source: str = "provider"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_token_task_id: ContextVar[str] = ContextVar("knowledgeforge_token_task_id", default="")


@contextmanager
def token_tracking_context(task_id: str) -> Iterator[None]:
    token = _token_task_id.set(task_id)
    try:
        yield
    finally:
        _token_task_id.reset(token)


def current_token_task_id() -> str:
    return _token_task_id.get()


def build_token_usage_record(
    *,
    request_id: str,
    kind: TokenUsageKind,
    operation: str,
    model: str,
    usage: dict[str, Any] | None,
    status: TokenUsageStatus,
    source: str = "provider",
    error: str = "",
) -> TokenUsageRecord | None:
    task_id = current_token_task_id()
    if not task_id:
        return None
    prompt_tokens, completion_tokens, total_tokens = normalize_usage(usage or {})
    return TokenUsageRecord(
        task_id=task_id,
        request_id=request_id,
        kind=kind,
        operation=operation,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status=status,
        timestamp=now_iso(),
        source=source,
        error=error,
    )


def normalize_usage(usage: dict[str, Any]) -> tuple[int, int, int]:
    prompt_tokens = _to_int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("total_prompt_tokens")
    )
    completion_tokens = _to_int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("total_completion_tokens")
    )
    total_tokens = _to_int(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return prompt_tokens, completion_tokens, total_tokens


def summarize_token_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    token_events = [entry for entry in records if entry.get("event") == "token_usage_recorded"]
    totals = {
        "request_count": len(token_events),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "failed_count": 0,
        "by_kind": {},
        "recent": [],
    }
    by_kind: dict[str, dict[str, int]] = {}
    recent: list[dict[str, Any]] = []
    for entry in token_events:
        details = entry.get("details") or {}
        kind = str(details.get("kind") or "unknown")
        bucket = by_kind.setdefault(
            kind,
            {"request_count": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        prompt_tokens = _to_int(details.get("prompt_tokens"))
        completion_tokens = _to_int(details.get("completion_tokens"))
        total_tokens = _to_int(details.get("total_tokens"))
        totals["prompt_tokens"] += prompt_tokens
        totals["completion_tokens"] += completion_tokens
        totals["total_tokens"] += total_tokens
        if details.get("status") == "failed":
            totals["failed_count"] += 1
        bucket["request_count"] += 1
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["total_tokens"] += total_tokens
        recent.append(details)
    totals["by_kind"] = by_kind
    totals["recent"] = recent[-12:]
    return totals


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
