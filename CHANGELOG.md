# Changelog

## v0.1.0 — Research preview · 2026-09-22

First standalone release of Minesweeper Thinking Lab, extracted from
[jev-playground](https://github.com/imom39a/jev-playground).

- Publishes three experiments: LLM vs Jev in the browser, Jev-only large boards
  in the browser, and a CLI study of stronger deterministic inference with
  code, proof-only, Jev, LLM, and hybrid policies.
- Includes the bounded constraint solver, guarded Jev → LLM cascade, paired
  seeded episodes, common-state replay, tests, and 11 recorded result files.
- Publishes the [article](minesweeper/docs/system-one-system-two-article.md),
  [research report](minesweeper/docs/system-one-system-two-research.md), and
  [architecture guide](docs/architecture.md).
- Packages a Python 3.10+ application that runs from a checkout with no
  third-party runtime dependencies or frontend build.

Recorded finding: stronger code completed 52/100 held-out expert boards versus
32/100 for the old heuristic. The four-state live pilot showed faster Jev
choices, no demonstrated hybrid reliability gain, and escalation on every
hybrid state. These records were produced by the original experiments; the
standalone extraction does not constitute a new model evaluation.

The stronger solver and cascade run through the CLI. Integrating them into a
shared browser controller and Solver Lab remains
[planned work](minesweeper/docs/v0.2-release-plan.md).
