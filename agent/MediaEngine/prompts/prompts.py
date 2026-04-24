from __future__ import annotations


MEDIA_SEARCH_PLAN_SYSTEM_PROMPT = """
任务目标：为“社区观点 / 社交讨论 / 技术博客趋势观察”生成结构化搜索计划。

规则：
1. MediaEngine 关注的是“当前怎么看、争议点是什么、采用信号在哪里、未来怎么走”，不是官方事实检索。
2. 技术领域默认优先中外技术社区混合来源：X、Reddit、Hacker News、GitHub Discussions、技术博客，同时补充 V2EX、掘金、知乎。
3. 官方文档、标准、厂商资料不是本节点的主来源，不要把结果做成 QueryEngine 风格。
4. 查询必须分成 social_queries、community_queries、blog_queries 三类。
5. 对技术领域要显式加入平台或站点线索，如 site:news.ycombinator.com、site:reddit.com、site:github.com、site:v2ex.com 等。

输出 JSON：
{
  "social_queries": ["..."],
  "community_queries": ["..."],
  "blog_queries": ["..."],
  "reasoning": "...",
  "is_technical": true
}
"""


MEDIA_REFLECTION_SYSTEM_PROMPT = """
请根据首轮社交媒体、技术社区、博客材料，判断当前趋势观察还缺什么。

要求：
1. 重点检查是否缺：主流看法、争议点、采用信号、未来走向。
2. 如果技术社区讨论不足，优先补 community 查询。
3. 如果案例和趋势长文不足，补 blog 查询。
4. 如果热度和即时讨论不足，补 social 查询。
5. 如果当前已足够，也要返回空数组。

输出 JSON：
{
  "missing_aspects": ["..."],
  "supplementary_social_queries": ["..."],
  "supplementary_community_queries": ["..."],
  "supplementary_blog_queries": ["..."],
  "reasoning": "..."
}
"""


MEDIA_SUMMARY_SYSTEM_PROMPT = """
请基于抓取到的社交媒体、技术社区、博客材料以及反思结果，输出“当前观点与未来走向”的结构化总结。

要求：
1. summary 必须概括当前主流看法，而不是复述事实文档。
2. current_sentiment 描述整体情绪和判断基调。
3. mainstream_views 总结主流共识。
4. debates 总结争议点、分歧点或质疑点。
5. adoption_signals 总结采用信号、案例苗头或工程落地趋势。
6. future_directions 总结未来 6-12 个月可能继续被讨论的方向。
7. 保持中文输出，避免把社区观点包装成“权威结论”。

输出 JSON：
{
  "summary": "...",
  "current_sentiment": "...",
  "mainstream_views": ["..."],
  "debates": ["..."],
  "adoption_signals": ["..."],
  "future_directions": ["..."],
  "coverage_topics": ["..."]
}
"""
