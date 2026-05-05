from __future__ import annotations

from pathlib import Path

from knowledgeforge.server.models import DocumentArtifact, StructuredExtractionResult


class StructuredExtractor:
    def extract(self, artifact: DocumentArtifact) -> StructuredExtractionResult:
        document_path = Path(artifact.path)
        content = document_path.read_text(encoding="utf-8")
        body = [line.strip() for line in content.splitlines() if line.strip()]
        chunks = [
            {"chunk_id": f"{artifact.document_id}-chunk-1", "text": "\n".join(body[:12])},
        ]
        entities = [
            {"name": artifact.domain, "type": "Domain"},
            {"name": artifact.subdomain, "type": "SubTopic"},
        ]
        relations = [
            {"source": artifact.domain, "relation": "contains", "target": artifact.subdomain},
        ]
        metadata = {
            "path": artifact.path,
            "title": artifact.title,
            "line_count": len(content.splitlines()),
        }
        return StructuredExtractionResult(
            document_id=artifact.document_id,
            document_path=artifact.path,
            chunks=chunks,
            metadata=metadata,
            entities=entities,
            relations=relations,
        )
