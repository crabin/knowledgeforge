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
    api_requests: list[dict[str, Any]] = []
    task_payload = _load_task(base_url, args.task_id)
    task_id = str(task_payload.get("task_id", "")).strip()
    context = _build_context(task_payload, task_id)
    if args.list_queue:
        queue_payload = _build_queue_listing(task_payload, context, args)
        _emit(args, [("queue_tasks", queue_payload)])
        return 0
    task = _select_or_build_task(task_payload, args)
    api_requests = _describe_api_requests(base_url, args, task_id)
    query_request = _build_query_request(context, task, args)

    sections: list[tuple[str, Any]] = [
        (
            "api_request",
            {
                "requests": api_requests,
                "note": "脚本只通过 API 读取 task/queue；单条查询在本进程内调用 QueryEngine.run_evidence_task，不会修改后端任务状态。",
            },
        ),
        (
            "query_request",
            {
                "task_id": task_id,
                "domain": context.domain,
                **query_request,
            },
        ),
    ]
    if args.dry_run:
        sections.append(("query_result", {"dry_run": True, "message": "未执行搜索；去掉 --dry-run 可查看真实查询结果。"}))
        _emit(args, sections)
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
        crawler=DomainKnowledgeCrawler(timeout=args.search_timeout, trace=lambda message: _trace(trace_lines, message, echo=args.show_trace)),
        max_concurrent_network_tasks=1,
        save_root=config.save_root,
    )
    result = engine.run_evidence_task(context=context, round_number=args.round_number, task=task)
    elapsed = time.perf_counter() - started
    selected = next((source for source in result.sources if source.url.startswith(("http://", "https://"))), None)
    query_attempts = _extract_query_attempts(result.execution_log)

    sections.append(
        (
            "query_result",
            {
                "elapsed_seconds": round(elapsed, 2),
                "summary": result.summary,
                "selected": selected.to_dict() if selected else None,
                "diagnostics": _build_diagnostics(selected.to_dict() if selected else None, query_attempts, trace_lines),
                "query_attempts": query_attempts,
                "sources": [source.to_dict() for source in result.sources],
                "execution_log": result.execution_log,
                "raw_material": result.raw_material,
                "trace": trace_lines[-args.trace_limit :],
            },
        )
    )
    _emit(args, sections)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "api_request": api_requests,
                    "query_request": query_request,
                    "result": result.to_dict(),
                    "diagnostics": _build_diagnostics(selected.to_dict() if selected else None, query_attempts, trace_lines),
                    "query_attempts": query_attempts,
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
    parser.add_argument("--list-queue", action="store_true", help="List queue tasks and exit.")
    parser.add_argument("--queue-status", action="append", default=[], help="Filter --list-queue by task status. Can be passed multiple times.")
    parser.add_argument("--queue-limit", type=int, default=30, help="Maximum queue tasks to print in --list-queue. Use 0 for all.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    parser.add_argument("--json-only", action="store_true", help="Print one JSON object instead of markdown-style sections.")
    parser.add_argument("--show-trace", action="store_true", help="Echo crawler trace to stderr while running.")
    parser.add_argument("--trace-limit", type=int, default=80, help="How many crawler trace lines to print.")
    parser.add_argument("--env-file", default=".env", help="Env file to load before creating clients.")
    parser.add_argument("--use-env-config", action="store_true", help="Use AppConfig.from_env instead of defaults.")
    return parser.parse_args()


def _build_queue_listing(task_payload: dict[str, Any], context: RequestContext, args: argparse.Namespace) -> dict[str, Any]:
    queue = task_payload.get("task_queue_snapshot") or {}
    tasks = queue.get("tasks") if isinstance(queue.get("tasks"), list) else []
    statuses = {str(status).strip() for status in args.queue_status if str(status).strip()}
    filtered = [task for task in tasks if isinstance(task, dict)]
    if statuses:
        filtered = [task for task in filtered if str(task.get("status", "")) in statuses]
    visible = filtered if args.queue_limit <= 0 else filtered[: args.queue_limit]
    return {
        "task_id": task_payload.get("task_id", ""),
        "domain": context.domain,
        "queue_status": queue.get("final_status") or queue.get("status") or "",
        "total": len(tasks),
        "filtered_total": len(filtered),
        "shown": len(visible),
        "tasks": [_queue_task_preview(context, task) for task in visible],
    }


def _queue_task_preview(context: RequestContext, task: dict[str, Any]) -> dict[str, Any]:
    rewritten = QueryEngine._rewrite_evidence_task_queries(context, task)
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "target_node_id": task.get("target_node_id"),
        "query_text": task.get("query_text"),
        "primary_query": rewritten["primary_query"],
        "preferred_source_types": rewritten["preferred_source_types"],
        "authority_queries": rewritten["authority_queries"],
        "claim_or_gap": task.get("claim_or_gap"),
        "selected_link": task.get("selected_link"),
    }


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


