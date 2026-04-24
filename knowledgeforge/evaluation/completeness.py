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

        if reasons:
            if missing_topics:
                supplement_queries = [
                    f"{context.domain} {topic} 官方资料"
                    for topic in missing_topics
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
