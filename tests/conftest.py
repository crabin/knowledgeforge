from __future__ import annotations

import json

import pytest

from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient


@pytest.fixture(autouse=True)
def fake_openai_compatible_chat(monkeypatch):
    """Keep service-level workflow tests deterministic while still exercising the LLM planning path."""

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        if "任务意图确认助手" in system_prompt:
            messages = " ".join(json.loads(user_prompt).get("messages", []))
            domain = "Machine Learning" if "ML" in messages else _extract_domain(messages)
            return {
                "normalized_domain": domain,
                "intent": "concept_explanation" if "解释" in messages and "知识库" not in messages else "knowledge_collection",
                "output_language": "en" if "英文" in messages else "zh-CN",
                "search_language": "en",
                "subdomains": ["最新论文方向"] if "论文" in messages else ["基础概念", "核心方法", "应用场景"],
                "focus_points": ["研究方向"] if "论文" in messages else ["定义与边界", "核心方法", "典型应用"],
                "search_terms": [domain],
                "needs_clarification": "解释" in messages and "知识库" not in messages,
                "clarification_questions": ["你是想做概念解释，还是要启动知识库采集？"]
                if "解释" in messages and "知识库" not in messages
                else [],
                "clarification_summary": f"测试 LLM 已识别为 {domain}。",
            }
        if "术语归一化助手" in system_prompt:
            domain = json.loads(user_prompt).get("domain", "")
            normalized = "Machine Learning" if str(domain).lower() == "ml" else domain
            return {
                "normalized_domain": normalized,
                "aliases": [domain, normalized],
                "search_terms": [normalized],
                "reasoning": "测试 LLM 术语归一化。",
            }
        if "InsightEngine" in system_prompt:
            payload = json.loads(user_prompt)
            domain = payload.get("domain", "知识工程")
            subdomains = payload.get("subdomains", []) or [domain]
            return {
                "items": [
                    {
                        "title": f"梳理 {topic} 的本地上下文",
                        "action": f"读取 intake 上下文与历史任务中关于 {topic} 的线索",
                        "targets": ["本地上下文", "历史任务", "已知空白"],
                        "success_criteria": ["形成可供评估的内部线索"],
                        "source_priority": ["intake context", "task history"],
                    }
                    for topic in subdomains[:3]
                ],
                "reasoning": "测试 LLM 生成 Insight 计划。",
            }
        if "QueryEngine 搜索规划器" in system_prompt:
            payload = json.loads(user_prompt)
            domain = payload.get("domain", "Knowledge Engineering")
            subdomains = payload.get("subdomains", []) or [domain]
            questions = []
            for index, topic in enumerate(subdomains[:3], start=1):
                search_topic = _topic_for_search(topic)
                questions.append(
                    {
                        "question": f"{domain} 在“{topic}”方面有哪些官方事实与权威说明？",
                        "google_query": f"{domain} {search_topic} official documentation standard",
                        "search_targets": ["官方定义", "权威来源"],
                        "expected_info": ["官方定义", "权威说明"],
                        "source_priority": ["official documentation", "official GitHub"],
                        "success_criteria": ["命中官方或权威来源"],
                        "fallback_queries": [f"{domain} {search_topic} official guide"],
                    }
                )
            return {
                "questions": questions,
                "official_queries": [question["google_query"] for question in questions],
                "tutorial_queries": [],
                "official_domains": [],
                "reasoning": "测试 LLM 生成 Query 计划。",
            }
        if "QueryEngine 反思器" in system_prompt:
            return {
                "missing_aspects": [],
                "supplementary_official_queries": [],
                "supplementary_tutorial_queries": [],
                "candidate_official_domains": [],
                "reasoning": "测试 LLM 判断当前结果足够。",
            }
        if "QueryEngine 总结器" in system_prompt:
            return {
                "summary": "测试 LLM 已整理官方优先的查询结果。",
                "key_points": ["官方来源已覆盖核心事实", "结果保留来源追溯", "可进入后续治理"],
                "coverage_topics": ["基础概念", "核心方法", "应用场景"],
                "official_findings": ["官方资料提供核心事实。"],
                "tutorial_findings": [],
            }
        if "MediaEngine" in system_prompt and "搜索计划" in system_prompt:
            payload = json.loads(user_prompt)
            domain = payload.get("domain", "Knowledge Engineering")
            topic = (payload.get("subdomains") or [domain])[0]
            search_topic = _topic_for_search(topic)
            return {
                "social_queries": [f"{domain} {search_topic} social discussion"],
                "community_queries": [f"{domain} {search_topic} community discussion"],
                "blog_queries": [f"{domain} {search_topic} engineering blog"],
                "reasoning": "测试 LLM 生成 Media 计划。",
                "is_technical": True,
            }
        if "MediaEngine" in system_prompt and "判断当前趋势观察还缺什么" in system_prompt:
            return {
                "missing_aspects": [],
                "supplementary_social_queries": [],
                "supplementary_community_queries": [],
                "supplementary_blog_queries": [],
                "reasoning": "测试 LLM 判断观点材料足够。",
            }
        if "MediaEngine" in system_prompt and "结构化总结" in system_prompt:
            return {
                "summary": "测试 LLM 已整理社区观点。",
                "current_sentiment": "整体稳定。",
                "mainstream_views": ["社区讨论具备可参考价值。"],
                "debates": [],
                "adoption_signals": [],
                "future_directions": [],
                "coverage_topics": ["基础概念", "核心方法", "应用场景"],
            }
        return {}

    monkeypatch.setattr(OpenAICompatibleChatClient, "complete_json", complete_json)


def _extract_domain(message: str) -> str:
    if "知识工程" in message:
        return "知识工程"
    if "deep learning" in message.lower():
        return "deep learning"
    return "知识工程"


def _topic_for_search(topic: str) -> str:
    mapping = {
        "基础概念": "basic concepts",
        "核心方法": "core methods",
        "应用场景": "applications",
        "工作流编排": "workflow orchestration",
        "知识沉淀": "knowledge base construction",
        "最新论文方向": "latest papers",
    }
    return mapping.get(str(topic), str(topic))
