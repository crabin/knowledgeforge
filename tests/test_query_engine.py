from __future__ import annotations

from agent.QueryEngine.agent import QueryEngine
from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.models import RequestContext


class FakeChatClient:
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
                "questions": [
                    {
                        "question": "LangGraph 的官方工作流编排能力是什么？",
                        "google_query": "langgraph official documentation workflow orchestration",
                        "expected_info": ["官方能力说明", "核心 API", "适用范围"],
                        "source_priority": ["official documentation", "official GitHub"],
                        "success_criteria": ["命中官方文档", "能支持工作流编排事实"],
                        "fallback_queries": ["langgraph workflow reference documentation"],
                    },
                    {
                        "question": "LangGraph 有哪些教程案例可补充知识沉淀场景？",
                        "google_query": "langgraph tutorial guide knowledge workflows",
                        "expected_info": ["教程示例", "最佳实践", "案例步骤"],
                        "source_priority": ["tutorial", "technical blog"],
                        "success_criteria": ["命中教程或技术参考", "能补充实践语境"],
                        "fallback_queries": ["langgraph best practices tutorial"],
                    },
                ],
                "official_queries": ["langgraph official documentation"],
                "tutorial_queries": ["langgraph tutorial guide"],
                "official_domains": ["langchain-ai.github.io", "python.langchain.com"],
                "reasoning": "先查官方文档，再查教程。",
            }
        if self.calls == 3:
            return {
                "missing_aspects": ["缺少最佳实践案例"],
                "supplementary_official_queries": [],
                "supplementary_tutorial_queries": ["langgraph best practices tutorial"],
                "candidate_official_domains": ["langchain-ai.github.io"],
                "reasoning": "官方资料已有，但还需要补教程案例。",
            }
        return {
            "summary": "已优先整理 LangGraph 官方文档，并补充教程资料。",
            "key_points": ["官方文档优先", "教程补充"],
            "coverage_topics": ["工作流编排", "知识沉淀"],
            "official_findings": ["LangGraph 官方文档提供核心工作流模式。"],
            "tutorial_findings": ["教程文档提供示例代码。"],
        }


class FakeNormalizationChatClient:
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
                "questions": [
                    {
                        "question": "machine learning basics 的官方基础定义是什么？",
                        "google_query": "machine learning basics official documentation",
                        "expected_info": ["官方定义", "基础概览"],
                        "source_priority": ["official documentation"],
                        "success_criteria": ["查询语句使用完整 machine learning 术语"],
                        "fallback_queries": ["machine learning basics official guide"],
                    }
                ],
                "official_queries": ["machine learning basics official documentation"],
                "tutorial_queries": ["machine learning basics tutorial guide"],
                "official_domains": [],
                "reasoning": "使用补全后的完整术语生成 query。",
            }
        if self.calls == 3:
            return {
                "missing_aspects": [],
                "supplementary_official_queries": [],
                "supplementary_tutorial_queries": [],
                "candidate_official_domains": [],
                "reasoning": "当前结果已足够。",
            }
        return {
            "summary": "已基于完整术语完成检索整理。",
            "key_points": ["已完成缩写补全"],
            "coverage_topics": ["基础概览"],
            "official_findings": [],
            "tutorial_findings": [],
        }


class FakeEmbeddingClient:
    def embed_texts(self, texts: list[str]):
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeCrawler(DomainKnowledgeCrawler):
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def search(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None = None,
        max_results: int = 5,
    ):
        self.queries.append((source_type, query))
        if source_type == "official":
            return [
                __import__("agent.QueryEngine.state.state", fromlist=["SearchHit"]).SearchHit(
                    title="LangGraph Docs",
                    url="https://langchain-ai.github.io/langgraph/",
                    snippet="Official reference",
                    source_type="official",
                    score=12.0,
                )
            ]
        return [
            __import__("agent.QueryEngine.state.state", fromlist=["SearchHit"]).SearchHit(
                title="LangGraph Tutorial",
                url="https://example.com/tutorial/langgraph",
                snippet="Tutorial reference",
                source_type="tutorial",
                score=4.0,
            )
        ]

    def fetch_documents(self, hits, *, max_documents: int = 6):
        CrawledDocument = __import__("agent.QueryEngine.state.state", fromlist=["CrawledDocument"]).CrawledDocument
        docs = []
        for hit in hits:
            docs.append(
                CrawledDocument(
                    title=hit.title,
                    url=hit.url,
                    snippet=hit.snippet,
                    content=f"{hit.title} content",
                    source_type=hit.source_type,
                    publisher="publisher.test",
                    score=hit.score,
                )
            )
        return docs


class EmptyCrawler(FakeCrawler):
    def search(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None = None,
        max_results: int = 5,
    ):
        self.queries.append((source_type, query))
        return []


class PartialCrawler(FakeCrawler):
    def search(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None = None,
        max_results: int = 5,
    ):
        if source_type == "official":
            self.queries.append((source_type, query))
            return []
        return super().search(
            query=query,
            source_type=source_type,
            official_domains=official_domains,
            preferred_domains=preferred_domains,
            max_results=max_results,
        )


