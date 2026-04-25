from __future__ import annotations

from agent.base import BaseEngine
from knowledgeforge.models import EnginePlan, EnginePlanItem, EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class InsightEngine(BaseEngine):
    name = "InsightEngine"

    def plan(self, context: RequestContext, round_number: int) -> EnginePlan:
        timestamp = now_iso()
        topics = context.subdomains or [context.domain]
        return EnginePlan(
            agent_name=self.name,
            plan_items=[
                EnginePlanItem(
                    plan_item_id=f"I{index}",
                    title=f"梳理 {topic} 的已有知识线索",
                    query_or_action=f"读取本地知识库、历史任务和 intake 上下文中关于 {topic} 的资料",
                    targets=["本地上下文", "历史沉淀", "领域边界", "已知空白"],
                    success_criteria=["形成可供完整性评估使用的背景线索", "保留 local:// 来源追溯"],
                    fallbacks=["没有历史知识时使用 intake 上下文生成首版知识框架"],
                    source_priority=["local markdown", "task history", "intake context"],
                )
                for index, topic in enumerate(topics[:3], start=1)
            ],
            reasoning="InsightEngine 优先确认本地已有知识、历史沉淀和用户澄清上下文，作为三路采集的内部线索。",
            status="awaiting_confirmation",
            created_at=timestamp,
        )

    def run(
        self,
        context: RequestContext,
        round_number: int,
        approved_plan: EnginePlan | None = None,
    ) -> EngineRunResult:
        timestamp = now_iso()
        execution_log = []
        if approved_plan is not None:
            execution_log.append(
                {
                    "event": "engine_plan_execution_started",
                    "timestamp": timestamp,
                    "node": "InsightEngine",
                    "details": {
                        "agent": self.name,
                        "plan_item_count": len(approved_plan.plan_items),
                    },
                }
            )
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
            execution_log=execution_log,
        )
