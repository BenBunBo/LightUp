# Presentation Outline — Light Up AI Search

1. **Problem and game rules** — show a sample board; explain bulbs, visibility, clues, and the goal.
2. **Search model** — state as a partial bulb set/bitmask; placement action; transition checks; exact goal test.
3. **DFS** — LIFO frontier, fixed row-major branch choice, pruning and backtracking; explain that the first solution is not optimized.
4. **A*** — `f = g + h`, unit bulb cost, each admissible lower-bound component, and the minimum-bulb guarantee if search completes.
5. **Puzzle generation** — show how seeded construction retains walls only when a known witness remains valid; distinguish verified solvability from uniqueness.
6. **Live demo** — start a 7×7 search, pause, step through sampled exploration, show counters and then replay the returned solution.
7. **Experimental setup** — same puzzle ID, seed, limits, repeats, `perf_counter`, and `tracemalloc`; identify memory as Python allocation peak.
8. **Measured comparison** — import actual CSV medians for time, peak memory, expanded nodes, and status; explain any limits or timeout results.
9. **Limitations** — exponential search, structural rather than calibrated difficulty labels, uniqueness not tested, and the separate second-puzzle requirement.
10. **Questions** — discuss alternative branch policies, stronger admissible bounds, and uniqueness checking.
