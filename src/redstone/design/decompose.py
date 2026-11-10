"""Functional decomposition of a truth table into two smaller gates joined by `compose.connect` (M4).

Simple disjoint decomposition (Ashenhurst): f(x) = h(g(x_S), x_F) for a bound set S and the free set F of the
other inputs. It exists when the decomposition chart (columns = assignments of S, rows = assignments of F)
has at most two distinct columns; g then says which of the two columns an assignment of S picks.

Both parts are designed on their own (templates, torch PLA, or again by decomposition), joined with the
output of g into the first input of h, and the result is checked against the whole spec in the simulator.
That goes beyond the input limit of the PLA (`synth.MAX_INPUTS`) and splits wide functions (e.g. XOR of four levers) into chains of
small gates.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from .candidate import Candidate
from .spec import Spec

MAX_SPLITS = 6  # decompositions tried per spec (smallest parts first)
PARTS = 2  # best designs per part that are combined
TRIES = 12  # layouts tried per pair of part designs


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


_DRIVABLE: dict[tuple, list[Candidate]] = {}


def _drivable_pla(spec: Spec) -> list[Candidate]:
    """The PLA with drivable inputs (`synth.pla(drivable=True)`) as a last resort for the driven part h:
    the normal PLA's inputs cannot take a line when both polarities of the input are used."""
    from .synth import pla

    key = (len(spec.inputs), _values(spec))
    if key not in _DRIVABLE:
        p = pla(spec, name="pla-ansteuerbar", drivable=True)
        _DRIVABLE[key] = [p] if p is not None else []
    return [replace(c, inputs=list(c.inputs)) for c in _DRIVABLE[key]]


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
    # the quick check (every combination, no transitions) is enough for a part: the whole design is
    # checked in full later
    evs = [e for e in (evaluate_any(c, spec, quick=True) for c in cands) if e.ok]
    evs.sort(key=Evaluation.rank_key)
    return [e.candidate for e in evs[:PARTS]]


def decomposed(spec: Spec, depth: int = 2, log: list[str] | None = None) -> list[Candidate]:
    """Working candidates for a single-output spec built from decompositions; inputs in spec order."""
    from .compose import chains
    from .evaluate import evaluate_any

    if len(spec.outputs) != 1 or len(spec.inputs) < 3 or spec.partial:
        return []
    out = []
    for sp in splits(spec):
        gs, hs = _best(sp.g, depth), _best(sp.h, depth) + _drivable_pla(sp.h)
        found = None
        for gc, hc in itertools.product(gs, hs):
            tries = 0
            for _, cand in chains(gc, 0, hc, 0):
                tries += 1
                if tries > TRIES:
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


# ---------------------------------------------------------------------- several outputs side by side
SIDES_TRIED = 4


def _project(spec: Spec, ins: list[int], outs: list[int]) -> Spec:
    """The spec restricted to some inputs (the others off) and outputs."""
    table = {}
    for combo in itertools.product([False, True], repeat=len(ins)):
        x = [False] * len(spec.inputs)
        for i, v in zip(ins, combo):
            x[i] = v
        row = spec.table[tuple(x)]
        table[combo] = tuple(row[j] for j in outs)
    return Spec([spec.inputs[i] for i in ins], [spec.outputs[j] for j in outs], table, source=spec.source)


def support(spec: Spec, out: int) -> list[int]:
    """Inputs output `out` depends on."""
    dep = []
    for i in range(len(spec.inputs)):
        for combo, row in spec.table.items():
            flipped = combo[:i] + (not combo[i],) + combo[i + 1:]
            if row[out] != spec.table[flipped][out]:
                dep.append(i)
                break
    return dep


def parallel(spec: Spec, log: list[str] | None = None) -> list[Candidate]:
    """A multi-output spec as one part per output, placed side by side. A lever needed by several parts sits
    in the first part that uses it; the later parts get its signal over a tapped line (`compose.wire`).
    After every added part the outputs so far are checked in the simulator. One result per working
    spacing between the parts (`compose.SPACINGS`); the ranking picks the smallest."""
    from .compose import SPACINGS

    out: list[Candidate] = []
    for spacing in SPACINGS:
        out += _parallel(spec, spacing, log if spacing == SPACINGS[-1] else None)
    return out


def _parallel(spec: Spec, spacing: int, log: list[str] | None) -> list[Candidate]:
    from .compose import HORIZONTAL, place_beside, rotate, wire
    from .evaluate import evaluate_any

    m = len(spec.outputs)
    if m < 2 or spec.partial:
        return []
    supports = [support(spec, j) for j in range(m)]
    if any(not s for s in supports):
        return []  # constant outputs are not built as parts
    comp: Candidate | None = None
    labels: list[int] = []  # spec input index of every input of comp, in order
    for j in range(m):
        sub = _project(spec, supports[j], [j])
        parts = _best(sub, 1)
        if not parts:
            return []
        if comp is None:
            comp, labels = parts[0], list(supports[j])
            continue
        done = None
        ins_so_far = sorted(set(labels) | set(supports[j]))
        check = _project(spec, ins_so_far, list(range(j + 1)))
        for part in parts:
            for turn in range(4):
                tp = rotate(part, turn)
                if tp is None:
                    continue
                for side in HORIZONTAL[:SIDES_TRIED]:
                    cand, _ = place_beside(comp, tp, side, spacing)
                    lab = labels + list(supports[j])
                    for k in supports[j]:
                        if cand is None or k not in labels:
                            continue
                        src = cand.inputs[lab.index(k)]
                        t = len(lab) - 1 - lab[::-1].index(k)
                        cand = wire(cand, src, cand.inputs[t])
                        if cand is not None:
                            del lab[t]
                    if cand is None:
                        continue
                    order = [lab.index(i) for i in ins_so_far]
                    trial = replace(cand, inputs=[cand.inputs[o] for o in order])
                    if evaluate_any(trial, check, quick=True).correct:
                        done = (cand, lab)
                        break
                if done:
                    break
            if done:
                break
        if log is not None:
            from .report import COMPOSE_PREFIX

            log.append(f"{COMPOSE_PREFIX}Ausgang {spec.outputs[j]} daneben gesetzt: "
                       + ("verbunden" if done else "keine funktionierende Anordnung gefunden"))
        if done is None:
            return []
        comp, labels = done
    order = [labels.index(i) for i in range(len(spec.inputs))]
    comp = replace(comp, inputs=[comp.inputs[o] for o in order], name="parallel: " + comp.name,
                   origin="nebeneinander: " + comp.origin)
    return [comp] if evaluate_any(comp, spec).ok else []
