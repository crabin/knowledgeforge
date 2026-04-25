from __future__ import annotations

from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.graph.neo4j_adapter import Neo4jPathMapper
from knowledgeforge.models import DocumentArtifact, RequestContext, StructuredExtractionResult
from agent.QueryEngine.state.state import CrawledDocument, SearchHit


class FakeChatClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.calls == 1:
            return {
                "normalized_domain": "知识工程",
                "aliases": ["知识工程"],
                "search_terms": ["知识工程", "knowledge engineering"],
                "reasoning": "原词已足够明确，保留原词并补英文别名。",
            }
        if self.calls == 2:
            return {
                "questions": [
                    {
                        "question": "LangGraph 官方工作流编排能力是什么？",
                        "google_query": "langgraph official documentation",
                        "search_targets": ["官方能力"],
                        "expected_info": ["官方能力"],
                        "source_priority": ["official documentation"],
                        "success_criteria": ["命中官方文档"],
                        "fallback_queries": [],
                    },
                    {
                        "question": "LangGraph 教程如何补充知识沉淀场景？",
                        "google_query": "langgraph tutorial guide",
                        "search_targets": ["教程示例"],
                        "expected_info": ["教程示例"],
                        "source_priority": ["tutorial"],
                        "success_criteria": ["命中教程"],
                        "fallback_queries": [],
                    },
                ],
                "official_queries": ["langgraph official documentation"],
                "tutorial_queries": ["langgraph tutorial guide"],
                "official_domains": ["langchain-ai.github.io"],
                "reasoning": "优先查询官方文档，再补充教程。",
            }
        if self.calls == 3:
            return {
                "missing_aspects": [],
                "supplementary_official_queries": [],
                "supplementary_tutorial_queries": [],
                "candidate_official_domains": ["langchain-ai.github.io"],
                "reasoning": "首轮结果已足够，并确认官方候选域名。",
            }
        return {
            "summary": "使用真实 LLM 客户端生成的检索摘要。",
            "key_points": ["权威来源优先", "保留来源元数据"],
            "coverage_topics": ["工作流编排", "知识沉淀"],
            "official_findings": ["LangGraph Docs 提供官方说明。"],
            "tutorial_findings": ["LangGraph Tutorial 提供补充示例。"],
        }


class FakeEmbeddingClient:
    def embed_texts(self, texts: list[str]):
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeCrawler:
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
            return [
                SearchHit(
                    title="LangGraph Docs",
                    url="https://langchain-ai.github.io/langgraph/",
                    snippet="Official reference",
                    source_type="official",
                    score=10.0,
                )
            ]
        return [
            SearchHit(
                title="LangGraph Tutorial",
                url="https://example.com/tutorial/langgraph",
                snippet="Tutorial reference",
                source_type="tutorial",
                score=4.0,
            )
        ]

    def fetch_documents(self, hits, *, max_documents: int = 6):
        return [
            CrawledDocument(
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                content=f"{hit.title} content",
                source_type=hit.source_type,
                publisher="publisher.test",
                score=hit.score,
            )
            for hit in hits
        ]


class FakeNeo4jClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def sync_document(self, **kwargs):
        self.calls.append(kwargs)


def test_query_engine_uses_chat_and_embedding_clients() -> None:
    engine = QueryEngine(
        chat_client=FakeChatClient(),
        embedding_client=FakeEmbeddingClient(),
        crawler=FakeCrawler(),
    )
    context = RequestContext(
        domain="知识工程",
        subdomains=["工作流编排", "知识沉淀"],
        time_window="近 12 个月",
        focus_points=["来源追溯"],
        constraints=[],
        initial_strategy=["知识工程 工作流编排"],
    )

    result = engine.run(context, round_number=1)

    assert result.summary == "使用真实 LLM 客户端生成的检索摘要。"
    assert result.sources[0].title == "LangGraph Docs"
    assert any("Embedding 已生成" in item for item in result.raw_material)
    assert any("候选官方域名：" in item for item in result.raw_material)


def test_neo4j_path_mapper_uses_client_when_available() -> None:
    client = FakeNeo4jClient()
    mapper = Neo4jPathMapper(client=client)
    artifact = DocumentArtifact(
        document_id="article-123",
        title="知识工程知识综述",
        domain="知识工程",
        subdomain="工作流编排",
        path="save/知识工程/工作流编排/test.md",
        status="draft",
        version="v1",
    )
    extraction = StructuredExtractionResult(
        document_id="article-123",
        document_path=artifact.path,
        chunks=[],
        metadata={},
        entities=[{"name": "LangGraph", "type": "Tool"}],
        relations=[],
    )

    result = mapper.sync(artifact, extraction)

    assert result.status == "passed"
    assert client.calls
    assert client.calls[0]["article_id"] == "article-123"
