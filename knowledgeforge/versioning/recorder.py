from __future__ import annotations

from knowledgeforge.models import (
    DocumentArtifact,
    GraphSyncResult,
    QualityCheckResult,
    VersionRecord,
)
from knowledgeforge.utils.time import now_iso


class VersionRecorder:
    def record(
        self,
        artifact: DocumentArtifact,
        graph_sync: GraphSyncResult,
        quality_check: QualityCheckResult,
    ) -> VersionRecord:
        return VersionRecord(
            document_id=artifact.document_id,
            version=artifact.version,
            updated_at=now_iso(),
            knowledge_objects=[artifact.domain, artifact.subdomain, artifact.document_id],
            file_paths=[artifact.path],
            graph_nodes=[node["id"] for node in graph_sync.nodes],
            pending_issues=[issue.detail for issue in quality_check.issues],
            status="verified" if quality_check.status == "passed" else "reviewed",
            frozen=quality_check.status == "passed",
            frozen_at=now_iso() if quality_check.status == "passed" else None,
            report_eligible=quality_check.status == "passed",
        )
