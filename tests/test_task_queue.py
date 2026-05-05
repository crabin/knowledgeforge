from __future__ import annotations

from threading import Lock
from time import sleep

from knowledgeforge.server.runtime.task_queue import QueuedTaskSpec, RetrievalTaskQueue


def test_retrieval_task_queue_caps_network_concurrency() -> None:
    active = 0
    max_seen = 0
    lock = Lock()

    def make_task(task_id: str):
        def network_call() -> str:
            nonlocal active, max_seen
            with lock:
                active += 1
                max_seen = max(max_seen, active)
            sleep(0.05)
            with lock:
                active -= 1
            return task_id

        return QueuedTaskSpec[str, None](
            task_id=task_id,
            task_type="network_query_and_optional_llm_summary",
            payload={"task_id": task_id},
            network_call=network_call,
        )

    queue = RetrievalTaskQueue(max_network_concurrency=2, max_llm_concurrency=1)
    results = queue.run_tasks([make_task(f"T{index}") for index in range(5)])

    assert [result.network_result for result in results] == ["T0", "T1", "T2", "T3", "T4"]
    assert max_seen <= 2
