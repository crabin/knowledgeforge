from __future__ import annotations

from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.graph.neo4j_adapter import Neo4jPathMapper
from knowledgeforge.models import DocumentArtifact, RequestContext, StructuredExtractionResult


class FakeChatClient:
    def complete_json(self, *, system_prompt: str, user_prompt: str):
        return {
            "summary": "使用真实 LLM 客户端生成的检索摘要。",
            "key_points": ["权威来源优先", "保留来源元数据"],
            "coverage_topics": ["工作流编排", "知识沉淀"],
            "recommended_queries": ["知识工程 工作流编排 官方资料"],
            "authoritative_sources": [
                {
                    "title": "LangGraph Docs",
                    "url": "https://langchain-ai.github.io/langgraph/",
                    "publisher": "LangChain",
                    "reliability": "high",
                }
            ],
        }


class FakeEmbeddingClient:
    def embed_texts(self, texts: list[str]):
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeNeo4jClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def sync_document(self, **kwargs):
        self.calls.append(kwargs)


def test_query_engine_uses_chat_and_embedding_clients() -> None:
    engine = QueryEngine(chat_client=FakeChatClient(), embedding_client=FakeEmbeddingClient())
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
