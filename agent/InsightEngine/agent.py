from __future__ import annotations

import json
from pathlib import Path

from agent.base import BaseEngine
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.models import EnginePlan, EnginePlanItem, EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.knowledge_tree import plan_path_for_role
from knowledgeforge.utils.time import now_iso


INSIGHT_PLAN_SYSTEM_PROMPT = """
你是 KnowledgeForge 的 InsightEngine 规划器。
任务目标：在执行本地知识/历史上下文梳理前，生成结构化执行计划。

要求：
1. 只规划 InsightEngine 的职责：本地知识库、历史任务、intake 上下文、领域边界、已知空白。
2. 不要规划外部事实检索，也不要规划社交媒体/社区抓取。
3. 每个子领域至少生成一个 plan item。
4. 只返回 JSON。

输出 JSON：
{
  "items": [
    {
      "title": "...",
      "action": "...",
      "targets": ["..."],
      "success_criteria": ["..."],
      "source_priority": ["..."]
    }
  ],
  "reasoning": "..."
}
"""


class InsightEngine(BaseEngine):
    name = "InsightEngine"

    def __init__(self, chat_client: OpenAICompatibleChatClient | None = None) -> None:
        self._chat_client = chat_client

    def plan(self, context: RequestContext, round_number: int) -> EnginePlan:
        if self._chat_client is None:
            raise RuntimeError("InsightEngine plan generation requires an LLM chat client.")
        timestamp = now_iso()
        payload = self._chat_client.complete_json(
            system_prompt=INSIGHT_PLAN_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "domain": context.domain,
                    "subdomains": context.subdomains,
                    "time_window": context.time_window,
                    "focus_points": context.focus_points,
                    "constraints": context.constraints,
                    "clarification_summary": context.clarification_summary,
                },
                ensure_ascii=False,
            ),
        )
        items = [
            item
            for item in payload.get("items", [])
            if isinstance(item, dict) and str(item.get("title", "")).strip() and str(item.get("action", "")).strip()
        ]
        if not items:
            raise RuntimeError("InsightEngine LLM did not return any valid plan items.")
        bootstrap_items = [
            EnginePlanItem(
                plan_item_id="I0",
                title="维护领域总览 README",
                query_or_action="整理领域定义、核心问题、重要性与学习路径",
                targets=["README.md", "领域总览", "学习路径"],
                success_criteria=["形成领域总览骨架"],
                source_priority=["intake context", "local knowledge"],
                metadata={
                    "module_id": "overview",
                    "module_label": "Overview",
                    "subdomain": "领域总览",
                    "doc_role": "domain_overview",
                    "planned_path": plan_path_for_role(
                        save_root=Path("save"),
                        domain=context.domain,
                        module_id="overview",
                        subdomain="",
                        doc_role="domain_overview",
                        title=f"{context.domain} Overview",
                        suffix="insight",
                    ),
                    "article_title": f"{context.domain} Overview",
                    "source_kind": "insight",
                },
            ),
            EnginePlanItem(
                plan_item_id="I00",
                title="维护领域导航 index",
                query_or_action="整理模块导航、学习顺序和进度占位",
                targets=["index.md", "模块导航", "学习顺序"],
                success_criteria=["形成领域导航骨架"],
                source_priority=["intake context", "local knowledge"],
                metadata={
                    "module_id": "overview",
                    "module_label": "Overview",
                    "subdomain": "领域导航",
                    "doc_role": "domain_index",
                    "planned_path": plan_path_for_role(
                        save_root=Path("save"),
                        domain=context.domain,
                        module_id="overview",
                        subdomain="",
                        doc_role="domain_index",
                        title=f"{context.domain} Index",
                        suffix="insight",
                    ),
                    "article_title": f"{context.domain} Index",
                    "source_kind": "insight",
                },
            ),
        ]
        return EnginePlan(
            agent_name=self.name,
            plan_items=bootstrap_items + [
                EnginePlanItem(
                    plan_item_id=f"I{index}",
                    title=str(item.get("title", "")).strip(),
                    query_or_action=str(item.get("action", "")).strip(),
                    targets=[str(value).strip() for value in item.get("targets", []) if str(value).strip()],
                    success_criteria=[
                        str(value).strip() for value in item.get("success_criteria", []) if str(value).strip()
                    ],
                    source_priority=[
                        str(value).strip() for value in item.get("source_priority", []) if str(value).strip()
                    ],
                    metadata={
                        "module_id": "overview",
                        "module_label": "Overview",
                        "subdomain": context.core_topics[min(index - 1, len(context.core_topics) - 1)] if context.core_topics else "领域概览",
                        "doc_role": "module_doc",
                        "planned_path": plan_path_for_role(
                            save_root=Path("save"),
                            domain=context.domain,
                            module_id="overview",
                            subdomain="",
                            doc_role="module_doc",
                            title=str(item.get("title", "")).strip() or f"{context.domain} insight",
                            suffix="insight",
                        ),
                        "article_title": str(item.get("title", "")).strip(),
                        "source_kind": "insight",
                    },
                )
                for index, item in enumerate(items[:5], start=1)
            ],
            reasoning=str(payload.get("reasoning", "")).strip() or "由 LLM 生成 InsightEngine 本地上下文计划。",
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
