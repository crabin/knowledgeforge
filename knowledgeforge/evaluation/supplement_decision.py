from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.models import CompletenessResult, EnginePlan, EnginePlanItem, EngineRunResult, RequestContext
from knowledgeforge.utils.paths import sanitize_path_segment
from knowledgeforge.utils.time import now_iso


SUPPLEMENT_DECISION_SYSTEM_PROMPT = """
你是 KnowledgeForge 的补充检索决策器。
任务：读取当前领域实时保存的知识 index / 查询计划 / 文章摘要，并结合完整性评估结果，判断知识库还缺什么，再生成只分发给 QueryEngine 的补检索计划。

约束：
1. 只规划 QueryEngine 的职责：外部事实、官方来源、标准、权威文档、可引用证据。
2. 不规划 MediaEngine 社区观点，也不规划 InsightEngine 本地梳理。
3. 每个缺陷必须说明为什么缺、补什么、优先级和可验证标准。
4. 优先补充 source_quality_failed、no_authoritative_source、query_plan_incomplete、missing_topics 对应的问题。
5. 只返回 JSON，不要 Markdown。

输出 JSON：
{
  "coverage_summary": "...",
  "defects": [
    {
      "topic": "...",
      "issue": "...",
      "priority": "high|medium|low",
      "query": "...",
      "expected_info": ["..."],
      "source_priority": ["official documentation", "standard", "vendor docs"],
      "fallback_queries": ["..."],
      "success_criteria": ["..."]
    }
  ],
  "reasoning": "..."
}
"""


@dataclass(slots=True)
class SupplementDefect:
    topic: str
    issue: str
    priority: str
    query: str
    expected_info: list[str]
    source_priority: list[str]
    fallback_queries: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SupplementDecision:
    defects: list[SupplementDefect]
    reasoning: str
    coverage_summary: str
    reviewed_documents: list[dict[str, str]]
    index_paths: list[str]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "defects": [asdict(defect) for defect in self.defects],
            "reasoning": self.reasoning,
            "coverage_summary": self.coverage_summary,
            "reviewed_documents": self.reviewed_documents,
            "index_paths": self.index_paths,
            "source": self.source,
        }


