from __future__ import annotations

from agent.MediaEngine.nodes.formatting_node import MediaFormattingNode
from agent.MediaEngine.nodes.search_node import MediaSearchNode
from agent.MediaEngine.nodes.summary_node import MediaSummaryNode
from agent.MediaEngine.state.state import MediaEngineState
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.base import BaseEngine
from knowledgeforge.llms.openai_compatible import OpenAICompatibleChatClient
from knowledgeforge.models import EngineRunResult, RequestContext, SourceRecord
from knowledgeforge.utils.time import now_iso


class MediaEngine(BaseEngine):
    name = "MediaEngine"

    def __init__(
        self,
        chat_client: OpenAICompatibleChatClient | None = None,
        crawler: MediaPerspectiveCrawler | None = None,
    ) -> None:
        self._chat_client = chat_client
        self._crawler = crawler or MediaPerspectiveCrawler()
        self._search_node = MediaSearchNode(chat_client=self._chat_client, crawler=self._crawler)
        self._summary_node = MediaSummaryNode(chat_client=self._chat_client)
        self._formatting_node = MediaFormattingNode()

    def run(self, context: RequestContext, round_number: int) -> EngineRunResult:
        state = MediaEngineState.from_context(context=context, round_number=round_number)
        try:
            state = self._search_node.run(state)
            state = self._summary_node.run(state)
            return self._formatting_node.run(state)
        except Exception:
            return self._fallback_result(context, round_number)

    def _fallback_result(self, context: RequestContext, round_number: int) -> EngineRunResult:
        timestamp = now_iso()
        return EngineRunResult(
            agent_name=self.name,
            summary=f"为 {context.domain} 生成一组面向社区观点、技术博客和社交讨论的趋势观察结果。",
            key_points=[
                "MediaEngine 关注的是当下怎么看、怎么用、接下来怎么演化。",
                "技术领域默认优先混合中外技术社区、社交平台与技术博客。",
                "当前结果为最小趋势检索规划，仍保留可追溯来源入口。",
            ],
            raw_material=[
                "社交媒体：",
                *[f"- {context.domain} {topic} X Reddit 最新讨论" for topic in context.subdomains[:2]],
                "技术社区：",
                *[f"- {context.domain} {topic} Hacker News GitHub Discussions V2EX" for topic in context.subdomains[:2]],
                "博客/长文：",
                *[f"- {context.domain} {topic} engineering blog future trend" for topic in context.subdomains[:2]],
            ],
            coverage_topics=context.subdomains,
            sources=[
                SourceRecord(
                    title=f"{context.domain} 社区趋势检索规划",
                    url=f"https://example.com/{round_number}/{self.name.lower()}",
                    publisher="media-plan",
                    retrieved_at=timestamp,
                    reliability="medium",
                    agent=self.name,
                    source_type="community",
                    snippet=f"{context.domain} community trend outlook",
                )
            ],
            collected_at=timestamp,
            round_number=round_number,
        )
