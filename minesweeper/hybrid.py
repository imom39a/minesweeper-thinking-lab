"""Experimental Jev -> LLM cascade; deterministic code retains move authority.

These thresholds are hypotheses for evaluation, not calibrated safety limits.
Choice confidence measures preference concentration, never P(cell is safe).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field

from . import agents

POLICY_VERSION = "system-one-two-v2"
REVIEW_PROBABILITY = 0.65
RISK_TOLERANCE = 1e-12
MAX_CONTEXT_CONSTRAINTS = 120
MAX_LLM_OUTPUT_TOKENS = 2048

CHOICE_INSTRUCTIONS = (
    "Choose one cell from `candidates` to reveal. Minimize the code-computed "
    "mine_risk first. Among equal-risk cells prefer a reveal likely to unlock "
    "further deductions from `constraints` or open an unconstrained region. "
    "A risk is an exact probability only when risk_exact is true. Hidden mine "
    "locations are unknown. Do not confuse preference probability with safety."
)
REVIEW_INSTRUCTIONS = (
    "Given only this visible Minesweeper state, is there a concrete distinction "
    "between candidate cells that warrants slower reasoning about subsequent "
    "deductions before choosing a reveal? Equal immediate risk alone is not "
    "a reason to escalate: symmetric guesses cannot be resolved by thinking "
    "longer. Judge the state independently; you cannot see another answer."
)


def probability(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def questions(state: dict) -> dict:
    """Independent Choice and review Noul share one request and one state."""
    return {
        "cell": {
            "type": "choice", "instructions": CHOICE_INSTRUCTIONS,
            "criteria": {c["cell"]: c for c in state["candidates"]},
        },
        "needs_review": {
            "type": "noul", "instructions": REVIEW_INSTRUCTIONS,
            "criteria": {
                "true": "Visible structural differences merit further deliberation.",
                "false": "No useful distinction beyond the supplied risks is evident.",
            },
        },
    }


def decision_state(game, analysis, round_number: int) -> dict:
    """Bound context by constraint count; explicitly disclose any truncation."""
    labels = {c["cell"] for c in analysis.candidates}
    # Relevant constraints first, then adjoining equations. The entire connected
    # structure may exceed the cap; never present the slice as complete evidence.
    remaining = list(analysis.constraints)
    selected = []
    while remaining and len(selected) < MAX_CONTEXT_CONSTRAINTS:
        linked = [c for c in remaining if labels.intersection(c["cells"])]
        if not linked:
            break
        take = linked[:MAX_CONTEXT_CONSTRAINTS - len(selected)]
        selected.extend(take)
        for c in take:
            labels.update(c["cells"])
        remaining = [c for c in remaining if c not in take]
    return {
        "game": "minesweeper", "round": round_number,
        "board": {"width": game.width, "height": game.height,
                  "mines": game.mines, "revealed_count": len(game.revealed),
                  "proven_mines_count": len(analysis.mines)},
        "rules": "Each constraint counts mines in its listed hidden cells. One mine loses.",
        "candidates": analysis.candidates,
        "constraints": selected,
        "constraint_count": len(analysis.constraints),
        "context_truncated": len(selected) < len(analysis.constraints),
        "probabilities_complete": analysis.complete,
        "solver_stats": analysis.stats,
    }


def guarded_choice(proposed: object, candidates: list[dict]) -> tuple[str, str | None]:
    """Prevent a model from exceeding the best offered immediate risk estimate.

    This is a policy check, not a proof of safety. On incomplete enumeration the
    same bound applies to a heuristic; it cannot guarantee true-risk ordering.
    """
    best = min(candidates, key=lambda c: (c["mine_risk"], c["row"], c["col"]))
    offered = {c["cell"]: c for c in candidates}
    if not isinstance(proposed, str) or proposed not in offered:
        return best["cell"], "choice_not_offered"
    if offered[proposed]["mine_risk"] > best["mine_risk"] + RISK_TOLERANCE:
        return best["cell"], "higher_computed_risk"
    return proposed, None


def review_reasons(state: dict, cell: object, metadata: dict) -> list[str]:
    _, rejection = guarded_choice(cell, state["candidates"])
    reasons = [rejection] if rejection else []
    if not state["probabilities_complete"]:
        reasons.append("incomplete_enumeration")
    review = probability(metadata.get("needs_review"))
    if review is None:
        reasons.append("review_signal_missing")
    elif review >= REVIEW_PROBABILITY:
        reasons.append("jev_requests_deliberation")
    # Confidence alone is not a trigger: probability can be split among several
    # equally good cells even when the list also contains worse alternatives.
    return reasons


@dataclass
class Providers:
    jev_model: str = "jev-1.13.0"
    llm_model: str = "openai/gpt-oss-20b"
    max_calls: int = 20
    deadline: float = float("inf")
    calls: list[dict] = field(default_factory=list)

    def call(self, engine: str, state: dict) -> tuple[str | None, dict]:
        if len(self.calls) >= self.max_calls:
            raise agents.ProviderError("call_budget_exhausted")
        remaining = self.deadline - time.monotonic()
        if remaining < 1:
            raise agents.ProviderError("time_budget_exhausted")
        event = {"engine": engine, "status": "started", "request_sent": False}
        self.calls.append(event)
        start = time.perf_counter()
        try:
            if engine == "jev":
                key = agents.jev_key()
                if not key:
                    raise agents.ProviderError("jev_key_missing")
                event["request_sent"] = True
                response = agents._http_json(
                    agents.JEV_URL,
                    {"state": state, "model": self.jev_model, "questions": questions(state)},
                    {"Authorization": f"Bearer {key}"}, min(remaining, 20),
                )
                answers = response.get("answers", {})
                if not isinstance(answers, dict):
                    raise agents.ProviderError("jev_answers_invalid")
                answer = answers.get("cell", {})
                review = answers.get("needs_review", {})
                if not isinstance(answer, dict) or not isinstance(review, dict):
                    raise agents.ProviderError("jev_answers_invalid")
                cell = answer.get("choice")
                metadata = {"confidence": probability(answer.get("confidence")),
                            "probabilities": answer.get("probabilities"),
                            "needs_review": probability(review.get("noul"))}
            else:
                key = agents.openrouter_key()
                if not key:
                    raise agents.ProviderError("llm_key_missing")
                event["request_sent"] = True
                response = agents._http_json(
                    agents.OPENROUTER_URL,
                    {"model": self.llm_model, "temperature": 0,
                     "max_tokens": MAX_LLM_OUTPUT_TOKENS,
                     "response_format": {"type": "json_object"},
                     "messages": [
                         {"role": "system", "content": (
                             "Deliberate over the supplied Minesweeper constraints. "
                             + CHOICE_INSTRUCTIONS +
                             ' Return JSON {"cell":"offered label","rationale":"brief justification"}. '
                             "Never claim unknown cells are proven safe. Do not assume "
                             "that a truncated constraint slice is the whole board.")},
                         {"role": "user", "content": json.dumps(state, separators=(",", ":"))},
                     ]},
                    {"Authorization": f"Bearer {key}", "X-Title": agents.TITLE},
                    min(remaining, 30),
                )
                try:
                    answer = json.loads(response["choices"][0]["message"]["content"])
                    if not isinstance(answer, dict):
                        raise ValueError()
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise agents.ProviderError("llm_decision_invalid") from exc
                cell = answer.get("cell")
                metadata = {"rationale": answer.get("rationale")}
            if not isinstance(cell, str):
                raise agents.ProviderError("provider_choice_missing")
            metadata.update({"provider_model": response.get("model"),
                             "usage": response.get("usage")})
            try:
                json.dumps(metadata, allow_nan=False)
            except (ValueError, TypeError) as exc:
                raise agents.ProviderError("provider_metadata_invalid") from exc
            event.update({"status": "ok", **metadata})
            return cell, metadata
        except agents.ProviderError as exc:
            event.update({"status": "error", "error": str(exc)})
            raise
        finally:
            event["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)


def choose(mode: str, state: dict, providers: Providers) -> tuple[str | None, dict]:
    """Failures abstain; budgets never turn into invisible random moves."""
    trace = {"mode": mode, "escalated": False}
    try:
        cell, metadata = providers.call("llm" if mode == "llm" else "jev", state)
        initial_guarded, initial_rejection = guarded_choice(cell, state["candidates"])
        trace.update({"initial_cell": cell, "initial_metadata": metadata,
                      "initial_guarded_cell": initial_guarded,
                      "initial_guard_rejection": initial_rejection})
        if mode == "hybrid":
            reasons = review_reasons(state, cell, metadata)
            trace["review_reasons"] = reasons
            if reasons:
                trace["escalated"] = True
                # Same evidence as the LLM-only baseline; no anchoring by S1's
                # tentative answer. Independent review makes disagreements useful.
                cell, metadata = providers.call("llm", state)
                trace.update({"review_cell": cell, "review_metadata": metadata})
        selected, rejected = guarded_choice(cell, state["candidates"])
        trace.update({"selected": selected, "guard_rejection": rejected})
        return selected, trace
    except agents.ProviderError as exc:
        trace["error"] = str(exc)
        return None, trace
