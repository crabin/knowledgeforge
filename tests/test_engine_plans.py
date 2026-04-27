from __future__ import annotations

import threading
import time

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.models import EnginePlan, EnginePlanItem, RequestContext
from knowledgeforge.storage.realtime_reviewer import RealtimeReviewResult


class FakePlanChatClient:
    def complete_json(self, *, system_prompt: str, user_prompt: str):
        if "术语归一化助手" in system_prompt:
            return {
                "normalized_domain": "知识工程",
                "aliases": ["知识工程"],
                "search_terms": ["知识工程"],
                "reasoning": "测试归一化。",
            }
        if "InsightEngine" in system_prompt:
            return {
                "items": [
                    {
                        "title": "梳理本地上下文",
                        "action": "读取 intake 上下文与历史任务",
                        "targets": ["本地上下文"],
                        "success_criteria": ["形成内部线索"],
                        "source_priority": ["intake context"],
                    }
                ],
                "reasoning": "先确认本地线索。",
            }
        if "QueryEngine 搜索规划器" in system_prompt:
            return {
                "questions": [
                    {
                        "question": "确认官方事实",
                        "google_query": "knowledge engineering official documentation",
                        "search_targets": ["官方事实"],
                        "expected_info": ["官方事实"],
                        "source_priority": ["official documentation"],
                        "success_criteria": ["命中官方来源"],
                        "fallback_queries": [],
                    }
                ],
                "official_queries": ["knowledge engineering official documentation"],
                "tutorial_queries": [],
                "official_domains": [],
                "reasoning": "官方优先。",
            }
        return {
            "social_queries": ["knowledge engineering social discussion"],
            "community_queries": ["knowledge engineering community discussion"],
            "blog_queries": ["knowledge engineering engineering blog"],
            "reasoning": "社区观点计划。",
            "is_technical": True,
        }


class FailingChatClient:
    def complete_json(self, *, system_prompt: str, user_prompt: str):
        raise RuntimeError("llm unavailable")


class FailingCrawler:
    def search(self, **kwargs):
        raise AssertionError("plan() must call a crawler that can return candidate links")

    def fetch_documents(self, hits, *, max_documents: int = 8):
        raise AssertionError("plan() must not call crawler.fetch_documents")


class RecordingQueryCrawler:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, **kwargs):
        from agent.QueryEngine.state.state import SearchHit

        self.queries.append(kwargs["query"])
        return [
            SearchHit(
                title=f"Hit for {kwargs['query']}",
                url=f"https://example.com/{kwargs['query'].replace(' ', '-')}",
                snippet="official reference",
                source_type=kwargs.get("source_type", "official"),
                score=1.0,
            )
        ]

    def fetch_documents(self, hits, *, max_documents: int = 8):
        return []


class RecordingMediaCrawler:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def search(self, **kwargs):
        from agent.MediaEngine.state.state import MediaSearchHit

        self.queries.append((kwargs["platform_type"], kwargs["query"]))
        return [
            MediaSearchHit(
                title=f"Hit for {kwargs['query']}",
                url=f"https://example.com/{kwargs['platform_type']}/{kwargs['query'].replace(' ', '-')}",
                snippet="community trend",
                platform_type=kwargs["platform_type"],
                score=1.0,
            )
        ]

    def fetch_documents(self, hits, *, max_documents: int = 8):
        return []


def _context() -> RequestContext:
    return RequestContext(
        domain="知识工程",
        subdomains=["工作流编排", "知识沉淀"],
        time_window="latest",
        focus_points=["状态恢复"],
        constraints=[],
        initial_strategy=["知识工程 工作流编排 official documentation"],
    )


def test_three_engines_generate_plans_without_execution() -> None:
    context = _context()
    chat_client = FakePlanChatClient()

    insight_plan = InsightEngine(chat_client=chat_client).plan(context, 1)
    query_plan = QueryEngine(chat_client=chat_client, crawler=RecordingQueryCrawler()).plan(context, 1)
    media_plan = MediaEngine(chat_client=chat_client, crawler=RecordingMediaCrawler()).plan(context, 1)

    assert insight_plan.agent_name == "InsightEngine"
    assert query_plan.agent_name == "QueryEngine"
    assert media_plan.agent_name == "MediaEngine"
    assert insight_plan.plan_items
    assert query_plan.plan_items
    assert media_plan.plan_items
    assert all(plan.status == "awaiting_confirmation" for plan in [insight_plan, query_plan, media_plan])


