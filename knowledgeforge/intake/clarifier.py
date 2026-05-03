from __future__ import annotations

import json
import re
from typing import Any

from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.models import ClarificationResult, TaskIntent
from knowledgeforge.utils.query_normalization import FALLBACK_ABBREVIATIONS, FALLBACK_DISPLAY_NAMES


CLARIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "normalized_domain": {"type": "string"},
        "intent": {"type": "string", "enum": ["knowledge_collection", "concept_explanation", "qa"]},
        "output_language": {"type": "string"},
        "search_language": {"type": "string"},
        "subdomains": {"type": "array", "items": {"type": "string"}},
        "focus_points": {"type": "array", "items": {"type": "string"}},
        "search_terms": {"type": "array", "items": {"type": "string"}},
        "needs_clarification": {"type": "boolean"},
        "clarification_questions": {"type": "array", "items": {"type": "string"}},
        "clarification_summary": {"type": "string"},
    },
    "required": [
        "normalized_domain",
        "intent",
        "output_language",
        "search_language",
        "subdomains",
        "focus_points",
        "search_terms",
        "needs_clarification",
        "clarification_questions",
        "clarification_summary",
    ],
}


CLARIFICATION_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的任务意图确认助手，只负责澄清用户意图，不执行搜索。

默认规则：
1. 默认输出语言是中文，output_language 使用 zh-CN。
2. 用户明确要求英文输出时，output_language 使用 en。
3. 技术缩写优先按最常见技术含义归一化，例如 ML=Machine Learning。
4. 明确要沉淀、整理、调研、构建知识库时，intent=knowledge_collection。
5. 用户只是问“是什么 / 解释一下 / 什么意思”时，intent=concept_explanation，并需要追问是否改为知识库采集。
6. 对明确技术缩写，不要把 ML 拆成 machine / machinery / vending machine 这类泛词。
7. 如果进入 knowledge_collection，subdomains 要贴合领域，不要默认使用“关键参与者 / 近期动态”。
8. 只返回 JSON。

输出 JSON Schema：
{json.dumps(CLARIFICATION_SCHEMA, ensure_ascii=False, indent=2)}
"""


class IntakeClarifier:
    def __init__(self, chat_client: OpenAICompatibleChatClient | None = None) -> None:
        self._chat_client = chat_client

    def clarify(self, messages: list[str]) -> ClarificationResult:
        original_input = " ".join(item.strip() for item in messages if item.strip()).strip()
        if not original_input:
            raise ValueError("`message` is required.")

        if self._chat_client is not None:
            try:
                payload = self._chat_client.complete_json(
                    system_prompt=CLARIFICATION_SYSTEM_PROMPT,
                    user_prompt=json.dumps({"messages": messages}, ensure_ascii=False),
                )
                return self._from_payload(original_input, payload)
            except Exception:
                pass

        return self._fallback(original_input)

    def _from_payload(self, original_input: str, payload: dict[str, Any]) -> ClarificationResult:
        fallback = self._fallback(original_input)
        intent = str(payload.get("intent", fallback.intent)).strip() or fallback.intent
        if intent not in {"knowledge_collection", "concept_explanation", "qa"}:
            intent = fallback.intent
        output_language = _normalize_language(str(payload.get("output_language", fallback.output_language)))
        normalized_domain = str(payload.get("normalized_domain", "")).strip() or fallback.normalized_domain
        search_terms = _dedupe(
            [normalized_domain, *[str(item).strip() for item in payload.get("search_terms", []) if str(item).strip()]]
        )
        return ClarificationResult(
            original_input=original_input,
            normalized_domain=_normalize_known_abbreviation(normalized_domain),
            intent=intent,  # type: ignore[arg-type]
            output_language=output_language,
            search_language=str(payload.get("search_language", fallback.search_language)).strip() or fallback.search_language,
            subdomains=_clean_list(payload.get("subdomains")) or fallback.subdomains,
            focus_points=_clean_list(payload.get("focus_points")) or fallback.focus_points,
            search_terms=search_terms or fallback.search_terms,
            needs_clarification=bool(payload.get("needs_clarification", fallback.needs_clarification)),
            clarification_questions=_clean_list(payload.get("clarification_questions")) or fallback.clarification_questions,
            clarification_summary=str(payload.get("clarification_summary", fallback.clarification_summary)).strip()
            or fallback.clarification_summary,
        )

    def _fallback(self, original_input: str) -> ClarificationResult:
        domain = _extract_domain(original_input)
        normalized_domain = _normalize_known_abbreviation(domain)
        output_language = "en" if _requests_english(original_input) else "zh-CN"
        intent = _infer_intent(original_input)
        needs_clarification = intent != "knowledge_collection"
        subdomains = _default_subdomains(original_input)
        focus_points = _default_focus_points(original_input)
        questions = []
        if needs_clarification:
            questions.append("你是想做概念解释，还是要启动知识库采集并保存为可追溯文档？")
        return ClarificationResult(
            original_input=original_input,
            normalized_domain=normalized_domain,
            intent=intent,
            output_language=output_language,
            search_language="en",
            subdomains=subdomains,
            focus_points=focus_points,
            search_terms=_dedupe([normalized_domain, domain]),
            needs_clarification=needs_clarification,
            clarification_questions=questions,
            clarification_summary=f"已将输入识别为 {normalized_domain}，默认语言为 {output_language}。",
        )


def _extract_domain(text: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+-]*", text)
    for word in words:
        if word.lower() in FALLBACK_ABBREVIATIONS:
            return word
    if words:
        return words[-1]
    cleaned = re.sub(r"(请|帮我|整理|调研|解释一下|解释|是什么|什么是|的|最新|论文方向)", " ", text)
    compact = " ".join(cleaned.split())
    return compact or text


def _normalize_known_abbreviation(domain: str) -> str:
    fallback = FALLBACK_ABBREVIATIONS.get(domain.strip().lower())
    if fallback:
        return FALLBACK_DISPLAY_NAMES.get(fallback, fallback)
    if domain.strip().lower() == "machine learning":
        return "Machine Learning"
    if domain.strip().lower() in FALLBACK_DISPLAY_NAMES:
        return FALLBACK_DISPLAY_NAMES[domain.strip().lower()]
    return domain.strip()


def _infer_intent(text: str) -> TaskIntent:
    if any(marker in text for marker in ("整理", "调研", "知识库", "沉淀", "保存为文档", "收集", "latest papers", "论文方向")):
        return "knowledge_collection"
    if any(marker in text for marker in ("解释", "是什么", "什么是", "什么意思")):
        return "concept_explanation"
    return "knowledge_collection"


def _requests_english(text: str) -> bool:
    lowered = text.lower()
    return "英文" in text or "英语" in text or " in english" in lowered or "english" in lowered


def _default_subdomains(text: str) -> list[str]:
    if "论文" in text or "paper" in text.lower():
        return ["最新论文方向", "代表性方法", "应用场景"]
    return ["基础概念", "核心方法", "应用场景"]


def _default_focus_points(text: str) -> list[str]:
    if "论文" in text or "paper" in text.lower():
        return ["研究方向", "代表论文", "发展趋势"]
    return ["定义与边界", "核心方法", "典型应用"]


def _normalize_language(language: str) -> str:
    lowered = language.strip().lower()
    if lowered in {"en", "english", "en-us", "en_us"}:
        return "en"
    return "zh-CN"


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen = set()
    for item in items:
        cleaned = item.strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped
