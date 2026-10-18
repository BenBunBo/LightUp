"""Constraint-pruned DFS and optimal A* over partial bulb configurations."""

from __future__ import annotations

import heapq
import math
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from lightup.core.model import Cell, Puzzle
from lightup.core.rules import is_goal_state

AlgorithmName = Literal["dfs", "astar"]


class SearchStatus(StrEnum):
    SOLVED = "SOLVED"
    UNSOLVABLE = "UNSOLVABLE"
    TIMEOUT = "TIMEOUT"
    NODE_LIMIT = "NODE_LIMIT"
    MEMORY_LIMIT = "MEMORY_LIMIT"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class SearchLimits:
    timeout_seconds: float = 30.0
    node_limit: int = 500_000
    memory_limit_mb: float = 512.0
    progress_interval: int = 100


@dataclass(frozen=True, slots=True)
class SearchEvent:
    kind: str
    bulbs: tuple[Cell, ...]
    expanded: int
    generated: int
    frontier_size: int
    depth: int
    g: int
    h: int
    f: int
    focus: Cell | None = None
    detail: str = ""
    elapsed_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchResult:
    algorithm: AlgorithmName
    status: SearchStatus
    solution: tuple[Cell, ...] = ()
    solution_path: tuple[tuple[Cell, ...], ...] = ()
    expanded: int = 0
    generated: int = 0
    max_frontier: int = 0
    elapsed_seconds: float = 0.0
    peak_memory_bytes: int = 0
    solution_cost: int | None = None
    message: str = ""


