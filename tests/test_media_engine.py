from __future__ import annotations

from agent.MediaEngine.agent import MediaEngine
from agent.MediaEngine.state.state import MediaCrawledDocument, MediaSearchHit
from agent.MediaEngine.utils.ranking import is_technical_context, score_media_url
from knowledgeforge.models import RequestContext


class FakeMediaChatClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.calls == 1:
            return {
                "normalized_domain": "machine learning",
                "aliases": ["ML", "machine learning"],
                "search_terms": ["machine learning", "ML"],
                "reasoning": "ML 在技术语境下应扩展为 machine learning。",
            }
        if self.calls == 2:
            return {
                "social_queries": [
                    "LangGraph site:x.com OR site:twitter.com opinion trend",
                    "LangGraph site:reddit.com discussion adoption",
                ],
                "community_queries": [
                    "LangGraph site:news.ycombinator.com discussion",
                    "LangGraph site:github.com discussions OR site:v2ex.com",
                ],
                "blog_queries": [
                    "LangGraph engineering blog future trend",
                    "LangGraph site:juejin.cn OR site:zhihu.com blog analysis",
                ],
                "reasoning": "优先抓取技术社区和博客，再用社交媒体补充观点热度。",
                "is_technical": True,
            }
        if self.calls == 3:
            return {
                "missing_aspects": ["缺少博客中的采用信号"],
                "supplementary_social_queries": [],
                "supplementary_community_queries": [],
                "supplementary_blog_queries": ["LangGraph production engineering blog adoption"],
                "reasoning": "首轮观点足够，但还缺更明确的工程采用信号。",
            }
        return {
            "summary": "LangGraph 当前在技术社区中的主流看法偏积极，但讨论重点已经转向复杂工作流的可维护性与落地边界。",
            "current_sentiment": "整体偏积极，但对复杂度控制保持谨慎。",
            "mainstream_views": ["社区认可其在多步骤编排上的表达力。"],
            "debates": ["是否会引入额外抽象成本仍有分歧。"],
            "adoption_signals": ["工程博客开始记录真实接入经验。"],
            "future_directions": ["后续讨论将更聚焦生产化治理与最佳实践沉淀。"],
            "coverage_topics": ["工作流编排", "状态持久化"],
        }


class FakeMediaNormalizationChatClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.calls == 1:
            return {
                "normalized_domain": "machine learning",
                "aliases": ["ML", "machine learning"],
                "search_terms": ["machine learning", "ML"],
                "reasoning": "ML 在技术语境下应扩展为 machine learning。",
            }
        if self.calls == 2:
            return {
                "social_queries": ["machine learning social media discussion trend"],
                "community_queries": ["machine learning community discussion outlook"],
                "blog_queries": ["machine learning blog analysis future trend"],
                "reasoning": "先做术语补全，再生成观点查询。",
                "is_technical": True,
            }
        if self.calls == 3:
            return {
                "missing_aspects": [],
                "supplementary_social_queries": [],
                "supplementary_community_queries": [],
                "supplementary_blog_queries": [],
                "reasoning": "当前结果已足够。",
            }
        return {
            "summary": "已基于完整术语完成趋势整理。",
            "current_sentiment": "整体讨论稳定。",
            "mainstream_views": [],
            "debates": [],
            "adoption_signals": [],
            "future_directions": [],
            "coverage_topics": ["基础概览"],
        }


class FakeMediaPlanFirstChatClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.calls == 1:
            return {
                "social_queries": ["Machine Learning social media discussion trend"],
                "community_queries": ["Machine Learning community discussion outlook"],
                "blog_queries": ["Machine Learning blog analysis future trend"],
                "reasoning": "使用已确认领域生成观点查询。",
                "is_technical": True,
            }
        if self.calls == 2:
            return {
                "missing_aspects": [],
                "supplementary_social_queries": [],
                "supplementary_community_queries": [],
                "supplementary_blog_queries": [],
                "reasoning": "当前结果已足够。",
            }
        return {
            "summary": "已基于确认术语完成趋势整理。",
            "current_sentiment": "整体讨论稳定。",
            "mainstream_views": [],
            "debates": [],
            "adoption_signals": [],
            "future_directions": [],
            "coverage_topics": ["基础概念"],
        }


class FakeMediaPlanningOnlyChatClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        self.calls.append(system_prompt)
        if "术语归一化助手" in system_prompt:
            return {
                "normalized_domain": "machine learning",
                "aliases": ["ML", "machine learning"],
                "search_terms": ["machine learning", "ML"],
                "reasoning": "规划阶段完成术语归一化。",
            }
        return {
            "social_queries": ["machine learning social discussion"],
            "community_queries": ["machine learning community discussion"],
            "blog_queries": ["machine learning engineering blog"],
            "reasoning": "规划阶段生成 Media 查询。",
            "is_technical": True,
        }


class FailingExecutionChatClient:
    def complete_json(self, *, system_prompt: str, user_prompt: str):
        raise AssertionError("MediaEngine.plan() must not use the execution chat client")


