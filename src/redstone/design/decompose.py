"""Functional decomposition of a truth table into two smaller gates joined by `compose.connect` (M4).

Simple disjoint decomposition (Ashenhurst): f(x) = h(g(x_S), x_F) for a bound set S and the free set F of the
other inputs. It exists when the decomposition chart (columns = assignments of S, rows = assignments of F)
has at most two distinct columns; g then says which of the two columns an assignment of S picks.

Both parts are designed on their own (templates, torch PLA, or again by decomposition), joined with the
output of g into the first input of h, and the result is checked against the whole spec in the simulator.
That lifts the 4-input limit of the PLA and splits wide functions (e.g. XOR of four levers) into chains of
small gates.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from .candidate import Candidate
from .spec import Spec

MAX_SPLITS = 6  # decompositions tried per spec (smallest parts first)
PARTS = 2  # best designs per part that are combined
TRIES = 12  # layouts tried per combination


@dataclass(frozen=True)
class Split:
    bound: tuple[int, ...]  # spec input indices fed into g
    free: tuple[int, ...]  # the others, fed into h after g
    g: Spec  # inputs = the bound inputs
    h: Spec  # inputs = ["g"] + the free inputs

    def describe(self, names: list[str]) -> str:
        return (f"g({', '.join(names[i] for i in self.bound)}), "
                f"h(g, {', '.join(names[i] for i in self.free)})")


def splits(spec: Spec, out: int = 0) -> list[Split]:
    """All simple disjoint decompositions of output `out` with |S| >= 2 and |F| >= 1, small g first."""
    n = len(spec.inputs)
    found, seen = [], set()
    for size in range(2, n):
        for bound in itertools.combinations(range(n), size):
            free = tuple(i for i in range(n) if i not in bound)
            columns: dict[tuple[bool, ...], tuple[bool, ...]] = {}
            for sb in itertools.product([False, True], repeat=len(bound)):
                col = []
                for fb in itertools.product([False, True], repeat=len(free)):
                    x = [False] * n
                    for i, v in zip(bound, sb):
                        x[i] = v
                    for i, v in zip(free, fb):
                        x[i] = v
                    col.append(spec.table[tuple(x)][out])
                columns[sb] = tuple(col)
            distinct = sorted(set(columns.values()))
            if len(distinct) != 2:
                continue  # one column: f ignores S; more than two: no simple decomposition
            # g is off for the column of the all-off assignment, so g rests off when all levers are off
            zero = columns[(False,) * len(bound)]
            g_table = {sb: (col != zero,) for sb, col in columns.items()}
            one = next(c for c in distinct if c != zero)
            h_table = {}
            for gv in (False, True):
                col = one if gv else zero
                for k, fb in enumerate(itertools.product([False, True], repeat=len(free))):
                    h_table[(gv, *fb)] = (col[k],)
            names = spec.inputs
            g = Spec([names[i] for i in bound], ["g"], g_table, source="Zerlegung")
            h = Spec(["g"] + [names[i] for i in free], [spec.outputs[out]], h_table, source="Zerlegung")
            key = (_values(g), _values(h))
            if key in seen:
                continue  # same parts as an earlier split (symmetric function), only the levers differ
            seen.add(key)
            found.append(Split(bound, free, g, h))
    return found[:MAX_SPLITS]


def _values(spec: Spec) -> tuple:
    return tuple(spec.output_column(i) for i in range(len(spec.outputs)))


_BEST: dict[tuple, list[Candidate]] = {}  # parts already designed in this process (by table and depth)


def _best(spec: Spec, depth: int) -> list[Candidate]:
    """The best few working designs of a part: templates, PLA, or a further decomposition."""
    key = (len(spec.inputs), _values(spec), depth)
    if key not in _BEST:
        _BEST[key] = _design_part(spec, depth)
    return [replace(c, inputs=list(c.inputs)) for c in _BEST[key]]


def _design_part(spec: Spec, depth: int) -> list[Candidate]:
    from .evaluate import Evaluation, evaluate_any
    from .search import template_candidates
    from .synth import pla

    cands = template_candidates(spec)
    p = pla(spec)
    if p is not None:
        cands.append(p)
    if depth > 0:  # also when a template or the PLA works: a chain of small gates is often smaller
        cands += decomposed(spec, depth - 1)
    evs = [e for e in (evaluate_any(c, spec) for c in cands) if e.ok]
    evs.sort(key=Evaluation.rank_key)
    return [e.candidate for e in evs[:PARTS]]


def decomposed(spec: Spec, depth: int = 2, log: list[str] | None = None) -> list[Candidate]:
    """Working candidates for a single-output spec built from decompositions; inputs in spec order."""
    from .compose import chains
    from .evaluate import evaluate_any

    if len(spec.outputs) != 1 or len(spec.inputs) < 3:
        return []
    out = []
    for sp in splits(spec):
        gs, hs = _best(sp.g, depth), _best(sp.h, depth)
        found = None
        for gc, hc in itertools.product(gs, hs):
            for k, (_, cand) in enumerate(chains(gc, 0, hc, 0)):
                if k >= TRIES:
                    break
                # composite inputs: bound inputs (g order), then free inputs (h order); put them in spec order
                order = list(sp.bound) + list(sp.free)
                inputs = [None] * len(spec.inputs)
                for pos, i in zip(cand.inputs, order):
                    inputs[i] = pos
                cand = replace(cand, inputs=inputs, name=f"{gc.name} → {hc.name}",
                               origin=f"zerlegt: {sp.describe(spec.inputs)}; {cand.origin}")
                if evaluate_any(cand, spec, quick=True).correct:
                    found = cand
                    break
            if found is not None:
                break
        if log is not None:
            from .report import COMPOSE_PREFIX

            log.append(f"{COMPOSE_PREFIX}Zerlegung {sp.describe(spec.inputs)}: "
                       + (f"{found.name}, {found.block_count} Blöcke" if found
                          else "keine funktionierende Verbindung gefunden"))
        if found is not None:
            out.append(found)
    return out
