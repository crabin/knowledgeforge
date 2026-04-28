from __future__ import annotations

import json
from collections import Counter

from knowledgeforge.agent.MediaEngine.nodes.base_node import BaseMediaNode
from knowledgeforge.agent.MediaEngine.prompts.prompts import MEDIA_SUMMARY_SYSTEM_PROMPT
from knowledgeforge.agent.MediaEngine.state.state import MediaEngineState
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient


class MediaSummaryNode(BaseMediaNode):
    def __init__(self, *, chat_client: OpenAICompatibleChatClient | None) -> None:
        self._chat_client = chat_client

    def run(self, state: MediaEngineState, **kwargs) -> MediaEngineState:
        if self._chat_client is None:
            state.summary_payload = self._fallback_summary(state)
            return state

        documents_payload = [
            {
                "title": doc.title,
                "url": doc.url,
                "platform_type": doc.platform_type,
                "publisher": doc.publisher,
                "content": doc.content[:1400],
            }
            for doc in state.crawled_documents
        ]
        user_prompt = json.dumps(
            {
                "domain": state.request_context.domain,
                "subdomains": state.request_context.subdomains,
                "time_window": state.request_context.time_window,
                "search_plan": {
                    "social_queries": state.search_plan.social_queries if state.search_plan else [],
                    "community_queries": state.search_plan.community_queries if state.search_plan else [],
                    "blog_queries": state.search_plan.blog_queries if state.search_plan else [],
                    "reasoning": state.search_plan.reasoning if state.search_plan else "",
                },
                "reflection": {
                    "missing_aspects": state.reflection_plan.missing_aspects if state.reflection_plan else [],
                    "reasoning": state.reflection_plan.reasoning if state.reflection_plan else "",
                },
                "documents": documents_payload,
            },
            ensure_ascii=False,
        )
        try:
            state.summary_payload = self._chat_client.complete_json(
                system_prompt=MEDIA_SUMMARY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception:
            state.summary_payload = self._fallback_summary(state)
        return state

    @staticmethod
    def _fallback_summary(state: MediaEngineState) -> dict[str, object]:
        documents = state.crawled_documents
        social_docs = [doc for doc in documents if doc.platform_type == "social"]
        community_docs = [doc for doc in documents if doc.platform_type == "community"]
        blog_docs = [doc for doc in documents if doc.platform_type == "blog"]
        platform_counter = Counter(doc.platform_type for doc in documents)
        dominant_platform = platform_counter.most_common(1)[0][0] if platform_counter else "community"
        return {
            "summary": (
                f"{state.request_context.domain} 当前在{dominant_platform}与相关博客中的讨论重点，"
                "主要集中在实际采用、能力边界和后续演化方向。"
            ),
            "current_sentiment": "整体讨论偏积极但审慎，更关注真实落地与边界条件。",
            "mainstream_views": [
                *[f"{doc.title}" for doc in community_docs[:2]],
                *[f"{doc.title}" for doc in blog_docs[:1]],
            ]
            or ["社区更关注落地方式、使用成本与可扩展性。"],
            "debates": [
                f"{state.request_context.domain} 在复杂场景下的适用边界仍有争议。",
                "社区讨论通常围绕性能、可维护性和学习成本展开。",
            ],
            "adoption_signals": [
                *[f"{doc.title}" for doc in social_docs[:1]],
                *[f"{doc.title}" for doc in blog_docs[:2]],
            ]
            or ["博客和社区文章开始将该主题纳入实践案例与经验总结。"],
            "future_directions": [
                "未来 6-12 个月的讨论会继续聚焦工程化落地、配套工具与最佳实践沉淀。",
            ],
            "coverage_topics": state.request_context.subdomains,
        }
