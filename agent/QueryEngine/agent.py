from __future__ import annotations

from typing import Any

from agent.base import BaseEngine
from knowledgeforge.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class QueryEngine(BaseEngine):
    name = "QueryEngine"

    def __init__(
        self,
        chat_client: OpenAICompatibleChatClient | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._embedding_client = embedding_client

    def run(self, context: RequestContext, round_number: int) -> EngineRunResult:
        timestamp = now_iso()
        llm_payload = self._generate_query_brief(context)
        embeddings = self._embed_topics(context)
        key_points = llm_payload.get("key_points") or [
            f"优先覆盖 {', '.join(context.subdomains)} 的事实型资料。",
            "保留了最小来源元数据结构，便于后续引用检查与图谱关联。",
        ]
        coverage_topics = llm_payload.get("coverage_topics") or context.subdomains
        sources = self._build_sources(llm_payload, timestamp, round_number, context)
        raw_material = [
            f"建议检索：{query}"
            for query in llm_payload.get("recommended_queries", context.initial_strategy)
        ]
        if embeddings:
            raw_material.append(
                f"Embedding 已生成：{len(embeddings)} 个向量，维度示例 {len(embeddings[0]) if embeddings[0] else 0}。"
            )
        return EngineRunResult(
            agent_name=self.name,
            summary=llm_payload.get(
                "summary",
                f"为 {context.domain} 生成一组优先面向官方与权威来源的事实检索结果。",
            ),
            key_points=key_points,
            raw_material=raw_material,
            coverage_topics=coverage_topics,
            sources=sources,
            collected_at=timestamp,
            round_number=round_number,
        )

    def _generate_query_brief(self, context: RequestContext) -> dict[str, Any]:
        if self._chat_client is None:
            return {}
        system_prompt = (
            "你是 KnowledgeForge 的 QueryEngine。"
            "请只输出 JSON，包含 summary、key_points、coverage_topics、recommended_queries、authoritative_sources。"
        )
        user_prompt = (
            f"领域：{context.domain}\n"
            f"子主题：{', '.join(context.subdomains)}\n"
            f"时间范围：{context.time_window}\n"
            f"关注点：{', '.join(context.focus_points)}\n"
            "请优先给出官方、权威或标准化来源建议。"
        )
        try:
            return self._chat_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            return {}

    def _embed_topics(self, context: RequestContext) -> list[list[float]]:
        if self._embedding_client is None:
            return []
        try:
            return self._embedding_client.embed_texts([context.domain, *context.subdomains])
        except Exception:
            return []

    def _build_sources(
        self,
        llm_payload: dict[str, Any],
        timestamp: str,
        round_number: int,
        context: RequestContext,
    ) -> list[SourceRecord]:
        source_payload = llm_payload.get("authoritative_sources") or []
        sources: list[SourceRecord] = []
        for item in source_payload:
            if not isinstance(item, dict):
                continue
            sources.append(
                SourceRecord(
                    title=str(item.get("title", f"{context.domain} 来源建议")).strip(),
                    url=str(item.get("url", f"https://example.com/{round_number}/{self.name.lower()}")).strip(),
                    publisher=str(item.get("publisher", "Unknown Publisher")).strip(),
                    retrieved_at=timestamp,
                    reliability=str(item.get("reliability", "high")).strip() or "high",
                    agent=self.name,
                )
            )
        if sources:
            return sources
        return [
            SourceRecord(
                title=f"{context.domain} 官方资料检索建议",
                url=f"https://example.com/{round_number}/{self.name.lower()}",
                publisher="Example Authority",
                retrieved_at=timestamp,
                reliability="high",
                agent=self.name,
            )
        ]
