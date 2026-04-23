from __future__ import annotations

from knowledgeforge.models import FrozenVersionRecord, ReportArtifact
from knowledgeforge.utils.time import now_iso


class ReportService:
    def build_report(self, frozen_record: FrozenVersionRecord) -> ReportArtifact:
        sections = [
            {
                "title": "摘要",
                "content": f"本报告基于冻结版本 {frozen_record.version} 生成，仅消费已通过质量检测的知识对象。",
            },
            {
                "title": "知识对象",
                "content": "、".join(frozen_record.knowledge_objects),
            },
            {
                "title": "来源边界",
                "content": "仅使用冻结版本快照中的来源，不直接读取未审查原始采集资料。",
            },
        ]
        return ReportArtifact(
            task_id=frozen_record.task_id,
            document_id=frozen_record.document_id,
            version=frozen_record.version,
            generated_at=now_iso(),
            source="frozen_version",
            sections=sections,
        )
