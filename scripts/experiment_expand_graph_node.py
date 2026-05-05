from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from typing import Any

from neo4j import GraphDatabase

from knowledgeforge.server.config import AppConfig


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query Neo4j for a suitable leaf structure node, then call the graph-node expansion API."
    )
    parser.add_argument("--base-url", default="http://localhost:5001", help="KnowledgeForge API base URL.")
    parser.add_argument("--task-id", default="", help="Task ID to test. Defaults to the newest task from /tasks.")
    parser.add_argument("--node-id", default="", help="Explicit structure node id. If omitted, a leaf node is selected from Neo4j.")
    parser.add_argument("--force", action="store_true", help="Pass force=true to the expansion API.")
    parser.add_argument("--dry-run", action="store_true", help="Only print the selected node; do not call the API.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    task = _load_task(base_url, args.task_id)
    task_id = str(task.get("task_id", "")).strip()
    request_context = task.get("request_context") or {}
    domain = str(request_context.get("domain") or request_context.get("normalized_domain") or task.get("domain") or "").strip()
    if not task_id or not domain:
        raise RuntimeError("Could not resolve task_id and domain from the API task payload.")

    node = {"node_id": args.node_id, "title": "(explicit)", "node_type": "unknown", "child_count": None}
    if not args.node_id:
        node = _select_leaf_node_from_neo4j(task_id=task_id, domain=domain)
    node_id = str(node.get("node_id", "")).strip()
    if not node_id:
        raise RuntimeError("No suitable leaf node found in Neo4j. Pass --node-id to test a specific node.")

    print(
        json.dumps(
            {
                "selected": {
                    "task_id": task_id,
                    "domain": domain,
                    "node_id": node_id,
                    "title": node.get("title", ""),
                    "node_type": node.get("node_type", ""),
                    "relative_path": node.get("relative_path", ""),
                    "generation_state": node.get("generation_state", ""),
                    "child_count": node.get("child_count"),
                },
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.dry_run:
        return 0

    result = _post_json(
        f"{base_url}/tasks/{_url_quote(task_id)}/graph/nodes/expand",
        {"node_id": node_id, "force": bool(args.force)},
    )
    added_nodes = result.get("added_nodes") if isinstance(result.get("added_nodes"), list) else []
    graph_snapshot = result.get("graph_snapshot") if isinstance(result.get("graph_snapshot"), dict) else {}
    print(
        json.dumps(
            {
                "api_status": result.get("status"),
                "expanded_node_id": result.get("node_id"),
                "added_count": len(added_nodes),
                "added_nodes": [
                    {
                        "node_id": item.get("node_id"),
                        "title": item.get("title"),
                        "relative_path": item.get("relative_path"),
                    }
                    for item in added_nodes
                    if isinstance(item, dict)
                ],
                "graph_snapshot_counts": {
                    "nodes": len(graph_snapshot.get("nodes", [])) if isinstance(graph_snapshot.get("nodes"), list) else 0,
                    "edges": len(graph_snapshot.get("edges", [])) if isinstance(graph_snapshot.get("edges"), list) else 0,
                },
                "sync": result.get("structure_graph_sync"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _load_task(base_url: str, task_id: str) -> dict[str, Any]:
    if task_id:
        return _get_json(f"{base_url}/tasks/{_url_quote(task_id)}")
    payload = _get_json(f"{base_url}/tasks")
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    if not tasks:
        raise RuntimeError("No tasks returned from /tasks. Start a task first or pass --task-id.")
    newest = tasks[0]
    newest_task_id = str(newest.get("task_id", "")).strip()
    if not newest_task_id:
        raise RuntimeError("Newest task summary does not include task_id.")
    return _get_json(f"{base_url}/tasks/{_url_quote(newest_task_id)}")


def _select_leaf_node_from_neo4j(*, task_id: str, domain: str) -> dict[str, Any]:
    config = _load_config()
    driver = GraphDatabase.driver(
        config.neo4j.uri,
        auth=(config.neo4j.user, config.neo4j.password),
        connection_timeout=2.0,
        max_transaction_retry_time=0,
    )
    try:
        with driver.session() as session:
            record = session.execute_read(_read_leaf_node, task_id, domain)
    finally:
        with suppress(Exception):
            driver.close()
    return record or {}


def _read_leaf_node(tx: Any, task_id: str, domain: str) -> dict[str, Any] | None:
    row = tx.run(
        """
        MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(n:KnowledgeStructureNode)
        WHERE (n.task_id = $task_id OR n.task_id IS NULL)
          AND n.node_type IN ['article', 'subtopic']
        OPTIONAL MATCH (n)-[r:STRUCTURE_EDGE {type: 'CONTAINS'}]->(:KnowledgeStructureNode)
        WITH n, count(r) AS child_count
        WHERE child_count = 0
        RETURN n.id AS node_id,
               n.title AS title,
               n.node_type AS node_type,
               n.suggested_relative_path AS relative_path,
               n.generation_state AS generation_state,
               child_count
        ORDER BY
          CASE n.node_type WHEN 'article' THEN 0 WHEN 'subtopic' THEN 1 ELSE 2 END,
          CASE n.generation_state WHEN 'completion_ready' THEN 0 WHEN 'planned' THEN 1 ELSE 2 END,
          n.title
        LIMIT 1
        """,
        task_id=task_id,
        domain=domain,
    ).single()
    if row is None:
        return None
    return {
        "node_id": row["node_id"],
        "title": row["title"],
        "node_type": row["node_type"],
        "relative_path": row["relative_path"],
        "generation_state": row["generation_state"],
        "child_count": row["child_count"],
    }


def _load_config() -> AppConfig:
    try:
        return AppConfig.from_env()
    except Exception:
        return AppConfig()


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: HTTP {exc.code} {detail}") from exc


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed: HTTP {exc.code} {detail}") from exc


def _url_quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
