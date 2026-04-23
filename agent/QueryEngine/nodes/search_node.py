from __future__ import annotations

import json

from agent.QueryEngine.nodes.base_node import BaseQueryNode
from agent.QueryEngine.prompts.prompts import SEARCH_PLAN_SYSTEM_PROMPT
from agent.QueryEngine.state.state import QueryEngineState, SearchPlan
from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)


class QuerySearchNode(BaseQueryNode):
    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        crawler: DomainKnowledgeCrawler,
    ) -> None:
        self._chat_client = chat_client
        self._crawler = crawler

    def run(
        self,
        state: QueryEngineState,
        *,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> QueryEngineState:
        plan = self._build_plan(state)
        state.search_plan = plan

        all_hits = []
        for query in plan.official_queries:
            all_hits.extend(
                self._crawler.search(
                    query=query,
                    source_type="official",
                    official_domains=plan.official_domains,
                    max_results=4,
                )
            )
        for query in plan.tutorial_queries:
            all_hits.extend(
                self._crawler.search(
                    query=query,
                    source_type="tutorial",
                    official_domains=plan.official_domains,
                    max_results=3,
                )
            )
        deduped_hits = self._dedupe_hits(all_hits)
        state.search_hits = deduped_hits
        state.crawled_documents = self._crawler.fetch_documents(deduped_hits, max_documents=6)

        if embedding_client is not None and state.crawled_documents:
            try:
                vectors = embedding_client.embed_texts(
                    [doc.content[:800] or doc.snippet or doc.title for doc in state.crawled_documents]
                )
                for doc, vector in zip(state.crawled_documents, vectors):
                    doc.embedding_dimensions = len(vector)
            except Exception:
                pass
        return state

    def _build_plan(self, state: QueryEngineState) -> SearchPlan:
        context = state.request_context
        if self._chat_client is None:
            return self._fallback_plan(state)
        user_prompt = json.dumps(
            {
                "domain": context.domain,
                "subdomains": context.subdomains,
                "time_window": context.time_window,
                "focus_points": context.focus_points,
                "constraints": context.constraints,
            },
            ensure_ascii=False,
        )
        try:
            payload = self._chat_client.complete_json(
                system_prompt=SEARCH_PLAN_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return SearchPlan(
                official_queries=[str(item).strip() for item in payload.get("official_queries", []) if str(item).strip()],
                tutorial_queries=[str(item).strip() for item in payload.get("tutorial_queries", []) if str(item).strip()],
                official_domains=[str(item).strip() for item in payload.get("official_domains", []) if str(item).strip()],
                reasoning=str(payload.get("reasoning", "")).strip() or "官方优先，教程补充。",
            )
        except Exception:
            return self._fallback_plan(state)

    def _fallback_plan(self, state: QueryEngineState) -> SearchPlan:
        context = state.request_context
        official_queries = [
            f"{context.domain} {topic} official documentation"
            for topic in context.subdomains[:3]
        ]
        tutorial_queries = [
            f"{context.domain} {topic} tutorial guide"
            for topic in context.subdomains[:2]
        ]
        return SearchPlan(
            official_queries=official_queries,
            tutorial_queries=tutorial_queries,
            official_domains=[],
            reasoning="未拿到 LLM 规划结果，按官方文档优先和教程补充的默认规则生成。",
        )

    @staticmethod
    def _dedupe_hits(hits):
        seen = set()
        deduped = []
        for hit in sorted(hits, key=lambda item: item.score, reverse=True):
            if hit.url in seen:
                continue
            seen.add(hit.url)
            deduped.append(hit)
        return deduped