def _describe_api_requests(base_url: str, args: argparse.Namespace, resolved_task_id: str) -> list[dict[str, Any]]:
    if args.task_id:
        return [
            {
                "method": "GET",
                "url": f"{base_url}/tasks/{_url_quote(args.task_id)}",
                "purpose": "读取指定任务状态和 task_queue_snapshot。",
            }
        ]
    return [
        {"method": "GET", "url": f"{base_url}/tasks", "purpose": "读取任务列表，选择最新任务。"},
        {
            "method": "GET",
            "url": f"{base_url}/tasks/{_url_quote(resolved_task_id)}",
            "purpose": "读取最新任务状态和 task_queue_snapshot。",
        },
    ]


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


def _build_query_request(context: RequestContext, task: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    rewritten = QueryEngine._rewrite_evidence_task_queries(context, task)
    executable_queries = _dedupe_strings(
        [
            str(rewritten["primary_query"]),
            *[str(item) for item in rewritten["authority_queries"]],
            *[str(item) for item in rewritten["fallback_queries"]],
        ]
    )
    return {
        "round_number": args.round_number,
        "target_node_id": task.get("target_node_id"),
        "task": {
            "task_id": task.get("task_id"),
            "task_type": task.get("task_type", "query"),
            "query_text": task.get("query_text"),
            "claim_or_gap": task.get("claim_or_gap"),
            "expected_evidence": task.get("expected_evidence"),
            "preferred_source_types": task.get("preferred_source_types"),
            "acceptance_criteria": task.get("acceptance_criteria"),
            "target_node_id": task.get("target_node_id"),
            "suggested_relative_path": task.get("suggested_relative_path"),
            "target_file_path": task.get("target_file_path"),
            "status": task.get("status"),
        },
        "effective_task_after_rewrite": {
            "query_text": rewritten["primary_query"],
            "expected_evidence": rewritten["expected_evidence"],
            "preferred_source_types": rewritten["preferred_source_types"],
            "acceptance_criteria": rewritten["acceptance_criteria"],
            "authority_queries": rewritten["authority_queries"],
            "fallback_queries": rewritten["fallback_queries"],
        },
        "rewritten_queries": rewritten,
        "executable_queries_in_order": executable_queries,
        "search_settings": {
            "providers": ["google"],
            "search_timeout_seconds": args.search_timeout,
            "llm_timeout_seconds": args.llm_timeout,
            "embeddings": not args.no_embeddings,
            "max_concurrent_network_tasks": 1,
        },
    }


def _extract_query_attempts(execution_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for entry in execution_log:
        if entry.get("event") not in {"query_search_executed", "query_search_failed"}:
            continue
        details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
        attempts.append(
            {
                "event": entry.get("event"),
                "query": details.get("query"),
                "status": details.get("status"),
                "hits": details.get("hits"),
                "source_type": details.get("source_type"),
                "failure_category": details.get("failure_category"),
                "error": details.get("error"),
            }
        )
    return attempts


def _build_diagnostics(selected: dict[str, Any] | None, attempts: list[dict[str, Any]], trace_lines: list[str]) -> dict[str, Any]:
    selected_url = str((selected or {}).get("url", ""))
    publisher = str((selected or {}).get("publisher", ""))
    source_type = str((selected or {}).get("source_type", ""))
    warnings: list[str] = []
    if selected_url.startswith(("https://www.google.com/url?", "http://www.google.com/url?")):
        warnings.append("selected_link_is_google_redirect")
    if source_type == "official" and publisher in {"www.google.com", "google.com"}:
        warnings.append("official_source_uses_search_engine_publisher")
    if not selected_url and attempts:
        warnings.append("no_selected_link_after_rewrite")
    if attempts and not any(int(attempt.get("hits") or 0) > 0 for attempt in attempts):
        warnings.append("all_search_attempts_returned_zero_hits")
    return {
        "selected_url": selected_url,
        "selected_publisher": publisher,
        "selected_source_type": source_type,
        "attempt_count": len(attempts),
        "hit_count_total": sum(int(attempt.get("hits") or 0) for attempt in attempts),
        "trace_count": len(trace_lines),
        "warnings": warnings,
    }


def _dedupe_strings(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = " ".join(str(item).split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            deduped.append(cleaned)
    return deduped


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


def _trace(lines: list[str], message: str, *, echo: bool) -> None:
    lines.append(message)
    if echo:
        print(message, file=sys.stderr)


def _emit(args: argparse.Namespace, sections: list[tuple[str, Any]]) -> None:
    if args.json_only:
        print(json.dumps({label: payload for label, payload in sections}, ensure_ascii=False, indent=2, default=str))
        return
    for label, payload in sections:
        print_json(label, payload)


def print_json(label: str, payload: Any) -> None:
    print(f"\n## {label}")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
