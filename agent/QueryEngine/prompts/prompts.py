from __future__ import annotations

import json


SEARCH_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "official_queries": {"type": "array", "items": {"type": "string"}},
        "tutorial_queries": {"type": "array", "items": {"type": "string"}},
        "official_domains": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": ["official_queries", "tutorial_queries", "official_domains", "reasoning"],
}


REFLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "missing_aspects": {"type": "array", "items": {"type": "string"}},
        "supplementary_official_queries": {"type": "array", "items": {"type": "string"}},
        "supplementary_tutorial_queries": {"type": "array", "items": {"type": "string"}},
        "candidate_official_domains": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": [
        "missing_aspects",
        "supplementary_official_queries",
        "supplementary_tutorial_queries",
        "candidate_official_domains",
        "reasoning",
    ],
}


SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "coverage_topics": {"type": "array", "items": {"type": "string"}},
        "official_findings": {"type": "array", "items": {"type": "string"}},
        "tutorial_findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "key_points", "coverage_topics", "official_findings", "tutorial_findings"],
}


SEARCH_PLAN_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的 QueryEngine 搜索规划器。
任务目标：为“知识/技术主题检索”生成官方文档优先、教程补充的搜索计划。

强制规则：
1. 官方文档、标准、规范、厂商文档、项目主页、官方 GitHub 文档是最权威来源，必须优先。
2. 教程、博客、社区文章只作为补充，用于解释用法、案例和经验。
3. 查询输出需要兼顾“概念定义、核心能力、安装/使用、最佳实践、版本变化”等主题。
4. 只返回 JSON，不要附加解释。

输出 JSON Schema：
{json.dumps(SEARCH_PLAN_SCHEMA, ensure_ascii=False, indent=2)}
"""


REFLECTION_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的 QueryEngine 反思器。
请根据首轮检索结果判断：当前结果还缺什么，是否需要继续补检索。

强制规则：
1. 优先检查是否缺官方文档、规范说明、核心主题覆盖。
2. 如果官方资料已足够，但缺少落地示例或最佳实践，再补 tutorial 查询。
3. 尽量从首轮结果中提取候选官方域名，写入 candidate_official_domains。
4. 如果当前结果已经足够，也要返回空的 supplementary 查询数组。
4. 只返回 JSON。

输出 JSON Schema：
{json.dumps(REFLECTION_SCHEMA, ensure_ascii=False, indent=2)}
"""


SUMMARY_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的 QueryEngine 总结器。
请基于抓取到的网页材料和反思结果，输出“官方文档优先、教程补充”的结构化总结。

要求：
1. summary 用中文，先写结论，再写范围。
2. key_points 至少 3 条，优先反映官方文档结论。
3. official_findings 专门总结官方文档中的事实、接口、规范、步骤。
4. tutorial_findings 专门总结教程中的示例、经验和注意事项。
5. coverage_topics 应覆盖用户提供的子主题。
6. 只返回 JSON。

输出 JSON Schema：
{json.dumps(SUMMARY_SCHEMA, ensure_ascii=False, indent=2)}
"""
