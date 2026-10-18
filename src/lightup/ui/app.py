"""Pygame and pygame_gui application for manual play and solver playback."""

from __future__ import annotations

import multiprocessing as mp
import queue
import time
from typing import Any

import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UIDropDownMenu, UIHorizontalSlider, UILabel, UITextEntryLine

from lightup.algorithms.search import SearchLimits, SearchResult
from lightup.benchmark.runner import BenchmarkRow
from lightup.benchmark.worker import benchmark_worker
from lightup.core.model import Cell
from lightup.core.rules import (
    get_adjacent_bulbs,
    get_illuminated_cells,
    get_legal_actions,
    has_bulb_conflicts,
    is_goal_state,
)
from lightup.generator import DIFFICULTIES, generate_puzzle, get_sample_puzzle
from lightup.worker import solver_worker

BG = (16, 22, 33)
PANEL = (26, 34, 49)
PANEL_EDGE = (53, 66, 88)
TEXT = (231, 237, 247)
MUTED = (153, 167, 188)
GOLD = (255, 207, 87)
LIT = (74, 87, 92)
UNLIT = (48, 62, 79)
WALL = (21, 27, 38)
ERROR = (243, 94, 105)
FOCUS = (77, 190, 255)


class LightUpApp:
    """Own the game loop, widgets, board display and worker lifecycle."""

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Light Up — AI Search Visualizer")
        self.screen = pygame.display.set_mode((1500, 920), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui,arial", 18)
        self.small_font = pygame.font.SysFont("segoeui,arial", 14)
        self.big_font = pygame.font.SysFont("segoeui,arial", 28, bold=True)
        self.manager = pygame_gui.UIManager(self.screen.get_size())
        self.widgets: list[Any] = []
        self._make_widgets()

        self.puzzle = get_sample_puzzle(7, "easy")
        self.bulbs: set[Cell] = set()
        self.notes: set[Cell] = set()
        self.undo_stack: list[tuple[set[Cell], set[Cell]]] = []
        self.redo_stack: list[tuple[set[Cell], set[Cell]]] = []
        self.hint_cell: Cell | None = None
        self.game_started_at = time.perf_counter()
        self.message = "Ready — place bulbs or start a search."

        self.process: mp.Process | None = None
        self.messages: Any = None
        self.stop_event: Any = None
        self.pause_event: Any = None
        self.step_event: Any = None
        self.sampling_interval: Any = None
        self.delay_seconds: Any = None
        self.search_result: SearchResult | None = None
        self.search_status = "Idle"
        self.search_stats: dict[str, Any] = {}
        self.benchmark_rows: list[BenchmarkRow] = []
        self.worker_kind = ""
        self.search_bulbs: set[Cell] = set()
        self.manual_edited_after_search = False
        self.focus_cell: Cell | None = None
        self.playback_index = 0
        self.playback_started = False
        self.playback_last = 0.0
        self._rebuild_widgets()

    def _make_widgets(self) -> None:
        # Widget references are replaced on window resize so sidebars stay anchored.
        self.size_menu = self.difficulty_menu = self.seed_entry = None
        self.mode_menu = self.algorithm_menu = None
        self.speed_slider = None
        self.sampling_interval = self.delay_seconds = None
        self.buttons: dict[str, UIButton] = {}
        self.labels: dict[str, UILabel] = {}
        self.widgets.clear()

    def _widget(self, widget: Any) -> Any:
        self.widgets.append(widget)
        return widget

    def _rebuild_widgets(self) -> None:
        for widget in self.widgets:
            widget.kill()
        self.widgets.clear()
        width, height = self.screen.get_size()
        manager = self.manager

        def label(name: str, text: str, x: int, y: int, w: int = 220, h: int = 26, font: int | None = None) -> None:
            self.labels[name] = self._widget(
                UILabel(pygame.Rect(x, y, w, h), text, manager, object_id="#lightup_label")
            )

        def button(name: str, text: str, x: int, y: int, w: int, h: int = 38) -> None:
            self.buttons[name] = self._widget(
                UIButton(pygame.Rect(x, y, w, h), text, manager, object_id="#lightup_button")
            )

        left_x, left_w = 20, 230
        right_w, right_x = 250, max(275, width - 270)
        current_size = self.puzzle.size if hasattr(self, "puzzle") else 7
        current_difficulty = self.puzzle.difficulty.title() if hasattr(self, "puzzle") else "Easy"
        self._widget(UILabel(pygame.Rect(left_x, 24, left_w, 42), "", manager, object_id="#lightup_title"))
        label("subtitle", "AI Search Visualizer", left_x + 2, 61, 220)
        label("size_title", "Board size", left_x + 2, 98)
        self.size_menu = self._widget(
            UIDropDownMenu(
                ["7×7", "10×10", "14×14", "25×25"],
                f"{current_size}×{current_size}",
                pygame.Rect(left_x, 124, left_w, 38),
                manager,
            )
        )
        label("difficulty_title", "Difficulty", left_x + 2, 171)
        self.difficulty_menu = self._widget(
            UIDropDownMenu(
                [s.title() for s in DIFFICULTIES], current_difficulty, pygame.Rect(left_x, 197, left_w, 38), manager
            )
        )
        label("seed_title", "Puzzle seed (blank = random)", left_x + 2, 244)
        self.seed_entry = self._widget(UITextEntryLine(pygame.Rect(left_x, 270, left_w, 38), manager))
        self.seed_entry.set_text(
            str(self.puzzle.seed) if hasattr(self, "puzzle") and self.puzzle.seed is not None else ""
        )
        button("new", "New Game", left_x, 316, left_w)

        label("mode_title", "Play mode", left_x + 2, 369)
        self.mode_menu = self._widget(
            UIDropDownMenu(["Manual", "Algorithm"], "Manual", pygame.Rect(left_x, 395, left_w, 38), manager)
        )
        label("algorithm_title", "Search algorithm", left_x + 2, 444)
        self.algorithm_menu = self._widget(
            UIDropDownMenu(["DFS", "A*"], "DFS", pygame.Rect(left_x, 470, left_w, 38), manager)
        )
        button("solve", "Start Search", left_x, 516, left_w)
        button("pause", "Pause", left_x, 562, 72)
        button("step", "Step", left_x + 79, 562, 72)
        button("stop", "Stop", left_x + 158, 562, 72)

        button("undo", "Undo", left_x, 615, 72)
        button("redo", "Redo", left_x + 79, 615, 72)
        button("reset", "Reset", left_x + 158, 615, 72)
        button("check", "Check Solution", left_x, 660, left_w)
        button("hint", "Hint", left_x, 706, left_w)
        button("back", "<", left_x, 751, 54)
        button("play", "Play", left_x + 63, 751, 95)
        button("forward", ">", left_x + 167, 751, 63)
        label("speed_title", "Animation speed", left_x + 2, 801)
        self.speed_slider = self._widget(
            UIHorizontalSlider(pygame.Rect(left_x, 827, left_w, 30), 45.0, (1.0, 100.0), manager)
        )
        label("speed_value", "45%", left_x + 2, 858)

        self._widget(
            UILabel(pygame.Rect(right_x, 24, right_w, 36), "SEARCH STATUS", manager, object_id="#lightup_title")
        )
        for name, text, y in (
            ("status", "Idle", 77),
            ("algorithm", "Algorithm: —", 122),
            ("expanded", "Expanded: 0", 170),
            ("generated", "Generated: 0", 207),
            ("depth", "Depth: 0", 244),
            ("frontier", "Frontier: 0", 281),
            ("runtime", "Runtime: 0.00s", 318),
            ("memory", "Peak memory: —", 355),
            ("cost", "Solution cost: —", 392),
            ("score", "A*: g 0  •  h 0  •  f 0", 429),
            ("timer", "Play time: 00:00", 477),
            ("game_status", "Not checked", 514),
            ("seed_info", "Seed: —", 551),
        ):
            label(name, text, right_x + 2, y, right_w - 8)
        self.buttons["benchmark"] = self._widget(
            UIButton(
                pygame.Rect(right_x + 10, 596, right_w - 20, 38),
                "Compare DFS and A*",
                manager,
                object_id="#lightup_button",
            )
        )
        label("comparison", "Algorithm / seconds / KiB / nodes", right_x + 2, 644, right_w - 8)
        label("comparison_dfs", "DFS —", right_x + 2, 672, right_w - 8)
        label("comparison_astar", "A* —", right_x + 2, 700, right_w - 8)
        label("comparison_status", "", right_x + 2, 728, right_w - 8)
        label(
            "controls",
            "Left click: bulb  •  Right click: X",
            right_x + 2,
            height - 122,
            right_w - 8,
        )
        label(
            "legend",
            "Gold: lit   Slate: dark   Blue: focus",
            right_x + 2,
            height - 66,
            right_w - 8,
        )

    def _geometry(self) -> tuple[pygame.Rect, int]:
        width, height = self.screen.get_size()
        left, right = 265, 270
        available_w = max(240, width - left - right)
        available_h = max(200, height - 80)
        board_px = min(available_w, available_h)
        x = left + (available_w - board_px) // 2
        y = max(28, (height - board_px) // 2)
        return pygame.Rect(x, y, board_px, board_px), board_px // self.puzzle.size

    def _save_undo(self) -> None:
        self.undo_stack.append((self.bulbs.copy(), self.notes.copy()))
        self.redo_stack.clear()

    def _restore(
        self, source: list[tuple[set[Cell], set[Cell]]], destination: list[tuple[set[Cell], set[Cell]]]
    ) -> None:
        if not source:
            return
        destination.append((self.bulbs.copy(), self.notes.copy()))
        self.bulbs, self.notes = source.pop()
        self.message = "Move restored."

    def _new_game(self) -> None:
        try:
            size_text = (
                self.size_menu.selected_option[0]
                if isinstance(self.size_menu.selected_option, tuple)
                else self.size_menu.selected_option
            )
            size = int(str(size_text).split("×")[0])
            difficulty_text = self.difficulty_menu.selected_option
            difficulty = (difficulty_text[0] if isinstance(difficulty_text, tuple) else difficulty_text).lower()
            seed_text = self.seed_entry.get_text().strip()
            seed = int(seed_text) if seed_text else time.time_ns() % (2**31)
            if self._worker_running():
                self._stop_worker()
            self.puzzle = generate_puzzle(size, difficulty, seed)
            self.bulbs.clear()
            self.notes.clear()
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.search_result = None
            self.search_bulbs.clear()
            self.manual_edited_after_search = False
            self.focus_cell = None
            self.search_status = "Idle"
            self.search_stats = {}
            self.benchmark_rows.clear()
            self.labels["comparison"].set_text("Algorithm / seconds / KiB / nodes")
            self.labels["comparison_dfs"].set_text("DFS —")
            self.labels["comparison_astar"].set_text("A* —")
            self.labels["comparison_status"].set_text("")
            self.hint_cell = None
            self.game_started_at = time.perf_counter()
            self.message = f"Loaded {self.puzzle.puzzle_id}; witness checked, uniqueness not tested."
            self.labels["game_status"].set_text("Not checked")
            self.labels["seed_info"].set_text(f"Seed: {seed}")
            self._rebuild_widgets()
        except (ValueError, RuntimeError) as exc:
            self.message = f"Could not create puzzle: {exc}"

    def _worker_running(self) -> bool:
        return self.process is not None and self.process.is_alive()

    def _new_message_queue(self, context: Any) -> Any:
        if self.messages is not None:
            self.messages.close()
            self.messages.join_thread()
        return context.Queue(maxsize=64)

    def _start_search(self) -> None:
        if self._worker_running():
            self.message = "A solver is already running."
            return
        algorithm_text = self.algorithm_menu.selected_option
        algorithm = (algorithm_text[0] if isinstance(algorithm_text, tuple) else algorithm_text).upper()
        ctx = mp.get_context("spawn")
        self.messages = self._new_message_queue(ctx)
        self.stop_event = ctx.Event()
        self.pause_event = ctx.Event()
        self.step_event = ctx.Event()
        self.sampling_interval = ctx.Value("i", 28)
        self.delay_seconds = ctx.Value("d", 0.045)
        limits = SearchLimits(timeout_seconds=30.0, node_limit=250_000, memory_limit_mb=384.0)
        self.process = ctx.Process(
            target=solver_worker,
            args=(
                self.puzzle,
                algorithm,
                limits,
                self.messages,
                self.stop_event,
                self.pause_event,
                self.step_event,
                self.sampling_interval,
                self.delay_seconds,
            ),
            daemon=True,
        )
        self.process.start()
        self.worker_kind = "search"
        self.search_result = None
        self.search_bulbs.clear()
        self.manual_edited_after_search = False
        self.search_status = "Running"
        self.search_stats = {
            "algorithm": algorithm,
            "expanded": 0,
            "generated": 0,
            "frontier_size": 0,
            "depth": 0,
            "elapsed_seconds": 0.0,
        }
        self.playback_index = 0
        self.message = f"{algorithm} is exploring states in a worker process."

    def _start_benchmark(self) -> None:
        if self._worker_running():
            self.message = "A solver or benchmark is already running."
            return
        ctx = mp.get_context("spawn")
        self.messages = self._new_message_queue(ctx)
        self.stop_event = ctx.Event()
        self.pause_event = None
        self.step_event = None
        self.sampling_interval = None
        self.delay_seconds = None
        limits = SearchLimits(timeout_seconds=20.0, node_limit=100_000, memory_limit_mb=256.0)
        self.process = ctx.Process(
            target=benchmark_worker,
            args=(self.puzzle, limits, self.messages, self.stop_event),
            daemon=True,
        )
        self.process.start()
        self.worker_kind = "benchmark"
        self.benchmark_rows.clear()
        self.search_status = "Benchmarking"
        self.labels["comparison_dfs"].set_text("DFS running…")
        self.labels["comparison_astar"].set_text("A* queued…")
        self.labels["comparison_status"].set_text("Same puzzle, one run each")
        self.message = "Side-by-side benchmark is running in a worker process."

    def _stop_worker(self) -> None:
        if self.process is None:
            return
        if self.stop_event is not None:
            self.stop_event.set()
        if self.pause_event is not None:
            self.pause_event.clear()
        if self.step_event is not None:
            self.step_event.set()
        self.process.join(timeout=0.5)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=0.5)
        self.search_status = "Stopped"

    def _poll_worker(self) -> None:
        if self.messages is not None:
            for _ in range(30):
                try:
                    kind, payload = self.messages.get_nowait()
                except queue.Empty:
                    break
                if kind == "progress":
                    self.search_bulbs = set(tuple(cell) for cell in payload["bulbs"])
                    self.focus_cell = tuple(payload["focus"]) if payload["focus"] else None
                    self.search_stats = payload
                    if payload["kind"] == "reject":
                        self.message = f"Rejected {payload['focus']}: {payload['detail']}"
                    else:
                        self.message = f"Exploring depth {payload['depth']} at {payload['focus']}"
                elif kind == "result":
                    self.search_result = payload
                    self.search_status = payload.status.value
                    self.search_stats.update(
                        expanded=payload.expanded,
                        generated=payload.generated,
                        frontier_size=payload.max_frontier,
                        elapsed_seconds=payload.elapsed_seconds,
                    )
                    if payload.solution:
                        self.search_bulbs = set(payload.solution)
                        self.manual_edited_after_search = False
                        self.playback_index = max(0, len(payload.solution_path) - 1)
                        self.message = (
                            f"Solved with {len(payload.solution)} bulbs. The final state passed the rule validator."
                        )
                    else:
                        self.message = f"Search finished: {payload.status.value}. {payload.message}"
                elif kind == "benchmark":
                    self.benchmark_rows = payload
                    self.search_status = "Benchmark complete"
                    self._show_benchmark_rows(payload)
                    self.message = "Benchmark finished. Results use one repetition per algorithm on this board."
                elif kind == "error":
                    self.search_status = "Worker error"
                    self.message = str(payload).splitlines()[0]
        if self.process is not None and not self.process.is_alive():
            self.process.join(timeout=0)
            if self.search_status == "Running":
                self.search_status = "Worker exited"

    def _toggle_pause(self) -> None:
        if self.worker_kind != "search" or not self._worker_running() or self.pause_event is None:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.message = "Search resumed."
            self.buttons["pause"].set_text("Pause")
        else:
            self.pause_event.set()
            self.message = "Search paused; Step advances to the next sampled state."
            self.buttons["pause"].set_text("Resume")

    def _button_action(self, name: str) -> None:
        if name == "new":
            self._new_game()
        elif name == "solve":
            self._start_search()
        elif name == "benchmark":
            self._start_benchmark()
        elif name == "pause":
            self._toggle_pause()
        elif name == "step":
            if self.step_event is not None:
                self.step_event.set()
        elif name == "stop":
            self._stop_worker()
        elif name == "undo":
            self._restore(self.undo_stack, self.redo_stack)
        elif name == "redo":
            self._restore(self.redo_stack, self.undo_stack)
        elif name == "reset":
            if self._worker_running():
                self._stop_worker()
            if self.bulbs or self.notes:
                self._save_undo()
            self.bulbs.clear()
            self.notes.clear()
            self.search_result = None
            self.search_bulbs.clear()
            self.focus_cell = None
            self.manual_edited_after_search = False
            self.search_stats = {}
            self.search_status = "Idle"
            self.message = "Board reset."
        elif name == "check":
            valid = is_goal_state(self.puzzle, self.bulbs)
            self.labels["game_status"].set_text("Solved! ✓" if valid else "Not solved — check clues and dark cells")
            self.message = (
                "Correct solution." if valid else "There are still dark cells, conflicts, or unsatisfied clues."
            )
        elif name == "hint":
            self.hint_cell = next(
                (cell for cell in get_legal_actions(self.puzzle, self.bulbs) if cell not in self.bulbs), None
            )
            self.message = (
                f"Hint: consider {self.hint_cell}." if self.hint_cell else "No legal bulb placement is available."
            )
        elif name == "back":
            self._playback_step(-1)
        elif name == "forward":
            self._playback_step(1)
        elif name == "play":
            self.playback_started = not self.playback_started
            if self.playback_started and self.search_result and self.search_result.solution_path:
                self.manual_edited_after_search = False
                if self.playback_index >= len(self.search_result.solution_path) - 1:
                    self.playback_index = 0
                    self.search_bulbs = set(self.search_result.solution_path[0])
            self.buttons["play"].set_text("Pause" if self.playback_started else "Play")

    def _playback_step(self, amount: int) -> None:
        if not self.search_result or not self.search_result.solution_path:
            self.message = "Run a solver first to create a solution playback."
            return
        self.playback_started = False
        last = len(self.search_result.solution_path) - 1
        self.manual_edited_after_search = False
        self.playback_index = min(last, max(0, self.playback_index + amount))
        self.search_bulbs = set(self.search_result.solution_path[self.playback_index])

    def _show_benchmark_rows(self, rows: list[BenchmarkRow]) -> None:
        by_algorithm = {row.algorithm: row for row in rows}
        for key, algorithm in (("comparison_dfs", "DFS"), ("comparison_astar", "ASTAR")):
            row = by_algorithm.get(algorithm)
            if row is None:
                self.labels[key].set_text(f"{algorithm}: cancelled")
            else:
                name = "A*" if algorithm == "ASTAR" else algorithm
                self.labels[key].set_text(
                    f"{name}  {row.execution_time_seconds:.3f}s  "
                    f"{row.peak_python_memory_bytes / 1024:.1f}KiB  {row.nodes_expanded}n"
                )
        statuses = "  ".join(f"{row.algorithm}: {row.status}" for row in rows)
        self.labels["comparison_status"].set_text(statuses or "No completed runs")

    def _board_click(self, pos: tuple[int, int], button: int) -> None:
        if self._worker_running():
            return
        mode = self.mode_menu.selected_option
        mode_text = (mode[0] if isinstance(mode, tuple) else mode).lower()
        if mode_text != "manual":
            return
        if self.search_result is not None and not self.manual_edited_after_search:
            self.bulbs = set(self.search_bulbs)
            self.manual_edited_after_search = True
        board_rect, cell_px = self._geometry()
        if cell_px <= 0 or not board_rect.collidepoint(pos):
            return
        cell = ((pos[1] - board_rect.y) // cell_px, (pos[0] - board_rect.x) // cell_px)
        if not self.puzzle.is_white(cell):
            return
        self._save_undo()
        if button == 1:
            if cell in self.bulbs:
                self.bulbs.remove(cell)
            elif cell not in self.bulbs:
                self.bulbs.add(cell)
                self.notes.discard(cell)
            self.hint_cell = None
            self.labels["game_status"].set_text("In progress")
            self.message = "Bulb placed. Red bulbs indicate a line-of-sight conflict."
        elif button == 3 and cell not in self.bulbs:
            if cell in self.notes:
                self.notes.remove(cell)
            else:
                self.notes.add(cell)
        if is_goal_state(self.puzzle, self.bulbs):
            self.labels["game_status"].set_text("Solved! ✓")
            self.message = "Puzzle solved — every white cell is lit and all clues match."

    def _draw_board(self) -> None:
        board_rect, cell_px = self._geometry()
        show_search = self._worker_running() or (self.search_result is not None and not self.manual_edited_after_search)
        display_bulbs = self.search_bulbs if show_search else self.bulbs
        lit = get_illuminated_cells(self.puzzle, display_bulbs)
        conflicts: set[Cell] = set()
        if has_bulb_conflicts(self.puzzle, display_bulbs):
            for cell in display_bulbs:
                row, col = cell
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    r, c = row + dr, col + dc
                    while self.puzzle.is_white((r, c)):
                        if (r, c) in display_bulbs:
                            conflicts.update((cell, (r, c)))
                        r += dr
                        c += dc

        pygame.draw.rect(self.screen, PANEL, board_rect.inflate(12, 12), border_radius=12)
        for row in range(self.puzzle.size):
            for col in range(self.puzzle.size):
                cell = (row, col)
                rect = pygame.Rect(board_rect.x + col * cell_px, board_rect.y + row * cell_px, cell_px, cell_px)
                value = self.puzzle.rows[row][col]
                if value is not None:
                    pygame.draw.rect(self.screen, WALL, rect)
                    if value >= 0:
                        adjacent = len(get_adjacent_bulbs(self.puzzle, cell, display_bulbs))
                        clue_color = TEXT if adjacent == value else GOLD if adjacent < value else ERROR
                        self._draw_text(str(value), rect.center, clue_color, small=cell_px < 35)
                else:
                    color = LIT if cell in lit else UNLIT
                    pygame.draw.rect(self.screen, color, rect)
                    if cell in self.notes:
                        self._draw_text("×", rect.center, MUTED, small=cell_px < 35)
                    if cell in display_bulbs:
                        bulb_color = ERROR if cell in conflicts else GOLD
                        radius = max(5, int(cell_px * 0.27))
                        pygame.draw.circle(self.screen, bulb_color, rect.center, radius)
                        pygame.draw.circle(self.screen, (255, 242, 191), rect.center, max(2, radius // 3))
                    if cell == self.focus_cell or cell == self.hint_cell:
                        pygame.draw.rect(
                            self.screen, FOCUS if cell == self.focus_cell else GOLD, rect, max(2, cell_px // 13)
                        )
                pygame.draw.rect(self.screen, PANEL_EDGE, rect, max(1, cell_px // 40))

    def _draw_text(self, text: str, pos: tuple[int, int], color: tuple[int, int, int], small: bool = False) -> None:
        font = self.small_font if small else self.font
        rendered = font.render(text, True, color)
        self.screen.blit(rendered, rendered.get_rect(center=pos))

    def _update_labels(self) -> None:
        stats = self.search_stats
        elapsed = int(time.perf_counter() - self.game_started_at)
        minutes, seconds = divmod(elapsed, 60)
        values = {
            "status": self.search_status,
            "algorithm": f"Algorithm: {stats.get('algorithm', '—')}",
            "expanded": f"Expanded: {stats.get('expanded', 0)}",
            "generated": f"Generated: {stats.get('generated', 0)}",
            "depth": f"Depth: {stats.get('depth', 0)}",
            "frontier": f"Frontier: {stats.get('frontier_size', 0)}",
            "runtime": f"Runtime: {stats.get('elapsed_seconds', 0):.2f}s",
            "memory": f"Peak memory: {self.search_result.peak_memory_bytes / 1024:.1f} KiB est."
            if self.search_result
            else "Peak memory: worker estimate",
            "cost": f"Solution cost: {self.search_result.solution_cost}" if self.search_result else "Solution cost: —",
            "score": f"A*: g {stats.get('g', 0)}  •  h {stats.get('h', 0)}  •  f {stats.get('f', 0)}",
            "timer": f"Play time: {minutes:02d}:{seconds:02d}",
            "seed_info": (
                f"Seed: {self.puzzle.seed}  •  {self.puzzle.size}×{self.puzzle.size} / {self.puzzle.difficulty.title()}"
            ),
            "speed_value": f"{int(self.speed_slider.get_current_value())}%",
        }
        for name, value in values.items():
            if name in self.labels:
                self.labels[name].set_text(value)
        if self.sampling_interval is not None:
            speed = self.speed_slider.get_current_value()
            self.sampling_interval.value = max(1, int(51 - speed * 0.5))
            self.delay_seconds.value = max(0.0, (100.0 - speed) / 100.0 * 0.08)

    def _update_playback(self, dt: float) -> None:
        if not self.playback_started or not self.search_result or not self.search_result.solution_path:
            return
        speed = self.speed_slider.get_current_value()
        interval = 0.8 * (101 - speed) / 100
        now = time.perf_counter()
        if now - self.playback_last >= interval:
            self.playback_last = now
            if self.playback_index < len(self.search_result.solution_path) - 1:
                self._playback_step(1)
            else:
                self.playback_started = False
                self.buttons["play"].set_text("Play")

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            self._poll_worker()
            self._update_playback(dt)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    resized_size = (max(1100, event.w), max(900, event.h))
                    self.screen = pygame.display.set_mode(resized_size, pygame.RESIZABLE)
                    self.manager.set_window_resolution(resized_size)
                    self._rebuild_widgets()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._board_click(event.pos, event.button)

                self.manager.process_events(event)
                if event.type == pygame_gui.UI_BUTTON_PRESSED:
                    for name, widget in self.buttons.items():
                        if event.ui_element == widget:
                            self._button_action(name)
                            break
                elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                    if event.ui_element == self.size_menu or event.ui_element == self.difficulty_menu:
                        # The choice is applied by New Game so size and difficulty remain independent.
                        pass
                    elif event.ui_element == self.mode_menu and self.search_result is not None:
                        if event.text.lower() == "manual":
                            self.bulbs = set(self.search_bulbs)
                            self.manual_edited_after_search = True
                        else:
                            self.manual_edited_after_search = False
            self.manager.update(dt)
            self.screen.fill(BG)
            width, height = self.screen.get_size()
            pygame.draw.rect(self.screen, PANEL, pygame.Rect(10, 10, 250, height - 20), border_radius=14)
            pygame.draw.rect(self.screen, PANEL, pygame.Rect(width - 260, 10, 250, height - 20), border_radius=14)
            self.screen.blit(self.big_font.render("LIGHT UP", True, TEXT), (30, 24))
            self._draw_board()
            # Small status strip under the board area.
            board_rect, _ = self._geometry()
            status_surface = self.small_font.render(self.message[:118], True, MUTED)
            self.screen.blit(status_surface, (board_rect.x, min(self.screen.get_height() - 22, board_rect.bottom + 15)))
            self._update_labels()
            self.manager.draw_ui(self.screen)
            pygame.display.flip()
        self._stop_worker()
        if self.messages is not None:
            self.messages.close()
            self.messages.join_thread()
        pygame.quit()


def run_app() -> None:
    """Start the desktop game from a proper multiprocessing main guard."""
    LightUpApp().run()
