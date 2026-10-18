from __future__ import annotations

import multiprocessing as mp

from lightup.algorithms.search import SearchLimits, SearchResult, SearchStatus
from lightup.benchmark.runner import BenchmarkRow
from lightup.benchmark.worker import benchmark_worker
from lightup.core.model import Puzzle
from lightup.worker import solver_worker


def test_spawn_worker_pauses_steps_and_returns_solution() -> None:
    context = mp.get_context("spawn")
    messages = context.Queue(maxsize=64)
    stop_event = context.Event()
    pause_event = context.Event()
    step_event = context.Event()
    pause_event.set()
    interval = context.Value("i", 1)
    delay = context.Value("d", 0.0)
    process = context.Process(
        target=solver_worker,
        args=(
            Puzzle(((None, None), (None, None))),
            "A*",
            SearchLimits(timeout_seconds=5, node_limit=100),
            messages,
            stop_event,
            pause_event,
            step_event,
            interval,
            delay,
        ),
    )
    process.start()
    try:
        kind, progress = messages.get(timeout=5)
        assert kind == "progress"
        assert progress["kind"] == "expand"
        assert process.is_alive()  # The worker is waiting while paused.
        step_event.set()
        kind, _ = messages.get(timeout=5)  # A sampled update is emitted for the stepped state.
        assert kind == "progress"
        pause_event.clear()
        deadline_messages = 0
        result = None
        while deadline_messages < 20:
            kind, payload = messages.get(timeout=5)
            if kind == "result":
                result = payload
                break
            deadline_messages += 1
        assert isinstance(result, SearchResult)
        assert result.status is SearchStatus.SOLVED
    finally:
        stop_event.set()
        pause_event.clear()
        step_event.set()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        messages.close()


def test_spawn_benchmark_worker_compares_both_algorithms_on_one_input() -> None:
    context = mp.get_context("spawn")
    messages = context.Queue(maxsize=64)
    stop_event = context.Event()
    process = context.Process(
        target=benchmark_worker,
        args=(
            Puzzle(((None, None), (None, None)), "benchmark-fixture", "test", 9),
            SearchLimits(timeout_seconds=5, node_limit=100),
            messages,
            stop_event,
        ),
    )
    process.start()
    try:
        kind, rows = messages.get(timeout=10)
        assert kind == "benchmark"
        assert [row.algorithm for row in rows] == ["DFS", "ASTAR"]
        assert all(isinstance(row, BenchmarkRow) for row in rows)
        assert all(row.puzzle_id == "benchmark-fixture" for row in rows)
    finally:
        stop_event.set()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        messages.close()
