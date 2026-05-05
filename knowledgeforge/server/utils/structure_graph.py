from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from knowledgeforge.server.models import (
    KnowledgeFileBlueprint,
    KnowledgeStructureEdge,
    KnowledgeStructureGraph,
    KnowledgeStructureNode,
)
from knowledgeforge.server.utils.paths import sanitize_path_segment, slugify_filename
from knowledgeforge.server.utils.time import now_iso


ALLOWED_NODE_TYPES = {"domain", "section", "subtopic", "article", "index"}
ALLOWED_EDGE_TYPES = {"CONTAINS", "INDEXES", "RELATED_TO"}


def build_fallback_structure_graph(
    *,
    domain: str,
    subdomains: list[str],
    source_intent: str,
) -> KnowledgeStructureGraph:
    root_id = _stable_node_id("domain", domain, "root")
    nodes = [
        KnowledgeStructureNode(
            node_id=root_id,
            title=f"{domain} Overview",
            node_type="domain",
            relative_path="README.md",
            description="领域结构目录索引。",
            doc_type="summary",
            owner_engine_candidates=["InsightEngine"],
            metadata={"subdomain": ""},
        )
    ]
    edges: list[KnowledgeStructureEdge] = []
    topics = [topic.strip() for topic in subdomains if topic.strip()] or [domain]
    for index, topic in enumerate(topics, start=1):
        topic_dir = sanitize_path_segment(topic, f"topic-{index}")
        topic_id = _stable_node_id("subtopic", topic, str(index))
        overview_id = _stable_node_id("article", f"{topic} overview", str(index))
        nodes.extend(
            [
                KnowledgeStructureNode(
                    node_id=topic_id,
                    title=topic,
                    node_type="subtopic",
                    relative_path=f"{topic_dir}/README.md",
                    description=f"{topic} 的主题索引。",
                    parent_node_id=root_id,
                    doc_type="summary",
                    owner_engine_candidates=["InsightEngine", "QueryEngine"],
                    required_query_tasks=1,
                    metadata={"subdomain": topic},
                ),
                KnowledgeStructureNode(
                    node_id=overview_id,
                    title=f"{topic} Overview",
                    node_type="article",
                    relative_path=f"{topic_dir}/overview.md",
                    description=f"{topic} 的入门概览与证据入口。",
                    parent_node_id=topic_id,
                    doc_type="article",
                    owner_engine_candidates=["QueryEngine", "InsightEngine"],
                    required_query_tasks=1,
                    metadata={"subdomain": topic},
                ),
            ]
        )
        edges.extend(
            [
                KnowledgeStructureEdge(from_node_id=root_id, edge_type="CONTAINS", to_node_id=topic_id),
                KnowledgeStructureEdge(from_node_id=topic_id, edge_type="CONTAINS", to_node_id=overview_id),
            ]
        )
    return KnowledgeStructureGraph(
        nodes=nodes,
        edges=edges,
        root_node_id=root_id,
        source_intent=source_intent,
        generated_at=now_iso(),
    )


