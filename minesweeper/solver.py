"""Bounded Minesweeper inference over public clues, never the hidden layout.

Exact risks condition a uniform distribution of mine placements on all revealed
numbers and the total mine count. They are probabilities of the *next* reveal
hitting a mine, not probabilities of eventually winning. Flags are annotations,
not evidence; callers should flag only cells in ``analysis.mines``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from heapq import nsmallest
from math import comb, nextafter

from minesweeper.game import MAX_CANDIDATES, MinesweeperGame, cell_label

Cell = tuple[int, int]
Equation = tuple[frozenset[Cell], int]


@dataclass
class Analysis:
    safe: set[Cell] = field(default_factory=set)
    mines: set[Cell] = field(default_factory=set)
    candidates: list[dict[str, object]] = field(default_factory=list)
    constraints: list[dict[str, object]] = field(default_factory=list)
    complete: bool = False
    stats: dict[str, object] = field(default_factory=dict)


class _LimitReached(Exception):
    pass


class _Inconsistent(Exception):
    pass


@dataclass
class _Component:
    cells: list[Cell]
    counts: dict[int, int]
    mine_counts: dict[Cell, dict[int, int]]


def _normalize(equations: list[Equation], safe: set[Cell], mines: set[Cell]) -> list[Equation]:
    unique: dict[frozenset[Cell], int] = {}
    for cells, count in equations:
        count -= len(cells & mines)
        cells = cells - safe - mines
        if not 0 <= count <= len(cells):
            raise _Inconsistent
        if not cells:
            continue
        if cells in unique and unique[cells] != count:
            raise _Inconsistent
        unique[cells] = count
    return sorted(unique.items(), key=lambda item: (len(item[0]), sorted(item[0]), item[1]))


def _propagate(equations: list[Equation], hidden: set[Cell], total: int) -> tuple[set[Cell], set[Cell], list[Equation]]:
    safe: set[Cell] = set()
    mines: set[Cell] = set()
    while True:
        equations = _normalize(equations, safe, mines)
        new_safe: set[Cell] = set()
        new_mines: set[Cell] = set()
        remaining = total - len(mines)
        unknown_count = len(hidden) - len(safe) - len(mines)
        if not 0 <= remaining <= unknown_count:
            raise _Inconsistent
        if remaining == 0:
            new_safe.update(hidden - safe - mines)
        elif remaining == unknown_count:
            new_mines.update(hidden - safe - mines)
        incidence: dict[Cell, set[int]] = defaultdict(set)
        for index, (cells, count) in enumerate(equations):
            if count == 0:
                new_safe.update(cells)
            elif count == len(cells):
                new_mines.update(cells)
            for cell in cells:
                incidence[cell].add(index)
        # Every superset shares every member, so the sparsest member's index
        # bounds the work; there is no quadratic scan of the entire frontier.
        for index, (cells, count) in enumerate(equations):
            possible = min((incidence[cell] for cell in cells), key=len)
            for other in possible:
                if other == index:
                    continue
                larger, larger_count = equations[other]
                if len(larger) <= len(cells) or not cells <= larger:
                    continue
                difference = larger - cells
                delta = larger_count - count
                if not 0 <= delta <= len(difference):
                    raise _Inconsistent
                if delta == 0:
                    new_safe.update(difference)
                elif delta == len(difference):
                    new_mines.update(difference)
        if (new_safe & new_mines) or (new_safe & mines) or (new_mines & safe):
            raise _Inconsistent
        new_safe -= safe
        new_mines -= mines
        if not new_safe and not new_mines:
            return safe, mines, equations
        safe.update(new_safe)
        mines.update(new_mines)


def _components(equations: list[Equation]) -> list[tuple[set[Cell], list[Equation]]]:
    incidence: dict[Cell, list[int]] = defaultdict(list)
    for index, (cells, _) in enumerate(equations):
        for cell in cells:
            incidence[cell].append(index)
    unseen = set(incidence)
    result: list[tuple[set[Cell], list[Equation]]] = []
    for start in sorted(incidence):
        if start not in unseen:
            continue
        unseen.remove(start)
        cells = {start}
        indices: set[int] = set()
        stack = [start]
        while stack:
            for index in incidence[stack.pop()]:
                if index in indices:
                    continue
                indices.add(index)
                for cell in equations[index][0]:
                    if cell in unseen:
                        unseen.remove(cell)
                        cells.add(cell)
                        stack.append(cell)
        result.append((cells, [equations[index] for index in sorted(indices)]))
    return result


def _enumerate(cells: set[Cell], equations: list[Equation], budget: list[int], total_remaining: int) -> _Component:
    incidence: dict[Cell, list[int]] = defaultdict(list)
    for index, (members, _) in enumerate(equations):
        for cell in members:
            incidence[cell].append(index)
    ordered = sorted(cells, key=lambda cell: (-len(incidence[cell]), cell))
    remaining = [len(members) for members, _ in equations]
    required = [count for _, count in equations]
    counts: dict[int, int] = defaultdict(int)
    mine_counts: dict[Cell, dict[int, int]] = {cell: defaultdict(int) for cell in ordered}
    selected: list[Cell] = []

    def visit(position: int, mine_count: int) -> None:
        if budget[0] <= 0:
            raise _LimitReached
        budget[0] -= 1
        if position == len(ordered):
            counts[mine_count] += 1
            for cell in selected:
                mine_counts[cell][mine_count] += 1
            return
        cell = ordered[position]
        affected = incidence[cell]
        for value in (0, 1):
            if mine_count + value > total_remaining:
                continue
            valid = True
            for index in affected:
                remaining[index] -= 1
                required[index] -= value
                if not 0 <= required[index] <= remaining[index]:
                    valid = False
            if valid:
                if value:
                    selected.append(cell)
                visit(position + 1, mine_count + value)
                if value:
                    selected.pop()
            for index in affected:
                remaining[index] += 1
                required[index] += value

    visit(0, 0)
    if not counts:
        raise _Inconsistent
    return _Component(ordered, dict(counts), {cell: dict(values) for cell, values in mine_counts.items()})


def _fraction(numerator: int, denominator: int) -> float:
    if numerator == 0:
        return 0.0
    if numerator == denominator:
        return 1.0
    return min(nextafter(1.0, 0.0), max(nextafter(0.0, 1.0), numerator / denominator))


def _global_risks(components: list[_Component], unconstrained: int, total: int, operation_limit: int) -> tuple[dict[Cell, float], set[Cell], set[Cell], float, int]:
    """Convolve component counts and weight with C(unconstrained, mines left).

    Polynomial division obtains each leave-one-component-out distribution. The
    separate arithmetic budget also bounds cases with many small components.
    No partially combined posterior is ever returned as exact.
    """
    operations = 0

    def spend(amount: int = 1) -> None:
        nonlocal operations
        operations += amount
        if operations > operation_limit:
            raise _LimitReached

    distribution = {0: 1}
    for component in components:
        combined: dict[int, int] = defaultdict(int)
        spend(len(distribution) * len(component.counts))
        for first, first_count in distribution.items():
            for second, second_count in component.counts.items():
                combined[first + second] += first_count * second_count
        distribution = dict(combined)
    valid_k = [total - mines for mines in distribution if 0 <= total - mines <= unconstrained]
    if not valid_k:
        raise _Inconsistent
    lower, upper = min(valid_k), max(valid_k)
    spend(upper - lower + 1)
    weights = {lower: comb(unconstrained, lower)}
    for k in range(lower, upper):
        weights[k + 1] = weights[k] * (unconstrained - k) // (k + 1)
    denominator = sum(count * weights.get(total - mines, 0) for mines, count in distribution.items())
    if not denominator:
        raise _Inconsistent
    unconstrained_numerator = (
        sum(count * (weights.get(total - mines, 0) * (total - mines) // unconstrained)
            for mines, count in distribution.items())
        if unconstrained else 0
    )
    risks: dict[Cell, float] = {}
    safe: set[Cell] = set()
    mines: set[Cell] = set()
    cached: dict[tuple[tuple[int, int], ...], dict[int, int]] = {}
    total_low, total_high = min(distribution), max(distribution)
    for component in components:
        signature = tuple(sorted(component.counts.items()))
        if signature not in cached:
            comp_low, comp_high = min(component.counts), max(component.counts)
            outside_low = total_low - comp_low
            outside_high = total_high - comp_high
            leading = component.counts[comp_low]
            outside: dict[int, int] = {}
            spend((outside_high - outside_low + 1) * len(component.counts))
            for degree in range(outside_low, outside_high + 1):
                coefficient = distribution.get(degree + comp_low, 0)
                for local, count in component.counts.items():
                    if local != comp_low:
                        coefficient -= count * outside.get(degree + comp_low - local, 0)
                quotient, remainder = divmod(coefficient, leading)
                if remainder or quotient < 0:
                    raise _Inconsistent
                if quotient:
                    outside[degree] = quotient
            spend(len(component.counts) * len(outside))
            cached[signature] = {
                local: sum(count * weights.get(total - local - degree, 0) for degree, count in outside.items())
                for local in component.counts
            }
        local_weights = cached[signature]
        for cell, cell_counts in component.mine_counts.items():
            numerator = sum(count * local_weights[local] for local, count in cell_counts.items())
            risks[cell] = _fraction(numerator, denominator)
            if numerator == 0:
                safe.add(cell)
            elif numerator == denominator:
                mines.add(cell)
    return risks, safe, mines, _fraction(unconstrained_numerator, denominator), operations


def analyze(game: MinesweeperGame, max_component_cells: int = 22, max_search_nodes: int = 200_000) -> Analysis:
    """Analyze only the revealed numbers and total mine count.

    Search limits apply across the whole analysis. Oversized/unfinished
    components retain heuristic estimates with ``risk_exact=False``. Sound
    propagation and fully enumerated local proofs survive that fallback.
    ``complete`` requires exact global weighting, including unconstrained cells.
    """
    if max_component_cells < 0 or max_search_nodes < 0:
        raise ValueError("solver bounds must be nonnegative")
    analysis = Analysis(stats={"components": 0, "largest_component": 0, "search_nodes": 0,
                               "aborted_components": 0, "oversized_components": 0,
                               "global_weighting_aborted": False, "inconsistent": False})
    if game.is_terminal:
        analysis.stats["terminal"] = True
        return analysis
    hidden = {(row, col) for row in range(game.height) for col in range(game.width)
              if (row, col) not in game.revealed}
    equations: list[Equation] = []
    frontier: set[Cell] = set()
    # adjacent_mines is called ONLY on revealed cells. No methods that inspect
    # hidden truth (deduce, frontier_hidden, risk_score, token_grid) are used.
    for cell in sorted(game.revealed):
        members = frozenset(neighbor for neighbor in game.neighbors(*cell) if neighbor in hidden)
        count = game.adjacent_mines(*cell)
        equations.append((members, count))
        frontier.update(members)
    analysis.constraints = [{"cells": [cell_label(*cell) for cell in sorted(members)], "mines": count}
                            for members, count in equations if members]
    budget = [max_search_nodes]
    risks: dict[Cell, float] = {}
    exact: set[Cell] = set()
    base_risk = game.mines / len(hidden) if hidden else 0.0
    try:
        safe, mines, residual = _propagate(equations, hidden, game.mines)
        analysis.safe, analysis.mines = safe, mines
        remaining = game.mines - len(mines)
        unknown = hidden - safe - mines
        base_risk = remaining / len(unknown) if unknown else 0.0
        # Heuristics are rankings only; they are neither proofs nor posteriors.
        fractions: dict[Cell, list[float]] = defaultdict(list)
        for members, count in residual:
            for cell in members:
                fractions[cell].append(count / len(members))
        risks = {cell: sum(values) / len(values) for cell, values in fractions.items()}
        partitions = _components(residual)
        analysis.stats["components"] = len(partitions)
        analysis.stats["largest_component"] = max((len(cells) for cells, _ in partitions), default=0)
        completed: list[_Component] = []
        for cells, component_equations in partitions:
            if len(cells) > max_component_cells:
                analysis.stats["oversized_components"] += 1
                continue
            try:
                component = _enumerate(cells, component_equations, budget, remaining)
            except (_LimitReached, RecursionError):
                # User-supplied component bounds can exceed Python's stack
                # limit. Discard that component's unfinished counts exactly
                # as for a search-budget exhaustion.
                analysis.stats["aborted_components"] += 1
                continue
            completed.append(component)
            local_total = sum(component.counts.values())
            for cell, counts in component.mine_counts.items():
                local_mines = sum(counts.values())
                if local_mines == 0:
                    safe.add(cell)
                elif local_mines == local_total:
                    mines.add(cell)
        unconstrained_cells = unknown - set(fractions)
        if len(completed) == len(partitions):
            try:
                exact_risks, exact_safe, exact_mines, outside_risk, operations = _global_risks(
                    completed, len(unconstrained_cells), remaining, max_search_nodes * 4 + 1)
                analysis.stats["weighting_operations"] = operations
                risks.update(exact_risks)
                exact.update(exact_risks)
                base_risk = outside_risk
                exact.update(unconstrained_cells)
                safe.update(exact_safe)
                mines.update(exact_mines)
                if outside_risk == 0.0:
                    safe.update(unconstrained_cells)
                elif outside_risk == 1.0:
                    mines.update(unconstrained_cells)
                analysis.complete = True
            except _LimitReached:
                analysis.stats["global_weighting_aborted"] = True
        # Exact local proofs remain valid even if another component was bounded.
        exact.update(safe)
        exact.update(mines)
        for cell in safe:
            risks[cell] = 0.0
        for cell in mines:
            risks[cell] = 1.0
    except _Inconsistent:
        # Invalid clues must not accidentally authorize a reveal.
        analysis.safe.clear()
        analysis.mines.clear()
        risks.clear()
        exact.clear()
        analysis.stats["inconsistent"] = True
        analysis.complete = False
        base_risk = min(1.0, max(0.0, game.mines / len(hidden))) if hidden else 0.0
    analysis.stats["search_nodes"] = max_search_nodes - budget[0]
    analysis.stats["frontier_cells"] = len(frontier)
    analysis.stats["hidden_cells"] = len(hidden)
    analysis.stats["exact_cells"] = len(exact)
    analysis.stats["proven_safe"] = len(analysis.safe)
    analysis.stats["proven_mines"] = len(analysis.mines)
    choices = nsmallest(MAX_CANDIDATES,
                        (cell for cell in hidden if cell not in analysis.mines and cell not in game.flagged),
                        key=lambda cell: (risks.get(cell, base_risk), cell))
    analysis.candidates = [{"cell": cell_label(*cell), "row": cell[0], "col": cell[1],
                            "provably_safe": cell in analysis.safe,
                            "mine_risk": risks.get(cell, base_risk),
                            "risk_exact": cell in exact, "frontier": cell in frontier}
                           for cell in choices]
    return analysis
