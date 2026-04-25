from __future__ import annotations

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.models import EnginePlan, EnginePlanItem, RequestContext


class FailingCrawler:
    def search(self, **kwargs):
        raise AssertionError("plan() must not call crawler.search")

    def fetch_documents(self, hits, *, max_documents: int = 8):
        raise AssertionError("plan() must not call crawler.fetch_documents")


class RecordingQueryCrawler:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, **kwargs):
        self.queries.append(kwargs["query"])
        return []

    def fetch_documents(self, hits, *, max_documents: int = 8):
        return []


class RecordingMediaCrawler:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def search(self, **kwargs):
        self.queries.append((kwargs["platform_type"], kwargs["query"]))
        return []

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

    insight_plan = InsightEngine().plan(context, 1)
    query_plan = QueryEngine(chat_client=None, crawler=FailingCrawler()).plan(context, 1)
    media_plan = MediaEngine(chat_client=None, crawler=FailingCrawler()).plan(context, 1)

    assert insight_plan.agent_name == "InsightEngine"
    assert query_plan.agent_name == "QueryEngine"
    assert media_plan.agent_name == "MediaEngine"
    assert insight_plan.plan_items
    assert query_plan.plan_items
    assert media_plan.plan_items
    assert all(plan.status == "awaiting_confirmation" for plan in [insight_plan, query_plan, media_plan])


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
