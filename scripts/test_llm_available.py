from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from os import getenv
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


@dataclass(frozen=True)
class LlmProbeConfig:
    api_key: str
    base_url: str
    model: str
    timeout: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a minimal chat request to verify the configured LLM can reply.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the env file to load before reading OPENAI_* variables.",
    )
    parser.add_argument(
        "--prompt",
        default="请用一句中文回复：LLM 连接正常。",
        help="User prompt used for the smoke test.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds.",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> LlmProbeConfig:
    env_path = Path(args.env_file)
    if env_path.exists():
        load_dotenv(env_path, override=True)

    missing = [
        name
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
        if not getenv(name)
    ]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Missing required environment variable(s): {names}")

    return LlmProbeConfig(
        api_key=getenv("OPENAI_API_KEY", ""),
        base_url=getenv("OPENAI_BASE_URL", "").rstrip("/"),
        model=getenv("OPENAI_MODEL", ""),
        timeout=args.timeout,
    )


def request_chat_completion(config: LlmProbeConfig, prompt: str) -> tuple[str, dict[str, Any] | None, float]:
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": "你是 KnowledgeForge 的 LLM 连通性测试助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 80,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    with httpx.Client(timeout=config.timeout) as client:
        response = client.post(
            f"{config.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    elapsed_seconds = time.perf_counter() - started

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Provider response did not contain any choices.")
    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Provider response choice did not contain message.content.")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return content.strip(), usage, elapsed_seconds


def mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


def main() -> int:
    args = parse_args()
    try:
        config = build_config(args)
        print("LLM smoke test")
        print(f"- base_url: {config.base_url}")
        print(f"- model: {config.model}")
        print(f"- api_key: {mask_secret(config.api_key)}")
        reply, usage, elapsed_seconds = request_chat_completion(config, args.prompt)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        print(f"[FAIL] HTTP {exc.response.status_code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[FAIL] {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"[OK] received reply in {elapsed_seconds:.2f}s")
    if usage:
        print(f"- usage: {usage}")
    print(f"- reply: {reply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
