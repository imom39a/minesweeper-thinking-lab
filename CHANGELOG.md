# Changelog

## Unreleased

- Add a separate V3 context lab with clue-only, equation, and code-assisted
  inputs, inspectable requests, and failure handling without random fallback.

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
