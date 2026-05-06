from __future__ import annotations

import json

from knowledgeforge.agent.QueryEngine.source_priority import SOURCE_PRIORITY_POLICY


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
                    "authority_queries": {"type": "array", "items": {"type": "string"}},
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
        "short_summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "coverage_topics": {"type": "array", "items": {"type": "string"}},
        "official_findings": {"type": "array", "items": {"type": "string"}},
        "tutorial_findings": {"type": "array", "items": {"type": "string"}},
        "structured_answer": {"type": "array", "items": {"type": "object"}},
        "excluded_concepts": {"type": "array", "items": {"type": "object"}},
        "source_cross_check": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["summary", "key_points", "coverage_topics", "official_findings", "tutorial_findings"],
}


SEARCH_PLAN_SYSTEM_PROMPT = f"""
你是 KnowledgeForge 的 QueryEngine 搜索规划器。
任务目标：在任何网络检索前，先生成“文章级采集候选模板”。系统只使用 Google 检索，再展开成逐条 URL 计划项。

权威来源优先级表：
{SOURCE_PRIORITY_POLICY}

强制规则：
1. google_query 必须是短搜索词：领域名 + 节点标题/证据主题；不要写“补充...关键依据”这类执行动作。
2. source_priority 按类别写清楚，系统会据此追加 site: 查询：
   - 通用概念：en.wikipedia.org、zh.wikipedia.org
   - 技术/编程：docs.python.org、developer.mozilla.org、arxiv.org、github.com
   - AI/ML 论文：arxiv.org、paperswithcode.com、huggingface.co
   - 新闻/时事：reuters.com、bbc.com、theguardian.com
   - 学术：scholar.google.com、semanticscholar.org
   - 官方文档：优先该技术/产品官网、官方文档或官方 GitHub。
3. 教程、博客、社区文章只作为补充，用于解释用法、案例和经验。
4. 每个子领域至少生成 1 个官方/权威事实问题，问题要能回答“需要确认什么事实”。
5. 每个 question 必须写清楚：
   - subdomain：该问题对应的子领域，必须来自用户提供的子领域。
   - module_id：该问题归属的知识模块，优先使用 overview、foundations、core_topics、advanced_topics、papers、projects、tools、review。
   - doc_role：目标文档角色，优先使用 domain_overview、module_doc、topic_overview、topic_article 之一。
   - google_query：面向 Google 的可执行查询语句。
   - authority_queries：基于同一意图改写出的 2-3 条 Google 补充查询，优先使用 site:权威域名、official documentation、standard、paper、project homepage、GitHub docs。
   - search_targets：这个计划项需要查询/确认的内容列表，写成可以逐条勾选的短句。
   - expected_info：需要从搜索结果中拿到哪些信息，例如定义、官方说明、版本/时间范围、关键能力、限制、案例证据。
   - source_priority：优先来源类型和类别，例如 wikipedia、official documentation、AI/ML paper、academic、technical docs。
   - success_criteria：什么结果算满足该问题。
   - fallback_queries：主查询不足时才执行的补查查询。
   - doc_type：推荐写 source、article、case、note 之一，默认优先 source / article。
6. 查询改写参考多 query 聚合搜索：一个问题至少有主查询和权威补充查询；fallback_queries 只在主查询/权威查询不足时使用。
7. 计划项数量要克制，优先覆盖最关键问题；每个计划项查询完后系统会立即标记完成或不足。
8. official_queries / tutorial_queries 保持兼容输出，应从 questions 中提取代表性查询。
9. 只返回 JSON，不要附加解释。

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
请基于抓取到的网页材料、候选概念池、验证矩阵和反思结果，输出“官方文档优先、教程补充”的结构化总结。

要求：
1. summary 用中文，先写结论，再写范围。
2. key_points 至少 3 条，优先反映官方文档结论。
3. official_findings 专门总结官方文档中的事实、接口、规范、步骤。
4. tutorial_findings 专门总结教程中的示例、经验和注意事项。
5. coverage_topics 应覆盖用户提供的子主题。
6. 如果 deep_search.search_intent 是 basic_components 或 core_concepts，必须额外输出：
   - structured_answer：按“结构组成 / 训练组成 / 核心内容”分组，每项包含 name 和 role。
   - excluded_concepts：非当前问题必需的扩展项及剔除原因。
   - source_cross_check：至少 3 个可靠来源的交叉验证摘要；不足 3 个时如实列出现有可靠来源。
   - short_summary：300 到 500 字内，适合初学者理解。
7. 不直接复制原文，要自己提炼。
8. 只返回 JSON。

输出 JSON Schema：
{json.dumps(SUMMARY_SCHEMA, ensure_ascii=False, indent=2)}
"""
