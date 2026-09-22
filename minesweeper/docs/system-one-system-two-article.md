# What the Minesweeper experiments show

September 22, 2026 · [Full report](system-one-system-two-research.md)

The strongest reliability improvement in these experiments came from
constraint solving. On 100 held-out expert boards, the stronger deterministic
solver won **52 games**, compared with **32** for the original heuristic.
A small live comparison showed Jev returning decisions faster than the tested
LLM, but adding LLM review did not improve the recorded outcomes.

## Three approaches to decision making

The repository includes an LLM-versus-Jev browser comparison, a Jev-only
large-board browser, and a CLI for comparing stronger inference with code,
Jev, LLM, and hybrid policies. The browsers use the original game policy.
The stronger solver and hybrid are currently available in the CLI.
[Run the experiments](../../README.md)

In this study, System One is Jev's bounded choice over supplied candidates.
System Two is an LLM reviewing the same evidence when the routing policy
requests it. Code owns deductions, candidate construction, execution, and
budgets. A guard restricts model choices to candidates tied at the minimum
computed mine risk. “Jev-only” therefore means one model provider; the game
still depends on deterministic code.
[Implemented architecture](../../docs/architecture.md)

## Better inference reduced guessing

The stronger solver enumerates consistent mine assignments and weights them
using the total mine count and unconstrained cells. Completed calculations
provide exact probabilities under the board prior; interrupted calculations
remain labeled as heuristic.

On held-out 30×16 boards with 99 mines, that solver reduced guesses from
444 to 266 while improving completion from 32% to 52%. No model calls were
involved. Larger boards remained difficult: the solver won 7/20 games on
50×50 boards despite averaging 98.63% safe-cell coverage. Progress across
most of a board is a different outcome from completing it.
[Held-out expert data](../results/expert-heldout.json),
[large-board data](../results/large-search-48.json)

## The hybrid added calls without improving the pilot outcomes

Four shared uncertain observations were evaluated with `jev-1.13.0` and
`openai/gpt-oss-20b`. Code and Jev each chose three safe cells and one mine.
LLM and hybrid each chose two safe cells, one mine, and failed to return a
usable decision on one state. These are next-action results, not full-game
win rates.

The hybrid escalated all four observations, saving no LLM calls. Median
cumulative provider time per state was 0.42 seconds for Jev, 14.57 seconds for
the LLM, and 20.70 seconds for the cascade. Two states had only one admissible
minimum-risk action, leaving no choice for a model to improve. The small
sample and narrow action policy limit conclusions about other models or
hybrid designs.
[Live replay data and failures](../results/expert-live-replay-v2.json)

## Design implications

The controller should first eliminate unnecessary decisions: execute proven
moves, and skip provider calls when the risk rule permits only one action.
Where alternatives remain, model routing needs to be tested against a strong
deterministic baseline on held-out states.

Model confidence and mine probability must remain separate. Jev's Choice
confidence describes its preference across options; it does not prove that a
cell is safe. Equally good guesses may spread that preference across several
options. Extra reasoning also cannot distinguish hidden layouts that produce
identical visible evidence.
[TypeSafe confidence documentation](https://docs.typesafe.ai/confidence.md)

The [research report](system-one-system-two-research.md) contains methods,
all recorded experiments, limitations, and reproduction commands. The
[roadmap](../../docs/roadmap.md) describes the next tests: better inference,
fewer unnecessary calls, and a measured evaluation of when LLM review helps.
