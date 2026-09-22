"""Verify observation isolation and censored outcomes in the experiment."""
import unittest
from unittest.mock import patch

from minesweeper.benchmark import replay, run_game
from minesweeper.hybrid import Providers
from minesweeper.game import MinesweeperGame


class BenchmarkTests(unittest.TestCase):
    def test_opening_flood_completed_after_deadline_is_not_a_budgeted_win(self):
        times = {"now": 0.0}
        original = MinesweeperGame.reveal

        def slow_reveal(game, row, col):
            outcome = original(game, row, col)
            times["now"] = 100
            return outcome

        with patch("minesweeper.benchmark.time.monotonic", side_effect=lambda: times["now"]), patch.object(
                MinesweeperGame, "reveal", slow_reveal):
            run = run_game("code", 100, 100, 1, 5, seconds=10)
        self.assertEqual(run["safe_coverage"], 1)
        self.assertEqual(run["status"], "time_limit")

    def test_expired_provider_result_never_reveals(self):
        times = {"now": 0.0}

        def late_choice(mode, state, providers):
            times["now"] = 100
            return state["candidates"][0]["cell"], {}

        with patch("minesweeper.benchmark.time.monotonic", side_effect=lambda: times["now"]), patch(
                "minesweeper.benchmark.choose", side_effect=late_choice):
            run = run_game("jev", 9, 9, 10, 1, seconds=10)
        self.assertEqual(run["status"], "time_limit")
        self.assertEqual(run["guesses"], 0)
        self.assertEqual(run["decisions"][-1]["discarded"], "expired_decision")

    def test_replay_does_not_send_truth_and_records_guarded_counterfactual(self):
        state = {"candidates": [
            {"cell": "r1c1", "row": 0, "col": 0, "mine_risk": .1},
            {"cell": "r1c2", "row": 0, "col": 1, "mine_risk": .9},
        ], "probabilities_complete": True}
        seen = []

        def call(provider, engine, submitted):
            seen.append(submitted)
            return "r1c2", {"confidence": 1, "needs_review": 0}

        with patch.object(Providers, "call", call):
            row = replay([{"state": state, "seed": 1, "mine_labels": ["r1c2"]}],
                         ["hybrid"], 2, 10, "mock", "mock")[0]
        self.assertTrue(all("mine_labels" not in submitted for submitted in seen))
        self.assertIs(seen[0], state)
        self.assertTrue(row["initial_would_hit_mine"])
        self.assertFalse(row["initial_guarded_would_hit_mine"])
        self.assertFalse(row["would_hit_mine"])

    def test_budget_exhaustion_counts_unfinished_game(self):
        run = run_game("hybrid", 9, 9, 10, 1, max_calls=0)
        self.assertEqual(run["status"], "call_budget_exhausted")
        self.assertEqual(run["guesses"], 0)
        self.assertEqual(run["calls"], [])


if __name__ == "__main__":
    unittest.main()
