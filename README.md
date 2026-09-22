# Minesweeper Thinking Lab

Experiments comparing deterministic solvers, TypeSafe Jev, and LLM review in
Minesweeper. The project measures board completion, decision quality, provider
calls, and latency to test when model-assisted decisions improve on code alone.

In these experiments, **System One** is Jev's typed decision model and
**System Two** is an LLM asked to review a candidate move. Code controls the
game, computes risks, and executes actions.

## Experiments

| Variant | Implementation | Purpose |
| --- | --- | --- |
| 1. LLM vs Jev | Browser at `/` | Compare two models using the original deductions and heuristic candidate ranking. |
| 2. System One alone | Browser at `/v2/` | Test Jev with compact frontier input on boards up to 500×500. |
| 3. Solver and model policies | Benchmark CLI | Compare six policies under stronger deterministic inference, including Jev with optional LLM review. |

Variant 3 has six modes: `heuristic`, `code`, `proof`, `jev`, `llm`, and `hybrid`.
Its solver and hybrid controller are available through the CLI; the browser
variants retain their original controller. The 500×500 input limit describes
supported board size, not demonstrated solving reliability.

## Findings

The stronger deterministic solver won **52 of 100 held-out expert boards**,
compared with **32 of 100** for the original heuristic. A four-state live pilot
found no reliability improvement from adding LLM review to Jev. Median cumulative
provider time was **0.42 seconds for Jev** and **20.70 seconds for the hybrid**;
all four hybrid decisions escalated.

These are separate experiments: the first measures full-board completion, while
the second measures one proposed move per shared observation. The live sample
is too small to establish a general model comparison. See the
[research report](minesweeper/docs/system-one-system-two-research.md) for methods,
all results, failures, and limitations.

## Browser gameplay

LLM and Jev playing the same 9×9 board with 10 mines (seed 1). Both lanes
cleared this board using the original browser policy.

![Completed LLM versus Jev game with both boards cleared](docs/images/llm-vs-jev.png)

See the [gameplay gallery and repeat experiments](docs/gameplay.md) for the
Jev-only view, configurations, and new CLI results. These screenshots show
individual games, not aggregate model performance.

## Quick start

Requires **Python 3.10+**. Running from a checkout uses only the Python standard
library; there is no frontend build step.

```bash
git clone https://github.com/imom39a/minesweeper-thinking-lab.git
cd minesweeper-thinking-lab

# Offline experiment: no API keys required.
python3 -m minesweeper.benchmark --width 9 --height 9 --mines 10 \
  --modes heuristic,code,proof --seeds 3 --seconds 10 \
  --output /tmp/minesweeper-smoke.json

# Browser experiments: add provider credentials to .env before starting.
cp .env.example .env
python3 -m minesweeper.server
```

Open [LLM vs Jev](http://127.0.0.1:5391/) or
[Jev on large boards](http://127.0.0.1:5391/v2/). Use `TYPESAFE_API_KEY`
(or `JEV_API_KEY`) for Jev and `OPENROUTER_API_KEY` for the LLM. Credentials
remain on the server. Live experiments consume provider credits.

## Documentation

- [Run guide](minesweeper/README.md): configuration, benchmark commands, and budgets.
- [Architecture](docs/architecture.md): solver, model interfaces, routing, and execution checks.
- [Research report](minesweeper/docs/system-one-system-two-research.md): experimental design and evidence.
- [Findings article](minesweeper/docs/system-one-system-two-article.md): a shorter discussion of the results.
- [Recorded results](minesweeper/results/): JSON datasets used by the report.
- [Roadmap](docs/roadmap.md): planned experiments and browser integration.
- [Changelog](CHANGELOG.md) and [attribution](ATTRIBUTION.md).

## Verification

```bash
python3 -m unittest discover -s minesweeper -p 'test_*.py'
python3 scripts/check_repo.py
```

Tests mock provider calls. The repository check verifies documentation links
and the integrity of the recorded result files.
