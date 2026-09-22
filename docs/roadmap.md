# Roadmap

The stronger constraint solver and Jev → LLM cascade currently run through the
benchmark CLI. The two browser experiments use the original game policy.
This roadmap describes proposed work; it is not part of the current release.

## Shared execution policy

Extract a session controller used by both the CLI and a new browser interface.
It should own the public board revision, decision policy, time limits, and
execution events. Keep hidden mine locations outside the decision interface.

The controller should execute proven-safe reveals directly. When a guess has
only one admissible candidate, select it without a provider request. For ties,
offer code, Jev, LLM, and hybrid policies under the same minimum-risk guard.
Retain the distinction between exact probabilities and estimates from bounded
search.

Before applying an asynchronous decision, check the session, board revision,
deadline, and stop state. Provider failures should produce explicit unfinished
outcomes. Verify that CLI and browser runs produce identical code-only
decisions for the same configuration, and that stale responses cannot change
the board.

## Browser experiment interface

Add a solver interface with code-only play as the default and the hybrid as
an experimental option. Compared runs should use the same seed, opening, and
solver limits, with separate clocks and terminal outcomes.

Show proven moves, guesses, selected-cell risk, decision source, escalation
reason, provider calls, and elapsed time. Support pause, stop, and JSON export.
Verify a complete run without credentials, a paired comparison, interruption
during inference, and a provider failure.

## Controlled hybrid evaluation

The current pilot does not establish a hybrid reliability advantage. A larger
study should test whether selective LLM review improves outcomes enough to
justify its additional latency and cost.

1. Calibrate the review threshold on development states, then freeze the
   questions, threshold, models, and solver configuration.
2. Compare code, Jev, LLM, and hybrid decisions on identical states with
   multiple admissible candidates. Include random escalation at a matched
   LLM-call rate to measure the value of the review signal.
3. Run paired full games on fresh held-out seeds. Report wins, losses,
   abstentions, time limits, provider failures, latency, and cost. Record
   whether LLM review rescues or harms the guarded Jev decision.
4. Retain the existing results as historical evidence and save new runs
   separately. Seeds used in development or regression checks are no longer
   held out for later studies.

## Large-board performance

Evaluate incremental frontier updates and deterministic lookahead among tied
guesses before attributing improvements to a model. Repeat bounded tests on
50×50, 100×100, and 500×500 boards, reporting full completion separately from
safe-cell coverage and time limits.

See the [research report](../minesweeper/docs/system-one-system-two-research.md)
for existing results and limitations, and the
[architecture guide](architecture.md) for the implemented design.
