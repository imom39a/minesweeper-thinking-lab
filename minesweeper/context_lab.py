"""V3 input ablation: neutral candidates and inspectable public evidence."""
from __future__ import annotations

from .game import MinesweeperGame, cell_label, parse_cell_label

MODES = ("clues", "equations", "llm")
MAX_CLUES = 512
INSTRUCTIONS = (
    "Choose one offered hidden cell to reveal next, aiming to avoid a mine. "
    "Use only the supplied public evidence. Each revealed number counts mines "
    "in its eight neighboring cells. Unknown cells may contain mines. "
    "The context may be incomplete; do not assume omitted regions are safe. "
    "Flags are annotations, not proof. Return one offered choice."
)


def neutral_candidates(game: MinesweeperGame, limit: int) -> list[dict]:
    """Evenly sample the visible frontier, without deductions or risk ranking."""
    pool = sorted(game.frontier_hidden())
    if not pool:
        pool = [(r, c) for r in range(game.height) for c in range(game.width)
                if (r, c) not in game.revealed and (r, c) not in game.flagged]
    if len(pool) > limit:
        pool = [pool[i * (len(pool) - 1) // (limit - 1)] for i in range(limit)] if limit > 1 else pool[:1]
    return [{"cell": cell_label(r, c), "row": r, "col": c} for r, c in pool]


def build_input(game: MinesweeperGame, mode: str, limit: int = 20) -> dict:
    if mode not in MODES:
        raise ValueError("context_mode_invalid")
    if mode == "llm":
        return public_board(game, limit)
    candidates = neutral_candidates(game, limit)
    # Start with every clue bordering a candidate. Expand through shared unknown
    # neighbors, retaining exact memberships for every included clue.
    seeds = sorted({neighbor for c in candidates
                    for neighbor in game.neighbors(c["row"], c["col"])
                    if neighbor in game.revealed})
    pending = list(seeds)
    seen = set(seeds)
    clues = []
    equations = []
    unknown = set()
    index = 0
    while index < len(pending) and len(clues) < MAX_CLUES:
        cell = pending[index]
        index += 1
        hidden = sorted(n for n in game.neighbors(*cell) if n not in game.revealed)
        if not hidden:
            continue
        number = game.adjacent_mines(*cell)  # Only an already-revealed clue.
        label = cell_label(*cell)
        clues.append({"cell": label, "row": cell[0], "col": cell[1], "number": number})
        equations.append({"clue": label, "cells": [cell_label(*n) for n in hidden], "mines": number})
        unknown.update(hidden)
        for n in hidden:
            for adjacent in game.neighbors(*n):
                if adjacent in game.revealed and adjacent not in seen:
                    pending.append(adjacent)
                    seen.add(adjacent)
    state = {
        "game": "minesweeper",
        "board": {"width": game.width, "height": game.height, "total_mines": game.mines,
                  "revealed_count": len(game.revealed),
                  "unrevealed_count": game.width * game.height - len(game.revealed)},
        "candidates": candidates,
        "visible_clues": clues,
        "unknown_cells": [{"cell": cell_label(*n), "row": n[0], "col": n[1]} for n in sorted(unknown)],
        "context": {"clue_limit": MAX_CLUES, "clue_count": len(clues),
                    "expansion_truncated": index < len(pending),
                    "scope": "Connected clues around offered candidates; other regions may be omitted."},
    }
    if mode == "equations":
        state["equations"] = equations
    return state


def request_for(game: MinesweeperGame, mode: str, model: str, limit: int = 20) -> dict:
    if mode == "llm":
        raise ValueError("llm_proposals_required")
    state = build_input(game, mode, limit)
    return {"model": model, "state": state,
            "questions": {"cell": {"type": "choice", "instructions": INSTRUCTIONS,
                                     "criteria": {c["cell"]: c["cell"] for c in state["candidates"]}}}}


def public_board(game: MinesweeperGame, limit: int) -> dict:
    """Serialize observations, with no frontier selection or derived equations."""
    return {"game": "minesweeper", "board": {
        "width": game.width, "height": game.height, "total_mines": game.mines,
        "rows": ["".join(row) for row in game.token_grid()],
        "legend": "Rows and columns are 1-based; r1c1 is top-left. ? = hidden, F = flag (not proof), digits = adjacent mine count."},
        "proposal_limit": limit}


def proposal_request(game: MinesweeperGame, evidence: dict, advice: dict, model: str) -> dict:
    """Validate the LLM's options without adding, ranking, or solving moves."""
    proposals = advice.get("proposals")
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= evidence["proposal_limit"]:
        raise ValueError("llm_proposals_invalid")
    labels = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("llm_proposals_invalid")
        label = proposal.get("cell")
        cell = parse_cell_label(label) if isinstance(label, str) else None
        if (cell is None or not game.in_bounds(*cell) or cell in game.revealed or cell in game.flagged
                or cell_label(*cell) != label or label in labels
                or not isinstance(proposal.get("rationale"), str) or not proposal["rationale"].strip()):
            raise ValueError("llm_proposals_invalid")
        labels.append(label)
    return {"model": model, "state": {"public_board": evidence["board"], "llm_guidance": advice},
            "questions": {"cell": {"type": "choice", "instructions": (
                "Choose one proposed cell to reveal, aiming to avoid a mine. Evaluate the LLM's "
                "proposals against the visible board. Advice is unverified and may be wrong. "
                "Each revealed digit counts mines in its eight neighbors. Return one offered choice."),
                "criteria": {label: label for label in labels}}}}