class SupplementDecisionPlanner:
    def __init__(
        self,
        *,
        save_root: Path,
        chat_client: OpenAICompatibleChatClient | None = None,
        max_index_chars: int = 12000,
    ) -> None:
        self._save_root = save_root
        self._chat_client = chat_client
        self._max_index_chars = max_index_chars

    def plan(
        self,
        *,
        context: RequestContext,
        completeness: CompletenessResult,
        outputs: dict[str, EngineRunResult],
        round_number: int,
    ) -> EnginePlan:
        decision = self.decide(
            context=context,
            completeness=completeness,
            outputs=outputs,
            round_number=round_number,
        )
        plan = self.to_query_engine_plan(decision, round_number=round_number)
        completeness.supplement_decision = decision.to_dict()
        if plan.plan_items:
            completeness.supplement_queries = [item.query_or_action for item in plan.plan_items]
        return plan

    def decide(
        self,
        *,
        context: RequestContext,
        completeness: CompletenessResult,
        outputs: dict[str, EngineRunResult],
        round_number: int,
    ) -> SupplementDecision:
        index_payload = self._read_index_payload(context)
        if self._chat_client is not None:
            try:
                payload = self._chat_client.complete_json(
                    system_prompt=SUPPLEMENT_DECISION_SYSTEM_PROMPT,
                    user_prompt=json.dumps(
                        {
                            "domain": context.domain,
                            "subdomains": context.subdomains,
                            "time_window": context.time_window,
                            "focus_points": context.focus_points,
                            "round_number": round_number,
                            "completeness": completeness.to_dict(),
                            "agent_summaries": {
                                name: {
                                    "summary": output.summary,
                                    "coverage_topics": output.coverage_topics,
                                    "source_count": len(output.sources),
                                    "source_reliability": [source.reliability for source in output.sources],
                                }
                                for name, output in outputs.items()
                            },
                            "knowledge_index": {
                                "paths": index_payload["paths"],
                                "readme_excerpt": index_payload["readme_excerpt"],
                            },
                            "knowledge_overview": {
                                "reviewed_documents": index_payload["documents"],
                                "coverage_outline": index_payload["coverage_outline"],
                            },
                        },
                        ensure_ascii=False,
                    ),
                )
                decision = self._parse_llm_decision(payload, index_payload)
                if decision.defects:
                    return decision
            except Exception:
                pass
        return self._fallback_decision(context, completeness, outputs, index_payload)

    def to_query_engine_plan(self, decision: SupplementDecision, *, round_number: int) -> EnginePlan:
        timestamp = now_iso()
        items = [
            EnginePlanItem(
                plan_item_id=f"SQ{round_number}-{index}",
                title=f"补充缺陷：{defect.topic}",
                query_or_action=defect.query,
                targets=defect.expected_info,
                success_criteria=defect.success_criteria or ["补齐可引用权威证据"],
                fallbacks=defect.fallback_queries,
                source_priority=defect.source_priority or ["official documentation", "standard", "vendor docs"],
                status="approved",
            )
            for index, defect in enumerate(decision.defects[:6], start=1)
            if defect.query.strip()
        ]
        return EnginePlan(
            agent_name="QueryEngine",
            plan_items=items,
            reasoning=decision.reasoning,
            status="approved",
            created_at=timestamp,
            approved_at=timestamp,
        )

    def _read_index_payload(self, context: RequestContext) -> dict[str, Any]:
        domain_dir = self._save_root / sanitize_path_segment(context.domain, "domain")
        readme_path = domain_dir / "README.md"
        candidates = [readme_path]
        if domain_dir.exists():
            candidates.extend(sorted(path for path in domain_dir.glob("**/*.md") if path.name != "README.md"))
        contents: list[dict[str, str]] = []
        coverage_outline: list[str] = []
        remaining = self._max_index_chars
        for path in candidates:
            if not path.exists() or not path.is_file() or remaining <= 0:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            if path.name == "README.md":
                snippet = text[: min(len(text), remaining, 2400)]
                remaining -= len(snippet)
                coverage_outline.append(f"README: {self._collapse_whitespace(snippet[:400])}")
                contents.append(
                    {
                        "path": path.as_posix(),
                        "title": context.domain,
                        "doc_type": "index",
                        "overview": self._collapse_whitespace(snippet[:900]),
                    }
                )
                continue
            doc = self._build_document_overview(path, text, remaining)
            if doc is None:
                continue
            remaining -= len(doc["overview"])
            contents.append(doc)
            coverage_outline.append(
                f"{doc['title']} ({doc['subdomain']}): {self._collapse_whitespace(doc['overview'][:160])}"
            )
        return {
            "paths": [item["path"] for item in contents],
            "documents": contents,
            "coverage_outline": coverage_outline[:12],
            "readme_excerpt": contents[0]["overview"] if contents and contents[0]["path"].endswith("README.md") else "",
        }

    @staticmethod
    def _parse_llm_decision(payload: dict[str, Any], index_payload: dict[str, Any]) -> SupplementDecision:
        defects: list[SupplementDefect] = []
        for item in payload.get("defects", []):
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            query = str(item.get("query", "")).strip()
            if not topic or not query:
                continue
            defects.append(
                SupplementDefect(
                    topic=topic,
                    issue=str(item.get("issue", "")).strip() or "缺少可引用权威证据。",
                    priority=str(item.get("priority", "medium")).strip() or "medium",
                    query=query,
                    expected_info=[
                        str(value).strip() for value in item.get("expected_info", []) if str(value).strip()
                    ],
                    source_priority=[
                        str(value).strip() for value in item.get("source_priority", []) if str(value).strip()
                    ],
                    fallback_queries=[
                        str(value).strip() for value in item.get("fallback_queries", []) if str(value).strip()
                    ],
                    success_criteria=[
                        str(value).strip() for value in item.get("success_criteria", []) if str(value).strip()
                    ],
                )
            )
        return SupplementDecision(
            defects=defects,
            reasoning=str(payload.get("reasoning", "")).strip() or "LLM 基于实时知识 index 生成补充决策。",
            coverage_summary=str(payload.get("coverage_summary", "")).strip()
            or "LLM 已审阅现有知识文档概述，并据此判断缺口。",
            reviewed_documents=index_payload.get("documents", [])[:10],
            index_paths=index_payload.get("paths", []),
            source="llm_saved_document_review",
        )

    @staticmethod
    def _fallback_decision(
        context: RequestContext,
        completeness: CompletenessResult,
        outputs: dict[str, EngineRunResult],
        index_payload: dict[str, Any],
    ) -> SupplementDecision:
        defects: list[SupplementDefect] = []
        for topic in completeness.missing_topics:
            defects.append(
                SupplementDefect(
                    topic=topic,
                    issue="核心子主题尚未覆盖。",
                    priority="high",
                    query=f"{context.domain} {topic} official documentation authoritative source",
                    expected_info=["官方定义", "权威说明", "可引用来源"],
                    source_priority=["official documentation", "standard", "vendor docs"],
                    fallback_queries=[f"{context.domain} {topic} standard guide"],
                    success_criteria=["命中相关官方或权威来源"],
                )
            )
        if not defects:
            for query in completeness.supplement_queries:
                defects.append(
                    SupplementDefect(
                        topic=context.domain,
                        issue="完整性评估发现现有证据不足。",
                        priority="high",
                        query=query,
                        expected_info=["权威事实", "来源出处", "适用边界"],
                        source_priority=["official documentation", "standard", "vendor docs"],
                        fallback_queries=[],
                        success_criteria=["补齐中高可信来源"],
                    )
                )
        if not defects:
            query_sources = len(outputs.get("QueryEngine").sources) if outputs.get("QueryEngine") else 0
            defects.append(
                SupplementDefect(
                    topic=context.domain,
                    issue=f"QueryEngine 当前可用来源数量不足：{query_sources}。",
                    priority="medium",
                    query=f"{context.domain} official authoritative overview",
                    expected_info=["官方概览", "关键事实", "引用入口"],
                    source_priority=["official documentation", "standard", "vendor docs"],
                    fallback_queries=[f"{context.domain} reference documentation"],
                    success_criteria=["至少命中一个中高可信来源"],
                )
            )
        return SupplementDecision(
            defects=defects[:6],
            reasoning="LLM 决策不可用，已根据完整性评估和已保存文档概述生成规则补充决策。",
            coverage_summary="规则模式已检查 README、历史文章摘要与后续动作，发现仍存在未覆盖主题或权威来源缺口。",
            reviewed_documents=index_payload.get("documents", [])[:10],
            index_paths=index_payload.get("paths", []),
            source="fallback_saved_document_review",
        )

    def _build_document_overview(self, path: Path, text: str, remaining: int) -> dict[str, str] | None:
        if remaining <= 0:
            return None
        front_matter, body = self._split_front_matter(text)
        summary = self._extract_section(body, "摘要")
        conclusions = self._extract_section(body, "关键结论")
        followups = self._extract_section(body, "后续动作")
        background = self._extract_section(body, "背景与上下文")
        overview_parts = [
            summary,
            conclusions,
            followups,
            background,
            self._collapse_whitespace(body[:320]),
        ]
        overview = "\n".join(part for part in overview_parts if part)
        if not overview:
            return None
        title = front_matter.get("title") or self._extract_heading(body) or path.stem
        subdomain = front_matter.get("subdomain") or path.parent.name
        doc_type = front_matter.get("doc_type") or "article"
        source_type = front_matter.get("source_type") or "mixed"
        return {
            "path": path.as_posix(),
            "title": title,
            "subdomain": subdomain,
            "doc_type": doc_type,
            "source_type": source_type,
            "overview": overview[: min(remaining, 1200)],
        }

    @staticmethod
    def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
        if not text.startswith("---"):
            return {}, text
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
        if not match:
            return {}, text
        raw_front_matter, body = match.groups()
        fields: dict[str, str] = {}
        for line in raw_front_matter.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"').strip("'")
        return fields, body

    @staticmethod
    def _extract_heading(body: str) -> str:
        match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_section(body: str, title: str) -> str:
        pattern = rf"^##\s+{re.escape(title)}\s*$([\s\S]*?)(?=^##\s+|\Z)"
        match = re.search(pattern, body, re.MULTILINE)
        if not match:
            return ""
        return SupplementDecisionPlanner._collapse_whitespace(match.group(1).strip())[:500]

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
