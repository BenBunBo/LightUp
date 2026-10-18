"""Spawn-safe multiprocessing entry point used by the Pygame interface."""

from __future__ import annotations

import queue
import time
import traceback
from dataclasses import asdict
from multiprocessing.queues import Queue
from typing import Any

from lightup.algorithms.search import SearchEvent, SearchLimits, astar, depth_first_search
from lightup.core.model import Puzzle


def solver_worker(
    puzzle: Puzzle,
    algorithm: str,
    limits: SearchLimits,
    messages: Queue,
    stop_event: Any,
    pause_event: Any,
    step_event: Any,
    sampling_interval: Any,
    delay_seconds: Any,
) -> None:
    """Run one solver in a spawned process and stream sampled updates."""
    last_sampled_expansion: dict[str, int] = {}

    def emit(event: SearchEvent) -> None:
        payload = asdict(event)
        if pause_event.is_set():
            try:
                messages.put_nowait(("progress", payload))
            except queue.Full:
                pass
            while pause_event.is_set() and not stop_event.is_set():
                if step_event.wait(0.1):
                    step_event.clear()
                    break
        if stop_event.is_set():
            return
        interval = max(1, int(sampling_interval.value))
        should_sample = event.expanded % interval == 0 and last_sampled_expansion.get(event.kind) != event.expanded
        if should_sample or event.kind == "solution":
            last_sampled_expansion[event.kind] = event.expanded
            try:
                messages.put_nowait(("progress", payload))
            except queue.Full:
                pass
            time.sleep(max(0.0, float(delay_seconds.value)))

    try:
        solver = depth_first_search if algorithm == "DFS" else astar
        result = solver(puzzle, limits, on_event=emit, cancelled=stop_event.is_set)
        messages.put(("result", result), timeout=2.0)
    except Exception as exc:  # Send a readable failure to the owning UI process.
        try:
            messages.put(("error", f"{exc}\n{traceback.format_exc()}"), timeout=1.0)
        except queue.Full:
            pass
