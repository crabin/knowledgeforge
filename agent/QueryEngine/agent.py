from __future__ import annotations

from agent.base import BaseEngine
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class QueryEngine(BaseEngine):
    name = "QueryEngine"

    def run(self, context: RequestContext, round_number: int) -> EngineRunResult:
        timestamp = now_iso()
        return EngineRunResult(
            agent_name=self.name,
            summary=f"为 {context.domain} 生成一组优先面向官方与权威来源的事实检索结果。",
            key_points=[
                f"优先覆盖 {', '.join(context.subdomains)} 的事实型资料。",
                "保留了最小来源元数据结构，便于后续引用检查与图谱关联。",
            ],
            raw_material=[
                f"建议检索：{query}"
                for query in context.initial_strategy
            ],
            coverage_topics=context.subdomains,
            sources=[
                SourceRecord(
                    title=f"{context.domain} 官方资料检索建议",
                    url=f"https://example.com/{round_number}/{self.name.lower()}",
                    publisher="Example Authority",
                    retrieved_at=timestamp,
                    reliability="high",
                    agent=self.name,
                )
            ],
            collected_at=timestamp,
            round_number=round_number,
        )
