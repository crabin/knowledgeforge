from __future__ import annotations

import json

from agent.QueryEngine.nodes.base_node import BaseQueryNode
from agent.QueryEngine.prompts.prompts import SUMMARY_SYSTEM_PROMPT
from agent.QueryEngine.state.state import QueryEngineState
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient


class QuerySummaryNode(BaseQueryNode):
    def __init__(self, *, chat_client: OpenAICompatibleChatClient | None) -> None:
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
                "documents": documents_payload,
            },
            ensure_ascii=False,
        )
        try:
            state.summary_payload = self._chat_client.complete_json(
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception:
            state.summary_payload = self._fallback_summary(state)
        return state

    @staticmethod
    def _fallback_summary(state: QueryEngineState) -> dict[str, object]:
        official_docs = [doc for doc in state.crawled_documents if doc.source_type == "official"]
        tutorial_docs = [doc for doc in state.crawled_documents if doc.source_type == "tutorial"]
        return {
            "summary": f"{state.request_context.domain} 的 QueryEngine 已优先检索官方文档，并用教程资料补充落地用法。",
            "key_points": [
                "官方文档是当前结果的主要依据。",
                "教程资料只用于补充步骤、案例与经验。",
                "当前结果已按知识主题聚合为可追溯来源列表。",
            ],
            "coverage_topics": state.request_context.subdomains,
            "official_findings": [doc.title for doc in official_docs[:3]],
            "tutorial_findings": [doc.title for doc in tutorial_docs[:3]],
        }
