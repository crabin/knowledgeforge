from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar


NetworkResultT = TypeVar("NetworkResultT")
LlmResultT = TypeVar("LlmResultT")


@dataclass(slots=True)
class QueuedTaskSpec(Generic[NetworkResultT, LlmResultT]):
    task_id: str
    task_type: str
    payload: dict[str, Any]
    network_call: Callable[[], NetworkResultT]
    llm_call: Callable[[NetworkResultT], LlmResultT] | None = None


@dataclass(slots=True)
class QueuedTaskResult(Generic[NetworkResultT, LlmResultT]):
    task_id: str
    task_type: str
    payload: dict[str, Any]
    network_result: NetworkResultT | None = None
    llm_result: LlmResultT | None = None
    network_status: str = "pending"
    llm_status: str = "skipped"
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class RetrievalTaskQueue:
    """Shared queue for retrieval work across engines.

    Network-bound work is globally capped so QueryEngine / MediaEngine can
    submit tasks in parallel without exceeding the configured concurrency.
    LLM post-processing is optional and uses its own smaller worker pool.
    """

    def __init__(
        self,
        *,
        max_network_concurrency: int = 5,
        max_llm_concurrency: int = 2,
    ) -> None:
        self._network_executor = ThreadPoolExecutor(max_workers=max(1, max_network_concurrency))
        self._llm_executor = ThreadPoolExecutor(max_workers=max(1, max_llm_concurrency))

    def run_tasks(
        self,
        tasks: list[QueuedTaskSpec[NetworkResultT, LlmResultT]],
    ) -> list[QueuedTaskResult[NetworkResultT, LlmResultT]]:
        if not tasks:
            return []

        network_futures: dict[Future[QueuedTaskResult[NetworkResultT, LlmResultT]], str] = {}
        task_lookup = {task.task_id: task for task in tasks}
        llm_futures: dict[Future[tuple[str, LlmResultT]], str] = {}
        results_by_id: dict[str, QueuedTaskResult[NetworkResultT, LlmResultT]] = {}

        for task in tasks:
            future = self._network_executor.submit(self._run_network_stage, task)
            network_futures[future] = task.task_id

        for future in as_completed(network_futures):
            result = future.result()
            results_by_id[result.task_id] = result
            task = task_lookup[result.task_id]
            if task.llm_call is None or result.network_status != "completed" or result.network_result is None:
                continue
            llm_future = self._llm_executor.submit(task.llm_call, result.network_result)
            llm_futures[llm_future] = result.task_id
            result.llm_status = "in_progress"

        for future in as_completed(llm_futures):
            task_id = llm_futures[future]
            result = results_by_id[task_id]
            try:
                result.llm_result = future.result()
                result.llm_status = "completed"
            except Exception as exc:
                result.llm_status = "failed"
                result.error = str(exc)

        ordered_results: list[QueuedTaskResult[NetworkResultT, LlmResultT]] = []
        for task in tasks:
            ordered_results.append(results_by_id[task.task_id])
        return ordered_results

    @staticmethod
    def _run_network_stage(
        task: QueuedTaskSpec[NetworkResultT, LlmResultT],
    ) -> QueuedTaskResult[NetworkResultT, LlmResultT]:
        result = QueuedTaskResult[NetworkResultT, LlmResultT](
            task_id=task.task_id,
            task_type=task.task_type,
            payload=task.payload,
            network_status="in_progress",
        )
        try:
            result.network_result = task.network_call()
            result.network_status = "completed"
        except Exception as exc:
            result.network_status = "failed"
            result.error = str(exc)
        return result
