# Run guide

Run commands from the repository root with **Python 3.10+**. No third-party
Python packages or frontend build are required. The
[architecture guide](../docs/architecture.md) describes the different browser
and CLI control paths.

## Browser experiments

```bash
cp .env.example .env
# Edit .env with provider credentials.
python3 -m minesweeper.server
```

| Experiment | URL | Credentials |
| --- | --- | --- |
| LLM vs Jev | [http://127.0.0.1:5391/](http://127.0.0.1:5391/) | Jev key and `OPENROUTER_API_KEY` |
| Context lab | [http://127.0.0.1:5391/v3/](http://127.0.0.1:5391/v3/) | `TYPESAFE_API_KEY` or `JEV_API_KEY` |
| Jev on large boards | [http://127.0.0.1:5391/v2/](http://127.0.0.1:5391/v2/) | `TYPESAFE_API_KEY` or `JEV_API_KEY` |

The server loads the root `.env` and keeps credentials server-side. Optional
variables are `JEV_MODEL`, `OPENROUTER_MODEL`, and `PORT`. The legacy
`openouterkey` name is also accepted. Server flags include `--host`, `--port`,
`--html`, and `--v2-html`; `./minesweeper/scripts/start.sh` forwards these flags.

The comparison starts both models on the same seeded board. Different actions
can produce different subsequent observations. The first reveal is safe;
revealing a mine loses the lane, and revealing every safe cell wins it.

The large-board browser accepts up to 500×500 cells and sends compact frontier
input above 4,096 cells. Both browsers use the original heuristic controller.
The stronger solver and hybrid policy below are CLI experiments.

In V2, use **Zoom** and scroll in either direction to explore large boards.
The viewport stays fixed by default. Enable **Follow Jev** to keep the latest
move in view, or click **Show latest move** for a one-time jump. Candidate
cells show Jev's choice percentages, with the selected cell
outlined in gold. Hover or tap a cell for its percentage and change from the
previous round, or select a candidate in the sidebar to locate it on the board.
The dashed trail shows recent completed moves. **Pause** pauses between moves;
an in-flight request may still finish. These percentages describe preference
among offered choices, not cell safety or a predicted future route.

## V3 context lab

The [context lab](../docs/v3-context-lab.md) offers **System 1 (Jev)** and
**System 1 + System 2 (LLM proposals → Jev selection)**. Its session is separate
from V2. System 1 uses code-sampled frontier candidates and visible clues;
combined mode uses the LLM's proposals from the full visible board. Neither
mode supplies solver deductions or computed risks. Expand **Input sent to Jev**
to inspect or download the latest request.

## Benchmark modes

The CLI automatically reveals proved-safe cells, then applies the selected
policy when no safe reveal is proved within budget.

| Mode | Policy | Providers |
| --- | --- | --- |
| `heuristic` | Original heuristic risk ranking | None |
| `code` | Stronger solver's deterministic risk ordering | None |
| `proof` | Stronger solver; abstain when no safe reveal is proved within budget | None |
| `jev` | Jev chooses from stronger-solver candidates | Jev |
| `llm` | LLM chooses from stronger-solver candidates | LLM |
| `hybrid` | Jev chooses; routing policy may request LLM review | Jev and, on escalation, LLM |

All model choices pass the CLI's minimum-computed-risk check. Jev's candidate
choice and independent review question are batched in one request, including
in `jev` mode, which records the review signal without using it to call an LLM.

### Offline comparisons

These commands make no provider calls.

```bash
# Paired expert boards, including the held-out seed range used in the report.
python3 -m minesweeper.benchmark --modes heuristic,code,proof \
  --width 30 --height 16 --mines 99 \
  --max-component-cells 48 --seed-start 100 --seeds 100 --seconds 10 \
  --output /tmp/minesweeper-expert-heldout.json

# Larger boards under the same component-size limit.
python3 -m minesweeper.benchmark --modes code,proof \
  --width 50 --height 50 --mines 500 --seeds 20 \
  --max-component-cells 48 --seconds 10 \
  --output /tmp/minesweeper-large.json
```

### Live comparisons

Add provider credentials to `.env`, then run in **bash**. Live modes require
`--live` and consume provider credits.

```bash
source scripts/load-jev-env.sh

# Jev-only full episodes.
python3 -m minesweeper.benchmark --live --modes jev \
  --width 30 --height 16 --mines 99 \
  --jev-model jev-1.13.0 --max-component-cells 48 \
  --seeds 5 --seconds 50 --max-calls 12 \
  --output /tmp/minesweeper-jev.json

# Shared uncertain observations for code, Jev, LLM, and hybrid.
python3 -m minesweeper.benchmark --live --modes code,jev,llm,hybrid \
  --width 30 --height 16 --mines 99 \
  --jev-model jev-1.13.0 --llm-model openai/gpt-oss-20b \
  --max-component-cells 48 --seeds 10 --replay-states 4 \
  --seconds 50 --max-calls 2 \
  --output /tmp/minesweeper-live-replay.json
```

The loader maps `JEV_API_KEY` to `TYPESAFE_API_KEY` when needed and requires a Jev
key. For an LLM-only run, export `OPENROUTER_API_KEY` directly.

`--replay-states` collects the first unresolved observation from each seeded
code trajectory and compares policies on those observations. It generates new
states rather than loading a recorded JSON file. Replay supports
`code,jev,llm,hybrid`; omit the option for full episodes. Use
`python3 -m minesweeper.benchmark --help` for all flags.

## Budgets and outcomes

| Option | Scope |
| --- | --- |
| `--seconds` | Elapsed-time budget per episode, or per policy per replay state |
| `--max-calls` | Provider attempts, including LLM review, within the same scope |
| `--max-component-cells` | Maximum frontier component size for enumeration |
| `--max-search-nodes` | Shared enumeration node budget per solver analysis |

Deadlines are checked around solver/provider work and between safe reveals.
A solver or flood-fill operation is not interrupted midway. Provider failures,
timeouts, and exhausted budgets remain explicit unfinished outcomes.
`proof` reports an abstention when no safe reveal is proved.

## Recorded results and reproducibility

The [results directory](results/) contains the 11 original reports measured on
September 22, 2026, with repeat runs in [verification/](results/verification/).
The [research report](docs/system-one-system-two-research.md) describes
their configurations and separates full-board outcomes from one-step replay
results.

Reports retain outcomes, decisions, timing, available provider usage, and, where
recorded, source hashes. Missing provider costs mean unknown cost. Commands in
this guide write outside `results/` to preserve the published datasets.

[SHA256SUMS](results/SHA256SUMS) records checksums for all recorded datasets.
Verify them with `python3 scripts/check_repo.py` from the repository root, or
`shasum -a 256 -c SHA256SUMS` from `minesweeper/results/`.

Offline boards are seeded, but deadline-dependent outcomes can differ across
machines. Live outputs, latency, and service availability can vary even with
the same requested model. Use explicit model versions and retain the full
configuration when comparing new runs.

## Verification

```bash
python3 -m unittest discover -s minesweeper -p 'test_*.py'
python3 scripts/check_repo.py
```

Tests mock provider calls. The repository check validates documentation links
and recorded-result hashes.
