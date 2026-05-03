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
        all_sources = [source for output in outputs.values() for source in output.sources]
        authoritative_sources = [
            source for source in all_sources if source.reliability in ("high", "medium")
        ]
        source_checks = {
            "source_relevance_check": bool(authoritative_sources),
            "authority_check": bool(all_sources) and bool(authoritative_sources),
            "evidence_support_check": bool(all_sources),
        }
        checks.update(source_checks)
        if context.completion_mode == "framework":
            checks.update(
                {
                    "framework_graph_check": bool(context.structure_graph.get("nodes")) if isinstance(context.structure_graph, dict) else False,
                    "framework_blueprint_check": bool(context.knowledge_blueprint),
                    "framework_generated_files_check": bool(artifact.generated_files),
                    "framework_official_evidence_check": bool(authoritative_sources),
                }
            )
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
        if not source_checks["evidence_support_check"]:
            issues.append(
                QualityIssue(
                    category="source_quality_failed",
                    detail="缺少任何可引用来源，需要重新检索权威证据。",
                    flow="research_flow",
                )
            )
        elif not source_checks["authority_check"]:
            issues.append(
                QualityIssue(
                    category="source_quality_failed",
                    detail="来源不相关或可信度不足，需要重新检索权威证据。",
                    flow="research_flow",
                )
            )
        if context.completion_mode == "framework":
            if not checks["framework_graph_check"] or not checks["framework_blueprint_check"]:
                issues.append(
                    QualityIssue(
                        category="quality_check_failed",
                        detail="知识框架图谱或蓝图缺失，需修复结构化规划结果。",
                        flow="repair_flow",
                    )
                )
            if not checks["framework_generated_files_check"]:
                issues.append(
                    QualityIssue(
                        category="file_write_failed",
                        detail="知识框架证据文件缺失，需重新生成本地文件。",
                        flow="repair_flow",
                    )
                )

        status = "failed" if issues else "passed"
        return QualityCheckResult(
            document_id=artifact.document_id,
            status=status,
            issues=issues,
            checks=checks,
        )
