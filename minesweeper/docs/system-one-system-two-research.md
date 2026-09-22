# System One and System Two in Minesweeper

Experimental report · September 22, 2026

[Findings summary](system-one-system-two-article.md) ·
[Architecture](../../docs/architecture.md) · [Run guide](../README.md)

## Abstract

A stronger constraint solver won **52 of 100 held-out expert boards**, compared
with **32 of 100** for the original heuristic. In a four-state live pilot,
Jev matched code's next-action outcomes faster than the tested LLM. The
Jev-to-LLM cascade escalated every state without improving reliability.
Reliable completion of large random boards remains unproven.

## Research question

Can a fast, bounded decision model improve the efficiency of a Minesweeper
controller, and can selective LLM review improve its decisions enough to
justify the additional latency and calls?

Here, **System One** means TypeSafe Jev's typed judgments; **System Two** means LLM
analysis. The names describe model roles. Rules, inference, budgets, and
execution remain in code. A hybrid must improve the win-rate, latency, or cost
tradeoff against that same controller and the single-provider policies.
[TypeSafe System One documentation](https://docs.typesafe.ai/concepts/system-one.md)

## Methods

### Experiment variants

Three variants are available: the LLM-versus-Jev browser (`/`), the Jev-only
large-board browser (`/v2/`), and the stronger-solver CLI. Results below come
from the CLI; both browsers retain the original deductions and heuristic
ranking. See the [architecture guide](../../docs/architecture.md).

### Policies and board generation

| CLI mode | Policy |
| --- | --- |
| `heuristic` | Original logical deductions and local risk heuristic, executed in code. |
| `code` | Stronger constraint solver, followed by the minimum computed-risk guess. |
| `proof` | Stronger solver; stop when no safe reveal is proved within the search budget. |
| `jev` | Stronger solver; Jev selects an uncertain candidate. |
| `llm` | Stronger solver; the LLM selects an uncertain candidate. |
| `hybrid` | Stronger solver; Jev selects a candidate, with conditional LLM review. |

Policies share seeds, dimensions, mine counts, and center openings. The opening
and, when density permits, its neighborhood are mine-free. Boards may still
require guesses. Both offline baselines batch proven-safe reveals. Hidden mines
are available only to the game and outcome evaluation, never to the solver or
providers.
[Game implementation](../game.py), [benchmark implementation](../benchmark.py)

### Constraint solving and action validation

The solver converts clues into constraints, propagates deductions, and
enumerates consistent assignments in connected frontier components. It combines
component counts with the remaining mine total and unconstrained cells. An
assignment leaving `r` mines among `u` unconstrained cells is weighted by
`C(u, r)` possible completions.
[Solver implementation](../solver.py)

Probabilities are exact under a uniform consistent-layout prior only when
enumeration and global weighting complete. Incomplete calculations remain
heuristic; zero observed mine frequency in a truncated search is never proof.
User flags are annotations, not evidence of mine locations. See also
[Johnny Deuss's solver](https://github.com/JohnnyDeuss/minesweeper-solver) for
model counting and the distinction between immediate risk and eventual wins.

The controller first reveals proven-safe cells. Its guard accepts guesses
only among offered minimum-risk candidates, within `1e-12`; other proposals
are replaced with the deterministic choice and logged. Approximate risks
guarantee compliance with the estimate only. Provider failures and expired
decisions leave games unfinished. Higher-risk information-seeking moves are
not permitted.
[Decision policy](../hybrid.py)

### Hybrid routing

The `system-one-two-v2` policy batches two independent Jev questions: a cell
Choice and a Noul judgment about whether structural differences warrant
review. Code escalates on incomplete enumeration, an invalid/higher-risk
proposal, a missing review signal, or review probability at least **0.65**.
This threshold is uncalibrated. The LLM receives the LLM-only policy's state
without Jev's answer.
[Questions and routing rules](../hybrid.py)

Choice confidence measures preference concentration, not cell safety. It is
logged separately from mine risk. The earlier v1 policy also used a 0.75
Choice-confidence escalation threshold; v2 removes it because equally good options
can appropriately produce a diffuse distribution.
[TypeSafe confidence documentation](https://docs.typesafe.ai/confidence.md)

### Evaluation protocol

Full-board trials record wins, losses, abstentions, timeouts, coverage, and
guesses. Unfinished games remain in the denominator. Proof-only abstention
means no safe action was found within budget, not that none exists.

Expert seeds 0–99 were used for development. The component cap of 48 was then
held fixed for seeds 100–199. Each analysis had a shared enumeration budget
of 200,000 nodes and a separate bounded global-weighting budget. Offline
episodes allowed ten seconds, except the 100×100 trials, which allowed fifteen.
The component cap limits which components may be searched; it does not ensure
that every eligible search completes.

Live replays score one reveal on identical observations, not whole-game wins.
The final pilot used the first unresolved observation from expert seeds 1–4
with component cap 48. Provider models were `jev-1.13.0`
and `openai/gpt-oss-20b` through OpenRouter. LLM output was capped at 2,048
tokens. Jev and LLM request timeouts were twenty and thirty seconds respectively,
subject to the remaining fifty-second decision budget and two-call limit.

## Results

### Offline full-board results

| Board / seeds | Component cap | Heuristic wins | Code wins | Proof-only wins / abstentions | Data |
| --- | ---: | ---: | ---: | ---: | --- |
| 9×9, 10 mines; 0–29 | 22 | 29/30 | 30/30 | 28 / 2 | [Beginner](../results/beginner-offline.json) |
| 30×16, 99 mines; 0–99 | 22 | 32/100 | 41/100 | 14 / 86 | [Expert development](../results/expert-offline.json) |
| 30×16, 99 mines; 0–99 | 48 | 32/100* | 46/100 | 16 / 84 | [Expert, larger search](../results/expert-search-48.json) |
| 30×16, 99 mines; **100–199 held out** | 48 | **32/100** | **52/100** | 15 / 85 | [Held-out expert](../results/expert-heldout.json) |
| 50×50, 500 mines; 0–19 | 22 | 3/20 | 6/20 | 2 / 18 | [Large](../results/large-offline.json) |
| 50×50, 500 mines; 0–19 | 48 | 3/20* | 7/20 | 3 / 17 | [Large, larger search](../results/large-search-48.json) |
| 100×100, 2,000 mines; 0–9 | 22 | Not run | 0/10 | 0 / 10 | [Very large](../results/very-large-offline.json) |
| 500×500, 50,000 mines; seed 0 | 22 | Not run | 0/1; timed out | 0 wins; timed out | [Maximum size](../results/maximum-board-bounded.json) |

\* Same-seed heuristic result from the cap-22 comparison; the heuristic does
not use component enumeration.

On held-out expert boards, the observed improvement was **20 percentage
points**. Code alone won 23 paired boards; the heuristic alone won three.
Both won 29 and both lost 45. The separate Wilson 95% intervals were
42.3–61.5% for code and 23.7–41.7% for the heuristic. These intervals describe
the individual rates, not the paired difference. Code made 266 guesses versus
444 for the heuristic. This is an improvement from deterministic inference,
with no learned model involved.
[Held-out records](../results/expert-heldout.json)

Large-board coverage did not imply completion. At 50×50 with cap 48, code
averaged 98.63% safe-cell coverage but lost 13 of 20 games. At 100×100, mean
coverage was 89.72% and all ten games lost. The 500×500 trial reached 7.82%
coverage before the time limit. It demonstrates bounded execution only.
[50×50](../results/large-search-48.json),
[100×100](../results/very-large-offline.json),
[500×500](../results/maximum-board-bounded.json)

### Live replay results

The four-state v2 pilot produced the following one-step outcomes:

| Policy | Safe reveals | Mine reveals | No decision | Provider calls | Median cumulative provider time per state |
| --- | ---: | ---: | ---: | --- | ---: |
| Code | 3 | 1 | 0 | 0 | — |
| Jev + guard | 3 | 1 | 0 | 4 Jev | 0.42 s |
| LLM + guard | 2 | 1 | 1 | 4 LLM | 14.57 s |
| Jev → LLM + guard | 2 | 1 | 1 | 4 Jev + 4 LLM | 20.70 s |

All four hybrid decisions escalated. LLM-only had one timeout; hybrid had one
unusable JSON response. Among the three completed hybrid decisions, LLM review
produced zero rescues and zero harms relative to the guarded initial Jev
choice. Failures are reported as no decision, not credited as successful
avoidance of a mine.
[Observations, traces, and replay summary](../results/expert-live-replay-v2.json)

Two observations had only one minimum-risk candidate, so the guard forced the
same action regardless of model preference. The other two had three and two
admissible candidates. All four observations had complete exact probabilities;
one selected minimum-risk cell still contained a mine. The pilot therefore
mainly measures request overhead and limited tie selection, not a general
planning advantage.
[Candidate states](../results/expert-live-replay-v2.json)

The earlier six-state v1 replay used cap-22 observations from seeds 0–5.
Code and Jev each selected five safe cells and one mine. LLM and hybrid each
returned three safe decisions and no decision on three states; LLM-only had
two invalid outputs and one timeout, while hybrid had three timeouts. All six
hybrid states escalated. Jev, LLM, and hybrid median cumulative provider times
were 0.51 s, 23.64 s, and 19.31 s. Different snapshots and routing rules prevent
a controlled v1-versus-v2 comparison.
[Exploratory v1 replay](../results/expert-live-replay.json)

### Live full-game check

All four policies won both beginner boards at seeds 1–2, needing one guess
each across the games. Code used no provider calls, Jev and LLM one each,
and hybrid one Jev call without escalation. Two easy games verify integration,
not relative win rates.
[Full-game records](../results/beginner-live-episodes.json)

## Limitations and implications

Results apply to the tested generator, seeds, and budgets. Exact probabilities
can still leave ambiguous guesses when hidden layouts produce identical clues.
Minimum immediate risk also differs from maximum eventual win probability.

The final live sample contains four states and one LLM. Context includes
candidate coordinates and clue equations, not complete visible-board geometry.
The review threshold is uncalibrated against successful LLM interventions.
A different policy may produce different outcomes.

Provider times are a small sample, not controlled service benchmarks. Missing
cost metadata prevents a complete cost comparison. Searches and flood reveals
are not preempted and may overrun episode deadlines. Historical source hashes,
where recorded, differ from the current implementation; early artifacts omit
them. The commands below rerun the protocol rather than reconstructing every
historical execution.

The next evaluation should skip model calls when only one action satisfies
the risk policy, strengthen deterministic lookahead among ties, and test
routing on new held-out states with multiple admissible actions. A
random-escalation policy at the same call rate would help measure whether the
review signal selects useful cases. The [roadmap](../../docs/roadmap.md)
separates these proposed changes from the implemented experiment.

## Reproduction

Run from the repository root with Python 3.10 or later. The offline comparison
requires no API credentials:

```bash
python3 -m minesweeper.benchmark --modes heuristic,code,proof \
  --width 30 --height 16 --mines 99 --max-component-cells 48 \
  --seed-start 100 --seeds 100 --seconds 10 \
  --output /tmp/minesweeper-expert-heldout.json
```

For the live replay, configure credentials as described in the
[run guide](../README.md), then run in Bash. This uses paid provider APIs:

```bash
source scripts/load-jev-env.sh
python3 -m minesweeper.benchmark --live --modes code,jev,llm,hybrid \
  --width 30 --height 16 --mines 99 \
  --jev-model jev-1.13.0 --llm-model openai/gpt-oss-20b \
  --max-component-cells 48 --seeds 10 --replay-states 4 \
  --seconds 50 --max-calls 2 \
  --output /tmp/minesweeper-expert-live-replay-v2.json
```

Each linked JSON artifact records configuration and individual outcomes.
Replay results are in `replay_summary`; the `summary` field in replay files
covers code episodes used to collect observations. New output paths preserve
the published records. Wall-clock outcomes can vary with machine speed;
provider outputs, availability, and latency can vary between runs.
