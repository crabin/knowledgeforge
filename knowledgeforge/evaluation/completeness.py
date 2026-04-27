from __future__ import annotations

from knowledgeforge.models import CompletenessResult, EngineRunResult, RequestContext


class CompletenessEvaluator:
    def evaluate(
        self,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
    ) -> CompletenessResult:
        covered_topics = {
            topic
            for output in outputs.values()
            for topic in output.coverage_topics
        }
        expected_topics = context.core_topics or context.subdomains
        missing_topics = [topic for topic in expected_topics if topic not in covered_topics]
        completed_structure = self._completed_structure_nodes(outputs)
        if completed_structure["modules"] or completed_structure["topic_overviews"]:
            required_modules = {"overview", "foundations", "papers"}
            missing_modules = sorted(required_modules - completed_structure["modules"])
            missing_topic_roles = [
                topic
                for topic in expected_topics
                if topic not in completed_structure["topic_overviews"]
            ]
        else:
            missing_modules = []
            missing_topic_roles = []

        all_sources = [source for output in outputs.values() for source in output.sources]
        authoritative_sources = [
            source for source in all_sources if source.reliability in ("high", "medium")
        ]
        has_authoritative_sources = bool(authoritative_sources)

        reasons: list[str] = []
        failure_categories: list[str] = []
        if not all_sources:
            reasons.append("缺少 QueryEngine 提供的可引用来源。")
            failure_categories.append("no_authoritative_source")
        elif not has_authoritative_sources:
            reasons.append("来源存在但可信度均为 unknown 或 low，无法作为权威证据。")
            failure_categories.append("no_authoritative_source")
        if missing_topics:
            reasons.append("存在未覆盖的核心子主题。")
            failure_categories.append("missing_topics")
        if missing_modules:
            reasons.append(f"知识结构关键模块未覆盖：{', '.join(missing_modules)}。")
            failure_categories.append("structure_coverage_gap")
        if missing_topic_roles:
            reasons.append("部分核心主题尚未形成 topic overview 级证据入口。")
            failure_categories.append("topic_navigation_missing")
        insufficient_plan_items = self._insufficient_query_plan_items(outputs.get("QueryEngine"))
        if insufficient_plan_items:
            reasons.append("QueryEngine 查询计划仍存在未完成项，不能进入最终入库。")
            failure_categories.append("query_plan_incomplete")

        if reasons:
            if missing_topics:
                supplement_queries = [
                    f"{context.domain} {topic} 官方资料"
                    for topic in missing_topics
                ]
            elif missing_topic_roles:
                supplement_queries = [
                    f"{context.domain} {topic} official guide representative methods"
                    for topic in missing_topic_roles
                ]
            elif missing_modules:
                supplement_queries = [
                    f"{context.domain} {module} official overview authoritative source"
                    for module in missing_modules
                ]
            elif insufficient_plan_items:
                supplement_queries = [
                    item.get("query", item.get("question", "补充查询"))
                    for item in insufficient_plan_items[:5]
                ]
            else:
                supplement_queries = [
                    f"{context.domain} official introduction authoritative source",
                    f"{context.domain} supervised unsupervised reinforcement learning authoritative source",
                    f"{context.domain} applications official documentation",
                ]
            return CompletenessResult(
                status="supplement_required",
                reasons=reasons,
                missing_topics=missing_topics,
                supplement_queries=supplement_queries,
                failure_categories=failure_categories,
            )

        return CompletenessResult(
            status="pass",
            reasons=["核心子主题已覆盖，且存在可引用来源。"],
            missing_topics=[],
            supplement_queries=[],
            failure_categories=[],
        )

    @staticmethod
    def _insufficient_query_plan_items(output: EngineRunResult | None) -> list[dict]:
        if output is None:
            return []
        items: list[dict] = []
        for entry in output.execution_log:
            if entry.get("event") != "query_question_completed":
                continue
            details = entry.get("details", {})
            if details.get("status") == "insufficient":
                items.append(
                    {
                        "question": str(details.get("question", "")).strip(),
                        "query": str(details.get("query", details.get("question", ""))).strip(),
                    }
                )
        return items

    @staticmethod
    def _completed_structure_nodes(outputs: dict[str, EngineRunResult]) -> dict[str, set[str]]:
        modules: set[str] = set()
        topic_overviews: set[str] = set()
        for output in outputs.values():
            for entry in output.execution_log:
                details = entry.get("details", {})
                if details.get("status") not in {"completed", "saved"}:
                    continue
                module_id = str(details.get("module_id", "")).strip()
                doc_role = str(details.get("doc_role", "")).strip()
                subdomain = str(details.get("subdomain", "")).strip()
                if module_id:
                    modules.add(module_id)
                if doc_role in {"topic_overview", "topic_article"} and subdomain:
                    topic_overviews.add(subdomain)
        return {"modules": modules, "topic_overviews": topic_overviews}
