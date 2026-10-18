"""Immutable puzzle model and JSON representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

type Cell = tuple[int, int]
type Wall = int | None


@dataclass(frozen=True, slots=True)
class Puzzle:
    """A square Akari board; ``None`` is white and ``-1`` is an unnumbered wall."""

    rows: tuple[tuple[Wall, ...], ...]
    puzzle_id: str = "custom"
    difficulty: str = "custom"
    seed: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not self.rows or not self.rows[0]:
            raise ValueError("A puzzle must have at least one row and one column")
        size = len(self.rows)
        if any(len(row) != size for row in self.rows):
            raise ValueError("Puzzle boards must be square")
        if any(value is not None and value not in {-1, 0, 1, 2, 3, 4} for row in self.rows for value in row):
            raise ValueError("Cells must be white (null), unnumbered wall (-1), or a clue from 0 to 4")

    @property
    def size(self) -> int:
        return len(self.rows)

    def is_white(self, cell: Cell) -> bool:
        row, col = cell
        return 0 <= row < self.size and 0 <= col < self.size and self.rows[row][col] is None

    def numbered_walls(self) -> tuple[Cell, ...]:
        return tuple(
            (row, col)
            for row in range(self.size)
            for col in range(self.size)
            if self.rows[row][col] is not None and self.rows[row][col] >= 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "lightup-puzzle-v1",
            "id": self.puzzle_id,
            "size": self.size,
            "difficulty": self.difficulty,
            "seed": self.seed,
            "board": [list(row) for row in self.rows],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Puzzle:
        if data.get("format") not in (None, "lightup-puzzle-v1"):
            raise ValueError("Unsupported puzzle JSON format")
        rows = tuple(tuple(cell for cell in row) for row in data["board"])
        puzzle = cls(
            rows=rows,
            puzzle_id=str(data.get("id", "imported")),
            difficulty=str(data.get("difficulty", "custom")),
            seed=data.get("seed"),
            metadata=dict(data.get("metadata", {})),
        )
        declared_size = data.get("size", puzzle.size)
        if declared_size != puzzle.size:
            raise ValueError("Declared size does not match board dimensions")
        return puzzle