def normalize_structure_graph_payload(
    *,
    payload: dict[str, Any],
    domain: str,
    subdomains: list[str],
    focus_points: list[str],
    source_intent: str,
) -> KnowledgeStructureGraph:
    raw_nodes = payload.get("nodes", [])
    raw_edges = payload.get("edges", [])
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return build_fallback_structure_graph(domain=domain, subdomains=subdomains, source_intent=source_intent)

    root_node_id = str(payload.get("root_node_id", "")).strip()
    nodes_by_id: dict[str, KnowledgeStructureNode] = {}
    used_paths: set[str] = set()
    raw_parent_by_id: dict[str, str] = {}

    ordered_raw_nodes = sorted(
        [item for item in raw_nodes if isinstance(item, dict)],
        key=lambda item: 0 if _normalize_node_type(item.get("node_type") or item.get("type")) == "domain" else 1,
    )
    for index, raw_node in enumerate(ordered_raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_type = _normalize_node_type(raw_node.get("node_type") or raw_node.get("type"))
        title = str(raw_node.get("title") or raw_node.get("name") or "").strip()
        if not title:
            title = domain if node_type == "domain" else f"Knowledge Node {index}"
        fallback_id = _stable_node_id(node_type, title, str(index))
        node_id = _sanitize_node_id(str(raw_node.get("node_id") or raw_node.get("id") or fallback_id))
        if not node_id or node_id in nodes_by_id:
            node_id = _dedupe_id(fallback_id, nodes_by_id)
        parent_node_id = _sanitize_node_id(str(raw_node.get("parent_node_id") or raw_node.get("parent_id") or ""))
        raw_parent_by_id[node_id] = parent_node_id
        relative_path = _normalize_relative_path(
            raw_node.get("relative_path") or raw_node.get("path"),
            title=title,
            node_type=node_type,
            parent_node_id=parent_node_id,
            nodes_by_id=nodes_by_id,
            fallback_index=index,
        )
        relative_path = _dedupe_path(relative_path, used_paths)
        used_paths.add(relative_path)
        owners = _normalize_owners(raw_node.get("owner_engine_candidates") or raw_node.get("owners"))
        if not owners:
            owners = _default_owners(node_type)
        nodes_by_id[node_id] = KnowledgeStructureNode(
            node_id=node_id,
            title=title,
            node_type=node_type,  # type: ignore[arg-type]
            relative_path=relative_path,
            description=str(raw_node.get("description", "")).strip(),
            parent_node_id=parent_node_id,
            doc_type=_normalize_doc_type(str(raw_node.get("doc_type", "")).strip(), node_type),
            owner_engine_candidates=owners,
            required_query_tasks=_normalize_required_query_tasks(raw_node, node_type),
            metadata={
                "focus_points": focus_points,
                **(raw_node.get("metadata") if isinstance(raw_node.get("metadata"), dict) else {}),
            },
        )

    if not nodes_by_id:
        return build_fallback_structure_graph(domain=domain, subdomains=subdomains, source_intent=source_intent)

    root_node_id = root_node_id if root_node_id in nodes_by_id else ""
    if not root_node_id:
        root_node_id = next((node.node_id for node in nodes_by_id.values() if node.node_type == "domain"), "")
    if not root_node_id:
        root_node_id = _stable_node_id("domain", domain, "root")
        path = _dedupe_path("README.md", used_paths)
        used_paths.add(path)
        nodes_by_id[root_node_id] = KnowledgeStructureNode(
            node_id=root_node_id,
            title=f"{domain} Overview",
            node_type="domain",
            relative_path=path,
            description="领域结构目录索引。",
            doc_type="summary",
            owner_engine_candidates=["InsightEngine"],
            metadata={"focus_points": focus_points, "subdomain": ""},
        )

    root = nodes_by_id[root_node_id]
    if root.relative_path != "README.md":
        root.relative_path = "README.md"
    root.parent_node_id = ""
    root.metadata["subdomain"] = ""

    edges = _normalize_edges(raw_edges, nodes_by_id, raw_parent_by_id, root_node_id)
    _attach_subdomain_metadata(nodes_by_id, edges, root_node_id)
    return KnowledgeStructureGraph(
        nodes=list(nodes_by_id.values()),
        edges=edges,
        root_node_id=root_node_id,
        source_intent=str(payload.get("source_intent") or source_intent),
        generated_at=str(payload.get("generated_at") or now_iso()),
    )


def derive_context_from_structure_graph(
    *,
    graph: KnowledgeStructureGraph,
    domain: str,
) -> dict[str, Any]:
    blueprint = _build_blueprint_from_graph(graph)
    return {
        "knowledge_modules": _build_modules_from_graph(graph),
        "core_topics": _build_core_topics_from_graph(graph),
        "navigation_targets": _build_navigation_targets_from_graph(graph),
        "knowledge_blueprint": blueprint,
        "required_files": build_required_file_paths(domain, blueprint),
        "structure_mode": "llm_structure_graph",
    }


def build_required_file_paths(domain: str, blueprint: list[dict[str, Any]]) -> list[str]:
    domain_segment = sanitize_path_segment(domain, "domain")
    required: list[str] = []
    for item in blueprint:
        requirements = item.get("completion_requirements", {})
        if isinstance(requirements, dict) and requirements.get("required"):
            required.append(str(PurePosixPath("save") / domain_segment / str(item.get("relative_path", ""))))
    return required


def structure_graph_summary(graph: KnowledgeStructureGraph) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for node in graph.nodes:
        counts[node.node_type] = counts.get(node.node_type, 0) + 1
    return {
        "root_node_id": graph.root_node_id,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "node_type_counts": counts,
        "generated_at": graph.generated_at,
    }


def _build_blueprint_from_graph(graph: KnowledgeStructureGraph) -> list[dict[str, Any]]:
    blueprints: list[KnowledgeFileBlueprint] = []
    for node in graph.nodes:
        module_id, module_label = _module_for_node(graph, node)
        blueprints.append(
            KnowledgeFileBlueprint(
                file_id=node.node_id,
                title=node.title,
                module_id=module_id,
                module_label=module_label,
                doc_role=_doc_role_for_node(node),
                relative_path=node.relative_path,
                subdomain=str(node.metadata.get("subdomain", "")),
                doc_type=node.doc_type,
                owner_engine_candidates=list(node.owner_engine_candidates),
                completion_requirements={
                    "required": True,
                    "required_query_tasks": max(0, int(node.required_query_tasks)),
                    "structure_node_id": node.node_id,
                    "structure_node_type": node.node_type,
                    "parent_node_id": node.parent_node_id,
                },
            ).to_dict()
        )
    return blueprints


def _build_modules_from_graph(graph: KnowledgeStructureGraph) -> list[dict[str, str]]:
    children = [node for node in graph.nodes if node.parent_node_id == graph.root_node_id and node.node_type in {"section", "subtopic"}]
    modules = []
    for node in children:
        modules.append(
            {
                "module_id": node.node_id,
                "label": node.title,
                "directory": _directory_for_path(node.relative_path),
                "purpose": node.description or node.title,
                "priority": "dynamic",
                "default_doc_type": node.doc_type,
            }
        )
    return modules


def _build_core_topics_from_graph(graph: KnowledgeStructureGraph) -> list[str]:
    topics = [node.title for node in graph.nodes if node.node_type == "subtopic"]
    return list(dict.fromkeys([topic for topic in topics if topic.strip()]))


def _build_navigation_targets_from_graph(graph: KnowledgeStructureGraph) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for node in graph.nodes:
        targets.append(
            {
                "doc_role": _doc_role_for_node(node),
                "title": node.title,
                "relative_path": node.relative_path,
                "module_id": _module_for_node(graph, node)[0],
                "module_label": _module_for_node(graph, node)[1],
                "subdomain": str(node.metadata.get("subdomain", "")),
                "doc_type": node.doc_type,
                "structure_node_id": node.node_id,
                "structure_node_type": node.node_type,
            }
        )
    return targets


def _normalize_node_type(value: object) -> str:
    node_type = str(value or "").strip().lower()
    return node_type if node_type in ALLOWED_NODE_TYPES else "article"


def _normalize_relative_path(
    value: object,
    *,
    title: str,
    node_type: str,
    parent_node_id: str,
    nodes_by_id: dict[str, KnowledgeStructureNode],
    fallback_index: int,
) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if raw.startswith("/") or ".." in PurePosixPath(raw).parts:
        raw = ""
    if raw:
        parts = [sanitize_path_segment(part, f"part-{fallback_index}") for part in PurePosixPath(raw).parts if part not in {"", "."}]
        raw = str(PurePosixPath(*parts)) if parts else ""
    parent_dir = ""
    parent = nodes_by_id.get(parent_node_id)
    if parent is not None:
        parent_dir = _directory_for_path(parent.relative_path)
    if not raw:
        if node_type == "domain":
            raw = "README.md"
        elif node_type in {"section", "subtopic"}:
            segment = sanitize_path_segment(title, f"section-{fallback_index}")
            raw = str(PurePosixPath(parent_dir) / segment / "README.md") if parent_dir else str(PurePosixPath(segment) / "README.md")
        elif node_type == "index":
            raw = str(PurePosixPath(parent_dir) / "index.md") if parent_dir else "index.md"
        else:
            filename = f"{slugify_filename(title, f'article-{fallback_index}')}.md"
            raw = str(PurePosixPath(parent_dir) / filename) if parent_dir else filename
    path = PurePosixPath(raw)
    if path.suffix != ".md":
        path = path / "README.md"
    return path.as_posix()


def _dedupe_path(path: str, used_paths: set[str]) -> str:
    if path not in used_paths:
        return path
    base = PurePosixPath(path)
    stem = base.stem
    suffix = base.suffix or ".md"
    parent = base.parent
    counter = 2
    while True:
        candidate = (parent / f"{stem}-{counter}{suffix}").as_posix() if str(parent) != "." else f"{stem}-{counter}{suffix}"
        if candidate not in used_paths:
            return candidate
        counter += 1


def _normalize_edges(
    raw_edges: object,
    nodes_by_id: dict[str, KnowledgeStructureNode],
    raw_parent_by_id: dict[str, str],
    root_node_id: str,
) -> list[KnowledgeStructureEdge]:
    edges: list[KnowledgeStructureEdge] = []
    seen: set[tuple[str, str, str]] = set()
    if isinstance(raw_edges, list):
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, dict):
                continue
            from_id = _sanitize_node_id(str(raw_edge.get("from_node_id") or raw_edge.get("from") or ""))
            to_id = _sanitize_node_id(str(raw_edge.get("to_node_id") or raw_edge.get("to") or ""))
            edge_type = str(raw_edge.get("edge_type") or raw_edge.get("type") or "CONTAINS").strip().upper()
            if edge_type not in ALLOWED_EDGE_TYPES:
                edge_type = "CONTAINS"
            if from_id not in nodes_by_id or to_id not in nodes_by_id or from_id == to_id:
                continue
            key = (from_id, edge_type, to_id)
            if key in seen:
                continue
            seen.add(key)
            edges.append(KnowledgeStructureEdge(from_node_id=from_id, edge_type=edge_type, to_node_id=to_id))  # type: ignore[arg-type]
    contained_children = {edge.to_node_id for edge in edges if edge.edge_type in {"CONTAINS", "INDEXES"}}
    for node_id, node in nodes_by_id.items():
        if node_id == root_node_id or node_id in contained_children:
            continue
        parent_id = raw_parent_by_id.get(node_id) or node.parent_node_id
        if parent_id not in nodes_by_id or parent_id == node_id:
            parent_id = root_node_id
        node.parent_node_id = parent_id
        key = (parent_id, "CONTAINS", node_id)
        if key not in seen:
            seen.add(key)
            edges.append(KnowledgeStructureEdge(from_node_id=parent_id, edge_type="CONTAINS", to_node_id=node_id))
    for edge in edges:
        if edge.edge_type in {"CONTAINS", "INDEXES"} and edge.to_node_id in nodes_by_id:
            nodes_by_id[edge.to_node_id].parent_node_id = edge.from_node_id
    return edges


