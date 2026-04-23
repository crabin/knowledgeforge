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


SUMMARY_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的 QueryEngine 总结器。
请基于抓取到的网页材料，输出“官方文档优先、教程补充”的结构化总结。

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
