from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json

from collections.abc import Callable
from typing import Any

from agent.QueryEngine.nodes.base_node import BaseQueryNode, QueryEventCallback
from agent.QueryEngine.prompts.prompts import SEARCH_PLAN_SYSTEM_PROMPT
from agent.QueryEngine.state.state import QueryEngineState, SearchPlan, SearchQuestion
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
from knowledgeforge.storage.realtime_reviewer import RealtimeReviewCandidate, RealtimeReviewResult
from knowledgeforge.runtime.task_queue import QueuedTaskSpec, RetrievalTaskQueue
from knowledgeforge.utils.time import now_iso

QueryRealtimeFileCallback = Callable[[str, RealtimeReviewCandidate], RealtimeReviewResult]


@dataclass(slots=True)
class SearchAttemptResult:
    query: str
    hits: list[Any]
    status: str
    error: str = ""


@dataclass(slots=True)
class QuestionTaskResult:
    question: SearchQuestion
    source_type: str
    hits: list[Any]
    attempts: list[SearchAttemptResult]


class QuerySearchNode(BaseQueryNode):
    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        crawler: DomainKnowledgeCrawler,
        event_callback: QueryEventCallback | None = None,
        realtime_file_callback: QueryRealtimeFileCallback | None = None,
        max_concurrent_network_tasks: int = 5,
        task_queue: RetrievalTaskQueue | None = None,
    ) -> None:
        super().__init__(event_callback=event_callback)
        self._chat_client = chat_client
        self._crawler = crawler
        self._realtime_file_callback = realtime_file_callback
        self._max_concurrent_network_tasks = max(1, max_concurrent_network_tasks)
        self._task_queue = task_queue

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
            questions=plan.questions,
            embedding_client=embedding_client,
        )
        return state

    def execute_plan(
        self,
        state: QueryEngineState,
        *,
        plan: SearchPlan,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> QueryEngineState:
        self._normalize_domain(state)
        state.search_plan = plan
        self._append_search_results(
            state,
            questions=plan.questions,
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
            questions=self._questions_from_supplemental_queries(
                state,
                official_queries=official_queries,
                tutorial_queries=tutorial_queries,
            ),
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
            raise RuntimeError("QueryEngine plan generation requires an LLM chat client.")
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
        payload = self._chat_client.complete_json(
            system_prompt=SEARCH_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        self._record_event(state, "query_plan_llm_completed", {"payload_keys": sorted(payload.keys())})
        questions = self._parse_questions(payload.get("questions", []))
        official_queries = [
            str(item).strip() for item in payload.get("official_queries", []) if str(item).strip()
        ]
        tutorial_queries = [
            str(item).strip() for item in payload.get("tutorial_queries", []) if str(item).strip()
        ]
        if not questions:
            raise RuntimeError("QueryEngine LLM did not return any valid search questions.")
        return SearchPlan(
            official_queries=official_queries or [
                question.google_query
                for question in questions
                if self._question_source_type(question) == "official"
            ],
            tutorial_queries=tutorial_queries or [
                question.google_query
                for question in questions
                if self._question_source_type(question) == "tutorial"
            ],
            official_domains=[str(item).strip() for item in payload.get("official_domains", []) if str(item).strip()],
            reasoning=str(payload.get("reasoning", "")).strip() or "官方优先，教程补充。",
            questions=questions,
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
        questions: list[SearchQuestion] | None = None,
        official_queries: list[str] | None = None,
        tutorial_queries: list[str] | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None,
    ) -> None:
        official_queries = official_queries or []
        tutorial_queries = tutorial_queries or []
        all_hits = list(state.search_hits)
        domain_phrases = self._domain_phrases(state)
        plan_questions = questions or self._questions_from_query_lists(
            state,
            official_queries=official_queries,
            tutorial_queries=tutorial_queries,
        )
        self._prepare_plan_questions(plan_questions)
        self._record_event(
            state,
            "query_plan_created",
            {
                "question_count": len(plan_questions),
                "max_concurrent_network_tasks": self._max_concurrent_network_tasks,
                "questions": [
                    {
                        "plan_item_id": question.plan_item_id,
                        "question": question.question,
                        "google_query": question.google_query,
                        "search_targets": question.search_targets,
                        "expected_info": question.expected_info,
                        "source_priority": question.source_priority,
                        "success_criteria": question.success_criteria,
                        "fallback_queries": question.fallback_queries,
                        "status": question.status,
                    }
                    for question in plan_questions
                ],
            },
        )
        if not plan_questions:
            return
        for question in plan_questions:
            question.status = "in_progress"
            source_type = self._question_source_type(question)
            self._record_event(
                state,
                "query_plan_item_started",
                self._question_log_details(question, status=question.status),
            )
        task_results = self._run_question_tasks(state, plan_questions, domain_phrases)
        for task_result in task_results:
                question = task_result.question
                question_hits = task_result.hits
                for attempt in task_result.attempts:
                    state.search_history.append(
                        {
                            "question": question.question,
                            "query": attempt.query,
                            "expected_info": question.expected_info,
                            "source_type": task_result.source_type,
                            "hits": len(attempt.hits),
                            "status": attempt.status,
                            "error": attempt.error,
                        }
                    )
                    event_name = "query_search_failed" if attempt.status == "failed" else "query_search_executed"
                    details = {
                        "plan_item_id": question.plan_item_id,
                        "question": question.question,
                        "query": attempt.query,
                        "search_targets": question.search_targets,
                        "expected_info": question.expected_info,
                        "source_type": task_result.source_type,
                        "hits": len(attempt.hits),
                        "status": attempt.status,
                    }
                    if attempt.error:
                        details["error"] = attempt.error
                        details["failure_category"] = "network_query_failed"
                    self._record_event(state, event_name, details)
                all_hits.extend(question_hits)
                question.status = "completed" if self._question_satisfied(question_hits) else "insufficient"
                if question.status == "completed":
                    question.completed_at = now_iso()
                self._record_event(
                    state,
                    "query_question_completed",
                    {
                        "plan_item_id": question.plan_item_id,
                        "question": question.question,
                        "search_targets": question.search_targets,
                        "status": question.status,
                        "total_hits": len(question_hits),
                        "completed_at": question.completed_at,
                    },
                )
                self._save_realtime_question_documents(
                    state,
                    question=question,
                    source_type=task_result.source_type,
                    hits=question_hits,
                )
        deduped_hits = self._dedupe_hits(all_hits)
        state.search_hits = deduped_hits
        state.candidate_official_domains = self._merge_candidate_domains(
            state,
            detect_candidate_official_domains(state.request_context.domain, deduped_hits),
        )
        state.crawled_documents = self._crawler.fetch_documents(deduped_hits, max_documents=8)
        self._record_event(
            state,
            "query_documents_fetched",
            {
                "hit_count": len(deduped_hits),
                "document_count": len(state.crawled_documents),
            },
        )
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
                self._record_event(
                    state,
                    "query_embeddings_completed",
                    {
                        "document_count": len(state.crawled_documents),
                        "dimensions": state.crawled_documents[0].embedding_dimensions,
                    },
                )
            except Exception:
                self._record_event(
                    state,
                    "query_embeddings_failed",
                    {"document_count": len(state.crawled_documents)},
                )

    def _run_question_tasks(
        self,
        state: QueryEngineState,
        questions: list[SearchQuestion],
        domain_phrases: list[str],
    ) -> list[QuestionTaskResult]:
        if self._task_queue is None:
            max_workers = min(self._max_concurrent_network_tasks, len(questions))
            futures = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for question in questions:
                    source_type = self._question_source_type(question)
                    futures[
                        executor.submit(
                            self._run_question_task,
                            state,
                            question=question,
                            source_type=source_type,
                            domain_phrases=domain_phrases,
                        )
                    ] = question.plan_item_id
                return [future.result() for future in as_completed(futures)]

        queued_tasks = [
            QueuedTaskSpec[QuestionTaskResult, None](
                task_id=question.plan_item_id,
                task_type="network_query_and_optional_llm_summary",
                payload={
                    "agent": "QueryEngine",
                    "question": question.question,
                    "query": question.google_query,
                    "round": state.round_number,
                },
                network_call=lambda question=question, source_type=self._question_source_type(question): self._run_question_task(
                    state,
                    question=question,
                    source_type=source_type,
                    domain_phrases=domain_phrases,
                ),
            )
            for question in questions
        ]
        queued_results = self._task_queue.run_tasks(queued_tasks)
        ordered_results: list[QuestionTaskResult] = []
        for queued_result in queued_results:
            if queued_result.network_result is None:
                raise RuntimeError(queued_result.error or f"Query task {queued_result.task_id} failed")
            ordered_results.append(queued_result.network_result)
        return ordered_results

    @staticmethod
    def _parse_questions(items: object) -> list[SearchQuestion]:
        questions: list[SearchQuestion] = []
        if not isinstance(items, list):
            return questions
        for item in items:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            google_query = str(item.get("google_query", "")).strip()
            if not question or not google_query:
                continue
            questions.append(
                SearchQuestion(
                    question=question,
                    google_query=google_query,
                    search_targets=[
                        str(value).strip()
                        for value in item.get("search_targets", item.get("expected_info", []))
                        if str(value).strip()
                    ],
                    expected_info=[
                        str(value).strip()
                        for value in item.get("expected_info", [])
                        if str(value).strip()
                    ],
                    source_priority=[
                        str(value).strip()
                        for value in item.get("source_priority", [])
                        if str(value).strip()
                    ],
                    success_criteria=[
                        str(value).strip()
                        for value in item.get("success_criteria", [])
                        if str(value).strip()
                    ],
                    fallback_queries=[
                        str(value).strip()
                        for value in item.get("fallback_queries", [])
                        if str(value).strip()
                    ],
                    status="planned",
                )
            )
        return questions

    def _questions_from_query_lists(
        self,
        state: QueryEngineState,
        *,
        official_queries: list[str],
        tutorial_queries: list[str],
    ) -> list[SearchQuestion]:
        questions = [
            SearchQuestion(
                question=f"需要确认 {state.normalized_domain or state.request_context.domain} 的官方事实：{query}",
                google_query=query,
                search_targets=["官方定义", "权威说明", "关键事实"],
                expected_info=["官方定义", "权威说明", "关键事实"],
                source_priority=["official documentation", "standard", "vendor docs", "official GitHub"],
                success_criteria=["命中相关官方或权威来源"],
                fallback_queries=[],
            )
            for query in official_queries
        ]
        questions.extend(
            SearchQuestion(
                question=f"需要补充 {state.normalized_domain or state.request_context.domain} 的实践资料：{query}",
                google_query=query,
                search_targets=["教程示例", "实践步骤", "注意事项"],
                expected_info=["教程示例", "实践步骤", "注意事项"],
                source_priority=["tutorial", "technical blog", "reference guide"],
                success_criteria=["命中相关教程或技术参考"],
                fallback_queries=self._expand_preferred_queries([query])[1:],
            )
            for query in tutorial_queries
        )
        return questions

    @staticmethod
    def _questions_from_supplemental_queries(
        state: QueryEngineState,
        *,
        official_queries: list[str],
        tutorial_queries: list[str],
    ) -> list[SearchQuestion]:
        questions: list[SearchQuestion] = []
        insufficient_questions = [
            question
            for question in (state.search_plan.questions if state.search_plan else [])
            if question.status == "insufficient"
        ]
        for query in official_queries:
            base_question = insufficient_questions[0].question if insufficient_questions else query
            questions.append(
                SearchQuestion(
                    question=f"补检索：{base_question}",
                    google_query=query,
                    search_targets=["补齐官方或权威证据"],
                    expected_info=["补齐官方或权威证据"],
                    source_priority=["official documentation", "standard", "vendor docs"],
                    success_criteria=["补检索命中相关官方或权威来源"],
                    fallback_queries=[],
                )
            )
        for query in tutorial_queries:
            base_question = insufficient_questions[0].question if insufficient_questions else query
            questions.append(
                SearchQuestion(
                    question=f"补检索：{base_question}",
                    google_query=query,
                    search_targets=["补齐教程、案例或最佳实践证据"],
                    expected_info=["补齐教程、案例或最佳实践证据"],
                    source_priority=["tutorial", "technical blog", "reference guide"],
                    success_criteria=["补检索命中相关实践资料"],
                    fallback_queries=[],
                )
            )
        return questions

    @staticmethod
    def _prepare_plan_questions(questions: list[SearchQuestion]) -> None:
        for index, question in enumerate(questions, start=1):
            if not question.plan_item_id:
                question.plan_item_id = f"Q{index}"
            if not question.search_targets:
                question.search_targets = list(question.expected_info)

    @staticmethod
    def _question_log_details(question: SearchQuestion, *, status: str | None = None) -> dict:
        return {
            "plan_item_id": question.plan_item_id,
            "question": question.question,
            "google_query": question.google_query,
            "search_targets": question.search_targets,
            "expected_info": question.expected_info,
            "source_priority": question.source_priority,
            "success_criteria": question.success_criteria,
            "fallback_queries": question.fallback_queries,
            "status": status or question.status,
            "completed_at": question.completed_at,
        }

    @staticmethod
    def _question_source_type(question: SearchQuestion) -> str:
        priority_text = " ".join(question.source_priority).lower()
        if any(token in priority_text for token in ["tutorial", "blog", "guide", "example", "practice"]):
            return "tutorial"
        return "official"

    @staticmethod
    def _question_satisfied(hits) -> bool:
        return any(getattr(hit, "score", 0) > 0 for hit in hits)

    def _run_question_task(
        self,
        state: QueryEngineState,
        *,
        question: SearchQuestion,
        source_type: str,
        domain_phrases: list[str],
    ) -> QuestionTaskResult:
        attempts: list[SearchAttemptResult] = []
        question_hits: list[Any] = []
        for index, query in enumerate(self._dedupe_terms([question.google_query, *question.fallback_queries])):
            if index > 0 and self._question_satisfied(question_hits):
                break
            try:
                hits = self._search_for_question(
                    state,
                    question=question,
                    query=query,
                    source_type=source_type,
                    domain_phrases=domain_phrases,
                )
            except Exception as exc:
                attempts.append(
                    SearchAttemptResult(
                        query=query,
                        hits=[],
                        status="failed",
                        error=str(exc),
                    )
                )
                continue
            status = "completed" if self._question_satisfied(hits) else "insufficient"
            attempts.append(SearchAttemptResult(query=query, hits=hits, status=status))
            question_hits.extend(hits)
        return QuestionTaskResult(
            question=question,
            source_type=source_type,
            hits=question_hits,
            attempts=attempts,
        )

    def _search_for_question(
        self,
        state: QueryEngineState,
        *,
        question: SearchQuestion,
        query: str,
        source_type: str,
        domain_phrases: list[str],
    ):
        if source_type == "official":
            return self._search(
                query=query,
                source_type="official",
                official_domains=state.candidate_official_domains
                or (state.search_plan.official_domains if state.search_plan else []),
                preferred_domains=[],
                max_results=4,
                domain_phrases=domain_phrases,
            )
        return self._search(
            query=query,
            source_type="tutorial",
            official_domains=state.search_plan.official_domains if state.search_plan else [],
            preferred_domains=self._preferred_domains(),
            max_results=3,
            domain_phrases=domain_phrases,
        )

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

    def _save_realtime_question_documents(
        self,
        state: QueryEngineState,
        *,
        question: SearchQuestion,
        source_type: str,
        hits: list[Any],
    ) -> None:
        task_id = getattr(state.request_context, "task_id", "")
        if not task_id or self._realtime_file_callback is None or not hits:
            return
        try:
            documents = self._crawler.fetch_documents(self._dedupe_hits(hits), max_documents=4)
            candidate = RealtimeReviewCandidate(
                agent="QueryEngine",
                round_number=state.round_number,
                plan_item_id=question.plan_item_id,
                query=question.google_query,
                source_type=source_type,
                documents=documents,
                context=state.request_context,
            )
            result = self._realtime_file_callback(task_id, candidate)
            self._record_event(
                state,
                "query_realtime_file_reviewed",
                {
                    "plan_item_id": question.plan_item_id,
                    "question": question.question,
                    "query": question.google_query,
                    **result.to_dict(),
                },
            )
        except Exception as exc:
            self._record_event(
                state,
                "query_realtime_file_failed",
                {
                    "plan_item_id": question.plan_item_id,
                    "question": question.question,
                    "query": question.google_query,
                    "error": str(exc),
                    "failure_category": "file_write_failed",
                },
            )
