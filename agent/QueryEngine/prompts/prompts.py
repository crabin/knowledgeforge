from __future__ import annotations

import json


SEARCH_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "subdomain": {"type": "string"},
                    "module_id": {"type": "string"},
                    "doc_role": {"type": "string"},
                    "google_query": {"type": "string"},
                    "search_targets": {"type": "array", "items": {"type": "string"}},
                    "expected_info": {"type": "array", "items": {"type": "string"}},
                    "source_priority": {"type": "array", "items": {"type": "string"}},
                    "success_criteria": {"type": "array", "items": {"type": "string"}},
                    "fallback_queries": {"type": "array", "items": {"type": "string"}},
                    "doc_type": {"type": "string"},
                },
                "required": [
                    "question",
                    "subdomain",
                    "google_query",
                    "search_targets",
                    "expected_info",
                    "source_priority",
                    "success_criteria",
                    "fallback_queries",
                    "doc_type",
                ],
            },
        },
        "official_queries": {"type": "array", "items": {"type": "string"}},
        "tutorial_queries": {"type": "array", "items": {"type": "string"}},
        "official_domains": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": ["questions", "official_queries", "tutorial_queries", "official_domains", "reasoning"],
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
任务目标：在任何网络检索前，先生成“文章级采集候选模板”。系统会先按你的 questions 做轻量检索，再展开成逐条 URL 计划项。

强制规则：
1. 官方文档、标准、规范、厂商文档、项目主页、官方 GitHub 文档是最权威来源，必须优先。
2. 教程、博客、社区文章只作为补充，用于解释用法、案例和经验。
3. 每个子领域至少生成 1 个官方/权威事实问题，问题要能回答“需要确认什么事实”。
   4. 每个 question 必须写清楚：
   - subdomain：该问题对应的子领域，必须来自用户提供的子领域。
   - module_id：该问题归属的知识模块，优先使用 overview、foundations、core_topics、advanced_topics、papers、projects、tools、review。
   - doc_role：目标文档角色，优先使用 domain_overview、module_doc、topic_overview、topic_article 之一。
   - google_query：面向 Google 风格的查询语句，但不要使用只能由 Google API 执行的特殊能力。
   - search_targets：这个计划项需要查询/确认的内容列表，写成可以逐条勾选的短句。
   - expected_info：需要从搜索结果中拿到哪些信息，例如定义、官方说明、版本/时间范围、关键能力、限制、案例证据。
   - source_priority：优先来源类型，例如 official documentation、standard、vendor docs、official GitHub、tutorial。
   - success_criteria：什么结果算满足该问题。
   - fallback_queries：主查询不足时才执行的补查查询。
   - doc_type：推荐写 source、article、case、note 之一，默认优先 source / article。
5. 计划项数量要克制，优先覆盖最关键问题；每个计划项查询完后系统会立即标记完成或不足。
6. official_queries / tutorial_queries 保持兼容输出，应从 questions 中提取代表性查询。
7. 只返回 JSON，不要附加解释。

输出 JSON Schema：
{json.dumps(SEARCH_PLAN_SCHEMA, ensure_ascii=False, indent=2)}
"""


REFLECTION_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的 QueryEngine 反思器。
请根据首轮检索结果判断：当前结果还缺什么，是否需要继续补检索。

强制规则：
1. 优先检查查询计划中的每个问题是否已被满足，特别是 status=insufficient 的问题。
2. missing_aspects 必须绑定具体问题，并说明原因：没搜到、搜到但不权威、信息不完整、证据不支持问题。
3. supplementary 查询只针对 insufficient 问题生成，避免泛化重复搜索。
4. 尽量从首轮结果中提取候选官方域名，写入 candidate_official_domains。
5. 如果当前结果已经足够，也要返回空的 supplementary 查询数组。
6. 只返回 JSON。

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