@dataclass(slots=True)
class _View:
    puzzle: Puzzle
    cells: tuple[Cell, ...]
    index: dict[Cell, int]
    white_mask: int
    covers: tuple[int, ...]
    conflicts: tuple[int, ...]
    wall_neighbors: tuple[tuple[int, int], ...]
    illuminators: tuple[tuple[int, ...], ...]

    @classmethod
    def build(cls, puzzle: Puzzle) -> _View:
        cells = tuple(
            (row, col) for row in range(puzzle.size) for col in range(puzzle.size) if puzzle.is_white((row, col))
        )
        index = {cell: i for i, cell in enumerate(cells)}
        covers: list[int] = []
        for row, col in cells:
            mask = 1 << index[(row, col)]
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                r, c = row + dr, col + dc
                while puzzle.is_white((r, c)):
                    mask |= 1 << index[(r, c)]
                    r += dr
                    c += dc
            covers.append(mask)
        conflicts = tuple(cover & ~(1 << i) for i, cover in enumerate(covers))
        walls: list[tuple[int, int]] = []
        for row, col in puzzle.numbered_walls():
            neighbors = tuple(
                index[(row + dr, col + dc)]
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                if (row + dr, col + dc) in index
            )
            walls.append((puzzle.rows[row][col], sum(1 << i for i in neighbors)))
        illuminators = tuple(
            tuple(i for i, cover in enumerate(covers) if cover & (1 << target)) for target in range(len(cells))
        )
        return cls(
            puzzle,
            cells,
            index,
            (1 << len(cells)) - 1,
            tuple(covers),
            conflicts,
            tuple(walls),
            illuminators,
        )

    def bulb_cells(self, mask: int) -> tuple[Cell, ...]:
        return tuple(self.cells[i] for i in range(len(self.cells)) if mask & (1 << i))

    def lit_mask(self, bulbs: int) -> int:
        lit = 0
        while bulbs:
            bit = bulbs & -bulbs
            lit |= self.covers[bit.bit_length() - 1]
            bulbs ^= bit
        return lit

    def can_place(self, bulb: int, bulbs: int) -> bool:
        bit = 1 << bulb
        if bulbs & bit or self.conflicts[bulb] & bulbs:
            return False
        for target, neighbors in self.wall_neighbors:
            if neighbors & bit and (neighbors & bulbs).bit_count() >= target:
                return False
        return True

    def feasible(self, bulbs: int, lit: int) -> bool:
        """Safe upper-bound checks for numbered clues and uncovered cells."""
        for target, neighbors in self.wall_neighbors:
            current = (neighbors & bulbs).bit_count()
            if current > target:
                return False
            eligible = 0
            remaining = neighbors & ~bulbs
            while remaining:
                bit = remaining & -remaining
                i = bit.bit_length() - 1
                if self.can_place(i, bulbs):
                    eligible += 1
                remaining ^= bit
            if current + eligible < target:
                return False

        dark = self.white_mask & ~lit
        while dark:
            bit = dark & -dark
            target_index = bit.bit_length() - 1
            if not any(self.can_place(i, bulbs) for i in self.illuminators[target_index]):
                return False
            dark ^= bit
        return True

    def branch_cell(self, lit: int, bulbs: int) -> tuple[int | None, tuple[int, ...]]:
        """Pick the first uncovered cell; this fixed order keeps DFS blind."""
        dark = self.white_mask & ~lit
        if not dark:
            return None, ()
        bit = dark & -dark
        target = bit.bit_length() - 1
        options = tuple(i for i in self.illuminators[target] if self.can_place(i, bulbs))
        return target, options

    def lower_bound(self, bulbs: int, lit: int) -> int:
        """Admissible lower bound on additional bulbs (coverage and clue deficits)."""
        dark = self.white_mask & ~lit
        if not dark:
            coverage_bound = 0
        else:
            max_gain = 0
            for i in range(len(self.cells)):
                if self.can_place(i, bulbs):
                    gain = (self.covers[i] & dark).bit_count()
                    max_gain = max(max_gain, gain)
            if max_gain == 0:
                return math.inf  # type: ignore[return-value]
            coverage_bound = math.ceil(dark.bit_count() / max_gain)

        deficits: list[int] = []
        total_deficit = 0
        max_help = 0
        for target, neighbors in self.wall_neighbors:
            deficit = target - (neighbors & bulbs).bit_count()
            if deficit > 0:
                deficits.append(deficit)
                total_deficit += deficit
        if not deficits:
            clue_bound = 0
        else:
            for i in range(len(self.cells)):
                if self.can_place(i, bulbs):
                    help_count = sum(
                        1
                        for target, neighbors in self.wall_neighbors
                        if target > (neighbors & bulbs).bit_count() and neighbors & (1 << i)
                    )
                    max_help = max(max_help, help_count)
            if max_help == 0:
                return math.inf  # type: ignore[return-value]
            clue_bound = max(max(deficits), math.ceil(total_deficit / max_help))
        return max(coverage_bound, clue_bound)


def _path_from_parents(
    view: _View, goal: int, parents: dict[int, tuple[int, int] | None]
) -> tuple[tuple[Cell, ...], ...]:
    actions: list[int] = []
    cursor = goal
    while parents[cursor] is not None:
        parent, action = parents[cursor]  # type: ignore[misc]
        actions.append(action)
        cursor = parent
    actions.reverse()
    state = 0
    path = [tuple()]
    for action in actions:
        state |= 1 << action
        path.append(view.bulb_cells(state))
    return tuple(path)


def _finish(
    algorithm: AlgorithmName,
    status: SearchStatus,
    start: float,
    expanded: int,
    generated: int,
    max_frontier: int,
    peak_bytes: int,
    goal: int | None = None,
    parents: dict[int, tuple[int, int] | None] | None = None,
    view: _View | None = None,
    message: str = "",
) -> SearchResult:
    solution = view.bulb_cells(goal) if goal is not None and view is not None else ()
    path = _path_from_parents(view, goal, parents) if goal is not None and parents is not None and view else ()
    return SearchResult(
        algorithm=algorithm,
        status=status,
        solution=solution,
        solution_path=path,
        expanded=expanded,
        generated=generated,
        max_frontier=max_frontier,
        elapsed_seconds=time.perf_counter() - start,
        peak_memory_bytes=peak_bytes,
        solution_cost=len(solution) if goal is not None else None,
        message=message,
    )


