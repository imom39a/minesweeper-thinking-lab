# Changelog

## Unreleased

- Add a separate V3 browser experiment with **System 1 (Jev)** and
  **System 1 + System 2 (LLM proposals → Jev selection)**. Combined mode sends
  the full visible board without code-selected candidates or equations;
  invalid proposals stop the run without replacement moves.
- Add model controls, inspectable Jev requests, and stage-specific status.
  Failures appear above the board; System 2 has up to 120 seconds within the
  game deadline. Retain the earlier equation baseline through the API only.
- Document V3 separately from the historical guarded CLI cascade and its results.
- Keep the V2 viewport fixed by default; make following opt-in and add a
  one-time **Show latest move** control.
- Add V2 cell-choice percentages, previous-round changes, recent move trails,
  pause/resume, and zoomable scrolling with an optional follow mode.
- Add browser gameplay screenshots and repeat experiment records.
- Replace the repository extraction manifest with dataset checksums in
  `minesweeper/results/SHA256SUMS`.
- Restructure the research report and guides around methods, results,
  limitations, and usage; consolidate proposed work in the
  [roadmap](docs/roadmap.md).

## v0.1.0 — Research preview · 2026-09-22

First standalone release of Minesweeper Thinking Lab, extracted from
[jev-playground](https://github.com/imom39a/jev-playground).

- Publishes three experiments: LLM vs Jev in the browser, Jev-only large boards
  in the browser, and a CLI study of stronger deterministic inference with
  code, proof-only, Jev, LLM, and hybrid policies.
- Includes the bounded constraint solver, guarded Jev → LLM cascade, paired
  seeded episodes, common-state replay, tests, and 11 recorded result files.
- Publishes the [findings](minesweeper/docs/system-one-system-two-article.md),
  [research report](minesweeper/docs/system-one-system-two-research.md), and
  [architecture guide](docs/architecture.md).
- Packages a Python 3.10+ application that runs from a checkout with no
  third-party runtime dependencies or frontend build.

The stronger solver and cascade run through the CLI. Browser integration is
[planned work](docs/roadmap.md).
