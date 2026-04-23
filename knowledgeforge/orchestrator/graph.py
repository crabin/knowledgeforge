from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.graph import END, StateGraph

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.QueryEngine.agent import QueryEngine
from knowledgeforge.evaluation.completeness import CompletenessEvaluator
from knowledgeforge.models import AgentMessage
from knowledgeforge.orchestrator.state import WorkflowState
from knowledgeforge.storage.markdown_writer import MarkdownKnowledgeWriter
from knowledgeforge.utils.time import now_iso


class KnowledgeGraphWorkflow:
    def __init__(
        self,
        insight_engine: InsightEngine,
        query_engine: QueryEngine,
        media_engine: MediaEngine,
        evaluator: CompletenessEvaluator,
        writer: MarkdownKnowledgeWriter,
    ) -> None:
        self._insight_engine = insight_engine
        self._query_engine = query_engine
        self._media_engine = media_engine
        self._evaluator = evaluator
        self._writer = writer
        self._graph = self._build_graph()

    def run(self, initial_state: WorkflowState) -> WorkflowState:
        return self._graph.invoke(initial_state)

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("collect_parallel", self._collect_parallel)
        graph.add_node("evaluate_completeness", self._evaluate_completeness)
        graph.add_node("write_markdown", self._write_markdown)
        graph.add_node("finish_incomplete", self._finish_incomplete)
        graph.set_entry_point("collect_parallel")
        graph.add_edge("collect_parallel", "evaluate_completeness")
        graph.add_conditional_edges(
            "evaluate_completeness",
            self._route_after_evaluation,
            {
                "write_markdown": "write_markdown",
                "finish_incomplete": "finish_incomplete",
            },
        )
        graph.add_edge("write_markdown", END)
        graph.add_edge("finish_incomplete", END)
        return graph.compile()

    def _collect_parallel(self, state: WorkflowState) -> dict[str, Any]:
        context = state["request_context"]
        round_number = state.get("round_number", 1)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                "InsightEngine": executor.submit(self._insight_engine.run, context, round_number),
                "QueryEngine": executor.submit(self._query_engine.run, context, round_number),
                "MediaEngine": executor.submit(self._media_engine.run, context, round_number),
            }
            outputs = {name: future.result() for name, future in futures.items()}

        messages = list(state.get("messages", []))
        messages.append(
            AgentMessage(
                role="assistant",
                content="三路采集已完成。",
                metadata={"timestamp": now_iso(), "round": round_number},
            )
        )
        return {
            "agent_outputs": outputs,
            "messages": messages,
            "task_status": "collected",
        }

    def _evaluate_completeness(self, state: WorkflowState) -> dict[str, Any]:
        completeness = self._evaluator.evaluate(
            state["request_context"],
            state["agent_outputs"],
        )
        return {
            "completeness": completeness,
            "task_status": completeness.status,
        }

    def _write_markdown(self, state: WorkflowState) -> dict[str, Any]:
        artifact = self._writer.write(
            context=state["request_context"],
            outputs=state["agent_outputs"],
            completeness=state["completeness"],
            round_number=state.get("round_number", 1),
        )
        return {
            "document_artifact": artifact,
            "task_status": "written",
        }

    def _finish_incomplete(self, state: WorkflowState) -> dict[str, Any]:
        return {
            "task_status": "supplement_required",
        }

    @staticmethod
    def _route_after_evaluation(state: WorkflowState) -> str:
        if state["completeness"].status == "pass":
            return "write_markdown"
        return "finish_incomplete"
