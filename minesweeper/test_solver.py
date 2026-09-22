"""Exact inference is checked against exhaustive public-state model counting."""

from __future__ import annotations

import itertools
import random
import sys
import unittest

from minesweeper.game import MinesweeperGame
from minesweeper.solver import analyze

Cell = tuple[int, int]


class PublicOnlyGame(MinesweeperGame):
    """Fail loudly if analysis reads hidden truth or requests an unrevealed clue."""

    def __init__(self, width: int, height: int, mines: set[Cell], revealed: set[Cell]) -> None:
        super().__init__(width, height, len(mines), seed=0)
        self.revealed = set(revealed)
        self.phase = "playing"
        self._clues = {cell: len(set(self.neighbors(*cell)) & mines) for cell in revealed}

    def __getattribute__(self, name: str):
        if name in {"mine_cells", "seed", "rng"}:
            raise AssertionError(f"hidden truth access: {name}")
        return super().__getattribute__(name)

    def adjacent_mines(self, row: int, col: int) -> int:
        if (row, col) not in self.revealed:
            raise AssertionError("requested an unrevealed clue")
        return self._clues[row, col]


def brute_force(game: MinesweeperGame) -> tuple[dict[Cell, int], int]:
    hidden = {(r, c) for r in range(game.height) for c in range(game.width)} - game.revealed
    counts = dict.fromkeys(hidden, 0)
    total = 0
    clues = [(set(game.neighbors(*cell)) & hidden, game.adjacent_mines(*cell)) for cell in game.revealed]
    for layout in itertools.combinations(sorted(hidden), game.mines):
        placed = set(layout)
        if all(len(cells & placed) == count for cells, count in clues):
            total += 1
            for cell in placed:
                counts[cell] += 1
    return counts, total