class FakeMediaCrawler:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def search(self, *, query: str, platform_type: str, is_technical: bool, max_results: int = 5):
        self.queries.append((platform_type, query))
        title_map = {
            "social": ("LangGraph on X", "https://x.com/example/status/1"),
            "community": ("LangGraph HN Thread", "https://news.ycombinator.com/item?id=1"),
            "blog": ("LangGraph Engineering Blog", "https://example.dev/blog/langgraph"),
        }
        title, url = title_map[platform_type]
        return [
            MediaSearchHit(
                title=title,
                url=url,
                snippet=f"{platform_type} perspective about adoption and tradeoffs",
                platform_type=platform_type,
                score=9.0 if platform_type == "community" else 7.0,
            )
        ]

    def fetch_documents(self, hits, *, max_documents: int = 8):
        return [
            MediaCrawledDocument(
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                content=f"{hit.title} content covering current views, debates, and adoption signals.",
                platform_type=hit.platform_type,
                publisher="publisher.test",
                score=hit.score,
            )
            for hit in hits
        ]


class EmptyMediaCrawler:
    def search(self, *, query: str, platform_type: str, is_technical: bool, max_results: int = 5):
        return []

    def fetch_documents(self, hits, *, max_documents: int = 8):
        return []


def test_media_engine_returns_trend_oriented_summary_for_technical_domain() -> None:
    crawler = FakeMediaCrawler()
    engine = MediaEngine(
        chat_client=FakeMediaChatClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="LangGraph",
        subdomains=["工作流编排", "状态持久化"],
        time_window="近 12 个月",
        focus_points=["社区观点", "未来走向"],
        constraints=[],
        initial_strategy=["LangGraph community trend"],
    )

    result = engine.run(context, round_number=1)

    assert "主流看法" in result.key_points[0]
    assert "落地边界" in result.summary
    assert {source.source_type for source in result.sources} == {"social", "community", "blog"}
    assert any("术语归一化：" in item for item in result.raw_material)
    assert any(item == "社交媒体：" for item in result.raw_material)
    assert any(item == "技术社区：" for item in result.raw_material)
    assert any(item == "博客/长文：" for item in result.raw_material)
    assert any("反思结论：" in item for item in result.raw_material)
    assert any("检索轨迹：" in item for item in result.raw_material)
    assert any(query == "LangGraph production engineering blog adoption" for _, query in crawler.queries)


def test_media_engine_run_without_llm_plan_fails_early() -> None:
    engine = MediaEngine(
        chat_client=None,
        crawler=EmptyMediaCrawler(),
    )
    context = RequestContext(
        domain="深度学习",
        subdomains=["模型训练"],
        time_window="近 12 个月",
        focus_points=["社区观点"],
        constraints=[],
        initial_strategy=["deep learning community trend"],
    )

    try:
        engine.run(context, round_number=1)
    except RuntimeError as exc:
        assert "requires an LLM chat client" in str(exc)
    else:
        raise AssertionError("MediaEngine must not fallback to a rule plan when LLM is missing")


def test_media_engine_plan_uses_planning_chat_client() -> None:
    planning_client = FakeMediaPlanningOnlyChatClient()
    engine = MediaEngine(
        chat_client=FailingExecutionChatClient(),
        planning_chat_client=planning_client,
        crawler=EmptyMediaCrawler(),
    )
    context = RequestContext(
        domain="ML",
        subdomains=["基础概览"],
        time_window="近 12 个月",
        focus_points=["社区观点"],
        constraints=[],
        initial_strategy=["ML community trend"],
    )

    plan = engine.plan(context, round_number=1)

    assert plan.agent_name == "MediaEngine"
    assert len(plan.plan_items) == 3
    assert len(planning_client.calls) == 2


def test_media_engine_normalizes_abbreviation_for_search() -> None:
    crawler = FakeMediaCrawler()
    engine = MediaEngine(
        chat_client=FakeMediaNormalizationChatClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="ML",
        subdomains=["基础概览"],
        time_window="近 12 个月",
        focus_points=["社区观点"],
        constraints=[],
        initial_strategy=["ML community trend"],
    )

    engine.run(context, round_number=1)

    assert any("machine learning" in query.lower() for _, query in crawler.queries)


def test_media_engine_uses_confirmed_normalized_domain_without_extra_normalization() -> None:
    crawler = FakeMediaCrawler()
    engine = MediaEngine(
        chat_client=FakeMediaPlanFirstChatClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="Machine Learning",
        normalized_domain="Machine Learning",
        original_input="ML",
        subdomains=["基础概念"],
        time_window="近 12 个月",
        focus_points=["社区观点"],
        constraints=[],
        initial_strategy=["Machine Learning community trend"],
        search_terms=["Machine Learning", "ML"],
        confirmed=True,
    )

    engine.run(context, round_number=1)

    assert crawler.queries
    assert any("machine learning" in query.lower() for _, query in crawler.queries)


def test_media_ranking_prefers_technical_community_sources() -> None:
    assert is_technical_context("深度学习", ["模型训练"], ["社区观点"]) is True
    community_score = score_media_url(
        "https://news.ycombinator.com/item?id=123",
        platform_type="community",
        requested_type="community",
        is_technical=True,
        snippet="community discussion about adoption trend",
    )
    social_score = score_media_url(
        "https://x.com/someone/status/123",
        platform_type="social",
        requested_type="social",
        is_technical=True,
        snippet="opinion trend",
    )

    assert community_score > social_score
