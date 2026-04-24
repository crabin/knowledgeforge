from __future__ import annotations

import json

from agent.QueryEngine.nodes.base_node import BaseQueryNode
from agent.QueryEngine.prompts.prompts import REFLECTION_SYSTEM_PROMPT
from agent.QueryEngine.state.state import QueryEngineState, ReflectionPlan
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient


class QueryReflectionNode(BaseQueryNode):
    def __init__(self, *, chat_client: OpenAICompatibleChatClient | None) -> None:
        self._chat_client = chat_client

    def run(self, state: QueryEngineState, **kwargs) -> QueryEngineState:
        reflection = self._build_reflection(state)
        state.reflection_plan = reflection
        state.reflection_notes.append(reflection.reasoning)
        if reflection.missing_aspects:
            state.observation_notes.extend(reflection.missing_aspects)
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
                },
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
        official_docs = [doc for doc in state.crawled_documents if doc.source_type == "official"]
        tutorial_docs = [doc for doc in state.crawled_documents if doc.source_type == "tutorial"]
        missing_aspects: list[str] = []
        supplementary_official_queries: list[str] = []
        supplementary_tutorial_queries: list[str] = []

        if not official_docs:
            missing_aspects.append("缺少官方资料")
            supplementary_official_queries.append(f"{state.request_context.domain} official documentation")
        if len(official_docs) < max(1, min(2, len(state.request_context.subdomains))):
            missing_aspects.append("官方主题覆盖仍偏窄")
            for topic in state.request_context.subdomains[:2]:
                supplementary_official_queries.append(f"{state.request_context.domain} {topic} official documentation")
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
