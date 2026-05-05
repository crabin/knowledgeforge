from __future__ import annotations

import json
from dataclasses import dataclass

from knowledgeforge.server.llms.openai_compatible import OpenAICompatibleChatClient


FALLBACK_ABBREVIATIONS = {
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "dl": "deep learning",
    "llm": "large language models",
    "nlp": "natural language processing",
    "rag": "retrieval augmented generation",
}


FALLBACK_DISPLAY_NAMES = {
    "machine learning": "Machine Learning",
    "artificial intelligence": "Artificial Intelligence",
    "deep learning": "Deep Learning",
    "large language models": "Large Language Models",
    "natural language processing": "Natural Language Processing",
    "retrieval augmented generation": "Retrieval Augmented Generation",
}


NORMALIZATION_SCHEMA = {
    "type": "object",
    "properties": {
        "normalized_domain": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "search_terms": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": ["normalized_domain", "aliases", "search_terms", "reasoning"],
}


NORMALIZATION_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的术语归一化助手。
任务：将用户输入的缩写、简称或模糊技术词，扩展成更适合搜索的完整术语。

强制规则：
1. 如果输入是常见技术缩写，如 ML、AI、DL、LLM、NLP、RAG，要优先输出最常见、最适合检索的完整英文术语。
2. normalized_domain 应该是最适合作为主检索词的完整名称。
3. aliases 保留原始缩写、常见别名或近义说法。
4. search_terms 提供 2-4 个适合后续搜索规划使用的关键词变体。
5. 如果原词已经足够完整，也要原样保留并输出合理别名。
6. 只返回 JSON。

输出 JSON Schema：
{json.dumps(NORMALIZATION_SCHEMA, ensure_ascii=False, indent=2)}
"""


@dataclass(slots=True)
class NormalizedQueryTerm:
    normalized_domain: str
    aliases: list[str]
    search_terms: list[str]
    reasoning: str


def normalize_query_term(
    domain: str,
    *,
    chat_client: OpenAICompatibleChatClient | None = None,
) -> NormalizedQueryTerm:
    normalized = domain.strip()
    if chat_client is not None:
        try:
            payload = chat_client.complete_json(
                system_prompt=NORMALIZATION_SYSTEM_PROMPT,
                user_prompt=json.dumps({"domain": domain}, ensure_ascii=False),
            )
            normalized_domain = str(payload.get("normalized_domain", "")).strip() or normalized
            aliases = [str(item).strip() for item in payload.get("aliases", []) if str(item).strip()]
            search_terms = [str(item).strip() for item in payload.get("search_terms", []) if str(item).strip()]
            reasoning = str(payload.get("reasoning", "")).strip() or "已完成术语归一化。"
            if normalized_domain:
                return NormalizedQueryTerm(
                    normalized_domain=normalized_domain,
                    aliases=_dedupe([domain, *aliases]),
                    search_terms=_dedupe([normalized_domain, *search_terms]),
                    reasoning=reasoning,
                )
        except Exception:
            pass

    fallback = _display_name(FALLBACK_ABBREVIATIONS.get(normalized.lower(), normalized))
    aliases = _dedupe([domain, fallback] if fallback != domain else [domain])
    search_terms = _dedupe([fallback, domain] if fallback != domain else [domain])
    return NormalizedQueryTerm(
        normalized_domain=fallback,
        aliases=aliases,
        search_terms=search_terms,
        reasoning="LLM 归一化不可用，已按本地缩写映射和原词回退。",
    )


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    ordered: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def _display_name(value: str) -> str:
    return FALLBACK_DISPLAY_NAMES.get(value.strip().lower(), value.strip())
