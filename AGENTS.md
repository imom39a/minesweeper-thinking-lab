# Project instructions

Use the `typesafe-ai` skill for every TypeSafe or Jev task, including System One API/SDK work, question design, routing, ranking, extraction, verification, and confidence handling. The repository skill is at `.agents/skills/typesafe-ai/SKILL.md`; read its linked live documentation before implementing version-dependent behavior.

Keep TypeSafe questions and decision thresholds together so they are easy to review. Batch independent questions over the same state in one request, and keep deterministic rules and side effects in ordinary code.

Load credentials with `source scripts/load-jev-env.sh`. It reads the local `.env` and maps the existing `JEV_API_KEY` name to the official `TYPESAFE_API_KEY` name expected by TypeSafe clients. Treat `.env` as secret and commit only `.env.example`.

Keep the three experiment variants distinct: the legacy LLM-versus-Jev browser demo, the Jev-only large-board browser demo, and the stronger-solver hybrid benchmark CLI. Share proposed future UI integration as a roadmap until implemented. Preserve recorded JSON results in `minesweeper/results/`; write new runs to a separate output path and distinguish model speed, whole-board wins, and one-step replay outcomes in published claims.
