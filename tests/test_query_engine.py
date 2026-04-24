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
                "official_queries": ["langgraph official documentation"],
                "tutorial_queries": ["langgraph tutorial guide"],
                "official_domains": ["langchain-ai.github.io", "python.langchain.com"],
                "reasoning": "先查官方文档，再查教程。",
            }
        if self.calls == 2:
            return {
                "missing_aspects": ["缺少最佳实践案例"],
                "supplementary_official_queries": [],
                "supplementary_tutorial_queries": ["langgraph best practices tutorial"],
                "reasoning": "官方资料已有，但还需要补教程案例。",
            }
        return {
            "summary": "已优先整理 LangGraph 官方文档，并补充教程资料。",
            "key_points": ["官方文档优先", "教程补充"],
            "coverage_topics": ["工作流编排", "知识沉淀"],
            "official_findings": ["LangGraph 官方文档提供核心工作流模式。"],
            "tutorial_findings": ["教程文档提供示例代码。"],
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
    assert any("官方文档优先：" in item or item == "官方文档优先：" for item in result.raw_material)
    assert any("反思结论：" in item for item in result.raw_material)
    assert any("检索轨迹：" in item for item in result.raw_material)
    assert any(query == "langgraph best practices tutorial" for _, query in crawler.queries)
    assert any("site:github.com" in query for _, query in crawler.queries if _ == "tutorial")
