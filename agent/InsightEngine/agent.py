from __future__ import annotations

from agent.base import BaseEngine
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class InsightEngine(BaseEngine):
    name = "InsightEngine"

    def run(self, context: RequestContext, round_number: int) -> EngineRunResult:
        timestamp = now_iso()
        return EngineRunResult(
            agent_name=self.name,
            summary=f"基于已有规划，整理 {context.domain} 的内部知识框架与关键背景。",
            key_points=[
                f"{context.domain} 的首版知识框架覆盖 {', '.join(context.subdomains)}。",
                "当前仓库尚无历史知识库，因此本轮以结构化提纲作为 Insight 起点。",
            ],
            raw_material=[
                f"目标领域：{context.domain}",
                f"关注点：{', '.join(context.focus_points)}",
                f"时间范围：{context.time_window}",
            ],
            coverage_topics=context.subdomains,
            sources=[
                SourceRecord(
                    title=f"{context.domain} 初始规划上下文",
                    url="local://intake-context",
                    publisher="KnowledgeForge",
                    retrieved_at=timestamp,
                    reliability="medium",
                    agent=self.name,
                )
            ],
            collected_at=timestamp,
            round_number=round_number,
        )
