"""Spawn-safe entry point for the in-app side-by-side benchmark."""

from __future__ import annotations

import traceback
from multiprocessing.queues import Queue
from typing import Any

from lightup.algorithms.search import SearchLimits
from lightup.benchmark.runner import benchmark
from lightup.core.model import Puzzle


def benchmark_worker(puzzle: Puzzle, limits: SearchLimits, messages: Queue, stop_event: Any) -> None:
    try:
        rows = benchmark(puzzle, ("dfs", "astar"), 1, limits, cancelled=stop_event.is_set)
        messages.put(("benchmark", rows), timeout=2.0)
    except Exception as exc:
        try:
            messages.put(("error", f"{exc}\n{traceback.format_exc()}"), timeout=1.0)
        except Exception:
            pass
