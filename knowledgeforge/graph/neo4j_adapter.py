from __future__ import annotations

from knowledgeforge.graph.client import Neo4jGraphClient
from knowledgeforge.models import DocumentArtifact, GraphSyncResult, StructuredExtractionResult


class Neo4jPathMapper:
    def __init__(self, client: Neo4jGraphClient | None = None) -> None:
        self._client = client

    def sync(
        self,
        artifact: DocumentArtifact,
        extraction: StructuredExtractionResult,
    ) -> GraphSyncResult:
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