def _memory_estimate_bytes(visited: int, frontier: int, bit_count: int) -> int:
    mask_bytes = sys.getsizeof(1 << bit_count)
    return visited * (88 + mask_bytes) + frontier * (64 + mask_bytes)


def _resource_status(
    start: float,
    limits: SearchLimits,
    expanded: int,
    estimated_bytes: int,
    cancelled: Callable[[], bool] | None,
) -> SearchStatus | None:
    if cancelled is not None and cancelled():
        return SearchStatus.CANCELLED
    if limits.timeout_seconds > 0 and time.perf_counter() - start >= limits.timeout_seconds:
        return SearchStatus.TIMEOUT
    if limits.node_limit > 0 and expanded >= limits.node_limit:
        return SearchStatus.NODE_LIMIT
    if limits.memory_limit_mb > 0 and estimated_bytes > limits.memory_limit_mb * 1024 * 1024:
        return SearchStatus.MEMORY_LIMIT
    return None


def depth_first_search(
    puzzle: Puzzle,
    limits: SearchLimits | None = None,
    *,
    on_event: Callable[[SearchEvent], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> SearchResult:
    """Depth-first blind search using a LIFO stack and safe constraint pruning.

    Each edge adds a legal bulb that lights the first uncovered cell. DFS does
    not use a heuristic priority; only deterministic row-major branching and
    sound impossibility checks are used.
    """
    limits = limits or SearchLimits()
    start = time.perf_counter()
    view = _View.build(puzzle)
    parents: dict[int, tuple[int, int] | None] = {0: None}
    if not view.feasible(0, 0):
        return _finish(
            "dfs", SearchStatus.UNSOLVABLE, start, 0, 0, 0, 0, view=view, message="Initial constraints are inconsistent"
        )
    stack = [0]
    visited = {0}
    expanded = generated = 0
    max_frontier = 1
    peak_bytes = _memory_estimate_bytes(1, 1, len(view.cells))

    while stack:
        estimated = _memory_estimate_bytes(len(visited), len(stack), len(view.cells))
        status = _resource_status(start, limits, expanded, estimated, cancelled)
        if status:
            return _finish(
                "dfs", status, start, expanded, generated, max_frontier, max(peak_bytes, estimated), view=view
            )
        state = stack.pop()
        lit = view.lit_mask(state)
        expanded += 1
        peak_bytes = max(peak_bytes, estimated)
        if (view.white_mask & ~lit) == 0:
            bulbs = view.bulb_cells(state)
            if is_goal_state(puzzle, bulbs):
                return _finish(
                    "dfs",
                    SearchStatus.SOLVED,
                    start,
                    expanded,
                    generated,
                    max_frontier,
                    peak_bytes,
                    state,
                    parents,
                    view,
                )
            continue

        target, options = view.branch_cell(lit, state)
        if target is None or not options:
            continue
        if on_event:
            bulbs = view.bulb_cells(state)
            on_event(
                SearchEvent(
                    "expand",
                    bulbs,
                    expanded,
                    generated,
                    len(stack),
                    len(bulbs),
                    len(bulbs),
                    0,
                    len(bulbs),
                    view.cells[target],
                    elapsed_seconds=time.perf_counter() - start,
                )
            )
        # Reverse push order so the first row-major option is expanded first.
        for action in reversed(options):
            child = state | (1 << action)
            if child in visited:
                continue
            child_lit = lit | view.covers[action]
            if not view.feasible(child, child_lit):
                if on_event:
                    on_event(
                        SearchEvent(
                            "reject",
                            view.bulb_cells(state),
                            expanded,
                            generated,
                            len(stack),
                            len(view.bulb_cells(state)),
                            len(view.bulb_cells(state)),
                            0,
                            len(view.bulb_cells(state)),
                            view.cells[action],
                            "Constraint check rejected bulb placement",
                            time.perf_counter() - start,
                        )
                    )
                continue
            visited.add(child)
            parents[child] = (state, action)
            stack.append(child)
            generated += 1
        max_frontier = max(max_frontier, len(stack))

    return _finish("dfs", SearchStatus.UNSOLVABLE, start, expanded, generated, max_frontier, peak_bytes, view=view)


def astar(
    puzzle: Puzzle,
    limits: SearchLimits | None = None,
    *,
    on_event: Callable[[SearchEvent], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> SearchResult:
    """A* over bulb sets with unit placement costs and an admissible heuristic.

    ``g`` is the number of bulbs already placed. ``h`` is the maximum of a
    coverage lower bound and a numbered-wall-deficit lower bound. A completed
    state popped from the priority queue is therefore a minimum-bulb solution.
    """
    limits = limits or SearchLimits()
    start = time.perf_counter()
    view = _View.build(puzzle)
    if is_goal_state(puzzle, ()):
        return _finish("astar", SearchStatus.SOLVED, start, 1, 0, 1, 0, 0, {0: None}, view)
    if not view.feasible(0, 0):
        return _finish(
            "astar",
            SearchStatus.UNSOLVABLE,
            start,
            0,
            0,
            0,
            0,
            view=view,
            message="Initial constraints are inconsistent",
        )
    root_h = view.lower_bound(0, 0)
    if math.isinf(root_h):
        return _finish(
            "astar",
            SearchStatus.UNSOLVABLE,
            start,
            0,
            0,
            0,
            0,
            view=view,
            message="No legal bulb can satisfy the initial state",
        )
    frontier: list[tuple[float, int, int, int]] = [(root_h, 0, 0, 0)]
    parents: dict[int, tuple[int, int] | None] = {0: None}
    best_g = {0: 0}
    tie = 1
    expanded = generated = 0
    max_frontier = 1
    peak_bytes = _memory_estimate_bytes(1, 1, len(view.cells))

    while frontier:
        estimated = _memory_estimate_bytes(len(best_g), len(frontier), len(view.cells))
        status = _resource_status(start, limits, expanded, estimated, cancelled)
        if status:
            return _finish(
                "astar", status, start, expanded, generated, max_frontier, max(peak_bytes, estimated), view=view
            )
        f_score, _, queued_g, state = heapq.heappop(frontier)
        if queued_g != best_g.get(state):
            continue
        lit = view.lit_mask(state)
        expanded += 1
        peak_bytes = max(peak_bytes, estimated)
        bulbs = view.bulb_cells(state)
        h = int(view.lower_bound(state, lit))
        if (view.white_mask & ~lit) == 0 and is_goal_state(puzzle, bulbs):
            return _finish(
                "astar", SearchStatus.SOLVED, start, expanded, generated, max_frontier, peak_bytes, state, parents, view
            )

        target, options = view.branch_cell(lit, state)
        if target is None or not options:
            continue
        if on_event:
            on_event(
                SearchEvent(
                    "expand",
                    bulbs,
                    expanded,
                    generated,
                    len(frontier),
                    len(bulbs),
                    len(bulbs),
                    h,
                    int(f_score),
                    view.cells[target],
                    elapsed_seconds=time.perf_counter() - start,
                )
            )
        for action in options:
            child = state | (1 << action)
            child_lit = lit | view.covers[action]
            if not view.feasible(child, child_lit):
                if on_event:
                    on_event(
                        SearchEvent(
                            "reject",
                            bulbs,
                            expanded,
                            generated,
                            len(frontier),
                            len(bulbs),
                            queued_g,
                            h,
                            int(f_score),
                            view.cells[action],
                            "Constraint check rejected bulb placement",
                            time.perf_counter() - start,
                        )
                    )
                continue
            child_g = queued_g + 1
            if child_g >= best_g.get(child, sys.maxsize):
                continue
            child_h = view.lower_bound(child, child_lit)
            if math.isinf(child_h):
                continue
            best_g[child] = child_g
            parents[child] = (state, action)
            heapq.heappush(frontier, (child_g + child_h, tie, child_g, child))
            tie += 1
            generated += 1
        max_frontier = max(max_frontier, len(frontier))

    return _finish("astar", SearchStatus.UNSOLVABLE, start, expanded, generated, max_frontier, peak_bytes, view=view)
