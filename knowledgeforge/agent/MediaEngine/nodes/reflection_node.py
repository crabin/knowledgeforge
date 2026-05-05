from __future__ import annotations

import json

from knowledgeforge.agent.MediaEngine.nodes.base_node import BaseMediaNode
from knowledgeforge.agent.MediaEngine.nodes.search_node import MediaSearchNode
from knowledgeforge.agent.MediaEngine.prompts.prompts import MEDIA_REFLECTION_SYSTEM_PROMPT
from knowledgeforge.agent.MediaEngine.state.state import MediaEngineState, MediaReflectionPlan
from knowledgeforge.server.llms.openai_compatible import OpenAICompatibleChatClient


class MediaReflectionNode(BaseMediaNode):
    def __init__(self, *, chat_client: OpenAICompatibleChatClient | None) -> None:
        self._chat_client = chat_client

    def run(self, state: MediaEngineState, **kwargs) -> MediaEngineState:
        reflection = self._build_reflection(state)
        state.reflection_plan = reflection
        state.reflection_notes.append(reflection.reasoning)
        if reflection.missing_aspects:
            state.observation_notes.extend(reflection.missing_aspects)
        return state

    def _build_reflection(self, state: MediaEngineState) -> MediaReflectionPlan:
        if self._chat_client is None:
            return self._fallback_reflection(state)

        documents_payload = [
            {
                "title": doc.title,
                "url": doc.url,
                "platform_type": doc.platform_type,
                "publisher": doc.publisher,
                "content": doc.content[:1000],
            }
            for doc in state.crawled_documents
        ]
        user_prompt = json.dumps(
            {
                "domain": state.request_context.domain,
                "subdomains": state.request_context.subdomains,
                "time_window": state.request_context.time_window,
                "documents": documents_payload,
            },
            ensure_ascii=False,
        )
        try:
            payload = self._chat_client.complete_json(
                system_prompt=MEDIA_REFLECTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            existing_social = list(state.search_plan.social_queries) if state.search_plan else []
            existing_community = list(state.search_plan.community_queries) if state.search_plan else []
            existing_blog = list(state.search_plan.blog_queries) if state.search_plan else []
            return MediaReflectionPlan(
                missing_aspects=[str(item).strip() for item in payload.get("missing_aspects", []) if str(item).strip()],
                supplementary_social_queries=MediaSearchNode._dedupe_queries(
                    [str(item).strip() for item in payload.get("supplementary_social_queries", []) if str(item).strip()],
                    limit=1,
                    existing_queries=existing_social,
                ),
                supplementary_community_queries=MediaSearchNode._dedupe_queries(
                    [
                        str(item).strip()
                        for item in payload.get("supplementary_community_queries", [])
                        if str(item).strip()
                    ],
                    limit=2,
                    existing_queries=existing_community,
                ),
                supplementary_blog_queries=MediaSearchNode._dedupe_queries(
                    [str(item).strip() for item in payload.get("supplementary_blog_queries", []) if str(item).strip()],
                    limit=1,
                    existing_queries=existing_blog,
                ),
                reasoning=str(payload.get("reasoning", "")).strip() or "已完成首轮趋势反思。",
            )
        except Exception:
            return self._fallback_reflection(state)

    @staticmethod
    def _fallback_reflection(state: MediaEngineState) -> MediaReflectionPlan:
        social_docs = [doc for doc in state.crawled_documents if doc.platform_type == "social"]
        community_docs = [doc for doc in state.crawled_documents if doc.platform_type == "community"]
        blog_docs = [doc for doc in state.crawled_documents if doc.platform_type == "blog"]
        missing_aspects: list[str] = []
        supplementary_social_queries: list[str] = []
        supplementary_community_queries: list[str] = []
        supplementary_blog_queries: list[str] = []
        topic = state.request_context.subdomains[0] if state.request_context.subdomains else state.request_context.domain

        if not community_docs:
            missing_aspects.append("缺少技术社区主流看法")
            supplementary_community_queries.append(f"{state.request_context.domain} {topic} community discussion")
        if not social_docs:
            missing_aspects.append("缺少社交平台即时热度")
            supplementary_social_queries.append(f"{state.request_context.domain} {topic} x reddit trend")
        if not blog_docs:
            missing_aspects.append("缺少博客长文中的采用信号")
            supplementary_blog_queries.append(f"{state.request_context.domain} {topic} engineering blog adoption")

        return MediaReflectionPlan(
            missing_aspects=missing_aspects,
            supplementary_social_queries=supplementary_social_queries[:2],
            supplementary_community_queries=supplementary_community_queries[:2],
            supplementary_blog_queries=supplementary_blog_queries[:2],
            reasoning="按社交热度、技术社区和博客长文覆盖情况完成首轮反思。",
        )
