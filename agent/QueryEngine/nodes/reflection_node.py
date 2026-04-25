from __future__ import annotations

import json

from agent.QueryEngine.nodes.base_node import BaseQueryNode, QueryEventCallback
from agent.QueryEngine.prompts.prompts import REFLECTION_SYSTEM_PROMPT
from agent.QueryEngine.state.state import QueryEngineState, ReflectionPlan
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient


class QueryReflectionNode(BaseQueryNode):
    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        event_callback: QueryEventCallback | None = None,
    ) -> None:
        super().__init__(event_callback=event_callback)
        self._chat_client = chat_client

    def run(self, state: QueryEngineState, **kwargs) -> QueryEngineState:
        reflection = self._build_reflection(state)
        state.reflection_plan = reflection
        state.reflection_notes.append(reflection.reasoning)
        for domain in reflection.candidate_official_domains:
            if domain not in state.candidate_official_domains:
                state.candidate_official_domains.append(domain)
        if reflection.missing_aspects:
            state.observation_notes.extend(reflection.missing_aspects)
        self._record_event(
            state,
            "query_reflection_completed",
            {
                "missing_aspects": reflection.missing_aspects,
                "supplementary_official_queries": reflection.supplementary_official_queries,
                "supplementary_tutorial_queries": reflection.supplementary_tutorial_queries,
                "reasoning": reflection.reasoning,
            },
        )
        return state

    def _build_reflection(self, state: QueryEngineState) -> ReflectionPlan:
        if self._chat_client is None:
            return self._fallback_reflection(state)

        documents_payload = [
            {
                "title": doc.title,
                "url": doc.url,
                "source_type": doc.source_type,
                "publisher": doc.publisher,
                "content": doc.content[:1000],
            }
            for doc in state.crawled_documents
        ]
        user_prompt = json.dumps(
            {
                "domain": state.request_context.domain,
                "subdomains": state.request_context.subdomains,
                "search_plan": {
                    "official_queries": state.search_plan.official_queries if state.search_plan else [],
                    "tutorial_queries": state.search_plan.tutorial_queries if state.search_plan else [],
                    "questions": [
                        {
                            "question": question.question,
                            "google_query": question.google_query,
                            "expected_info": question.expected_info,
                            "source_priority": question.source_priority,
                            "success_criteria": question.success_criteria,
                            "fallback_queries": question.fallback_queries,
                            "status": question.status,
                        }
                        for question in (state.search_plan.questions if state.search_plan else [])
                    ],
                },
                "search_history": state.search_history,
                "documents": documents_payload,
            },
            ensure_ascii=False,
        )
        try:
            payload = self._chat_client.complete_json(
                system_prompt=REFLECTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return ReflectionPlan(
                missing_aspects=[str(item).strip() for item in payload.get("missing_aspects", []) if str(item).strip()],
                supplementary_official_queries=[
                    str(item).strip()
                    for item in payload.get("supplementary_official_queries", [])
                    if str(item).strip()
                ],
                supplementary_tutorial_queries=[
                    str(item).strip()
                    for item in payload.get("supplementary_tutorial_queries", [])
                    if str(item).strip()
                ],
                candidate_official_domains=[
                    str(item).strip()
                    for item in payload.get("candidate_official_domains", state.candidate_official_domains)
                    if str(item).strip()
                ],
                reasoning=str(payload.get("reasoning", "")).strip() or "已完成首轮反思。",
            )
        except Exception:
            return self._fallback_reflection(state)

    @staticmethod
    def _fallback_reflection(state: QueryEngineState) -> ReflectionPlan:
        missing_aspects: list[str] = []
        supplementary_official_queries: list[str] = []
        supplementary_tutorial_queries: list[str] = []

        insufficient_questions = [
            question
            for question in (state.search_plan.questions if state.search_plan else [])
            if question.status == "insufficient"
        ]
        if insufficient_questions:
            for question in insufficient_questions:
                missing_aspects.append(f"{question.question}：检索结果不足或缺少权威支撑")
                priority_text = " ".join(question.source_priority).lower()
                if "tutorial" in priority_text or "blog" in priority_text or "guide" in priority_text:
                    supplementary_tutorial_queries.extend(question.fallback_queries or [question.google_query])
                else:
                    supplementary_official_queries.extend(question.fallback_queries or [question.google_query])
        elif not state.search_plan:
            official_docs = [doc for doc in state.crawled_documents if doc.source_type == "official"]
            tutorial_docs = [doc for doc in state.crawled_documents if doc.source_type == "tutorial"]
            if not official_docs:
                missing_aspects.append("缺少官方资料")
                supplementary_official_queries.append(f"{state.request_context.domain} official documentation")
            if not tutorial_docs:
                missing_aspects.append("缺少教程与最佳实践补充")
                supplementary_tutorial_queries.append(f"{state.request_context.domain} tutorial best practices")

        return ReflectionPlan(
            missing_aspects=missing_aspects,
            supplementary_official_queries=supplementary_official_queries[:2],
            supplementary_tutorial_queries=supplementary_tutorial_queries[:2],
            candidate_official_domains=state.candidate_official_domains[:3],
            reasoning="按官方覆盖度和教程补充情况完成首轮反思。",
        )
