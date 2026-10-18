"""Deterministic puzzle generation with a constructive witness.

The generator starts with one bulb in every row and column. It adds walls only
when that witness remains a valid solution, then derives each clue directly
from the witness. This guarantees at least one solution without storing an
answer in the puzzle file.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from lightup.core.model import Cell, Puzzle
from lightup.core.rules import is_goal_state

SIZES = (7, 10, 14, 25)
DIFFICULTIES = ("easy", "normal", "hard")
_WALL_DENSITY = {"easy": 0.16, "normal": 0.105, "hard": 0.055}
_SAMPLE_SEEDS = {
    (size, difficulty): size * 10_000 + (index + 1) * 97
    for size in SIZES
    for index, difficulty in enumerate(DIFFICULTIES)
}


@dataclass(frozen=True, slots=True)
class DifficultyMetrics:
    clue_density: float
    constrained_white_fraction: float
    mean_clue_extremity: float


def difficulty_metrics(puzzle: Puzzle) -> DifficultyMetrics:
    whites = sum(value is None for row in puzzle.rows for value in row)
    clues = puzzle.numbered_walls()
    adjacent_whites = {
        (r + dr, c + dc)
        for r, c in clues
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
        if puzzle.is_white((r + dr, c + dc))
    }
    extremities: list[float] = []
    for r, c in clues:
        degree = sum(puzzle.is_white((r + dr, c + dc)) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        target = puzzle.rows[r][c]
        if degree:
            # 0 or degree is a stronger local requirement than a split clue.
            extremities.append(1.0 - (2.0 * min(target, degree - target) / degree))
    return DifficultyMetrics(
        clue_density=len(clues) / max(1, whites),
        constrained_white_fraction=len(adjacent_whites) / max(1, whites),
        mean_clue_extremity=sum(extremities) / max(1, len(extremities)),
    )


def generate_puzzle(size: int, difficulty: str, seed: int) -> Puzzle:
    """Create a seed-reproducible puzzle and independently verify its witness."""
    if size not in SIZES:
        raise ValueError(f"Board size must be one of {SIZES}")
    difficulty = difficulty.lower()
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Difficulty must be one of {DIFFICULTIES}")

    rng = random.Random(seed)
    offset = rng.randrange(size)
    witness: tuple[Cell, ...] = tuple((row, (row + offset) % size) for row in range(size))
    bulb_set = set(witness)
    target_walls = round(size * size * _WALL_DENSITY[difficulty])
    possible_walls = [(row, col) for row in range(size) for col in range(size) if (row, col) not in bulb_set]
    rng.shuffle(possible_walls)

    grid: list[list[int | None]] = [[None for _ in range(size)] for _ in range(size)]
    accepted = 0
    for row, col in possible_walls:
        if accepted >= target_walls:
            break
        grid[row][col] = -1
        candidate = _with_clues(grid, witness, size, seed, difficulty, "candidate")
        if is_goal_state(candidate, witness):
            accepted += 1
        else:
            grid[row][col] = None

    puzzle_id = f"akari-{size}-{difficulty}-{seed}"
    puzzle = _with_clues(grid, witness, size, seed, difficulty, puzzle_id)
    if not is_goal_state(puzzle, witness):
        # Keeping fewer blockers is safe; this guard protects future changes.
        raise RuntimeError("Generator produced a board whose constructive witness is invalid")
    metrics = difficulty_metrics(puzzle)
    metadata = {
        "generator": "cyclic-witness-v1",
        "witness_verified": True,
        "uniqueness": "not_checked",
        "wall_count": accepted,
        "target_wall_count": target_walls,
        "difficulty_method": "seeded wall density; easy has more numbered clues, hard has fewer",
        "difficulty_metrics": {
            "clue_density": round(metrics.clue_density, 5),
            "constrained_white_fraction": round(metrics.constrained_white_fraction, 5),
            "mean_clue_extremity": round(metrics.mean_clue_extremity, 5),
        },
    }
    return Puzzle(puzzle.rows, puzzle_id, difficulty, seed, metadata)


def _with_clues(
    grid: list[list[int | None]], witness: tuple[Cell, ...], size: int, seed: int, difficulty: str, puzzle_id: str
) -> Puzzle:
    bulbs = set(witness)
    rows = [row.copy() for row in grid]
    for row in range(size):
        for col in range(size):
            if rows[row][col] == -1:
                rows[row][col] = sum((row + dr, col + dc) in bulbs for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
    return Puzzle(tuple(tuple(row) for row in rows), puzzle_id, difficulty, seed)


def get_sample_puzzle(size: int, difficulty: str) -> Puzzle:
    """Return the deterministic, validated sample for one of the 12 modes."""
    try:
        seed = _SAMPLE_SEEDS[(size, difficulty.lower())]
    except KeyError as exc:
        raise ValueError("No sample exists for that size and difficulty") from exc
    return generate_puzzle(size, difficulty, seed)


def all_sample_modes() -> tuple[tuple[int, str], ...]:
    return tuple((size, difficulty) for size in SIZES for difficulty in DIFFICULTIES)