def test_query_and_media_plans_dedupe_repeated_queries() -> None:
    context = _context()

    class DuplicatePlanChatClient(FakePlanChatClient):
        def complete_json(self, *, system_prompt: str, user_prompt: str):
            payload = super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
            if "QueryEngine 搜索规划器" in system_prompt:
                payload["questions"] = [payload["questions"][0], dict(payload["questions"][0])]
            elif "MediaEngine" in system_prompt:
                payload["community_queries"] = [
                    'site:news.ycombinator.com "knowledge engineering" discussion',
                    'site:github.com/discussions "knowledge engineering" community discussion',
                    'site:v2ex.com "knowledge engineering" forum discussion',
                    'site:reddit.com "knowledge engineering" community discussion',
                ]
            return payload

    chat_client = DuplicatePlanChatClient()
    query_plan = QueryEngine(chat_client=chat_client, crawler=RecordingQueryCrawler()).plan(context, 1)
    media_plan = MediaEngine(chat_client=chat_client, crawler=RecordingMediaCrawler()).plan(context, 1)

    assert len(query_plan.plan_items) == 1
    assert [
        item.query_or_action
        for item in media_plan.plan_items
        if "community" in item.source_priority
    ] == ['site:news.ycombinator.com "knowledge engineering" discussion']


def test_plan_generation_requires_llm() -> None:
    context = _context()

    for engine in [
        InsightEngine(chat_client=None),
        QueryEngine(chat_client=None, crawler=FailingCrawler()),
        MediaEngine(chat_client=None, crawler=FailingCrawler()),
    ]:
        try:
            engine.plan(context, 1)
        except RuntimeError as exc:
            assert "requires an LLM chat client" in str(exc)
        else:
            raise AssertionError("plan() must fail when LLM client is missing")


def test_plan_generation_failure_is_not_rule_fallback() -> None:
    context = _context()

    for engine in [
        InsightEngine(chat_client=FailingChatClient()),
        QueryEngine(chat_client=FailingChatClient(), crawler=FailingCrawler()),
        MediaEngine(chat_client=FailingChatClient(), crawler=FailingCrawler()),
    ]:
        try:
            engine.plan(context, 1)
        except RuntimeError:
            pass
        else:
            raise AssertionError("plan() must fail when LLM planning fails")


def test_query_engine_executes_approved_plan() -> None:
    context = _context()
    crawler = RecordingQueryCrawler()
    plan = EnginePlan(
        agent_name="QueryEngine",
        plan_items=[
            EnginePlanItem(
                plan_item_id="Q1",
                title="确认权威事实",
                query_or_action="custom approved query",
                targets=["权威事实"],
                success_criteria=["执行已确认 query"],
                source_priority=["official documentation"],
            )
        ],
        reasoning="人工确认计划",
        status="approved",
        created_at="2026-04-25T00:00:00+09:00",
        approved_at="2026-04-25T00:01:00+09:00",
    )

    result = QueryEngine(chat_client=None, crawler=crawler).run(context, 1, approved_plan=plan)

    assert crawler.queries[0] == "custom approved query"
    assert result.agent_name == "QueryEngine"
    assert any(entry["event"] == "query_plan_created" for entry in result.execution_log)


