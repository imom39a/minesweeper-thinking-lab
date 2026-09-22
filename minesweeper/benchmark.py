"""Reproducible offline and live experiments, separate from the comparison UI.

Run ``python3 -m minesweeper.benchmark --help``. No network unless --live is set.
Every reported timeout, provider failure, or call cap remains an unfinished game.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

from .game import MinesweeperGame, parse_cell_label
from .hybrid import (REVIEW_PROBABILITY, POLICY_VERSION,
                     Providers, choose, decision_state)
from .solver import analyze


def wilson(wins: int, count: int) -> list[float]:
    if not count:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = wins / count
    d = 1 + z * z / count
    center = (p + z * z / (2 * count)) / d
    half = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / d
    return [max(0.0, center - half), min(1.0, center + half)]


def run_game(mode: str, width: int, height: int, mines: int, seed: int,
             max_rounds: int = 2000, seconds: float = 30, max_calls: int = 12,
             jev_model: str = "jev-1.13.0", llm_model: str = "openai/gpt-oss-20b",
             max_component_cells: int = 22, max_search_nodes: int = 200000,
             frozen_states: list | None = None) -> dict:
    game = MinesweeperGame(width, height, mines, seed)
    start = time.monotonic()
    deadline = start + seconds
    providers = Providers(jev_model, llm_model, max_calls, deadline)
    game.reveal(*game.opening_cell())
    safe_reveals = 0
    guesses = 0
    uncertain_analyses = 0
    exact_analyses = 0
    traces = []
    compute_ms = 0.0
    status = "time_limit" if time.monotonic() >= deadline else game.phase
    rounds = 0
    while not game.is_terminal and rounds < max_rounds:
        if time.monotonic() >= deadline:
            status = "time_limit"
            break
        rounds += 1
        tick = time.perf_counter()
        if mode == "heuristic":
            safes, _ = game.deduce()
            candidates = game.offered_candidates() if not safes else []
            analysis = None
        else:
            analysis = analyze(game, max_component_cells, max_search_nodes)
            if analysis.stats.get("inconsistent"):
                status = "inconsistent_state"
                break
            safes = analysis.safe - game.revealed - game.flagged
            candidates = analysis.candidates
            exact_analyses += int(analysis.complete)
            uncertain_analyses += int(not analysis.complete)
        compute_ms += (time.perf_counter() - tick) * 1000
        if time.monotonic() >= deadline:
            status = "time_limit"
            break
        if safes:
            # All cells in a proof batch are safe under this same observation;
            # flood reveal may reveal some before their turn in the batch.
            for row, col in sorted(safes):
                if game.is_terminal:
                    break
                if time.monotonic() >= deadline:
                    status = "time_limit"
                    break
                if (row, col) not in game.revealed:
                    outcome = game.reveal(row, col)
                    safe_reveals += 1
                    if outcome == "mine":
                        raise AssertionError("solver_proof_revealed_mine")
                    if time.monotonic() >= deadline:
                        status = "time_limit"
                        break
            if status == "time_limit":
                break
            status = game.phase
            continue
        if not candidates:
            status = "stalled"
            break
        if mode == "proof":
            status = "abstained_guess_required"
            break
        trace = {"round": rounds}
        if mode in {"code", "heuristic"}:
            cell = candidates[0]["cell"]
        else:
            state = decision_state(game, analysis, rounds)
            cell, trace = choose(mode, state, providers)
            if cell is None:
                traces.append(trace)
                status = trace.get("error", "provider_failure")
                break
            if time.monotonic() >= deadline:
                trace["discarded"] = "expired_decision"
                traces.append(trace)
                status = "time_limit"
                break
        selected = next(c for c in candidates if c["cell"] == cell)
        # Hidden truth is used ONLY by this evaluator after selection, never by
        # solver or provider state. Replay labels are kept outside model state.
        if frozen_states is not None and analysis is not None:
            state = decision_state(game, analysis, rounds)
            frozen_states.append({
                "seed": seed, "state": state,
                "mine_labels": [c["cell"] for c in candidates
                                if (c["row"], c["col"]) in game.mine_cells],
            })
        coords = parse_cell_label(cell)
        if coords is None:
            raise AssertionError("invalid_solver_label")
        guesses += 1
        outcome = game.reveal(*coords)
        trace.update({"round": rounds, "selected": cell, "outcome": outcome,
                      "mine_risk": selected["mine_risk"],
                      "risk_exact": selected.get("risk_exact", False),
                      "candidate_count": len(candidates)})
        traces.append(trace)
        status = "time_limit" if time.monotonic() >= deadline else game.phase
        if status == "time_limit":
            break
    if not game.is_terminal and rounds >= max_rounds and status == "playing":
        status = "round_limit"
    revealed_safe = len(game.revealed) - int(game.phase == "lost")
    return {
        "mode": mode, "seed": seed, "width": width, "height": height, "mines": mines,
        "status": status, "rounds": rounds, "moves": game.moves,
        "proven_safe_reveals": safe_reveals, "guesses": guesses,
        "revealed_safe": revealed_safe, "safe_total": game.safe_total,
        "safe_coverage": revealed_safe / game.safe_total,
        "exact_analyses": exact_analyses, "incomplete_analyses": uncertain_analyses,
        "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
        "compute_ms": round(compute_ms, 3), "calls": providers.calls, "decisions": traces,
    }


def summarize(runs: list[dict]) -> dict:
    result = {}
    for mode in dict.fromkeys(r["mode"] for r in runs):
        group = [r for r in runs if r["mode"] == mode]
        counts = Counter(r["status"] for r in group)
        calls = [c for r in group for c in r["calls"]]
        latencies = sorted(c["latency_ms"] for c in calls)
        known_costs = [c["usage"]["cost"] for c in calls
                       if isinstance(c.get("usage"), dict)
                       and isinstance(c["usage"].get("cost"), (float, int))]
        decisions = [d for r in group for d in r["decisions"]]
        result[mode] = {
            "games": len(group), "statuses": dict(counts),
            "win_rate": counts["won"] / len(group),
            "win_rate_wilson95": wilson(counts["won"], len(group)),
            "mean_safe_coverage": statistics.mean(r["safe_coverage"] for r in group),
            "mean_elapsed_ms": statistics.mean(r["elapsed_ms"] for r in group),
            "guesses": sum(r["guesses"] for r in group),
            "proven_safe_reveals": sum(r["proven_safe_reveals"] for r in group),
            "provider_attempts": len(calls),
            "api_calls": sum(c.get("request_sent", True) for c in calls),
            "calls_by_engine": dict(Counter(c["engine"] for c in calls if c.get("request_sent", True))),
            "provider_errors": sum(c["status"] == "error" for c in calls),
            "call_latency_p50_ms": statistics.median(latencies) if latencies else None,
            "call_latency_p95_ms": latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
            "escalations": sum(bool(d.get("escalated")) for d in decisions),
            "guard_rejections": sum(bool(d.get("guard_rejection")) for d in decisions),
            "reported_cost_usd": sum(known_costs) if known_costs else None,
            "calls_with_reported_cost": len(known_costs),
            "cost_note": "Only provider-reported costs; missing usage cost is unknown, not zero.",
        }
    return result


def replay(states: list[dict], modes: list[str], max_calls: int, seconds: float,
           jev_model: str, llm_model: str) -> list[dict]:
    """Common-state counterfactual one-step test, NOT whole-board wins."""
    results = []
    for index, item in enumerate(states):
        state = item["state"]
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]
        for mode in modes:
            provider = Providers(jev_model, llm_model, max_calls, time.monotonic() + seconds)
            if mode == "code":
                cell, trace = state["candidates"][0]["cell"], {}
            else:
                cell, trace = choose(mode, state, provider)
            if time.monotonic() >= provider.deadline:
                cell = None
                trace["error"] = "expired_decision"
            mine_labels = set(item["mine_labels"])
            results.append({
                "state_index": index, "state_hash": digest, "seed": item["seed"],
                "mode": mode, "cell": cell,
                "would_hit_mine": cell in mine_labels if cell else None,
                "initial_would_hit_mine": trace.get("initial_cell") in mine_labels
                    if trace.get("initial_cell") in {c["cell"] for c in state["candidates"]} else None,
                "initial_guarded_would_hit_mine": trace.get("initial_guarded_cell") in mine_labels
                    if trace.get("initial_guarded_cell") else None,
                "trace": trace, "calls": provider.calls,
            })
    return results


def summarize_replay(rows: list[dict]) -> dict:
    """Descriptive one-step outcomes; abstentions stay visible, no win claims."""
    result = {}
    for mode in dict.fromkeys(r["mode"] for r in rows):
        group = [r for r in rows if r["mode"] == mode]
        calls = [c for r in group for c in r["calls"]]
        reviewed = [r for r in group if r["trace"].get("escalated") and r["cell"] is not None]
        result[mode] = {
            "states": len(group),
            "safe_next_reveals": sum(r["would_hit_mine"] is False for r in group),
            "mine_next_reveals": sum(r["would_hit_mine"] is True for r in group),
            "no_decision": sum(r["would_hit_mine"] is None for r in group),
            "api_calls": sum(c.get("request_sent", True) for c in calls),
            "calls_by_engine": dict(Counter(c["engine"] for c in calls if c.get("request_sent", True))),
            "provider_errors": dict(Counter(c.get("error") for c in calls if c["status"] == "error")),
            "escalations": sum(bool(r["trace"].get("escalated")) for r in group),
            "median_total_provider_ms": statistics.median(
                sum(c["latency_ms"] for c in r["calls"]) for r in group),
            "s2_rescues_vs_guarded_s1": sum(r.get("initial_guarded_would_hit_mine") is True
                                            and r["would_hit_mine"] is False for r in reviewed),
            "s2_harms_vs_guarded_s1": sum(r.get("initial_guarded_would_hit_mine") is False
                                          and r["would_hit_mine"] is True for r in reviewed),
            "guarded_counterfactual_available": sum(
                r.get("initial_guarded_would_hit_mine") is not None for r in reviewed),
        }
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--width", type=int, default=30)
    p.add_argument("--height", type=int, default=16)
    p.add_argument("--mines", type=int, default=99)
    p.add_argument("--seeds", type=int, default=20, help="number of consecutive paired seeds")
    p.add_argument("--seed-start", type=int, default=0)
    p.add_argument("--modes", default="heuristic,code,proof")
    p.add_argument("--seconds", type=float, default=30, help="per episode (also per replay decision)")
    p.add_argument("--max-rounds", type=int, default=2000)
    p.add_argument("--max-calls", type=int, default=12, help="per episode, including S2 calls")
    p.add_argument("--max-component-cells", type=int, default=22)
    p.add_argument("--max-search-nodes", type=int, default=200000)
    p.add_argument("--jev-model", default=os.getenv("JEV_MODEL", "jev-1.13.0"))
    p.add_argument("--llm-model", default=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b"))
    p.add_argument("--live", action="store_true", help="allow billed model calls")
    p.add_argument("--replay-states", type=int, default=0,
                   help="collect this many unresolved code-trajectory states and compare modes there")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    modes = args.modes.split(",")
    if not modes or any(m not in {"heuristic", "code", "proof", "jev", "llm", "hybrid"} for m in modes):
        p.error("unknown mode")
    if (args.seeds < 1 or not math.isfinite(args.seconds) or args.seconds <= 0
            or args.max_calls < 0 or args.max_rounds < 1 or args.replay_states < 0
            or args.max_component_cells < 1 or args.max_search_nodes < 1):
        p.error("invalid budget")
    if any(m in {"jev", "llm", "hybrid"} for m in modes) and not args.live:
        p.error("model modes require --live; load credentials with source scripts/load-jev-env.sh")
    if args.replay_states and any(m in {"heuristic", "proof"} for m in modes):
        p.error("replay supports code,jev,llm,hybrid")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(), "policy_version": POLICY_VERSION,
        "source_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                          for name in ("game.py", "solver.py", "hybrid.py", "benchmark.py")},
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "thresholds": {"review_probability": REVIEW_PROBABILITY, "calibrated": False},
        "runs": [], "replay": [],
        "limitations": ["Seeded layouts, provider outputs not guaranteed deterministic.",
                        "Exact refers to bounded complete model counting under a uniform layout prior.",
                        "Models choose minimum-computed-risk ties; no proof of optimal eventual wins.",
                        "Unfinished games stay in denominator; replay is one-step evidence only."],
    }

    def save():
        report["summary"] = summarize(report["runs"])
        report["replay_summary"] = summarize_replay(report["replay"])
        tmp = args.output.with_suffix(args.output.suffix + ".tmp")
        tmp.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        tmp.replace(args.output)

    states = []
    for seed in range(args.seed_start, args.seed_start + args.seeds):
        for mode in (["code"] if args.replay_states else modes):
            seed_states = []
            run = run_game(mode, args.width, args.height, args.mines, seed,
                           args.max_rounds, args.seconds, args.max_calls,
                           args.jev_model, args.llm_model, args.max_component_cells,
                           args.max_search_nodes, seed_states if args.replay_states else None)
            # One first unresolved observation per seed avoids treating a long
            # trajectory's correlated decisions as independent board evidence.
            states.extend(seed_states[:1])
            report["runs"].append(run)
            save()
            print(json.dumps({k: run[k] for k in ["mode", "seed", "status", "guesses", "elapsed_ms"]}), flush=True)
        if args.replay_states and len(states) >= args.replay_states:
            break
    if args.replay_states:
        # Keep evaluator outcomes separate from sanitized provider input.
        report["frozen_states"] = states[:args.replay_states]
        for item in states[:args.replay_states]:
            rows = replay([item], modes, args.max_calls, args.seconds, args.jev_model, args.llm_model)
            for row in rows:
                row["state_index"] = len(report["replay"]) // len(modes)
                report["replay"].append(row)
                print(json.dumps({k: row[k] for k in ["state_index", "mode", "cell", "would_hit_mine"]}), flush=True)
            save()
    print(json.dumps(report["replay_summary"] if args.replay_states else report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
