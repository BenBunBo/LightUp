"""Pure Light Up rules. These functions do not depend on rendering or Pygame."""

from __future__ import annotations

from collections.abc import Iterable

from lightup.core.model import Cell, Puzzle

_DIRECTIONS: tuple[Cell, ...] = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _check_bulbs(puzzle: Puzzle, bulbs: Iterable[Cell]) -> frozenset[Cell]:
    result = frozenset(bulbs)
    for cell in result:
        if not puzzle.is_white(cell):
            raise ValueError(f"A bulb can only be placed on a white cell: {cell}")
    return result


def get_illuminated_cells(puzzle: Puzzle, bulbs: Iterable[Cell]) -> frozenset[Cell]:
    """Return all white cells lit by bulbs, including each bulb's own cell."""
    bulb_set = _check_bulbs(puzzle, bulbs)
    lit: set[Cell] = set()
    for row, col in bulb_set:
        lit.add((row, col))
        for dr, dc in _DIRECTIONS:
            r, c = row + dr, col + dc
            while puzzle.is_white((r, c)):
                lit.add((r, c))
                r += dr
                c += dc
    return frozenset(lit)


def get_adjacent_bulbs(puzzle: Puzzle, cell: Cell, bulbs: Iterable[Cell]) -> frozenset[Cell]:
    """Return bulbs orthogonally adjacent to ``cell`` (usually a numbered wall)."""
    bulb_set = _check_bulbs(puzzle, bulbs)
    row, col = cell
    return frozenset((row + dr, col + dc) for dr, dc in _DIRECTIONS if (row + dr, col + dc) in bulb_set)


def has_bulb_conflicts(puzzle: Puzzle, bulbs: Iterable[Cell]) -> bool:
    """Whether any two bulbs see one another along an unobstructed row or column."""
    bulb_set = _check_bulbs(puzzle, bulbs)
    for bulb in bulb_set:
        if len(get_illuminated_cells(puzzle, (bulb,)) & bulb_set) > 1:
            return True
    return False


def validate_numbered_walls(puzzle: Puzzle, bulbs: Iterable[Cell]) -> bool:
    """Return whether every numbered wall has exactly its required adjacent bulbs."""
    bulb_set = _check_bulbs(puzzle, bulbs)
    return all(
        len(get_adjacent_bulbs(puzzle, wall, bulb_set)) == puzzle.rows[wall[0]][wall[1]]
        for wall in puzzle.numbered_walls()
    )


def is_valid_partial_state(puzzle: Puzzle, bulbs: Iterable[Cell]) -> bool:
    """Check constraints that already-assigned bulbs may not violate."""
    bulb_set = _check_bulbs(puzzle, bulbs)
    if has_bulb_conflicts(puzzle, bulb_set):
        return False
    return all(
        len(get_adjacent_bulbs(puzzle, wall, bulb_set)) <= puzzle.rows[wall[0]][wall[1]]
        for wall in puzzle.numbered_walls()
    )


def is_goal_state(puzzle: Puzzle, bulbs: Iterable[Cell]) -> bool:
    """The Akari goal: conflict free, exact clues, and every white cell illuminated."""
    bulb_set = _check_bulbs(puzzle, bulbs)
    if not is_valid_partial_state(puzzle, bulb_set) or not validate_numbered_walls(puzzle, bulb_set):
        return False
    white_count = sum(cell is None for row in puzzle.rows for cell in row)
    return len(get_illuminated_cells(puzzle, bulb_set)) == white_count


def get_legal_actions(puzzle: Puzzle, bulbs: Iterable[Cell]) -> tuple[Cell, ...]:
    """List legal bulb placements in row-major order for manual play and hints."""
    bulb_set = _check_bulbs(puzzle, bulbs)
    if not is_valid_partial_state(puzzle, bulb_set):
        return ()
    actions: list[Cell] = []
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            cell = (row, col)
            if not puzzle.is_white(cell) or cell in bulb_set:
                continue
            candidate = (*bulb_set, cell)
            if is_valid_partial_state(puzzle, candidate):
                actions.append(cell)
    return tuple(actions)