class SolverTests(unittest.TestCase):
    def assert_matches_exhaustive(self, game: MinesweeperGame) -> None:
        counts, total = brute_force(game)
        self.assertGreater(total, 0)
        analysis = analyze(game)
        self.assertTrue(analysis.complete, analysis.stats)
        self.assertEqual(analysis.safe, {cell for cell, count in counts.items() if count == 0})
        self.assertEqual(analysis.mines, {cell for cell, count in counts.items() if count == total})
        for candidate in analysis.candidates:
            cell = candidate["row"], candidate["col"]
            self.assertTrue(candidate["risk_exact"])
            self.assertAlmostEqual(candidate["mine_risk"], counts[cell] / total, places=14)
            self.assertEqual(candidate["provably_safe"], counts[cell] == 0)
        keys = [(item["mine_risk"], item["row"], item["col"]) for item in analysis.candidates]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(analysis.candidates), min(24, len(counts.keys() - analysis.mines - game.flagged)))

    def test_random_small_boards_match_exhaustive_global_probabilities(self) -> None:
        rng = random.Random(4291)
        cells = list(itertools.product(range(3), range(4)))
        for index in range(80):
            mines = set(rng.sample(cells, rng.randint(1, 5)))
            safe = sorted(set(cells) - mines)
            revealed = set(rng.sample(safe, rng.randint(1, len(safe))))
            with self.subTest(index=index):
                self.assert_matches_exhaustive(PublicOnlyGame(4, 3, mines, revealed))

    def test_unconstrained_cells_compete_even_when_frontier_exists(self) -> None:
        game = PublicOnlyGame(4, 3, {(0, 1), (2, 3)}, {(0, 0)})
        analysis = analyze(game)
        self.assert_matches_exhaustive(game)
        self.assertEqual(analysis.candidates[0]["mine_risk"], 1 / 8)
        self.assertFalse(analysis.candidates[0]["frontier"])
        self.assertTrue(any(candidate["frontier"] for candidate in analysis.candidates))

    def test_global_total_couples_disconnected_components(self) -> None:
        # Revealed left and right corner clues create separate frontiers;
        # unobserved middle cells supply the combinatorial global weight.
        game = PublicOnlyGame(5, 3, {(0, 1), (1, 4), (2, 2)}, {(0, 0), (0, 4)})
        self.assert_matches_exhaustive(game)
        self.assertEqual(analyze(game).stats["components"], 2)

    def test_global_weighting_couples_variable_component_mine_counts(self) -> None:
        game = PublicOnlyGame(5, 4,
                              {(0, 0), (0, 4), (1, 2), (1, 4), (2, 2)},
                              {(0, 1), (0, 2), (3, 1), (3, 3)})
        self.assert_matches_exhaustive(game)
        self.assertEqual(analyze(game).stats["components"], 2)

    def test_global_arithmetic_limit_does_not_publish_partial_posteriors(self) -> None:
        # Many disconnected ambiguous components can make global convolution
        # more expensive than each local search, so it has its own bound.
        repeats = 81
        mines = {(0, 0), (0, 4), (1, 2), (1, 4), (2, 2)}
        revealed = {(0, 1), (0, 2), (3, 1), (3, 3)}
        game = PublicOnlyGame(6 * repeats, 4,
                              {(r, c + 6 * i) for i in range(repeats) for r, c in mines},
                              {(r, c + 6 * i) for i in range(repeats) for r, c in revealed})
        analysis = analyze(game, max_search_nodes=85 * repeats)
        self.assertFalse(analysis.complete)
        self.assertEqual(analysis.stats["aborted_components"], 0)
        self.assertTrue(analysis.stats["global_weighting_aborted"])
        self.assertTrue(all(not item["risk_exact"] for item in analysis.candidates))

    def test_flags_are_not_assumed_to_be_mines(self) -> None:
        game = PublicOnlyGame(4, 3, {(0, 1), (2, 3)}, {(0, 0)})
        before = analyze(game)
        game.flagged = {(0, 2)}  # Deliberately wrong flag.
        self.assert_matches_exhaustive(game)
        after = analyze(game)
        self.assertEqual(before.safe, after.safe)
        self.assertEqual(before.mines, after.mines)
        self.assertFalse(any((item["row"], item["col"]) in game.flagged for item in after.candidates))

    def test_all_proven_safe_cells_are_returned_beyond_candidate_limit(self) -> None:
        game = PublicOnlyGame(30, 30, {(0, 0)}, {(0, 1), (1, 0), (1, 1), (0, 2), (1, 2), (2, 0), (2, 1)})
        analysis = analyze(game)
        self.assertTrue(analysis.complete)
        self.assertEqual(analysis.mines, {(0, 0)})
        self.assertEqual(len(analysis.safe), 892)
        self.assertEqual(len(analysis.candidates), 24)
        self.assertTrue(all(item["provably_safe"] for item in analysis.candidates))

    def test_node_limit_discards_partial_solution_counts(self) -> None:
        game = PublicOnlyGame(4, 3, {(0, 1), (2, 3)}, {(0, 0)})
        for limit in (0, 1, 5):
            with self.subTest(limit=limit):
                analysis = analyze(game, max_search_nodes=limit)
                self.assertFalse(analysis.complete)
                self.assertEqual(analysis.stats["aborted_components"], 1)
                self.assertLessEqual(analysis.stats["search_nodes"], limit)
                self.assertFalse(analysis.safe)
                self.assertFalse(analysis.mines)
                self.assertTrue(all(not item["risk_exact"] for item in analysis.candidates))

    def test_deep_component_stack_limit_discards_partial_counts(self) -> None:
        game = PublicOnlyGame(500, 3, {(0, col) for col in range(500)},
                              {(1, col) for col in range(500)})
        previous_limit = sys.getrecursionlimit()
        try:
            # Exercise a real recursive search, independently of the test
            # runner's configured limit, and restore that setting afterward.
            sys.setrecursionlimit(400)
            analysis = analyze(game, max_component_cells=1100)
        finally:
            sys.setrecursionlimit(previous_limit)
        self.assertFalse(analysis.complete)
        self.assertEqual(analysis.stats["largest_component"], 1000)
        self.assertEqual(analysis.stats["aborted_components"], 1)
        self.assertEqual(analysis.stats["oversized_components"], 0)
        self.assertGreater(analysis.stats["search_nodes"], 0)
        self.assertFalse(analysis.safe)
        self.assertFalse(analysis.mines)
        self.assertTrue(analysis.candidates)
        self.assertTrue(all(not item["risk_exact"] for item in analysis.candidates))

    def test_oversized_component_does_not_claim_exact_risk(self) -> None:
        game = PublicOnlyGame(4, 3, {(0, 1), (2, 3)}, {(0, 0)})
        analysis = analyze(game, max_component_cells=2)
        self.assertFalse(analysis.complete)
        self.assertEqual(analysis.stats["oversized_components"], 1)
        self.assertTrue(all(not item["risk_exact"] for item in analysis.candidates))

    def test_propagation_proofs_survive_a_search_limit(self) -> None:
        game = PublicOnlyGame(6, 3, {(0, 0), (0, 5)}, {(0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 4)})
        analysis = analyze(game, max_search_nodes=0)
        self.assertFalse(analysis.complete)
        self.assertIn((0, 0), analysis.mines)
        self.assertTrue(analysis.safe)
        counts, total = brute_force(game)
        self.assertTrue(all(counts[cell] == 0 for cell in analysis.safe))
        self.assertTrue(all(counts[cell] == total for cell in analysis.mines))
        self.assertTrue(all(item["risk_exact"] for item in analysis.candidates if item["provably_safe"]))

    def test_analysis_never_changes_the_board(self) -> None:
        game = PublicOnlyGame(4, 3, {(0, 1), (2, 3)}, {(0, 0)})
        before = set(game.revealed), set(game.flagged), game.moves, game.phase
        analyze(game)
        self.assertEqual(before, (game.revealed, game.flagged, game.moves, game.phase))

    def test_inconsistent_public_clues_fail_closed(self) -> None:
        game = PublicOnlyGame(3, 3, {(0, 0)}, {(1, 1)})
        game._clues[(1, 1)] = 9
        analysis = analyze(game)
        self.assertFalse(analysis.complete)
        self.assertTrue(analysis.stats["inconsistent"])
        self.assertFalse(analysis.safe)
        self.assertFalse(analysis.mines)
        self.assertTrue(all(not item["risk_exact"] for item in analysis.candidates))

    def test_terminal_board_is_not_queried_for_clues(self) -> None:
        game = PublicOnlyGame(3, 3, {(0, 0)}, {(0, 0)})
        game.phase = "lost"
        game.adjacent_mines = lambda *_: self.fail("terminal clue read")
        self.assertFalse(analyze(game).candidates)


if __name__ == "__main__":
    unittest.main()
