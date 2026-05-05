from __future__ import annotations

import json
import time
import uuid
from json import JSONDecodeError
from threading import Lock
from typing import Any

import httpx

from knowledgeforge.server.config import OpenAIConfig
from knowledgeforge.server.runtime.token_usage import TokenUsageStatus, build_token_usage_record


class OpenAICompatibleChatClient:
    _request_lock = Lock()

    def __init__(
        self,
        config: OpenAIConfig,
        timeout: float = 5.0,
        *,
        operation: str = "chat.completions",
        token_usage_callback: Any | None = None,
        llm_event_callback: Any | None = None,
        max_retries: int = 2,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._operation = operation
        self._token_usage_callback = token_usage_callback
        self._llm_event_callback = llm_event_callback
        self._max_retries = max(0, max_retries)

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        prompt_text = json.dumps(payload["messages"], ensure_ascii=False)
        attempts = self._max_retries + 1
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            request_id = uuid.uuid4().hex
            usage_payload: dict[str, Any] | None = None
            content = ""
            self._emit_llm_event(
                request_id=request_id,
                kind="chat",
                status="started",
                attempt=attempt,
                max_attempts=attempts,
            )
            try:
                started_at = time.perf_counter()
                with type(self)._request_lock:
                    with httpx.Client(timeout=self._timeout) as client:
                        response = client.post(
                            f"{self._config.base_url.rstrip('/')}/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        response.raise_for_status()
                        response_payload = response.json()
                        usage_payload = response_payload.get("usage")
                        content = response_payload["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                elapsed_ms = round((time.perf_counter() - started_at) * 1000)
                self._emit_llm_event(
                    request_id=request_id,
                    kind="chat",
                    status="completed",
                    attempt=attempt,
                    max_attempts=attempts,
                    elapsed_ms=elapsed_ms,
                )
                self._emit_token_usage(
                    request_id=request_id,
                    usage=usage_payload,
                    status="completed",
                    estimated_prompt_text=prompt_text,
                    estimated_completion_text=content,
                )
                return parsed
            except Exception as exc:
                last_exc = exc
                error_message = str(exc)
                if attempt < attempts:
                    error_message = f"{error_message} (attempt {attempt}/{attempts})"
                self._emit_llm_event(
                    request_id=request_id,
                    kind="chat",
                    status="failed",
                    attempt=attempt,
                    max_attempts=attempts,
                    error=error_message,
                )
                self._emit_token_usage(
                    request_id=request_id,
                    usage=usage_payload,
                    status="failed",
                    error=error_message,
                    estimated_prompt_text=prompt_text,
                    estimated_completion_text=content,
                )
                if not self._should_retry(exc) or attempt >= attempts:
                    raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("LLM JSON completion failed without an explicit exception.")

    @staticmethod
    def _should_retry(exc: Exception) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return False
        return isinstance(exc, (JSONDecodeError, httpx.HTTPError, KeyError, TypeError, ValueError))

    def _emit_token_usage(
        self,
        *,
        request_id: str,
        usage: dict[str, Any] | None,
        status: TokenUsageStatus,
        error: str = "",
        estimated_prompt_text: str = "",
        estimated_completion_text: str = "",
    ) -> None:
        record = build_token_usage_record(
            request_id=request_id,
            kind="chat",
            operation=self._operation,
            model=self._config.model,
            usage=usage,
            status=status,
            source="provider" if usage else "unavailable",
            error=error,
            estimated_prompt_text=estimated_prompt_text,
            estimated_completion_text=estimated_completion_text,
        )
        if record and self._token_usage_callback:
            self._token_usage_callback(record)

    def _emit_llm_event(
        self,
        *,
        request_id: str,
        kind: str,
        status: str,
        attempt: int,
        max_attempts: int,
        error: str = "",
        elapsed_ms: int | None = None,
    ) -> None:
        if not self._llm_event_callback:
            return
        self._llm_event_callback(
            {
                "request_id": request_id,
                "kind": kind,
                "operation": self._operation,
                "model": self._config.model,
                "status": status,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "base_url": self._config.base_url,
                "timeout": self._timeout,
                "error": error,
                "elapsed_ms": elapsed_ms,
            }
        )


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        config: OpenAIConfig,
        timeout: float = 5.0,
        *,
        operation: str = "embeddings",
        token_usage_callback: Any | None = None,
        llm_event_callback: Any | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._operation = operation
        self._token_usage_callback = token_usage_callback
        self._llm_event_callback = llm_event_callback

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        request_id = uuid.uuid4().hex
        payload: dict[str, Any] = {
            "model": self._config.embedding_model,
            "input": texts,
        }
        if self._should_send_dimensions():
            payload["dimensions"] = self._config.embedding_dimensions
        headers = {
            "Authorization": f"Bearer {self._config.embedding_api_key}",
            "Content-Type": "application/json",
        }
        usage_payload: dict[str, Any] | None = None
        prompt_text = "\n".join(texts)
        self._emit_llm_event(request_id=request_id, kind="embedding", status="started", error="")
        with httpx.Client(timeout=self._timeout) as client:
            try:
                response = client.post(
                    f"{self._config.embedding_base_url.rstrip('/')}/embeddings",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                response_payload = response.json()
                usage_payload = response_payload.get("usage")
                data = response_payload["data"]
            except Exception as exc:
                self._emit_llm_event(request_id=request_id, kind="embedding", status="failed", error=str(exc))
                self._emit_token_usage(
                    request_id=request_id,
                    usage=None,
                    status="failed",
                    error=str(exc),
                    estimated_prompt_text=prompt_text,
                )
                raise
        self._emit_llm_event(request_id=request_id, kind="embedding", status="completed", error="")
        self._emit_token_usage(
            request_id=request_id,
            usage=usage_payload,
            status="completed",
            estimated_prompt_text=prompt_text,
        )
        return [item["embedding"] for item in data]

    def _should_send_dimensions(self) -> bool:
        base_url = self._config.embedding_base_url
        model = self._config.embedding_model
        return "11434" not in base_url and ":" not in model and self._config.embedding_dimensions > 0

    def _emit_token_usage(
        self,
        *,
        request_id: str,
        usage: dict[str, Any] | None,
        status: TokenUsageStatus,
        error: str = "",
        estimated_prompt_text: str = "",
    ) -> None:
        record = build_token_usage_record(
            request_id=request_id,
            kind="embedding",
            operation=self._operation,
            model=self._config.embedding_model,
            usage=usage,
            status=status,
            source="provider" if usage else "unavailable",
            error=error,
            estimated_prompt_text=estimated_prompt_text,
        )
        if record and self._token_usage_callback:
            self._token_usage_callback(record)

    def _emit_llm_event(
        self,
        *,
        request_id: str,
        kind: str,
        status: str,
        error: str,
    ) -> None:
        if not self._llm_event_callback:
            return
        self._llm_event_callback(
            {
                "request_id": request_id,
                "kind": kind,
                "operation": self._operation,
                "model": self._config.embedding_model,
                "status": status,
                "base_url": self._config.embedding_base_url,
                "timeout": self._timeout,
                "error": error,
            }
        )
