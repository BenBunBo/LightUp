from __future__ import annotations

import itertools

from lightup.algorithms.search import SearchLimits, SearchStatus, astar, depth_first_search
from lightup.core.model import Puzzle
from lightup.core.rules import is_goal_state


def test_dfs_and_astar_find_valid_solutions_on_same_small_puzzle() -> None:
    puzzle = Puzzle(((None, None), (None, None)))
    dfs_result = depth_first_search(puzzle)
    astar_result = astar(puzzle)
    assert dfs_result.status is SearchStatus.SOLVED
    assert astar_result.status is SearchStatus.SOLVED
    assert is_goal_state(puzzle, dfs_result.solution)
    assert is_goal_state(puzzle, astar_result.solution)
    assert len(dfs_result.solution_path) == len(dfs_result.solution) + 1
    assert len(astar_result.solution_path) == len(astar_result.solution) + 1


def test_astar_returns_minimum_bulb_count_on_small_board() -> None:
    puzzle = Puzzle(((None, None), (None, None)))
    white_cells = [(r, c) for r in range(2) for c in range(2)]
    exhaustive_minimum = min(
        len(candidate)
        for count in range(len(white_cells) + 1)
        for candidate in itertools.combinations(white_cells, count)
        if is_goal_state(puzzle, candidate)
    )
    result = astar(puzzle)
    assert result.solution_cost == exhaustive_minimum


def test_inconsistent_numbered_wall_is_unsolvable_not_timeout() -> None:
    puzzle = Puzzle(((1,),))
    assert depth_first_search(puzzle).status is SearchStatus.UNSOLVABLE
    assert astar(puzzle).status is SearchStatus.UNSOLVABLE


def test_limits_and_cancellation_have_distinct_statuses() -> None:
    puzzle = Puzzle(tuple(tuple(None for _ in range(5)) for _ in range(5)))
    assert depth_first_search(puzzle, SearchLimits(timeout_seconds=1e-10)).status is SearchStatus.TIMEOUT
    assert depth_first_search(puzzle, SearchLimits(node_limit=1)).status is SearchStatus.NODE_LIMIT
    assert depth_first_search(puzzle, SearchLimits(memory_limit_mb=1e-9)).status is SearchStatus.MEMORY_LIMIT
    assert astar(puzzle, cancelled=lambda: True).status is SearchStatus.CANCELLED
