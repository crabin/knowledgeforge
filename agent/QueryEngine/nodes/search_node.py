from __future__ import annotations

import json

from agent.QueryEngine.nodes.base_node import BaseQueryNode
from agent.QueryEngine.prompts.prompts import SEARCH_PLAN_SYSTEM_PROMPT
from agent.QueryEngine.state.state import QueryEngineState, SearchPlan
from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from agent.QueryEngine.utils.ranking import (
    PREFERRED_TECH_REFERENCE_DOMAINS,
    PREFERRED_TUTORIAL_DOMAINS,
    build_site_constrained_queries,
    detect_candidate_official_domains,
)
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
        self._append_search_results(
            state,
            official_queries=plan.official_queries,
            tutorial_queries=plan.tutorial_queries,
            embedding_client=embedding_client,
        )
        return state

    def supplement(
        self,
        state: QueryEngineState,
        *,
        official_queries: list[str],
        tutorial_queries: list[str],
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> QueryEngineState:
        self._append_search_results(
            state,
            official_queries=official_queries,
            tutorial_queries=tutorial_queries,
            embedding_client=embedding_client,
        )
        state.iteration_count += 1
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

    def _append_search_results(
        self,
        state: QueryEngineState,
        *,
        official_queries: list[str],
        tutorial_queries: list[str],
        embedding_client: OpenAICompatibleEmbeddingClient | None,
    ) -> None:
        all_hits = list(state.search_hits)
        for query in official_queries:
            hits = self._crawler.search(
                query=query,
                source_type="official",
                official_domains=state.candidate_official_domains or (state.search_plan.official_domains if state.search_plan else []),
                preferred_domains=[],
                max_results=4,
            )
            state.search_history.append({"query": query, "source_type": "official", "hits": len(hits)})
            all_hits.extend(hits)
        expanded_tutorial_queries = self._expand_preferred_queries(tutorial_queries)
        for query in expanded_tutorial_queries:
            hits = self._crawler.search(
                query=query,
                source_type="tutorial",
                official_domains=state.search_plan.official_domains if state.search_plan else [],
                preferred_domains=self._preferred_domains(),
                max_results=3,
            )
            state.search_history.append({"query": query, "source_type": "tutorial", "hits": len(hits)})
            all_hits.extend(hits)
        deduped_hits = self._dedupe_hits(all_hits)
        state.search_hits = deduped_hits
        state.candidate_official_domains = self._merge_candidate_domains(
            state,
            detect_candidate_official_domains(state.request_context.domain, deduped_hits),
        )
        state.crawled_documents = self._crawler.fetch_documents(deduped_hits, max_documents=8)

        if embedding_client is not None and state.crawled_documents:
            try:
                vectors = embedding_client.embed_texts(
                    [doc.content[:800] or doc.snippet or doc.title for doc in state.crawled_documents]
                )
                for doc, vector in zip(state.crawled_documents, vectors):
                    doc.embedding_dimensions = len(vector)
            except Exception:
                pass

    @staticmethod
    def _preferred_domains() -> list[str]:
        return [*PREFERRED_TUTORIAL_DOMAINS, *PREFERRED_TECH_REFERENCE_DOMAINS]

    def _expand_preferred_queries(self, tutorial_queries: list[str]) -> list[str]:
        expanded: list[str] = []
        for query in tutorial_queries:
            expanded.append(query)
            expanded.extend(build_site_constrained_queries(query, self._preferred_domains()))
        deduped: list[str] = []
        seen = set()
        for query in expanded:
            if query in seen:
                continue
            seen.add(query)
            deduped.append(query)
        return deduped

    @staticmethod
    def _merge_candidate_domains(state: QueryEngineState, domains: list[str]) -> list[str]:
        merged = list(state.candidate_official_domains)
        for domain in state.search_plan.official_domains if state.search_plan else []:
            if domain not in merged:
                merged.append(domain)
        for domain in domains:
            if domain not in merged:
                merged.append(domain)
        return merged