def _attach_subdomain_metadata(
    nodes_by_id: dict[str, KnowledgeStructureNode],
    edges: list[KnowledgeStructureEdge],
    root_node_id: str,
) -> None:
    children_by_parent: dict[str, list[str]] = {}
    for edge in edges:
        if edge.edge_type in {"CONTAINS", "INDEXES"}:
            children_by_parent.setdefault(edge.from_node_id, []).append(edge.to_node_id)

    def visit(node_id: str, active_subdomain: str) -> None:
        node = nodes_by_id[node_id]
        subdomain = node.title if node.node_type == "subtopic" else active_subdomain
        node.metadata["subdomain"] = "" if node_id == root_node_id else subdomain
        for child_id in children_by_parent.get(node_id, []):
            visit(child_id, subdomain)

    visit(root_node_id, "")


def _module_for_node(graph: KnowledgeStructureGraph, node: KnowledgeStructureNode) -> tuple[str, str]:
    by_id = {item.node_id: item for item in graph.nodes}
    current = node
    while current.parent_node_id and current.parent_node_id != graph.root_node_id:
        parent = by_id.get(current.parent_node_id)
        if parent is None:
            break
        current = parent
    if current.node_id == graph.root_node_id:
        return "overview", "Overview"
    return current.node_id, current.title


