"""Routing failure modes matter more than fitting tests to prompt wording."""
import unittest
from unittest.mock import patch

from minesweeper.agents import ProviderError
from minesweeper.hybrid import Providers, choose, guarded_choice, probability, review_reasons


def state(risks=(.2, .2), complete=True):
    return {"probabilities_complete": complete, "candidates": [
        {"cell": f"r1c{i+1}", "row": 0, "col": i, "mine_risk": risk}
        for i, risk in enumerate(risks)
    ]}


class HybridTests(unittest.TestCase):
    def test_equivalent_choices_do_not_escalate_for_flat_distribution(self):
        self.assertEqual(review_reasons(state(), "r1c2", {"confidence": 0, "needs_review": .1}), [])

    def test_irrelevant_bad_choice_does_not_make_equal_best_choices_uncertain(self):
        self.assertEqual(review_reasons(state((.1, .1, .9)), "r1c2", {
            "confidence": .25, "needs_review": .1,
            "probabilities": {"r1c1": .5, "r1c2": .5, "r1c3": 0},
        }), [])

    def test_invalid_and_higher_risk_choices_are_rejected(self):
        self.assertEqual(guarded_choice("r9c9", state()["candidates"]), ("r1c1", "choice_not_offered"))
        self.assertEqual(guarded_choice("r1c2", state((.1, .2))["candidates"]),
                         ("r1c1", "higher_computed_risk"))

    def test_incomplete_solver_escalates_even_with_confident_jev(self):
        self.assertIn("incomplete_enumeration", review_reasons(
            state(complete=False), "r1c1", {"confidence": 1, "needs_review": 0}))

    def test_cascade_reviews_then_guards_llm_result(self):
        provider = Providers()
        with patch.object(provider, "call", side_effect=[
            ("r1c1", {"confidence": .9, "needs_review": .9}),
            ("r1c2", {}),
        ]) as call:
            cell, trace = choose("hybrid", state((.1, .2)), provider)
        self.assertEqual(cell, "r1c1")
        self.assertTrue(trace["escalated"])
        self.assertEqual(trace["guard_rejection"], "higher_computed_risk")
        self.assertEqual(trace["initial_guarded_cell"], "r1c1")
        self.assertEqual(call.call_count, 2)

    def test_provider_failure_abstains_instead_of_random_reveal(self):
        provider = Providers()
        with patch.object(provider, "call", side_effect=ProviderError("provider_request_timeout")):
            cell, trace = choose("hybrid", state(), provider)
        self.assertIsNone(cell)
        self.assertEqual(trace["error"], "provider_request_timeout")

    def test_second_stage_failure_abstains_despite_valid_first_choice(self):
        provider = Providers()
        with patch.object(provider, "call", side_effect=[
            ("r1c1", {"confidence": 1, "needs_review": .9}),
            ProviderError("provider_request_timeout"),
        ]):
            cell, trace = choose("hybrid", state(), provider)
        self.assertIsNone(cell)
        self.assertTrue(trace["escalated"])
        self.assertEqual(trace["initial_guarded_cell"], "r1c1")

    def test_one_call_budget_prevents_second_request(self):
        response = {"answers": {"cell": {"choice": "r1c1", "confidence": 1},
                                 "needs_review": {"noul": .9}}}
        with patch("minesweeper.agents.jev_key", return_value="fake"), patch(
                "minesweeper.agents._http_json", return_value=response) as request:
            cell, trace = choose("hybrid", state(), Providers(max_calls=1))
        self.assertIsNone(cell)
        self.assertEqual(trace["error"], "call_budget_exhausted")
        self.assertEqual(request.call_count, 1)

    def test_call_budget_does_not_send_request(self):
        with patch("minesweeper.agents._http_json") as request:
            cell, trace = choose("hybrid", state(), Providers(max_calls=0))
        request.assert_not_called()
        self.assertIsNone(cell)
        self.assertEqual(trace["error"], "call_budget_exhausted")

    def test_nonfinite_and_untyped_confidence_is_missing(self):
        for value in [True, float("nan"), float("inf"), "0.9", -1, 2]:
            self.assertIsNone(probability(value))


if __name__ == "__main__":
    unittest.main()
