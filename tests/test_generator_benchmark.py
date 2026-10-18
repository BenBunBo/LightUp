from __future__ import annotations

import random

from lightup.algorithms.search import SearchLimits
from lightup.benchmark.runner import benchmark
from lightup.core.model import Puzzle
from lightup.core.rules import is_goal_state, validate_numbered_walls
from lightup.core.serialization import load_puzzle, save_puzzle
from lightup.generator import DIFFICULTIES, SIZES, get_sample_puzzle


def test_all_twelve_sample_modes_are_seeded_and_have_valid_constructive_witnesses() -> None:
    for size in SIZES:
        for difficulty in DIFFICULTIES:
            puzzle = get_sample_puzzle(size, difficulty)
            assert puzzle.size == size
            assert puzzle.difficulty == difficulty
            assert puzzle.metadata["witness_verified"] is True
            assert puzzle.metadata["uniqueness"] == "not_checked"
            assert len(puzzle.numbered_walls()) == puzzle.metadata["wall_count"]
            offset = random.Random(puzzle.seed).randrange(size)
            witness = {(row, (row + offset) % size) for row in range(size)}
            assert is_goal_state(puzzle, witness)
            assert validate_numbered_walls(puzzle, witness)
            assert get_sample_puzzle(size, difficulty).rows == puzzle.rows


def test_more_easy_clues_than_hard_clues_for_sample_mode() -> None:
    easy = get_sample_puzzle(10, "easy")
    hard = get_sample_puzzle(10, "hard")
    easy_clues = sum(value is not None for row in easy.rows for value in row)
    hard_clues = sum(value is not None for row in hard.rows for value in row)
    assert easy_clues > hard_clues


def test_puzzle_json_round_trip(tmp_path) -> None:
    puzzle = get_sample_puzzle(7, "normal")
    file_path = tmp_path / "puzzle.json"
    save_puzzle(puzzle, file_path)
    loaded = load_puzzle(file_path)
    assert loaded.rows == puzzle.rows
    assert loaded.seed == puzzle.seed
    assert loaded.puzzle_id == puzzle.puzzle_id


def test_benchmark_records_same_puzzle_and_real_solver_metrics() -> None:
    puzzle = Puzzle(((None, None), (None, None)), "same-input", "test", 12)
    rows = benchmark(puzzle, ("dfs", "astar"), repeats=1, limits=SearchLimits())
    assert [row.algorithm for row in rows] == ["DFS", "ASTAR"]
    assert all(row.puzzle_id == "same-input" and row.seed == 12 for row in rows)
    assert all(row.status == "SOLVED" and row.execution_time_seconds >= 0 for row in rows)
    assert all(row.peak_python_memory_bytes > 0 and row.nodes_expanded > 0 for row in rows)
