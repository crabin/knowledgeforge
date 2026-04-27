from __future__ import annotations

from knowledgeforge.models import RequestContext
from knowledgeforge.utils.query_normalization import FALLBACK_ABBREVIATIONS
from knowledgeforge.utils.knowledge_tree import (
    build_default_modules,
    build_knowledge_blueprint,
    build_navigation_targets,
    build_required_file_paths,
    normalize_core_topics,
)


DEFAULT_SUBDOMAINS = ["基础概念", "核心方法", "应用场景"]
DEFAULT_FOCUS_POINTS = ["定义与边界", "核心方法", "典型应用"]


class ContextBuilder:
    def build(self, payload: dict[str, object]) -> RequestContext:
        original_input = str(payload.get("original_input", payload.get("message", ""))).strip()
        domain = str(payload.get("domain", "")).strip()
        if not domain:
            raise ValueError("`domain` is required.")

        normalized_domain = str(payload.get("normalized_domain", "")).strip() or _fallback_normalized_domain(domain)
        subdomains = self._normalize_list(payload.get("subdomains")) or DEFAULT_SUBDOMAINS
        focus_points = self._normalize_list(payload.get("focus_points")) or DEFAULT_FOCUS_POINTS
        constraints = self._normalize_list(payload.get("constraints"))
        time_window = str(payload.get("time_window", "近 12 个月")).strip() or "近 12 个月"
        intent = str(payload.get("intent", "knowledge_collection")).strip() or "knowledge_collection"
        output_language = str(payload.get("output_language", "zh-CN")).strip() or "zh-CN"
        search_language = str(payload.get("search_language", "en")).strip() or "en"
        search_terms = self._normalize_list(payload.get("search_terms")) or [normalized_domain, domain]
        clarification_summary = str(payload.get("clarification_summary", "")).strip()
        confirmed = bool(payload.get("confirmed", False))
        knowledge_modules = build_default_modules()
        core_topics = normalize_core_topics(subdomains, domain)
        navigation_targets = build_navigation_targets(domain, core_topics)
        knowledge_blueprint = build_knowledge_blueprint(domain, core_topics)
        required_files = build_required_file_paths(domain, knowledge_blueprint)

        initial_strategy = [
            f"围绕 {normalized_domain} 的 {topic} 收集可追溯资料"
            for topic in core_topics
        ]

        return RequestContext(
            domain=domain,
            normalized_domain=normalized_domain,
            subdomains=subdomains,
            time_window=time_window,
            focus_points=focus_points,
            constraints=constraints,
            initial_strategy=initial_strategy,
            original_input=original_input or domain,
            intent=intent,  # type: ignore[arg-type]
            output_language=output_language,
            search_language=search_language,
            search_terms=self._dedupe(search_terms),
            clarification_summary=clarification_summary,
            confirmed=confirmed,
            knowledge_modules=knowledge_modules,
            core_topics=core_topics,
            navigation_targets=navigation_targets,
            knowledge_blueprint=knowledge_blueprint,
            required_files=required_files,
        )

    @staticmethod
    def _normalize_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = value
        else:
            return []
        return [str(item).strip() for item in items if str(item).strip()]

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen = set()
        for item in items:
            cleaned = item.strip()
            if not cleaned or cleaned.lower() in seen:
                continue
            seen.add(cleaned.lower())
            deduped.append(cleaned)
        return deduped


def _fallback_normalized_domain(domain: str) -> str:
    fallback = FALLBACK_ABBREVIATIONS.get(domain.strip().lower())
    if fallback == "machine learning":
        return "Machine Learning"
    if fallback:
        return fallback
    return domain
