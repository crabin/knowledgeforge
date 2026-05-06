from __future__ import annotations

import json

from knowledgeforge.agent.QueryEngine.nodes.base_node import BaseQueryNode, QueryEventCallback
from knowledgeforge.agent.QueryEngine.prompts.prompts import SUMMARY_SYSTEM_PROMPT
from knowledgeforge.agent.QueryEngine.state.state import QueryEngineState
from knowledgeforge.server.llms.openai_compatible import OpenAICompatibleChatClient


class QuerySummaryNode(BaseQueryNode):
    def __init__(
        self,
        *,
        chat_client: OpenAICompatibleChatClient | None,
        event_callback: QueryEventCallback | None = None,
    ) -> None:
        super().__init__(event_callback=event_callback)
        self._chat_client = chat_client

    def run(self, state: QueryEngineState, **kwargs) -> QueryEngineState:
        if self._chat_client is None:
            state.summary_payload = self._fallback_summary(state)
            return state

        documents_payload = [
            {
                "title": doc.title,
                "url": doc.url,
                "source_type": doc.source_type,
                "publisher": doc.publisher,
                "content": doc.content[:1400],
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
                    "official_domains": state.search_plan.official_domains if state.search_plan else [],
                },
                "reflection": {
                    "missing_aspects": state.reflection_plan.missing_aspects if state.reflection_plan else [],
                    "reasoning": state.reflection_plan.reasoning if state.reflection_plan else "",
                },
                "deep_search": {
                    "search_intent": state.search_intent,
                    "broad_queries": state.broad_queries,
                    "verification_queries": state.verification_queries,
                    "candidate_concepts": [
                        {
                            "name": concept.name,
                            "canonical_name": concept.canonical_name,
                            "mentions": concept.mentions,
                            "source_urls": concept.source_urls,
                            "source_types": concept.source_types,
                            "preliminary_category": concept.preliminary_category,
                        }
                        for concept in state.candidate_concepts
                    ],
                    "verification_matrix": [
                        {
                            "canonical_name": item.canonical_name,
                            "support_count": item.support_count,
                            "reliable_support_count": item.reliable_support_count,
                            "category": item.category,
                            "included": item.included,
                            "reason": item.reason,
                            "one_sentence_role": item.one_sentence_role,
                        }
                        for item in state.verification_matrix
                    ],
                    "structured_answer": [
                        {"title": section.title, "items": section.items}
                        for section in state.structured_answer_sections
                    ],
                    "excluded_concepts": state.excluded_concepts,
                    "source_cross_check": state.source_cross_check,
                    "short_summary": state.short_summary,
                },
                "documents": documents_payload,
            },
            ensure_ascii=False,
        )
        try:
            state.summary_payload = self._chat_client.complete_json(
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            self._record_event(
                state,
                "query_summary_llm_completed",
                {"payload_keys": sorted(state.summary_payload.keys())},
            )
        except Exception:
            state.summary_payload = self._fallback_summary(state)
            self._record_event(state, "query_summary_fallback_used", {"reason": "llm_summary_failed"})
        return state

    @staticmethod
    def _fallback_summary(state: QueryEngineState) -> dict[str, object]:
        official_docs = [doc for doc in state.crawled_documents if doc.source_type == "official"]
        tutorial_docs = [doc for doc in state.crawled_documents if doc.source_type == "tutorial"]
        return {
            "summary": state.short_summary or f"{state.request_context.domain} 的 QueryEngine 已优先检索官方文档，并用教程资料补充落地用法。",
            "short_summary": state.short_summary,
            "key_points": [
                *[
                    f"{item.canonical_name}：{item.one_sentence_role}"
                    for item in state.verification_matrix
                    if item.included
                ][:4],
                "官方文档是当前结果的主要依据。",
                "教程资料只用于补充步骤、案例与经验。",
            ],
            "coverage_topics": state.request_context.subdomains,
            "official_findings": [doc.title for doc in official_docs[:3]],
            "tutorial_findings": [doc.title for doc in tutorial_docs[:3]],
            "structured_answer": [
                {"title": section.title, "items": section.items}
                for section in state.structured_answer_sections
            ],
            "excluded_concepts": state.excluded_concepts,
            "source_cross_check": state.source_cross_check,
        }
