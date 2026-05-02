from __future__ import annotations

from knowledgeforge.graph.neo4j_adapter import Neo4jPathMapper
from knowledgeforge.models import DocumentArtifact, EngineRunResult, PostStorageResult, RequestContext
from knowledgeforge.postprocess.extractor import StructuredExtractor
from knowledgeforge.quality.checker import QualityChecker
from knowledgeforge.versioning.recorder import VersionRecorder


class PostStoragePipeline:
    def __init__(
        self,
        extractor: StructuredExtractor,
        graph_mapper: Neo4jPathMapper,
        quality_checker: QualityChecker,
        version_recorder: VersionRecorder,
        strict_graph_sync: bool = False,
    ) -> None:
        self._extractor = extractor
        self._graph_mapper = graph_mapper
        self._quality_checker = quality_checker
        self._version_recorder = version_recorder
        self._strict_graph_sync = strict_graph_sync

    def run(
        self,
        artifact: DocumentArtifact,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
    ) -> PostStorageResult:
        extraction = self._extractor.extract(artifact)
        graph_sync = self._graph_mapper.sync(artifact, extraction, context=context)
        if graph_sync.status == "failed" and self._strict_graph_sync:
            return PostStorageResult(
                extraction=extraction,
                graph_sync=graph_sync,
                quality_check=self._quality_checker.check(artifact, extraction, graph_sync, context, outputs),
                version_record=None,
                status="failed",
                remediation_flows=["repair_flow"],
                next_round_queries=["修复 Neo4j 写入或路径关联后重试。"],
                failure_category="graph_write_failed",
            )
        quality_check = self._quality_checker.check(artifact, extraction, graph_sync, context, outputs)

        if quality_check.status == "failed":
            remediation_flows = sorted({issue.flow for issue in quality_check.issues})
            next_round_queries = []
            if "repair_flow" in remediation_flows:
                next_round_queries.append(f"修复 {artifact.document_id} 的结构化抽取与元数据。")
            if "research_flow" in remediation_flows:
                next_round_queries.extend(
                    f"{context.domain} {topic} 权威来源复核"
                    for topic in context.subdomains
                )
            return PostStorageResult(
                extraction=extraction,
                graph_sync=graph_sync,
                quality_check=quality_check,
                version_record=None,
                status="failed",
                remediation_flows=remediation_flows,
                next_round_queries=next_round_queries,
                failure_category="quality_check_failed",
            )

        version_record = self._version_recorder.record(artifact, graph_sync, quality_check)
        return PostStorageResult(
            extraction=extraction,
            graph_sync=graph_sync,
            quality_check=quality_check,
            version_record=version_record,
            status="passed",
            remediation_flows=[],
            next_round_queries=[],
        )

    def sync_structure_graph(self, *, domain: str, task_id: str, structure_graph: dict):
        if not hasattr(self._graph_mapper, "sync_structure_graph"):
            return None
        return self._graph_mapper.sync_structure_graph(domain=domain, task_id=task_id, structure_graph=structure_graph)

    def mark_structure_node_generated(
        self,
        *,
        domain: str,
        task_id: str,
        node_id: str,
        generated_path: str,
    ):
        if not hasattr(self._graph_mapper, "mark_structure_node_generated"):
            return None
        return self._graph_mapper.mark_structure_node_generated(
            domain=domain,
            task_id=task_id,
            node_id=node_id,
            generated_path=generated_path,
        )
