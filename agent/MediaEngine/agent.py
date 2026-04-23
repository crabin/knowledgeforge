from __future__ import annotations

from agent.base import BaseEngine
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class MediaEngine(BaseEngine):
    name = "MediaEngine"

    def run(self, context: RequestContext, round_number: int) -> EngineRunResult:
        timestamp = now_iso()
        return EngineRunResult(
            agent_name=self.name,
            summary=f"补充 {context.domain} 的趋势、社区和媒体观察视角。",
            key_points=[
                "媒体视角用于补齐应用场景与热点变化，不替代事实型来源。",
                f"当前聚焦 {context.time_window} 内与 {context.domain} 相关的动态。",
            ],
            raw_material=[
                f"观察主题：{topic}"
                for topic in context.subdomains
            ],
            coverage_topics=context.subdomains,
            sources=[
                SourceRecord(
                    title=f"{context.domain} 媒体观察样例",
                    url=f"https://example.com/{round_number}/{self.name.lower()}",
                    publisher="Example Media",
                    retrieved_at=timestamp,
                    reliability="medium",
                    agent=self.name,
                )
            ],
            collected_at=timestamp,
            round_number=round_number,
        )
