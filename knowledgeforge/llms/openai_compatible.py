from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from knowledgeforge.config import OpenAIConfig
from knowledgeforge.runtime.token_usage import TokenUsageStatus, build_token_usage_record


class OpenAICompatibleChatClient:
    def __init__(
        self,
        config: OpenAIConfig,
        timeout: float = 5.0,
        *,
        operation: str = "chat.completions",
        token_usage_callback: Any | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._operation = operation
        self._token_usage_callback = token_usage_callback

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
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
        usage_payload: dict[str, Any] | None = None
        with httpx.Client(timeout=self._timeout) as client:
            try:
                response = client.post(
                    f"{self._config.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                response_payload = response.json()
                usage_payload = response_payload.get("usage")
                content = response_payload["choices"][0]["message"]["content"]
            except Exception as exc:
                self._emit_token_usage(
                    request_id=request_id,
                    usage=None,
                    status="failed",
                    error=str(exc),
                )
                raise
        self._emit_token_usage(request_id=request_id, usage=usage_payload, status="completed")
        return json.loads(content)

    def _emit_token_usage(
        self,
        *,
        request_id: str,
        usage: dict[str, Any] | None,
        status: TokenUsageStatus,
        error: str = "",
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
        )
        if record and self._token_usage_callback:
            self._token_usage_callback(record)


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        config: OpenAIConfig,
        timeout: float = 5.0,
        *,
        operation: str = "embeddings",
        token_usage_callback: Any | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._operation = operation
        self._token_usage_callback = token_usage_callback

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
                self._emit_token_usage(
                    request_id=request_id,
                    usage=None,
                    status="failed",
                    error=str(exc),
                )
                raise
        self._emit_token_usage(request_id=request_id, usage=usage_payload, status="completed")
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
        )
        if record and self._token_usage_callback:
            self._token_usage_callback(record)
