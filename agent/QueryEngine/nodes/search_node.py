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
from knowledgeforge.utils.query_normalization import normalize_query_term
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
        self._normalize_domain(state)
        if self._chat_client is None:
            return self._fallback_plan(state)
        user_prompt = json.dumps(
            {
                "domain": state.normalized_domain or context.domain,
                "original_domain": context.domain,
                "aliases": state.domain_aliases,
                "search_terms": state.search_terms,
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
        subject = state.normalized_domain or context.domain
        official_queries = [
            f"{subject} {topic} official documentation"
            for topic in context.subdomains[:3]
        ]
        tutorial_queries = [
            f"{subject} {topic} tutorial guide"
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
        domain_phrases = self._domain_phrases(state)
        for query in official_queries:
            hits = self._search(
                query=query,
                source_type="official",
                official_domains=state.candidate_official_domains
                or (state.search_plan.official_domains if state.search_plan else []),
                preferred_domains=[],
                max_results=4,
                domain_phrases=domain_phrases,
            )
            state.search_history.append({"query": query, "source_type": "official", "hits": len(hits)})
            all_hits.extend(hits)
        expanded_tutorial_queries = self._expand_preferred_queries(tutorial_queries)
        for query in expanded_tutorial_queries:
            hits = self._search(
                query=query,
                source_type="tutorial",
                official_domains=state.search_plan.official_domains if state.search_plan else [],
                preferred_domains=self._preferred_domains(),
                max_results=3,
                domain_phrases=domain_phrases,
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
        wiki_doc = (
            self._crawler.fetch_wikipedia_supplement(state.normalized_domain or state.request_context.domain)
            if hasattr(self._crawler, "fetch_wikipedia_supplement") and hasattr(self._crawler, "_wiki")
            else None
        )
        if wiki_doc and all(doc.url != wiki_doc.url for doc in state.crawled_documents):
            state.crawled_documents.append(wiki_doc)

        if embedding_client is not None and state.crawled_documents:
            try:
                vectors = embedding_client.embed_texts(
                    [doc.content[:800] or doc.snippet or doc.title for doc in state.crawled_documents]
                )
                for doc, vector in zip(state.crawled_documents, vectors):
                    doc.embedding_dimensions = len(vector)
            except Exception:
                pass

    def _normalize_domain(self, state: QueryEngineState) -> None:
        if state.normalized_domain:
            return
        context = state.request_context
        if context.normalized_domain:
            state.normalized_domain = context.normalized_domain
            state.domain_aliases = self._dedupe_terms([context.domain, context.normalized_domain])
            state.search_terms = self._dedupe_terms([context.normalized_domain, *context.search_terms, context.domain])
            state.normalization_reasoning = context.clarification_summary or "已使用 Intake 阶段确认的领域归一化结果。"
            return
        normalized = normalize_query_term(
            state.request_context.domain,
            chat_client=self._chat_client,
        )
        state.normalized_domain = normalized.normalized_domain
        state.domain_aliases = normalized.aliases
        state.search_terms = normalized.search_terms
        state.normalization_reasoning = normalized.reasoning

    @staticmethod
    def _dedupe_terms(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen = set()
        for item in items:
            cleaned = item.strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

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

    @staticmethod
    def _domain_phrases(state: QueryEngineState) -> list[str]:
        return QuerySearchNode._dedupe_terms(
            [
                state.normalized_domain or state.request_context.domain,
                state.request_context.domain,
                *state.domain_aliases,
                *state.search_terms,
            ]
        )

    def _search(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None,
        max_results: int,
        domain_phrases: list[str],
    ):
        try:
            return self._crawler.search(
                query=query,
                source_type=source_type,
                official_domains=official_domains,
                preferred_domains=preferred_domains,
                max_results=max_results,
                domain_phrases=domain_phrases,
            )
        except TypeError as exc:
            if "domain_phrases" not in str(exc):
                raise
            return self._crawler.search(
                query=query,
                source_type=source_type,
                official_domains=official_domains,
                preferred_domains=preferred_domains,
                max_results=max_results,
            )
