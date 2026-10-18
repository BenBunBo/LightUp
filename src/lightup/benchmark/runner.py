"""Measure solver runtime and peak Python allocations without rendering."""

from __future__ import annotations

import csv
import statistics
import tracemalloc
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lightup.algorithms.search import SearchLimits, SearchResult, astar, depth_first_search
from lightup.core.model import Puzzle


@dataclass(frozen=True, slots=True)
class BenchmarkRow:
    algorithm: str
    size: int
    difficulty: str
    seed: int | None
    puzzle_id: str
    status: str
    repeat: int
    repeats: int
    execution_time_seconds: float
    peak_python_memory_bytes: int
    nodes_expanded: int
    nodes_generated: int
    max_frontier_size: int
    solution_cost: int | None


def _run_one(
    puzzle: Puzzle, algorithm: str, limits: SearchLimits, cancelled: Callable[[], bool] | None = None
) -> tuple[SearchResult, int]:
    solver = depth_first_search if algorithm.lower() == "dfs" else astar
    tracemalloc.start()
    try:
        result = solver(puzzle, limits, cancelled=cancelled)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


def benchmark(
    puzzle: Puzzle,
    algorithms: tuple[str, ...] = ("dfs", "astar"),
    repeats: int = 1,
    limits: SearchLimits | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[BenchmarkRow]:
    """Run each algorithm repeatedly on the same immutable puzzle instance."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    unknown = {name.lower() for name in algorithms} - {"dfs", "astar"}
    if unknown:
        raise ValueError(f"Unknown algorithms: {', '.join(sorted(unknown))}")
    limits = limits or SearchLimits()
    rows: list[BenchmarkRow] = []
    for algorithm in algorithms:
        for repeat in range(1, repeats + 1):
            if cancelled is not None and cancelled():
                return rows
            result, peak = _run_one(puzzle, algorithm, limits, cancelled)
            rows.append(_row(puzzle, algorithm.upper(), repeat, repeats, result, peak))
    return rows


def _row(puzzle: Puzzle, algorithm: str, repeat: int, repeats: int, result: SearchResult, peak: int) -> BenchmarkRow:
    return BenchmarkRow(
        algorithm,
        puzzle.size,
        puzzle.difficulty,
        puzzle.seed,
        puzzle.puzzle_id,
        result.status.value,
        repeat,
        repeats,
        result.elapsed_seconds,
        peak,
        result.expanded,
        result.generated,
        result.max_frontier,
        result.solution_cost,
    )


def write_csv(rows: list[BenchmarkRow], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        target.write_text("", encoding="utf-8")
        return
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def median_summary(rows: list[BenchmarkRow]) -> list[dict[str, Any]]:
    """Summarize medians by algorithm while retaining only real measurements."""
    summary: list[dict[str, Any]] = []
    for algorithm in sorted({row.algorithm for row in rows}):
        subset = [row for row in rows if row.algorithm == algorithm]
        summary.append(
            {
                "algorithm": algorithm,
                "runs": len(subset),
                "median_seconds": statistics.median(r.execution_time_seconds for r in subset),
                "median_peak_python_memory_bytes": statistics.median(r.peak_python_memory_bytes for r in subset),
                "median_nodes_expanded": statistics.median(r.nodes_expanded for r in subset),
            }
        )
    return summary
