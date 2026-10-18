# Light Up — AI Search Visualizer

A Python desktop implementation of the Akari / Light Up logic puzzle. Play by hand, watch a real DFS or A* search explore partial bulb configurations, replay a solution, or benchmark both algorithms on the same seeded board.

The workspace did not contain `BTL1.pdf`, so this implementation follows the assignment requirements included in the project brief. This repository covers the Light Up puzzle only; the assignment's second logic puzzle remains a separate project task.

## Features

- 7×7, 10×10, 14×14, and 25×25 boards; Easy, Normal, and Hard modes.
- Seeded deterministic generation. A constructive bulb layout is independently checked before a generated puzzle is returned. Puzzle uniqueness is not tested or claimed.
- Manual play with left-click bulbs, right-click X marks, lit and unlit cell colors, red conflict bulbs, clue feedback, undo, redo, reset, check, and hint.
- Blind depth-first search and optimal A* under a minimum-bulb objective, subject to configured resource limits.
- Search runs in a spawned worker process. The UI provides pause, resume, sampled step, stop, live state and counter updates, speed control, and solution playback.
- In-app side-by-side DFS/A* benchmark on the currently loaded puzzle, plus the standalone CSV benchmark CLI.
- JSON puzzle import/export helpers and CSV benchmark export.

## Game rules

Bulbs occupy white cells and illuminate their own cell plus white cells in straight lines in four directions. A wall or board edge stops light. Bulbs may not see one another. Each numbered wall must have exactly its number of bulbs in its orthogonally adjacent cells. Every white cell must be illuminated; a cell may be lit by more than one bulb.

## Requirements and setup

The project targets Python 3.12 and uses `uv` to install the interpreter and dependencies from `pyproject.toml` and `uv.lock`.

```sh
uv sync
uv run python -m lightup
```

The console entry point is also available as `uv run lightup`. No Conda environment or separate `pip` install is required.

## Controls

- **New Game:** choose the size, difficulty, and optionally a numeric seed, then create the board. A blank seed chooses a new seed.
- **Manual:** left-click a white cell to toggle a bulb; right-click to toggle an X mark.
- **Check Solution, Hint, Undo, Redo, Reset:** act on the current manual board.
- **Start Search:** select DFS or A* and start a separate worker process.
- **Pause, Step, Stop:** control search exploration. Step releases the worker through the next sampled event.
- **Speed:** controls search event sampling/delay and solution playback speed.
- **Playback:** use the back, play/pause, and forward controls after a solution is found.
- **Compare DFS and A*:** run one measured comparison on the current puzzle and show both results in the right panel.

The board scales to the available center area. At 25×25, cells shrink to fit the window. Search updates are sampled into a bounded queue rather than retaining the search tree or a full animation.

## Model and architecture

```text
src/lightup/
  core/          immutable puzzle model, rules, JSON import/export
  algorithms/    bit-mask search model, DFS, A*, resource limits and statistics
  generator/     seeded generator and structural difficulty metrics
  worker.py      spawn-safe solver process and sampled event stream
  ui/            Pygame and pygame_gui desktop application
  benchmark/     headless benchmark runner, CLI and CSV export
tests/           game logic, search, generation and benchmark tests
docs/            report draft and presentation outline
results/         real benchmark output (created by the CLI)
```

Game rules are pure functions in `core/rules.py`; rendering is never used as game state. Search states are integer bitmasks whose set bits identify placed bulbs. An edge adds a legal bulb that illuminates the first currently unlit cell. A state is complete only when all white cells are lit and all numbered walls are exact.

## Algorithms

### DFS (blind search)

DFS stores states in a LIFO stack. It branches in a fixed row-major order from the first unlit cell, without assigning a global heuristic priority. The solver prunes only sound failures: bulb conflicts, an overfilled numbered wall, a numbered wall that cannot reach its target with any remaining legal adjacent cell, or an unlit cell with no legal possible illuminator. A visited set avoids exploring the same bulb configuration twice. The first valid solution is returned; DFS does not optimize bulb count.

### A* (heuristic search)

Each placement costs one, so `g(n)` is the number of bulbs already placed. The heuristic is:

```text
h(n) = max(
  ceil(unlit cells / largest current legal coverage),
  largest remaining numbered-wall deficit,
  ceil(total numbered-wall deficit / largest clue help from one bulb)
)
```

Each term is a lower bound: one added bulb cannot cover more than the current maximum coverage, cannot add more than one bulb to a particular wall, and cannot satisfy more currently unmet wall incidences than the maximum counted. Taking their maximum remains admissible. With unit action cost, duplicate-state handling, and search allowed to complete, A* returns a solution with the fewest bulbs. A timeout or resource limit provides no optimality or unsolvability conclusion.

Both algorithms use the same transition constraints and independent `is_goal_state` validation. Search has timeout, expanded-node, estimated-memory, and cancellation limits. The memory cap inside the search is an estimate based on retained states; benchmark memory is measured separately with `tracemalloc`.

### Complexity

With `W` white cells, the number of possible bulb subsets is at most `2^W`. In the worst case both searches have exponential time. DFS uses memory proportional to its visited set and stack; A* can retain an exponential number of states in its priority queue and best-cost map. Bit masks, visibility precomputation, and early constraint pruning reduce work but do not change the worst-case bound. A 25×25 board may hit the configured limits.

## Puzzle generation and difficulty

For a seed, generation picks one bulb in each row and column using a cyclic permutation, then tries adding walls away from those witness bulbs. A wall is kept only if all remaining white cells stay illuminated and the bulbs remain conflict-free. Its clue is derived from the witness's adjacent bulbs. The final board is checked again with the shared goal validator. Thus every returned generated board has at least one verified solution.

Easy, Normal, and Hard use decreasing target clue-wall densities (16%, 10.5%, and 5.5% of board area). Metadata reports actual clue density, constrained-white fraction, and clue extremity. This is a structural difficulty proxy, not a claim that a mode has a unique solution or a particular measured solve time. The benchmark records actual search complexity for selected puzzles; uniqueness is currently not checked.

Each mode's sample is the deterministic puzzle for its documented local seed. New boards can be reproduced by entering that numeric seed. JSON helpers are available from `lightup.core.serialization`:

```python
from lightup.core.serialization import load_puzzle, save_puzzle

save_puzzle(puzzle, "board.json")
puzzle = load_puzzle("board.json")
```

## Tests and lint

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests cover four-direction illumination, wall occlusion, conflicts, numbered clues, goal checks, invalid boards, both solvers, small-board A* optimality, limits, all twelve seeded sample modes, JSON round trips, and benchmark metrics.

## Benchmarks

Run DFS and A* against the same generated puzzle instance:

```sh
uv run python -m lightup.benchmark \
  --size 7 --difficulty easy --algorithms dfs astar \
  --repeats 3 --timeout 30 --csv results/benchmark.csv
```

Supply `--seed N` to select a specific deterministic seed, or `--puzzle-json board.json` to benchmark an imported board. Limits are shared between algorithms and repetitions. CSV rows retain every run and include status, measured wall time, peak Python allocations, expanded/generated nodes, maximum frontier, and solution cost. `tracemalloc` is started immediately before each solver call, so `peak_python_memory_bytes` excludes the already-created puzzle and does not represent process RSS. The CLI prints median summaries; no benchmark value is pre-filled or fabricated.

## Report materials

- [Report draft](docs/report_draft.md)
- [Presentation outline](docs/slides_outline.md)

The BTL assignment asks each group to implement two logic puzzles. This app intentionally implements Akari only; it does not claim to complete the second-puzzle requirement.
