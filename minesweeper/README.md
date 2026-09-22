# Running the Minesweeper experiments

This package contains the three experiments published in
[Minesweeper Thinking Lab](../README.md): the original LLM/Jev browser
comparison, the Jev-only large-board browser, and the stronger solver/cascade
benchmark. The [architecture guide](../docs/architecture.md) explains why the
browser experiments and benchmark have different control paths.

## Browser variants 1 and 2

From the repository root, use Python 3.10+:

```bash
cp .env.example .env
# Edit .env with your provider credentials.
python3 -m minesweeper.server
```

`./minesweeper/scripts/start.sh` is an equivalent entrypoint and forwards
server flags. No third-party Python package, Node.js, or build step is needed.

| Variant | URL | Credentials |
| --- | --- | --- |
| 1 · LLM vs Jev | [http://127.0.0.1:5391/](http://127.0.0.1:5391/) | Jev key and `OPENROUTER_API_KEY` for the default comparison |
| 2 · Jev on large boards | [http://127.0.0.1:5391/v2/](http://127.0.0.1:5391/v2/) | `JEV_API_KEY` or `TYPESAFE_API_KEY` |

Optional variables are `JEV_MODEL`, `OPENROUTER_MODEL`, and `PORT`. The server
loads `.env` from the repository root. Explicit server flags include `--host`,
`--port`, `--html`, and `--v2-html`. The original `openouterkey` credential
name remains recognized for compatibility. Credentials stay in Python and are
never sent to the browser.

Both browser variants use the original game policy: logical deductions,
a bounded offered-candidate list, and a code-computed heuristic risk. Each
provider is asked to choose a proven-safe cell first, then the lowest supplied
risk when a guess is needed. Both lanes start from the same seeded board;
after different actions, their observations can diverge. The first reveal is
safe, a mine loses a lane, and revealing every safe cell wins it.

The Jev large-board variant accepts boards up to 500×500. Above 4,096 cells,
state omits the full grid and retains a compact board summary, frontier
candidates, and local constraints. Bounded model input does not mean constant
local computation or reliable completion at that size. These browsers retain
the original provider-per-turn loop; they do not use the variant 3 solver or
cascade.

## Variant 3: deterministic solver and model experiments

The benchmark uses an observation-only constraint solver, automatically
reveals proven-safe cells, and compares the following policies:

| CLI mode | Decision when no safe reveal is proved | Provider calls |
| --- | --- | --- |
| `heuristic` | Original risk ranking, executed in code | None |
| `code` | First candidate from stronger solver's risk ordering | None |
| `proof` | Stop with an explicit abstention | None |
| `jev` | Jev chooses, then code applies the risk guard | Jev only |
| `llm` | LLM chooses, then code applies the risk guard | LLM only |
| `hybrid` | Jev chooses; policy may request LLM review; code guards the result | Jev and, on escalation, LLM |

The `jev`, `llm`, and `hybrid` arms share the stronger solver. They isolate
model use under that solver, rather than recreating the earlier browser policy.
Jev's choice and independent review question are batched even in `jev` mode;
that mode records the review signal but never calls the LLM.

```bash
# Offline paired-seed comparison; no provider calls.
python3 -m minesweeper.benchmark --modes heuristic,code,proof \
  --max-component-cells 48 --seed-start 100 --seeds 100 --seconds 10 \
  --output /tmp/minesweeper-expert-heldout.json

# A bounded large-board comparison.
python3 -m minesweeper.benchmark --modes code,proof \
  --width 50 --height 50 --mines 500 --seeds 20 \
  --max-component-cells 48 --seconds 10 \
  --output /tmp/minesweeper-large.json
```

For live modes, add credentials to `.env` and run these commands in **bash**:

```bash
source scripts/load-jev-env.sh

# System One alone on full expert episodes.
python3 -m minesweeper.benchmark --live --modes jev \
  --jev-model jev-1.13.0 --max-component-cells 48 \
  --seeds 5 --seconds 50 --max-calls 12 \
  --output /tmp/minesweeper-jev.json

# Same uncertain observations for code, Jev, LLM and hybrid.
python3 -m minesweeper.benchmark --live --modes code,jev,llm,hybrid \
  --jev-model jev-1.13.0 --llm-model openai/gpt-oss-20b \
  --max-component-cells 48 --seeds 10 --replay-states 4 \
  --seconds 50 --max-calls 2 \
  --output /tmp/minesweeper-live-replay.json
```

Live modes require `--live` and consume provider credits. The loader maps the
legacy `JEV_API_KEY` to `TYPESAFE_API_KEY`. To run only `llm`, exporting
`OPENROUTER_API_KEY` is sufficient; the supplied loader expects a Jev key.

`--replay-states` collects the first unresolved observation from each seeded
code trajectory, then compares policies on identical observations. It does
not load an existing JSON file. Omit that option for full games. Replay supports
`code,jev,llm,hybrid`; `proof` and `heuristic` belong in full-game comparisons.
Use `python3 -m minesweeper.benchmark --help` for all flags.

## Budgets, guards, and outcomes

`--max-calls` counts provider attempts, including LLM reviews, per episode or
per mode per frozen state. `--seconds` has the same scope. The wall-clock limit
is checked before and after solver/provider work and between safe reveals;
a single solver or flood-fill operation is not preempted. Provider failures,
timeouts, and exhausted budgets remain unfinished outcomes.

[solver.py](solver.py) enumerates bounded frontier components and weights valid
assignments by global mine count and unconstrained cells. Completed calculations
can produce exact probabilities under the board prior. Incomplete calculations
remain explicitly heuristic; their zero-frequency observations are not proofs.

[hybrid.py](hybrid.py) keeps questions and thresholds together. Jev returns a
cell Choice and independent review Noul in one request. Incomplete enumeration,
a missing review signal, an invalid or higher-risk recommendation, or review
probability at least **0.65** causes hybrid escalation. That cutoff is
uncalibrated. Choice confidence is logged separately from mine safety.

Every model recommendation passes a minimum-computed-risk check. An invalid
or higher-risk choice is corrected to the code fallback and recorded. Models
can choose among risk ties, but cannot introduce safety proofs or deliberately
trade immediate risk for future information. The current benchmark still asks
models on unique-minimum guess states; skipping those calls is planned.

## Recorded evidence and reproduction

[results/](results/) contains 11 historical reports from September 22, 2026:
seeded full episodes, scale checks, frozen-state pilots, unsuccessful decisions,
and a small end-to-end live check. The
[research report](docs/system-one-system-two-research.md#local-experiment-results)
indexes all datasets and distinguishes full-board wins from one-step choices.

Reports retain configuration, outcomes, decisions, timing, and available usage.
Later reports include source hashes; early exploratory reports predate that
instrumentation. The source hashes refer to the original experiment source,
not a promise that every file in this standalone packaging is unchanged.
Frozen-state truth labels are separate from public provider inputs. Missing
provider cost information means unknown cost. New commands above write outside
`results/` to preserve the original records.

Offline decisions are seeded, but deadlines can produce different outcomes
on different machines. Live responses, latency, service availability, and model
aliases may change. Pin model versions when comparing new runs.

## Tests

```bash
python3 -m unittest discover -s minesweeper -p 'test_*.py'
python3 -m compileall -q minesweeper
```

The tests mock providers and spend no credits. They cover game behavior,
solver probabilities, hidden-state isolation, bounded-search fallback, guards,
provider failures, deadlines, and replay evaluation.

The [published article](docs/system-one-system-two-article.md) explains the
findings; the [future integration plan](docs/v0.2-release-plan.md) describes a
shared controller and Solver Lab browser that have not shipped. See
[ATTRIBUTION.md](../ATTRIBUTION.md) for provenance and license notes.
