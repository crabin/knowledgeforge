from __future__ import annotations

from knowledgeforge.graph.client import Neo4jGraphClient
from knowledgeforge.models import DocumentArtifact, GraphSyncResult, RequestContext, StructuredExtractionResult


class Neo4jPathMapper:
    def __init__(self, client: Neo4jGraphClient | None = None) -> None:
        self._client = client

    def sync_structure_graph(self, *, domain: str, task_id: str, structure_graph: dict) -> GraphSyncResult:
        nodes = []
        relationships = []
        if isinstance(structure_graph, dict):
            for node in structure_graph.get("nodes", []):
                if not isinstance(node, dict):
                    continue
                generation_state = str(node.get("generation_state", "planned"))
                nodes.append(
                    {
                        "label": _graph_label_for_structure_type(str(node.get("node_type", ""))),
                        "id": str(node.get("node_id", "")),
                        "title": str(node.get("title", "")),
                        "path": str(node.get("relative_path", "")),
                        "is_generated": bool(node.get("is_generated", False)) or generation_state in {"completion_ready", "document_generating", "documented", "link_querying", "link_verified", "approved"},
                        "is_completed": bool(node.get("is_completed", False)) or generation_state in {"completion_ready", "documented", "link_verified", "approved"},
                        "generation_state": generation_state,
                        "suggested_relative_path": str(node.get("suggested_relative_path", node.get("relative_path", ""))),
                        "document_completion_status": str(node.get("document_completion_status", "not_requested")),
                        "review_status": str(node.get("review_status", "")),
                    }
                )
            for edge in structure_graph.get("edges", []):
                if not isinstance(edge, dict):
                    continue
                relationships.append(
                    {
                        "from": str(edge.get("from_node_id", "")),
                        "type": str(edge.get("edge_type", "CONTAINS")),
                        "to": str(edge.get("to_node_id", "")),
                    }
                )
        status = "passed"
        error = None
        if self._client is not None:
            try:
                self._client.sync_structure_graph(domain=domain, task_id=task_id, structure_graph=structure_graph)
            except Exception as exc:
                status = "failed"
                error = str(exc)
        return GraphSyncResult(
            document_id=f"{domain}-structure-graph",
            article_path="",
            nodes=nodes,
            relationships=relationships,
            status=status,
            error=error,
        )

    def structure_review_context(self, *, domain: str, task_id: str, knowledge_id: str) -> dict:
        if self._client is None:
            return {
                "status": "skipped",
                "reason": "neo4j_client_unavailable",
                "domain": domain,
                "task_id": task_id,
                "knowledge_id": knowledge_id,
                "nodes": [],
                "edges": [],
            }
        try:
            graph = self._client.structure_review_context(
                domain=domain,
                task_id=task_id,
                knowledge_id=knowledge_id,
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "domain": domain,
                "task_id": task_id,
                "knowledge_id": knowledge_id,
                "nodes": [],
                "edges": [],
            }
        return {
            "status": "ok",
            "domain": domain,
            "task_id": task_id,
            "knowledge_id": knowledge_id,
            "nodes": graph.get("nodes", []),
            "edges": graph.get("edges", []),
        }

    def mark_structure_node_generated(
        self,
        *,
        domain: str,
        task_id: str,
        node_id: str,
        generated_path: str,
    ) -> GraphSyncResult:
        status = "passed"
        error = None
        if self._client is not None:
            try:
                self._client.mark_structure_node_generated(
                    domain=domain,
                    task_id=task_id,
                    node_id=node_id,
                    generated_path=generated_path,
                )
            except Exception as exc:
                status = "failed"
                error = str(exc)
        return GraphSyncResult(
            document_id=node_id,
            article_path=generated_path,
            nodes=[{"label": "KnowledgeStructureNode", "id": node_id, "is_generated": status == "passed"}],
            relationships=[],
            status=status,
            error=error,
        )

    def update_structure_node_status(
        self,
        *,
        domain: str,
        task_id: str,
        node_id: str,
        generation_state: str,
        generated_path: str = "",
        pending_task_count: int | None = None,
        completed_task_count: int | None = None,
        extra_properties: dict | None = None,
    ) -> GraphSyncResult:
        status = "passed"
        error = None
        if self._client is not None:
            try:
                self._client.update_structure_node_status(
                    domain=domain,
                    task_id=task_id,
                    node_id=node_id,
                    generation_state=generation_state,
                    generated_path=generated_path,
                    pending_task_count=pending_task_count,
                    completed_task_count=completed_task_count,
                    extra_properties=extra_properties or {},
                )
            except Exception as exc:
                status = "failed"
                error = str(exc)
        return GraphSyncResult(
            document_id=node_id,
            article_path=generated_path,
            nodes=[
                {
                    "label": "KnowledgeStructureNode",
                    "id": node_id,
                    "generation_state": generation_state,
                    "is_generated": generation_state in {"completion_ready", "document_generating", "documented", "link_querying", "link_verified", "approved"},
                    "is_completed": generation_state in {"completion_ready", "documented", "link_verified", "approved"},
                    **(extra_properties or {}),
                }
            ],
            relationships=[],
            status=status,
            error=error,
        )

    def sync(
        self,
        artifact: DocumentArtifact,
        extraction: StructuredExtractionResult,
        context: RequestContext | None = None,
    ) -> GraphSyncResult:
        structure_graph = context.structure_graph if context is not None else {}
        nodes = [
            {"label": "Domain", "id": artifact.domain},
            {"label": "KnowledgeModule", "id": artifact.module_id or "core_topics", "label_text": artifact.module_label or artifact.module_id},
            {"label": "SubTopic", "id": artifact.subdomain},
            {"label": "Article", "id": artifact.document_id, "path": artifact.path},
        ]
        relationships = [
            {"from": artifact.domain, "type": "HAS_MODULE", "to": artifact.module_id or "core_topics"},
            {"from": artifact.module_id or "core_topics", "type": "HAS_SUBTOPIC", "to": artifact.subdomain},
            {"from": artifact.module_id or "core_topics", "type": "HAS_ARTICLE", "to": artifact.document_id},
            {"from": artifact.subdomain, "type": "HAS_ARTICLE", "to": artifact.document_id},
        ]
        if isinstance(structure_graph, dict):
            for node in structure_graph.get("nodes", []):
                if not isinstance(node, dict):
                    continue
                label = _graph_label_for_structure_type(str(node.get("node_type", "")))
                nodes.append(
                    {
                        "label": label,
                        "id": str(node.get("node_id", "")),
                        "title": str(node.get("title", "")),
                        "path": str(node.get("relative_path", "")),
                    }
                )
            for edge in structure_graph.get("edges", []):
                if not isinstance(edge, dict):
                    continue
                relationships.append(
                    {
                        "from": str(edge.get("from_node_id", "")),
                        "type": str(edge.get("edge_type", "CONTAINS")),
                        "to": str(edge.get("to_node_id", "")),
                    }
                )
        for entity in extraction.entities:
            nodes.append({"label": entity["type"], "id": entity["name"]})
        status = "passed"
        error = None
        if self._client is not None:
            try:
                self._client.sync_document(
                    domain=artifact.domain,
                    subdomain=artifact.subdomain,
                    article_id=artifact.document_id,
                    article_path=artifact.path,
                    entities=extraction.entities,
                    structure_graph=structure_graph if isinstance(structure_graph, dict) else {},
                )
            except Exception as exc:
                status = "failed"
                error = str(exc)
        return GraphSyncResult(
            document_id=artifact.document_id,
            article_path=artifact.path,
            nodes=nodes,
            relationships=relationships,
            status=status,
            error=error,
        )


def _graph_label_for_structure_type(node_type: str) -> str:
    return {
        "domain": "Domain",
        "section": "KnowledgeSection",
        "subtopic": "SubTopic",
        "article": "Article",
        "index": "KnowledgeIndex",
    }.get(node_type, "KnowledgeNode")