def _doc_role_for_node(node: KnowledgeStructureNode) -> str:
    if node.node_type == "domain":
        return "domain_overview"
    if node.node_type == "index":
        return "topic_index" if node.metadata.get("subdomain") else "domain_index"
    if node.node_type in {"section", "subtopic"}:
        return "topic_overview" if node.node_type == "subtopic" else "module_overview"
    return "topic_article"


def _normalize_doc_type(value: str, node_type: str) -> str:
    allowed = {"source", "article", "summary", "case", "trend", "note"}
    if value in allowed:
        return value
    if node_type in {"domain", "section", "subtopic"}:
        return "summary"
    if node_type == "index":
        return "note"
    return "article"


def _normalize_owners(value: object) -> list[str]:
    allowed = {"InsightEngine", "QueryEngine", "MediaEngine"}
    if not isinstance(value, list):
        return []
    owners = [str(item).strip() for item in value if str(item).strip() in allowed]
    return list(dict.fromkeys(owners))


def _default_owners(node_type: str) -> list[str]:
    if node_type in {"domain", "section", "index"}:
        return ["InsightEngine"]
    if node_type == "subtopic":
        return ["InsightEngine", "QueryEngine"]
    return ["QueryEngine", "InsightEngine"]


def _normalize_required_query_tasks(raw_node: dict[str, Any], node_type: str) -> int:
    if "required_query_tasks" in raw_node:
        try:
            requested_tasks = max(0, int(raw_node.get("required_query_tasks") or 0))
        except (TypeError, ValueError):
            requested_tasks = 0
        if requested_tasks > 0:
            return requested_tasks
        if raw_node.get("requires_query") is False:
            return 0
        return 1 if node_type in {"subtopic", "article"} else 0
    if raw_node.get("requires_query") is True:
        return 1
    return 1 if node_type in {"subtopic", "article"} else 0


def _directory_for_path(relative_path: str) -> str:
    parent = PurePosixPath(relative_path).parent
    return "" if str(parent) == "." else parent.as_posix()


def _stable_node_id(node_type: str, title: str, fallback: str) -> str:
    return _sanitize_node_id(f"{node_type}-{slugify_filename(title, fallback)}")


def _sanitize_node_id(value: str) -> str:
    cleaned = slugify_filename(value, "node")
    return cleaned.replace("-", "_")


def _dedupe_id(node_id: str, nodes_by_id: dict[str, KnowledgeStructureNode]) -> str:
    candidate = node_id
    counter = 2
    while candidate in nodes_by_id:
        candidate = f"{node_id}_{counter}"
        counter += 1
    return candidate
