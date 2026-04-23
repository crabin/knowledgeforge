from __future__ import annotations

import json
from typing import Any

import httpx

from knowledgeforge.config import OpenAIConfig


class OpenAICompatibleChatClient:
    def __init__(self, config: OpenAIConfig, timeout: float = 5.0) -> None:
        self._config = config
        self._timeout = timeout

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
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)


class OpenAICompatibleEmbeddingClient:
    def __init__(self, config: OpenAIConfig, timeout: float = 5.0) -> None:
        self._config = config
        self._timeout = timeout

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
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
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._config.embedding_base_url.rstrip('/')}/embeddings",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()["data"]
        return [item["embedding"] for item in data]

    def _should_send_dimensions(self) -> bool:
        base_url = self._config.embedding_base_url
        model = self._config.embedding_model
        return "11434" not in base_url and ":" not in model and self._config.embedding_dimensions > 0
