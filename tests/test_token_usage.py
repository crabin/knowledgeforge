from __future__ import annotations

from pathlib import Path

from knowledgeforge.config import AppConfig
from knowledgeforge.runtime.token_usage import (
    TokenUsageRecord,
    build_token_usage_record,
    estimate_text_tokens,
    summarize_token_usage,
    token_tracking_context,
)
from knowledgeforge.services.task_service import TaskService


def test_token_usage_summary_counts_prompt_completion_and_total_tokens() -> None:
    logs = [
        {
            "event": "token_usage_recorded",
            "details": {
                "kind": "chat",
                "prompt_tokens": 12,
                "completion_tokens": 8,
                "total_tokens": 20,
                "status": "completed",
            },
        },
        {
            "event": "token_usage_recorded",
            "details": {
                "kind": "embedding",
                "prompt_tokens": 5,
                "completion_tokens": 0,
                "total_tokens": 5,
                "status": "completed",
            },
        },
        {"event": "workflow_step", "details": {"step_id": "collecting"}},
    ]

    summary = summarize_token_usage(logs)

    assert summary["request_count"] == 2
    assert summary["prompt_tokens"] == 17
    assert summary["completion_tokens"] == 8
    assert summary["total_tokens"] == 25
    assert summary["by_kind"]["chat"]["total_tokens"] == 20
    assert summary["by_kind"]["embedding"]["request_count"] == 1


def test_token_usage_record_estimates_tokens_when_provider_usage_missing() -> None:
    with token_tracking_context("token-task"):
        record = build_token_usage_record(
            request_id="req-estimated",
            kind="chat",
            operation="planning.chat_json",
            model="gpt-5.2",
            usage=None,
            status="completed",
            source="unavailable",
            estimated_prompt_text="发送 token 测试 prompt",
            estimated_completion_text="接收 token 测试 completion",
        )

    assert record is not None
    assert record.source == "estimated"
    assert record.prompt_tokens == estimate_text_tokens("发送 token 测试 prompt")
    assert record.completion_tokens == estimate_text_tokens("接收 token 测试 completion")
    assert record.total_tokens == record.prompt_tokens + record.completion_tokens


def test_task_logs_include_realtime_token_usage_summary(tmp_path: Path) -> None:
    service = TaskService(
        AppConfig(
            save_root=tmp_path / "save",
            task_state_root=tmp_path / "runtime" / "tasks",
            intake_session_root=tmp_path / "runtime" / "intake",
            audit_root=tmp_path / "runtime" / "audit",
            frozen_root=tmp_path / "runtime" / "frozen",
        )
    )
    service._state_store.save(  # noqa: SLF001
        "token-task",
        {
            "task_id": "token-task",
            "task_status": "running",
            "request_context": {"domain": "知识工程", "subdomains": []},
        },
    )

    with token_tracking_context("token-task"):
        service._record_token_usage(  # noqa: SLF001
            TokenUsageRecord(
                task_id="token-task",
                request_id="req-1",
                kind="chat",
                operation="planning.chat_json",
                model="gpt-5.2",
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
                status="completed",
                timestamp="2026-04-26T00:00:00+09:00",
            )
        )

    payload = service.get_task_logs("token-task")

    assert payload is not None
    assert payload["token_usage"]["request_count"] == 1
    assert payload["token_usage"]["total_tokens"] == 18
    assert payload["logs"][0]["event"] == "token_usage_recorded"