def test_query_engine_reviews_files_after_plan_item_completion() -> None:
    context = _context()
    context.task_id = "task-query-review"
    crawler = RecordingQueryCrawler()
    reviewed = []

    def review_callback(task_id, candidate):
        reviewed.append((task_id, candidate))
        return RealtimeReviewResult(
            saved_paths=["save/知识工程/工作流编排/q1.md"],
            index_path="save/知识工程/README.md",
            status="saved",
        )

    class HitCrawler(RecordingQueryCrawler):
        def search(self, **kwargs):
            from agent.QueryEngine.state.state import SearchHit

            self.queries.append(kwargs["query"])
            return [
                SearchHit(
                    title="Official Hit",
                    url="https://example.com/docs",
                    snippet="official reference",
                    source_type="official",
                    score=1.0,
                )
            ]

        def fetch_documents(self, hits, *, max_documents: int = 8):
            from agent.QueryEngine.state.state import CrawledDocument

            return [
                CrawledDocument(
                    title=hit.title,
                    url=hit.url,
                    snippet=hit.snippet,
                    content="official reference content",
                    source_type=hit.source_type,
                    publisher=hit.publisher,
                    score=hit.score,
                )
                for hit in hits
            ]

    plan = EnginePlan(
        agent_name="QueryEngine",
        plan_items=[
            EnginePlanItem(
                plan_item_id="Q1",
                title="确认权威事实",
                query_or_action="custom approved query",
                targets=["权威事实"],
                success_criteria=["执行已确认 query"],
                source_priority=["official documentation"],
            )
        ],
        reasoning="人工确认计划",
        status="approved",
        created_at="2026-04-25T00:00:00+09:00",
    )

    result = QueryEngine(
        chat_client=None,
        crawler=HitCrawler(),
        realtime_file_callback=review_callback,
    ).run(context, 1, approved_plan=plan)

    assert reviewed
    assert reviewed[0][0] == "task-query-review"
    assert reviewed[0][1].plan_item_id == "Q1"
    assert reviewed[0][1].agent == "QueryEngine"
    assert any(entry["event"] == "query_realtime_file_reviewed" for entry in result.execution_log)


def test_query_engine_limits_concurrent_network_tasks_to_five() -> None:
    context = _context()

    class SlowCrawler(RecordingQueryCrawler):
        def __init__(self) -> None:
            super().__init__()
            self._lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def search(self, **kwargs):
            from agent.QueryEngine.state.state import SearchHit

            with self._lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            self.queries.append(kwargs["query"])
            time.sleep(0.05)
            with self._lock:
                self.active -= 1
            return [
                SearchHit(
                    title=f"Hit for {kwargs['query']}",
                    url=f"https://example.com/{kwargs['query'].replace(' ', '-')}",
                    snippet="official reference",
                    source_type="official",
                    score=1.0,
                )
            ]

        def fetch_documents(self, hits, *, max_documents: int = 8):
            from agent.QueryEngine.state.state import CrawledDocument

            return [
                CrawledDocument(
                    title=hit.title,
                    url=hit.url,
                    snippet=hit.snippet,
                    content="official reference content",
                    source_type=hit.source_type,
                    publisher=hit.publisher,
                    score=hit.score,
                )
                for hit in hits
            ]

    crawler = SlowCrawler()
    plan = EnginePlan(
        agent_name="QueryEngine",
        plan_items=[
            EnginePlanItem(
                plan_item_id=f"Q{i + 1}",
                title=f"问题 {i + 1}",
                query_or_action=f"query {i + 1}",
                targets=["权威事实"],
                success_criteria=["执行查询"],
                source_priority=["official documentation"],
            )
            for i in range(7)
        ],
        reasoning="并发控制测试",
        status="approved",
        created_at="2026-04-27T00:00:00+09:00",
    )

    QueryEngine(
        chat_client=None,
        crawler=crawler,
        max_concurrent_network_tasks=5,
    ).run(context, 1, approved_plan=plan)

    assert len(crawler.queries) == 7
    assert crawler.max_active <= 5


def test_query_engine_uses_fallback_query_when_primary_search_fails() -> None:
    context = _context()

    class FallbackCrawler(RecordingQueryCrawler):
        def search(self, **kwargs):
            from agent.QueryEngine.state.state import SearchHit

            self.queries.append(kwargs["query"])
            if kwargs["query"] == "primary query":
                raise RuntimeError("google browser timeout")
            return [
                SearchHit(
                    title="Fallback Official Hit",
                    url="https://example.com/fallback-docs",
                    snippet="fallback official reference",
                    source_type="official",
                    score=1.0,
                )
            ]

        def fetch_documents(self, hits, *, max_documents: int = 8):
            from agent.QueryEngine.state.state import CrawledDocument

            return [
                CrawledDocument(
                    title=hit.title,
                    url=hit.url,
                    snippet=hit.snippet,
                    content="fallback official content",
                    source_type=hit.source_type,
                    publisher=hit.publisher,
                    score=hit.score,
                )
                for hit in hits
            ]

    crawler = FallbackCrawler()
    plan = EnginePlan(
        agent_name="QueryEngine",
        plan_items=[
            EnginePlanItem(
                plan_item_id="Q1",
                title="确认权威事实",
                query_or_action="primary query",
                targets=["权威事实"],
                success_criteria=["执行 fallback 查询"],
                fallbacks=["fallback query"],
                source_priority=["official documentation"],
            )
        ],
        reasoning="失败兜底测试",
        status="approved",
        created_at="2026-04-27T00:00:00+09:00",
    )

    result = QueryEngine(chat_client=None, crawler=crawler).run(context, 1, approved_plan=plan)

    assert crawler.queries == ["primary query", "fallback query"]
    assert any(entry["event"] == "query_search_failed" for entry in result.execution_log)
    assert any(source.url == "https://example.com/fallback-docs" for source in result.sources)


