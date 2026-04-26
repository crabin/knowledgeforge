from __future__ import annotations

import json
import threading
import time

import httpx

from knowledgeforge.config import AppConfig
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient


REAL_COMPLETE_JSON = OpenAICompatibleChatClient.complete_json


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }


def test_chat_client_retries_when_provider_returns_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", REAL_COMPLETE_JSON)
    monkeypatch.setattr(OpenAICompatibleChatClient, "_request_lock", threading.Lock())

    contents = ['{"questions": [{"question": "broken"}]', '{"result": "ok"}']
    post_calls: list[str] = []

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _FakeResponse:
            post_calls.append(url)
            return _FakeResponse(contents.pop(0))

    monkeypatch.setattr(httpx, "Client", FakeClient)

    client = OpenAICompatibleChatClient(AppConfig().openai, max_retries=2)

    result = client.complete_json(system_prompt="planner", user_prompt='{"domain":"ML"}')

    assert result == {"result": "ok"}
    assert len(post_calls) == 2


def test_chat_client_serializes_concurrent_llm_requests(monkeypatch) -> None:
    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", REAL_COMPLETE_JSON)
    monkeypatch.setattr(OpenAICompatibleChatClient, "_request_lock", threading.Lock())

    metrics = {"active": 0, "max_active": 0, "call_count": 0}
    metrics_lock = threading.Lock()

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _FakeResponse:
            with metrics_lock:
                metrics["active"] += 1
                metrics["call_count"] += 1
                metrics["max_active"] = max(metrics["max_active"], metrics["active"])
                current = metrics["call_count"]
            time.sleep(0.05)
            with metrics_lock:
                metrics["active"] -= 1
            return _FakeResponse(json_module.dumps({"call": current}, ensure_ascii=False))

    json_module = json
    monkeypatch.setattr(httpx, "Client", FakeClient)

    client = OpenAICompatibleChatClient(AppConfig().openai, max_retries=0)
    results: list[dict[str, object]] = []

    def worker() -> None:
        results.append(client.complete_json(system_prompt="planner", user_prompt='{"domain":"ML"}'))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 2
    assert metrics["call_count"] == 2
    assert metrics["max_active"] == 1
