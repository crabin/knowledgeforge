from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from knowledgeforge.agent.QueryEngine.agent import QueryEngine
from knowledgeforge.agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.server.config import AppConfig
from knowledgeforge.server.intake.context_builder import ContextBuilder
from knowledgeforge.server.llms.openai_compatible import OpenAICompatibleChatClient, OpenAICompatibleEmbeddingClient
from knowledgeforge.server.models import RequestContext


def main() -> int:
    args = _parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    config = AppConfig.from_env() if args.use_env_config else AppConfig()
    base_url = args.base_url.rstrip("/")
    task_payload = _load_task(base_url, args.task_id)
    task_id = str(task_payload.get("task_id", "")).strip()
    context = _build_context(task_payload, task_id)
    task = _select_or_build_task(task_payload, args)

    print_json(
        "input",
        {
            "task_id": task_id,
            "domain": context.domain,
            "target_node_id": task.get("target_node_id"),
            "query_text": task.get("query_text"),
            "claim_or_gap": task.get("claim_or_gap"),
            "expected_evidence": task.get("expected_evidence"),
            "preferred_source_types": task.get("preferred_source_types"),
        },
    )
    if args.dry_run:
        return 0

    trace_lines: list[str] = []
    started = time.perf_counter()
    engine = QueryEngine(
        chat_client=OpenAICompatibleChatClient(
            config.openai,
            timeout=args.llm_timeout,
            operation="simulate.query.chat_json",
            max_retries=0,
        ),
        embedding_client=None if args.no_embeddings else OpenAICompatibleEmbeddingClient(config.openai, timeout=2.0),
        crawler=DomainKnowledgeCrawler(timeout=args.search_timeout, trace=lambda message: _trace(trace_lines, message)),
        max_concurrent_network_tasks=1,
        save_root=config.save_root,
    )
    result = engine.run_evidence_task(context=context, round_number=args.round_number, task=task)
    elapsed = time.perf_counter() - started
    selected = next((source for source in result.sources if source.url.startswith(("http://", "https://"))), None)

    print_json(
        "result",
        {
            "elapsed_seconds": round(elapsed, 2),
            "summary": result.summary,
            "selected": selected.to_dict() if selected else None,
            "sources": [source.to_dict() for source in result.sources],
            "execution_log": result.execution_log,
            "raw_material": result.raw_material,
            "trace": trace_lines[-args.trace_limit :],
        },
    )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "input": {"task_id": task_id, "task": task},
                    "result": result.to_dict(),
                    "trace": trace_lines,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"saved: {output_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate one KnowledgeForge QueryEngine evidence task without running the whole queue."
    )
    parser.add_argument("--base-url", default="http://localhost:5001", help="KnowledgeForge API base URL.")
    parser.add_argument("--task-id", default="", help="Task id. Defaults to newest task from /tasks.")
    parser.add_argument("--queue-task-id", default="", help="Existing task_queue_snapshot task id to run.")
    parser.add_argument("--node-id", default="", help="Target node id for an ad-hoc query task.")
    parser.add_argument("--query", default="", help="Override or provide query_text.")
    parser.add_argument("--claim", default="", help="Override or provide claim_or_gap.")
    parser.add_argument(
        "--expected",
        action="append",
        default=[],
        help="Expected evidence item. Can be passed multiple times.",
    )
    parser.add_argument(
        "--preferred-source",
        action="append",
        default=[],
        help="Preferred source type. Can be passed multiple times.",
    )
    parser.add_argument("--round-number", type=int, default=1, help="Round number passed to QueryEngine.")
    parser.add_argument("--search-timeout", type=float, default=6.0, help="Crawler timeout seconds.")
    parser.add_argument("--llm-timeout", type=float, default=8.0, help="LLM timeout seconds.")
    parser.add_argument("--no-embeddings", action="store_true", help="Skip embedding calls.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected task and exit.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    parser.add_argument("--trace-limit", type=int, default=80, help="How many crawler trace lines to print.")
    parser.add_argument("--env-file", default=".env", help="Env file to load before creating clients.")
    parser.add_argument("--use-env-config", action="store_true", help="Use AppConfig.from_env instead of defaults.")
    return parser.parse_args()


def _load_task(base_url: str, task_id: str) -> dict[str, Any]:
    if task_id:
        return _get_json(f"{base_url}/tasks/{_url_quote(task_id)}")
    payload = _get_json(f"{base_url}/tasks")
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    if not tasks:
        raise RuntimeError("No tasks returned from /tasks. Pass --task-id after creating a task.")
    newest_task_id = str(tasks[0].get("task_id", "")).strip()
    if not newest_task_id:
        raise RuntimeError("Newest task summary does not include task_id.")
    return _get_json(f"{base_url}/tasks/{_url_quote(newest_task_id)}")


def _build_context(task_payload: dict[str, Any], task_id: str) -> RequestContext:
    raw_context = dict(task_payload.get("request_context") or {})
    raw_context.setdefault("domain", task_payload.get("domain") or task_payload.get("normalized_domain") or "Unknown")
    raw_context.setdefault("subdomains", task_payload.get("subdomains") or [raw_context["domain"]])
    raw_context.setdefault("time_window", "")
    raw_context.setdefault("focus_points", [])
    raw_context.setdefault("constraints", [])
    raw_context.setdefault("initial_strategy", [])
    raw_context["task_id"] = task_id
    return ContextBuilder().build(raw_context)


def _select_or_build_task(task_payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    queue = task_payload.get("task_queue_snapshot") or {}
    tasks = queue.get("tasks") if isinstance(queue.get("tasks"), list) else []
    selected = None
    if args.queue_task_id:
        selected = next((task for task in tasks if str(task.get("task_id", "")) == args.queue_task_id), None)
        if selected is None:
            raise RuntimeError(f"Queue task not found: {args.queue_task_id}")
    elif tasks and not args.query:
        selected = next((task for task in tasks if str(task.get("status", "pending")) in {"pending", "running", "insufficient"}), tasks[0])
    task = dict(selected or {})
    task["task_id"] = str(task.get("task_id") or args.queue_task_id or "simulate-query-task-1")
    if args.node_id:
        task["target_node_id"] = args.node_id
    if args.query:
        task["query_text"] = args.query
    if args.claim:
        task["claim_or_gap"] = args.claim
    if args.expected:
        task["expected_evidence"] = args.expected
    if args.preferred_source:
        task["preferred_source_types"] = args.preferred_source
    task.setdefault("query_text", task.get("claim_or_gap") or "official documentation")
    task.setdefault("claim_or_gap", task.get("query_text") or "补充证据")
    task.setdefault("expected_evidence", ["官方或高公信力链接", "与知识点最贴近的说明入口"])
    task.setdefault("preferred_source_types", ["official documentation", "wikipedia"])
    task.setdefault("acceptance_criteria", ["命中可访问链接", "能支撑目标知识点"])
    task.setdefault("status", "pending")
    return task


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: HTTP {exc.code} {detail}") from exc


def _url_quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _trace(lines: list[str], message: str) -> None:
    lines.append(message)
    print(message, file=sys.stderr)


def print_json(label: str, payload: dict[str, Any]) -> None:
    print(f"\n## {label}")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
