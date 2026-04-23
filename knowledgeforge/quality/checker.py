from __future__ import annotations

from pathlib import Path

from knowledgeforge.models import (
    DocumentArtifact,
    EngineRunResult,
    GraphSyncResult,
    QualityCheckResult,
    QualityIssue,
    RequestContext,
    StructuredExtractionResult,
)


class QualityChecker:
    def check(
        self,
        artifact: DocumentArtifact,
        extraction: StructuredExtractionResult,
        graph_sync: GraphSyncResult,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
    ) -> QualityCheckResult:
        content = Path(artifact.path).read_text(encoding="utf-8")
        entity_names = [entity["name"] for entity in extraction.entities]
        has_duplicate_entities = len(entity_names) != len(set(entity_names))
        has_sources = any(output.sources for output in outputs.values())
        simulate_duplicate = "simulate_duplicate" in context.constraints
        simulate_conflict = "simulate_conflict" in context.constraints
        simulate_missing_citation = "simulate_missing_citation" in context.constraints
        checks = {
            "has_front_matter": content.startswith("---\n"),
            "has_sources_section": "## 证据与来源" in content,
            "has_entities": bool(extraction.entities),
            "has_graph_nodes": bool(graph_sync.nodes),
            "duplicate_check": not (has_duplicate_entities or simulate_duplicate),
            "conflict_check": not simulate_conflict,
            "citation_check": has_sources and not simulate_missing_citation,
        }
        issues: list[QualityIssue] = []
        if not checks["has_front_matter"]:
            issues.append(
                QualityIssue(
                    category="quality_check_failed",
                    detail="缺少 YAML front matter。",
                    flow="repair_flow",
                )
            )
        if not checks["has_sources_section"]:
            issues.append(
                QualityIssue(
                    category="quality_check_failed",
                    detail="缺少证据与来源章节。",
                    flow="research_flow",
                )
            )
        if not checks["duplicate_check"]:
            issues.append(
                QualityIssue(
                    category="quality_check_failed",
                    detail="检测到重复实体，需修复结构化抽取结果。",
                    flow="repair_flow",
                )
            )
        if not checks["conflict_check"]:
            issues.append(
                QualityIssue(
                    category="quality_check_failed",
                    detail="存在未裁决冲突，需补充检索高可信证据。",
                    flow="research_flow",
                )
            )
        if not checks["citation_check"]:
            issues.append(
                QualityIssue(
                    category="quality_check_failed",
                    detail="引用链不足或证据缺失，需补充检索。",
                    flow="research_flow",
                )
            )

        status = "failed" if issues else "passed"
        return QualityCheckResult(
            document_id=artifact.document_id,
            status=status,
            issues=issues,
            checks=checks,
        )
