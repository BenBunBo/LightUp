"""Puzzle JSON import/export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from lightup.core.model import Puzzle


def save_puzzle(puzzle: Puzzle, path: str | Path) -> None:
    Path(path).write_text(json.dumps(puzzle.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_puzzle(path: str | Path) -> Puzzle:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Puzzle JSON must contain an object")
    return Puzzle.from_dict(data)