def test_media_engine_executes_approved_plan() -> None:
    context = _context()
    crawler = RecordingMediaCrawler()
    plan = EnginePlan(
        agent_name="MediaEngine",
        plan_items=[
            EnginePlanItem(
                plan_item_id="M-C1",
                title="确认社区观点",
                query_or_action="custom community query",
                targets=["社区观点"],
                success_criteria=["执行已确认社区 query"],
                source_priority=["community"],
            )
        ],
        reasoning="人工确认计划",
        status="approved",
        created_at="2026-04-25T00:00:00+09:00",
        approved_at="2026-04-25T00:01:00+09:00",
    )

    result = MediaEngine(chat_client=None, crawler=crawler).run(context, 1, approved_plan=plan)

    assert crawler.queries[0] == ("community", "custom community query")
    assert result.agent_name == "MediaEngine"
    assert any(entry["event"] == "media_search_executed" for entry in result.execution_log)
    assert any(
        entry["event"] == "media_search_executed"
        and entry["details"].get("plan_item_id") == "M-C1"
        for entry in result.execution_log
    )


def test_media_engine_reviews_files_after_query_item_completion() -> None:
    context = _context()
    context.task_id = "task-media-review"
    reviewed = []

    def review_callback(task_id, candidate):
        reviewed.append((task_id, candidate))
        return RealtimeReviewResult(
            saved_paths=["save/知识工程/工作流编排/m1.md"],
            index_path="save/知识工程/README.md",
            status="saved",
        )

    class HitMediaCrawler(RecordingMediaCrawler):
        def search(self, **kwargs):
            from agent.MediaEngine.state.state import MediaSearchHit

            self.queries.append((kwargs["platform_type"], kwargs["query"]))
            return [
                MediaSearchHit(
                    title="Community Hit",
                    url="https://example.com/thread",
                    snippet="community trend",
                    platform_type=kwargs["platform_type"],
                    score=1.0,
                )
            ]

        def fetch_documents(self, hits, *, max_documents: int = 8):
            from agent.MediaEngine.state.state import MediaCrawledDocument

            return [
                MediaCrawledDocument(
                    title=hit.title,
                    url=hit.url,
                    snippet=hit.snippet,
                    content="community trend content",
                    platform_type=hit.platform_type,
                    publisher=hit.publisher,
                    score=hit.score,
                )
                for hit in hits
            ]

    plan = EnginePlan(
        agent_name="MediaEngine",
        plan_items=[
            EnginePlanItem(
                plan_item_id="M-C1",
                title="确认社区观点",
                query_or_action="custom community query",
                targets=["社区观点"],
                success_criteria=["执行已确认社区 query"],
                source_priority=["community"],
            )
        ],
        reasoning="人工确认计划",
        status="approved",
        created_at="2026-04-25T00:00:00+09:00",
    )

    result = MediaEngine(
        chat_client=None,
        crawler=HitMediaCrawler(),
        realtime_file_callback=review_callback,
    ).run(context, 1, approved_plan=plan)

    assert reviewed
    assert reviewed[0][0] == "task-media-review"
    assert reviewed[0][1].agent == "MediaEngine"
    assert reviewed[0][1].platform_type == "community"
    assert any(entry["event"] == "media_realtime_file_reviewed" for entry in result.execution_log)
