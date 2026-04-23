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
        missing_topics = [topic for topic in context.subdomains if topic not in covered_topics]

        query_output = outputs.get("QueryEngine")
        has_authoritative_sources = bool(query_output and query_output.sources)

        reasons: list[str] = []
        if not has_authoritative_sources:
            reasons.append("缺少 QueryEngine 提供的可引用来源。")
        if missing_topics:
            reasons.append("存在未覆盖的核心子主题。")

        if reasons:
            return CompletenessResult(
                status="supplement_required",
                reasons=reasons,
                missing_topics=missing_topics,
                supplement_queries=[
                    f"{context.domain} {topic} 官方资料"
                    for topic in (missing_topics or context.subdomains)
                ],
            )

        return CompletenessResult(
            status="pass",
            reasons=["核心子主题已覆盖，且存在可引用来源。"],
            missing_topics=[],
            supplement_queries=[],
        )
