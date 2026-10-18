# Light Up AI Search — Report Draft

> This report covers the Light Up / Akari puzzle implemented in this repository. The BTL assignment requires a second logic puzzle as well; that second puzzle is outside this implementation's scope.

## 1. Problem statement

Given a square board containing white cells, unnumbered black walls, and numbered walls, place bulbs so every white cell is illuminated, no two bulbs see one another in a row or column without a wall between them, and each numbered wall has exactly its stated number of orthogonally adjacent bulbs.

## 2. Search problem formulation

- **State:** a set of placed bulb cells, represented internally by an integer bitmask. A set bit identifies one white cell containing a bulb.
- **Initial state:** no bulbs.
- **Action:** place a bulb in an eligible white cell that illuminates the first currently unlit white cell selected by the transition policy.
- **Transition:** add the bulb if it creates no line-of-sight conflict and does not overfill a numbered wall. Reject the successor if any clue cannot still be reached or any unlit cell has no possible legal illuminator.
- **Goal test:** all white cells are lit, all numbered walls equal their clues, and there are no bulb conflicts.
- **Path cost:** one per bulb placement. This is the A* objective; DFS returns its first solution and does not minimize bulbs.

## 3. DFS

DFS uses a LIFO stack, fixed row-major choice of the first unlit cell, and deterministic successor order. The choice rule is not a global heuristic priority. Each generated state is a bulb configuration, and a visited set avoids duplicate configurations. Constraint checks prune only branches that are already invalid or cannot reach a clue/illumination requirement.

Worst-case time is exponential in the number of white cells, `O(2^W)` states, with additional work for visibility and constraint checks. Retained-state and frontier memory are also exponential in the worst case. DFS is complete only when allowed to finish without hitting a resource limit.

## 4. A*

A* uses a priority queue ordered by `f(n) = g(n) + h(n)`. `g(n)` is the number of bulbs placed. The admissible `h` is the maximum of (a) the ceiling of dark cells divided by the maximum number any currently legal bulb can light, (b) the largest single numbered-wall deficit, and (c) the ceiling of total wall deficits divided by the most unmet wall adjacencies one legal bulb could satisfy.

Each component is a lower bound on bulbs still needed. Their maximum is therefore admissible. With unit placement cost and completed search, A* returns a minimum-bulb solution. A* has exponential worst-case time and can require exponential memory for its frontier and duplicate-state table.

## 5. Puzzle construction and validation

Puzzles are generated from a deterministic seed. The generator constructs a bulb witness with one bulb per row and column, proposes walls away from witness bulbs, derives clue values from adjacent witness bulbs, and retains only walls that leave the witness valid. `is_goal_state` validates the witness before the board is returned. Sample seeds cover all twelve board-size/difficulty combinations.

The generator records clue density, the fraction of white cells adjacent to clues, and average clue extremity. Easy, Normal, and Hard target decreasing wall densities of 16%, 10.5%, and 5.5% of board area. These values describe a structural difficulty proxy. The generator does not currently measure solver node counts when assigning a difficulty label, and it does not test uniqueness. Do not claim unique solutions or calibrated difficulty in a submission.

## 6. Experimental results

Run the benchmark using identical puzzle IDs and resource limits for both solvers:

```sh
uv run python -m lightup.benchmark --size 7 --difficulty easy --algorithms dfs astar --repeats 3 --timeout 30 --csv results/benchmark.csv
```

The desktop interface also has a **Compare DFS and A*** control that runs one bounded measurement per algorithm on the currently loaded puzzle. Use the CLI for repeated runs and CSV records.

| Puzzle ID | Size / mode | Algorithm | Runs | Median time (s) | Median peak Python bytes | Median expanded | Status |
|---|---|---|---:|---:|---:|---:|---|
| `akari-7-easy-70097` | 7×7 Easy, seed 70097 | DFS | 3 | 0.016231 | 18,440 | 8 | SOLVED |
| `akari-7-easy-70097` | 7×7 Easy, seed 70097 | A* | 3 | 0.155982 | 37,352 | 70 | SOLVED |

These are the actual measurements saved in [`results/benchmark.csv`](../results/benchmark.csv) on Python 3.12.13 in the current workspace. Times include the solver's runtime while `tracemalloc` is active and are machine-specific. Both algorithms returned a 7-bulb solution for this instance; A* expanded more states and used more peak Python memory while proving its minimum-cost result. This is one puzzle and does not establish a general ranking.

The runner uses `time.perf_counter()` and starts `tracemalloc` around each solver call. The memory metric measures peak Python allocations, not process RSS, and excludes the input puzzle constructed before tracing. Timeout, node-limit, memory-limit, and cancellation statuses are distinct from an exhausted unsolvable search. Report repeats, seed, puzzle ID, and limits with any table or chart.

## 7. Result interpretation

Compare the two algorithms only on the same puzzle instance and under equal limits. DFS may find a valid but non-minimum bulb set and can benefit strongly from its fixed branching order. A* spends memory on the frontier and duplicate-state map, but its lower bound can reduce expansions and its completed result is minimum-cost. A run that times out is incomplete evidence, not evidence of unsolvability. Add explanations based on measured CSV rows rather than assumed trends.

## 8. Limitations and future work

- Difficulty labels use clue/wall structure; solve-complexity calibration and controlled uniqueness testing remain future work.
- The constructive witness is checked during generation but intentionally not stored in the board exposed to players.
- Search remains exponential. Large boards can reach time, node, or estimated-memory limits.
- UI behavior is implemented, but graphical smoke coverage depends on the platform's display support.
- The assignment's required second puzzle is not implemented here.

## 9. References

- Akari rules and puzzle format: [Puzzle Light Up](https://www.puzzle-light-up.com/).
- Russell, S. J., and Norvig, P. *Artificial Intelligence: A Modern Approach*, 4th ed. (2021), search chapters.
- Python 3.12 standard-library documentation for [multiprocessing](https://docs.python.org/3.12/library/multiprocessing.html), [tracemalloc](https://docs.python.org/3.12/library/tracemalloc.html), and [time](https://docs.python.org/3.12/library/time.html).
- [pygame-ce documentation](https://pyga.me/docs/) and [pygame_gui documentation](https://pygame-gui.readthedocs.io/).