def test_query_engine_prioritizes_official_sources() -> None:
    crawler = FakeCrawler()
    engine = QueryEngine(
        chat_client=FakeChatClient(),
        embedding_client=FakeEmbeddingClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="LangGraph",
        subdomains=["工作流编排", "知识沉淀"],
        time_window="近 12 个月",
        focus_points=["官方文档", "最佳实践"],
        constraints=[],
        initial_strategy=["LangGraph official docs"],
    )

    result = engine.run(context, round_number=1)

    assert result.summary.startswith("已优先整理 LangGraph 官方文档")
    assert result.sources[0].source_type == "official"
    assert result.sources[0].reliability == "high"
    assert any("官方文档优先" in item for item in result.key_points)
    assert any("术语归一化：" in item for item in result.raw_material)
    assert any("官方文档优先：" in item or item == "官方文档优先：" for item in result.raw_material)
    assert any(item == "查询计划：" for item in result.raw_material)
    assert any("Google 查询：langgraph official documentation workflow orchestration" in item for item in result.raw_material)
    assert any("预期信息：" in item and "官方能力说明" in item for item in result.raw_material)
    assert any("满足标准：" in item and "命中官方文档" in item for item in result.raw_material)
    assert crawler.queries[0] == ("official", "langgraph official documentation workflow orchestration")
    assert crawler.queries[1] == ("tutorial", "langgraph tutorial guide knowledge workflows")
    assert any("反思结论：" in item for item in result.raw_material)
    assert any("候选官方域名：" in item for item in result.raw_material)
    assert any("检索轨迹：" in item for item in result.raw_material)
    assert any(query == "langgraph best practices tutorial" for _, query in crawler.queries)
    assert any("langchain-ai.github.io" in item for item in result.raw_material)


def test_query_engine_normalizes_abbreviation_for_search() -> None:
    crawler = FakeCrawler()
    engine = QueryEngine(
        chat_client=FakeNormalizationChatClient(),
        embedding_client=FakeEmbeddingClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="ML",
        subdomains=["基础概览"],
        time_window="近 12 个月",
        focus_points=["官方文档"],
        constraints=[],
        initial_strategy=["ML official docs"],
    )

    engine.run(context, round_number=1)

    assert any("machine learning" in query.lower() for _, query in crawler.queries)


def test_query_engine_uses_confirmed_normalized_domain_without_extra_normalization() -> None:
    crawler = FakeCrawler()
    engine = QueryEngine(
        chat_client=None,
        embedding_client=FakeEmbeddingClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="Machine Learning",
        normalized_domain="Machine Learning",
        original_input="ML",
        subdomains=["基础概念"],
        time_window="近 12 个月",
        focus_points=["官方文档"],
        constraints=[],
        initial_strategy=["Machine Learning official docs"],
        search_terms=["Machine Learning", "ML"],
        confirmed=True,
    )

    engine.run(context, round_number=1)

    assert crawler.queries
    assert any("machine learning" in query.lower() for _, query in crawler.queries)
    assert not any("machinery" in query.lower() or "vending machine" in query.lower() for _, query in crawler.queries)


def test_query_engine_fallback_plan_emits_structured_questions() -> None:
    crawler = FakeCrawler()
    engine = QueryEngine(
        chat_client=None,
        embedding_client=FakeEmbeddingClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="Machine Learning",
        subdomains=["基础概念"],
        time_window="近 12 个月",
        focus_points=["官方文档"],
        constraints=[],
        initial_strategy=["Machine Learning official docs"],
    )

    result = engine.run(context, round_number=1)

    assert any(item == "查询计划：" for item in result.raw_material)
    assert any("Machine Learning 在“基础概念”方面有哪些官方事实与权威说明？" in item for item in result.raw_material)
    assert any("Google 查询：Machine Learning 基础概念 official documentation standard" in item for item in result.raw_material)
    assert any("预期信息：" in item and "官方定义" in item for item in result.raw_material)
    assert crawler.queries[0] == ("official", "Machine Learning 基础概念 official documentation standard")


def test_query_engine_marks_empty_plan_sources_as_unknown() -> None:
    crawler = EmptyCrawler()
    engine = QueryEngine(
        chat_client=None,
        embedding_client=FakeEmbeddingClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="UnknownTool",
        subdomains=["能力边界"],
        time_window="近 12 个月",
        focus_points=["官方文档"],
        constraints=[],
        initial_strategy=["UnknownTool official docs"],
    )

    result = engine.run(context, round_number=1)

    assert result.sources
    assert all(source.publisher == "query-plan" for source in result.sources)
    assert all(source.reliability == "unknown" for source in result.sources)
    assert any("[insufficient]" in item for item in result.raw_material)


def test_query_engine_reflection_supplements_only_insufficient_questions() -> None:
    crawler = PartialCrawler()
    engine = QueryEngine(
        chat_client=None,
        embedding_client=FakeEmbeddingClient(),
        crawler=crawler,
    )
    context = RequestContext(
        domain="LangGraph",
        subdomains=["工作流编排"],
        time_window="近 12 个月",
        focus_points=["官方文档", "教程"],
        constraints=[],
        initial_strategy=["LangGraph official docs"],
    )

    result = engine.run(context, round_number=1)

    official_queries = [query for source_type, query in crawler.queries if source_type == "official"]
    tutorial_queries = [query for source_type, query in crawler.queries if source_type == "tutorial"]
    assert any("official guide" in query for query in official_queries)
    assert not any("best practices" in query for query in tutorial_queries[1:])
    assert any("检索结果不足或缺少权威支撑" in item for item in result.raw_material)
