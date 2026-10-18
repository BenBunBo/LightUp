from __future__ import annotations

import pytest

from lightup.core.model import Puzzle
from lightup.core.rules import (
    get_adjacent_bulbs,
    get_illuminated_cells,
    get_legal_actions,
    has_bulb_conflicts,
    is_goal_state,
    is_valid_partial_state,
    validate_numbered_walls,
)


def test_light_travels_in_four_directions_and_stops_at_walls() -> None:
    puzzle = Puzzle(
        (
            (None, None, -1, None),
            (None, None, None, None),
            (None, 2, None, None),
            (None, None, None, None),
        )
    )
    lit = get_illuminated_cells(puzzle, {(1, 1)})
    assert {(1, 1), (0, 1), (1, 0), (1, 2), (1, 3)} <= lit
    assert (0, 0) not in lit
    assert (3, 1) not in lit  # The numbered wall blocks light.


def test_bulb_conflict_requires_unobstructed_line_of_sight() -> None:
    open_board = Puzzle(tuple(tuple(None for _ in range(3)) for _ in range(3)))
    blocked_board = Puzzle(((None, None, None), (None, -1, None), (None, None, None)))
    assert has_bulb_conflicts(open_board, {(1, 0), (1, 2)})
    assert not has_bulb_conflicts(blocked_board, {(1, 0), (1, 2)})
    assert not has_bulb_conflicts(open_board, {(0, 0), (1, 1)})


@pytest.mark.parametrize(
    "clue,bulbs,expected",
    [
        (0, set(), True),
        (1, {(0, 1)}, True),
        (2, {(0, 1), (2, 1)}, True),
        (3, {(0, 1), (2, 1)}, False),
        (4, {(0, 1), (2, 1), (1, 0), (1, 2)}, True),
    ],
)
def test_numbered_wall_counts_exactly(clue: int, bulbs: set[tuple[int, int]], expected: bool) -> None:
    puzzle = Puzzle(((None, None, None), (None, clue, None), (None, None, None)))
    assert validate_numbered_walls(puzzle, bulbs) is expected
    assert len(get_adjacent_bulbs(puzzle, (1, 1), bulbs)) == len(bulbs)


def test_partial_state_rejects_conflicts_and_overfilled_clues() -> None:
    puzzle = Puzzle(((None, 1, None), (None, None, None), (None, None, None)))
    assert is_valid_partial_state(puzzle, {(0, 0)})
    assert not is_valid_partial_state(puzzle, {(0, 0), (0, 2)})
    assert (0, 2) not in get_legal_actions(puzzle, {(0, 0)})


def test_goal_requires_lighting_and_clues_and_bulbs_must_be_on_white_cells() -> None:
    puzzle = Puzzle(((None, None), (None, None)))
    solution = {(0, 0), (1, 1)}
    assert is_goal_state(puzzle, solution)
    assert not is_goal_state(puzzle, set())
    assert get_illuminated_cells(puzzle, solution) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    with pytest.raises(ValueError):
        get_illuminated_cells(puzzle, {(0, 0), (1, 1), (3, 3)})


def test_lighting_every_white_cell_does_not_override_an_unsatisfied_clue() -> None:
    puzzle = Puzzle(((None, -1, -1), (None, 1, -1), (-1, -1, -1)))
    bulbs = {(0, 0)}
    assert len(get_illuminated_cells(puzzle, bulbs)) == 2
    assert not validate_numbered_walls(puzzle, bulbs)
    assert not is_goal_state(puzzle, bulbs)


def test_puzzle_rejects_empty_non_square_and_invalid_clues() -> None:
    with pytest.raises(ValueError):
        Puzzle(())
    with pytest.raises(ValueError):
        Puzzle(((None, None), (None,)))
    with pytest.raises(ValueError):
        Puzzle(((5,),))
