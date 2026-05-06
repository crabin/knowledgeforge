from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from os import getenv
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from knowledgeforge.agent.QueryEngine.source_priority import (
    SOURCE_PRIORITY_SYSTEM_PROMPT,
    build_source_priority_user_prompt,
    normalize_source_priority_queue,
    parse_source_priority_json_response,
)


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    base_url: str
    model: str
    timeout: float


def main() -> int:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)

    try:
        query_items = load_query_items(args)
        user_prompt = build_source_priority_user_prompt(query_items=query_items, domain=args.domain)
        if args.dry_run:
            emit_json(
                {
                    "dry_run": True,
                    "system_prompt": SOURCE_PRIORITY_SYSTEM_PROMPT,
                    "user_prompt": user_prompt,
                },
                args.output,
            )
            return 0

        if args.mock_response:
            llm_payload = parse_source_priority_json_response(Path(args.mock_response).read_text(encoding="utf-8"))
            elapsed_seconds = 0.0
        else:
            config = build_llm_config(args)
            started = time.perf_counter()
            llm_payload = request_query_queue(config, user_prompt)
            elapsed_seconds = time.perf_counter() - started

        queue = normalize_source_priority_queue(llm_payload, domain=args.domain)
        result = {
            "domain": args.domain,
            "source_policy": "query_engine_internal_authority_priority",
            "elapsed_seconds": round(elapsed_seconds, 2),
            "total": len(queue),
            "tasks": queue,
        }
        if args.include_raw:
            result["raw_response"] = llm_payload
        emit_json(result, args.output)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        print(f"[FAIL] HTTP {exc.response.status_code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[FAIL] {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a KnowledgeForge JSON query queue using QueryEngine's source-priority policy.",
    )
    parser.add_argument("--domain", default="", help="Optional domain name prepended to generated search terms.")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="One query item. Can be passed multiple times.",
    )
    parser.add_argument(
        "--queries-json",
        default="",
        help="JSON file containing a list of strings or objects with title/query/claim fields.",
    )
    parser.add_argument("--env-file", default=".env", help="Env file to load for OPENAI_* settings.")
    parser.add_argument("--timeout", type=float, default=60.0, help="LLM request timeout seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling the LLM.")
    parser.add_argument("--mock-response", default="", help="Use a saved LLM JSON response instead of calling the LLM.")
    parser.add_argument("--include-raw", action="store_true", help="Include raw LLM JSON in output.")
    parser.add_argument("--output", default="", help="Optional path to write the generated JSON queue.")
    return parser.parse_args()


def load_query_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    loaded: list[Any] = []
    if args.queries_json:
        payload = json.loads(Path(args.queries_json).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("--queries-json must contain a JSON list.")
        loaded.extend(payload)
    loaded.extend(args.query)
    if not loaded:
        raise ValueError("Pass at least one --query or provide --queries-json.")

    items: list[dict[str, Any]] = []
    for index, item in enumerate(loaded, start=1):
        if isinstance(item, str):
            text = item.strip()
            if text:
                items.append({"id": f"item-{index}", "title": text, "claim_or_gap": text})
            continue
        if not isinstance(item, dict):
            raise ValueError("Query items must be strings or JSON objects.")
        normalized = dict(item)
        normalized.setdefault("id", f"item-{index}")
        normalized.setdefault(
            "title",
            normalized.get("query") or normalized.get("query_text") or normalized.get("claim_or_gap") or "",
        )
        normalized.setdefault("claim_or_gap", normalized.get("title", ""))
        if str(normalized.get("title", "")).strip():
            items.append(normalized)
    if not items:
        raise ValueError("No non-empty query items were provided.")
    return items


def build_llm_config(args: argparse.Namespace) -> LlmConfig:
    missing = [
        name
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
        if not getenv(name)
    ]
    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")
    return LlmConfig(
        api_key=getenv("OPENAI_API_KEY", ""),
        base_url=getenv("OPENAI_BASE_URL", "").rstrip("/"),
        model=getenv("OPENAI_MODEL", ""),
        timeout=args.timeout,
    )


def request_query_queue(config: LlmConfig, user_prompt: str) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SOURCE_PRIORITY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=config.timeout) as client:
        response = client.post(
            f"{config.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Provider response did not contain choices.")
    content = str(choices[0].get("message", {}).get("content", "")).strip()
    if not content:
        raise RuntimeError("Provider response did not contain message.content.")
    return parse_source_priority_json_response(content)


def emit_json(payload: dict[str, Any], output: str) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{text}\n", encoding="utf-8")
        print(f"saved: {output_path}")
        return
    print(text)


if __name__ == "__main__":
    raise SystemExit(main())
