"""Command line benchmark runner: ``python -m lightup.benchmark``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lightup.algorithms.search import SearchLimits
from lightup.benchmark.runner import benchmark, median_summary, write_csv
from lightup.core.serialization import load_puzzle
from lightup.generator import DIFFICULTIES, SIZES, generate_puzzle, get_sample_puzzle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Light Up search algorithms on one puzzle")
    parser.add_argument("--size", type=int, choices=SIZES, default=7)
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default="easy")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--puzzle-json", type=Path)
    parser.add_argument("--algorithms", nargs="+", choices=("dfs", "astar"), default=("dfs", "astar"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--node-limit", type=int, default=500_000)
    parser.add_argument("--memory-limit-mb", type=float, default=512.0)
    parser.add_argument("--csv", type=Path, default=Path("results/benchmark.csv"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least one")
    if args.puzzle_json:
        puzzle = load_puzzle(args.puzzle_json)
    elif args.seed is None:
        puzzle = get_sample_puzzle(args.size, args.difficulty)
    else:
        puzzle = generate_puzzle(args.size, args.difficulty, args.seed)
    limits = SearchLimits(args.timeout, args.node_limit, args.memory_limit_mb)
    rows = benchmark(puzzle, tuple(args.algorithms), args.repeats, limits)
    write_csv(rows, args.csv)
    print(
        json.dumps(
            {
                "puzzle_id": puzzle.puzzle_id,
                "same_puzzle_for_all_algorithms": True,
                "summary": median_summary(rows),
                "csv": str(args.csv),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
