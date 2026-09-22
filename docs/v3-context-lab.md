# V3: what does Jev infer from the input?

Open `/v3/` to compare three representations of the same public evidence.
V3 has its own game session, separate from the original browser experiments.
It retains zoom, manual scrolling, choice percentages, and optional following.

| Input mode | Evidence supplied | Solver assistance |
| --- | --- | --- |
| Visible clues only | Candidate coordinates, revealed clue coordinates and numbers, nearby unknown-cell coordinates, board counts | None |
| Clues + explicit equations | The same evidence plus the exact unknown neighbors counted by each clue | No deductions or risk estimates |
| Clues + equations + LLM guidance | The same evidence and equations plus an LLM's analysis of the same clues and candidates | LLM advice, unverified |

Equations restate observations. For example, a revealed `1` bordering unknown
cells A, B, and C becomes `A + B + C = 1`. The equation mode does not simplify
or combine equations, mark cells safe, or calculate mine probabilities.

## What stays fixed

All modes use the same prompt and candidate-selection procedure. Code evenly
samples the frontier in row/column order up to the candidate limit; it does
not rank by safety or remove proven mines. If there is no frontier, it samples
unrevealed, unflagged cells. Candidates are identical **for identical board
states**. Code still owns game rules, legal-action checks, and execution.

The context starts with clues adjacent to the candidates and expands through
shared unknown neighbors, up to 512 clues. Both unguided modes receive the
same clue set; equation mode adds explicit memberships. A truncation flag and
scope description identify incomplete context. Unconnected regions may be
omitted even when expansion completes. No mode receives hidden mine locations
or move history.

The LLM-guided mode makes an OpenRouter call before each Jev decision. The
LLM receives the same public evidence and equations, without solver outputs.
Its advice is attached as `llm_guidance`; Jev still chooses from the unchanged
candidates. Advice may be wrong and is not a verified proof or calibrated risk.
Select the guidance model in the UI; `OPENROUTER_API_KEY` is required in addition
to the Jev key. Both calls count toward the game deadline, so this mode adds
latency and cost. A failed guidance call stops the run without a replacement move.

## Inspect and compare

1. Choose a board size, seed, pinned Jev model, candidate limit, and input mode. For LLM guidance, also choose the OpenRouter model.
2. Start the game. Expand **Input sent to Jev** below the board to inspect the
   exact latest request, including the Choice prompt and offered answers.
3. Use **Download request JSON** to retain that request without credentials.
4. Repeat with the same settings and another mode.

Different choices lead to different subsequent board states, so same-seed
full games are not identical-state decision comparisons. A controlled study
should replay frozen observations across all modes and report repeated games,
failures, calls, and latency. The UI itself does not establish which mode is
more capable.

V3 stops on provider errors, invalid choices, and expired decisions. It makes
no random replacement move and applies no minimum-risk correction. Choice
percentages remain model preferences, not probabilities of cell safety.

![V3 LLM-guided mode on a beginner board](images/v3-llm-guidance.png)

Implementation: [context construction](../minesweeper/context_lab.py),
[provider adapter](../minesweeper/agents.py), and
[isolation tests](../minesweeper/test_context_lab.py).
