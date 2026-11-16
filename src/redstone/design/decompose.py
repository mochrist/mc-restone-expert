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


# parts already designed in this process, by input names, table and depth (the names are in the designs'
# descriptions, so a part with the same table but other inputs must not reuse them)
_BEST: dict[tuple, list[Candidate]] = {}


def _best(spec: Spec, depth: int, driven: bool = False) -> list[Candidate]:
    """The best few working designs of a part: templates, PLA, or a further decomposition. driven: the
    first input will take a line from another part (`drivable_first`)."""
    key = (tuple(spec.inputs), _values(spec), depth, driven)
    if key not in _BEST:
        _BEST[key] = _design_part(spec, depth, driven)
    return [replace(c, inputs=list(c.inputs)) for c in _BEST[key]]


def drivable_first(c: Candidate, spec: Spec) -> bool:
    """Whether another part can drive the first input of c: a buffer (lever, dust, lamp) in front of it,
    connected by `compose.chains`, still computes the spec. Not every template input can be driven, e.g. the
    lever of a full adder's b and c inputs also feeds blocks that a line would power the wrong way."""
    from .compose import chains
    from .evaluate import evaluate_any
    from .templates import TEMPLATES

    buffer = next(t for t in TEMPLATES if t.name == "buffer-dust").build()  # buffer-direct never connects
    for k, (_, cand) in enumerate(chains(buffer, 0, c, 0)):
        if k >= TRIES:
            break
        if evaluate_any(cand, spec, quick=True).correct:
            return True
    return False


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


def _pairs(gs: list[Candidate], hs: list[Candidate]) -> list[tuple[Candidate, Candidate]]:
    """Pairs of part designs, the smallest estimated result (sum of the parts' volumes) first: the first pair
    that connects is taken, and the parts are each sorted by their own rank, so a large PLA for G would win
    over a cascade of small parts just by coming first."""
    return sorted(itertools.product(gs, hs), key=lambda p: p[0].volume + p[1].volume)


def _design_part(spec: Spec, depth: int, driven: bool = False) -> list[Candidate]:
    """The PARTS best designs by rank (volume first) plus the one with the fewest blocks; for a driven part,
    designs whose first input can be driven first."""
    from .evaluate import Evaluation, evaluate_any
    from .search import template_candidates
    from .synth import pla

    # the quick check (every combination, no transitions) is enough for a part: the whole design is
    # checked in full later
    evs = [e for e in (evaluate_any(c, spec, quick=True) for c in template_candidates(spec, first_inputs=driven))
           if e.ok]
    cands = []
    p = pla(spec)
    if p is not None:
        cands.append(p)
    # also when a template or the PLA works: a chain of small gates is often smaller; but not for a partial
    # spec (the stage of a cascade) that a template covers
    if depth > 0 and not (spec.partial and evs):
        cands += decomposed(spec, depth - 1, driven=driven) + shared(spec, depth - 1, driven=driven)
    evs += [e for e in (evaluate_any(c, spec, quick=True) for c in cands) if e.ok]
    # driven parts: those whose first input passed `drivable_first` come first (a failed test only moves a
    # part back: the real composition may still work)
    blocked = {id(e): driven and not drivable_first(e.candidate, spec) for e in evs}
    evs.sort(key=lambda e: (blocked[id(e)], Evaluation.rank_key(e)))
    keep = evs[:PARTS]
    fewest = min(evs, key=lambda e: (blocked[id(e)], e.candidate.block_count), default=None)
    if fewest is not None and fewest not in keep:
        keep.append(fewest)
    return [e.candidate for e in keep]


def decomposed(spec: Spec, depth: int = 2, log: list[str] | None = None, driven: bool = False) -> list[Candidate]:
    """Working candidates for a single-output spec built from decompositions; inputs in spec order. driven:
    the first input will be driven by another part (g gets driven parts when it takes that input)."""
    from .compose import chains
    from .evaluate import evaluate_any

    if len(spec.outputs) != 1 or len(spec.inputs) < 3 or spec.partial:
        return []
    out = []
    for sp in splits(spec):
        gs, hs = _best(sp.g, depth, driven and 0 in sp.bound), _best(sp.h, depth, True) + _drivable_pla(sp.h)
        found = None
        for gc, hc in _pairs(gs, hs):
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
    # non-disjoint splits only where no PLA can be built: inside the parts (a PLA each) they multiplied the
    # search time (mux8: 48 nested tries, 15 of 17 minutes) without a smaller result
    from .synth import MAX_INPUTS

    if not out:  # no disjoint split: a multiplexer of the two cofactors (the PLA competes in the ranking)
        out = _shannon(spec, shannon_splits(spec), depth, log, driven)
    if not out and len(spec.inputs) > MAX_INPUTS and not splits(spec):
        out = _nondisjoint(spec, nondisjoint_splits(spec), depth, log, driven)
    return out


# ---------------------------------------------------------------------- non-disjoint decomposition
@dataclass(frozen=True)
class CommonSplit:
    """Non-disjoint decomposition f(x) = h(g(x_S, x_C), x_C, x_F): the common inputs C feed both parts (one
    lever, its line tapped for H). It exists when, for every assignment of C, the chart over S × F has at
    most two distinct columns. An 8:1 multiplexer: g = the 4:1 multiplexer of the low data inputs, h picks
    between g and the high data inputs; both need the two low select inputs."""
    bound: tuple[int, ...]  # S
    common: tuple[int, ...]  # C
    free: tuple[int, ...]  # F
    g: Spec  # inputs = C ∪ S in spec order
    h: Spec  # inputs = ["g"] + C ∪ F in spec order

    def describe(self, names: list[str]) -> str:
        gi = ", ".join(names[i] for i in sorted(self.bound + self.common))
        hi = ", ".join(names[i] for i in sorted(self.common + self.free))
        return f"g({gi}), h(g, {hi}) mit gemeinsamen {', '.join(names[i] for i in self.common)}"


MAX_COMMON = 2  # common inputs C tried
MAX_COMMON_SPLITS = 4


def _perm(n: int, first: tuple[int, ...]) -> list[int]:
    """Indices of the 2^n combinations (input 0 most significant, as itertools.product) in the order where
    the inputs `first` vary slowest, the others fastest."""
    perm = [0]
    for i in list(first) + [i for i in range(n) if i not in first]:
        w = 1 << (n - 1 - i)
        perm = [p + b for p in perm for b in (0, w)]
    return perm


def nondisjoint_splits(spec: Spec, out: int = 0) -> list[CommonSplit]:
    """Non-disjoint decompositions of output `out` with 1 to MAX_COMMON common inputs, |S| >= 2, |F| >= 1,
    every input of S used by g; the most balanced first (the larger part smallest), then fewer common inputs.
    Only for full specs; columns are compared as slices of the reordered truth table (operator.itemgetter)."""
    import operator

    n = len(spec.inputs)
    if spec.partial or n < 4:
        return []
    values = tuple(spec.table[c][out] for c in itertools.product([False, True], repeat=n))
    sup = set(support(spec, out))
    found = []
    for k in range(1, MAX_COMMON + 1):
        for common in itertools.combinations(sorted(sup), k):
            others = [i for i in range(n) if i not in common]
            for size in range(2, len(others)):
                for bound in itertools.combinations(others, size):
                    if not set(bound) <= sup:
                        continue
                    free = tuple(i for i in others if i not in bound)
                    perm = operator.itemgetter(*_perm(n, common + bound))(values)
                    w, nb = 2 ** len(free), 2 ** size
                    slices, two = [], False
                    for c in range(2 ** k):
                        base = c * nb * w
                        cols = [perm[base + s * w: base + (s + 1) * w] for s in range(nb)]
                        distinct = set(cols)
                        if len(distinct) > 2:
                            break
                        two |= len(distinct) == 2
                        slices.append(cols)
                    else:
                        if two:
                            found.append((common, bound, free, slices))
    found.sort(key=lambda f: (max(len(f[0]) + len(f[1]), 1 + len(f[0]) + len(f[2])), len(f[0])))
    out_splits = []
    for common, bound, free, slices in found:
        sp = _common_split(spec, out, common, bound, free, slices)
        if sp is not None:
            out_splits.append(sp)
        if len(out_splits) >= MAX_COMMON_SPLITS:
            break
    return out_splits


def _common_split(spec: Spec, out: int, common, bound, free, slices) -> CommonSplit | None:
    """The parts of one non-disjoint split; g is off for the column of S all off in every slice. None when
    an input of S does not change g (it would be a dead lever)."""
    k, size = len(common), len(bound)
    gi, hi = sorted(common + bound), sorted(common + free)
    g_table, h_table = {}, {}
    for c, cbits in enumerate(itertools.product([False, True], repeat=k)):
        cols = slices[c]
        zero = cols[0]
        one = next((col for col in cols if col != zero), zero)
        for s, sbits in enumerate(itertools.product([False, True], repeat=size)):
            x = dict(zip(common, cbits)) | dict(zip(bound, sbits))
            g_table[tuple(x[i] for i in gi)] = (cols[s] != zero,)
        for gv in (False, True):
            col = one if gv else zero
            for f, fbits in enumerate(itertools.product([False, True], repeat=len(free))):
                x = dict(zip(common, cbits)) | dict(zip(free, fbits))
                h_table[(gv, *(x[i] for i in hi))] = (col[f],)
    names = spec.inputs
    g = Spec([names[i] for i in gi], ["g"], g_table, source="Zerlegung")
    if not {gi.index(i) for i in bound} <= set(support(g, 0)):
        return None
    h = Spec(["g"] + [names[i] for i in hi], [spec.outputs[out]], h_table, source="Zerlegung")
    return CommonSplit(tuple(bound), tuple(common), tuple(free), g, h)


def _nondisjoint(spec: Spec, sps: list[CommonSplit], depth: int, log: list[str] | None,
                 driven: bool) -> list[Candidate]:
    """Candidates from `nondisjoint_splits`: g's output drives h's first input (`compose.chains`), then the
    lines of h's common levers are fed from g's levers (`compose.wire` taps them)."""
    from .compose import chains
    from .evaluate import evaluate_any

    out = []
    for sp in sps:
        gi, hi = sorted(sp.common + sp.bound), sorted(sp.common + sp.free)
        gs = _best(sp.g, depth, driven and 0 in gi)
        hs = _best(sp.h, depth, True) + _drivable_pla(sp.h)
        apart = _apart(sp, gi, hi)
        found = None
        for gc, hc in _pairs(gs, hs):
            tries = 0
            for k, (_, chained) in enumerate(chains(gc, 0, hc, 0)):
                if tries >= TRIES or k >= CHAINS_SEEN:
                    break
                # the chain with H's common levers still separate must work before lines are tapped (most
                # layouts fail already there: a PLA lamp lit from above needs the "stone" output)
                if not evaluate_any(chained, apart, quick=True).correct:
                    continue
                tries += 1
                for cand in _tapped(chained, gi + hi, sp.common):
                    cand = replace(cand, name=f"{gc.name} → {hc.name}",
                                   origin=f"zerlegt: {sp.describe(spec.inputs)}; {cand.origin}")
                    if evaluate_any(cand, spec, quick=True).correct:
                        found = cand
                        break
                if found is not None:
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


CHAINS_SEEN = 60  # chains looked at per pair of parts (only those that work count against TRIES)
APART_SAMPLE = 128  # combinations checked before tapping


def _apart(sp: CommonSplit | SharedCommonSplit, gi: list[int], hi: list[int]) -> Spec:
    """The spec of the chain before tapping: G's inputs, then H's own (common ones again, separate levers);
    outputs H's, then G's other ones.
    Wide chains get a partial spec (APART_SAMPLE combinations: all off, every single lever, the rest drawn
    with a fixed seed): it only has to sort out broken joints, the tapped design is checked in full."""
    import random

    n = len(gi) + len(hi)
    if 2 ** n <= APART_SAMPLE:
        combos = list(itertools.product([False, True], repeat=n))
    else:
        rng = random.Random(0)
        picked = {(False,) * n} | {tuple(k == j for k in range(n)) for j in range(n)}
        while len(picked) < APART_SAMPLE:
            picked.add(tuple(rng.random() < 0.5 for _ in range(n)))
        combos = sorted(picked)
    table = {}
    for x in combos:
        g = sp.g.table[x[:len(gi)]]
        table[x] = sp.h.table[(g[0], *x[len(gi):])] + g[1:]  # G's other outputs (local) after H's
    return Spec([f"i{k}" for k in range(n)], sp.h.outputs + sp.g.outputs[1:], table, source="Zerlegung",
                care=None if len(table) == 2 ** n else set(table))


TAP_MODES = ("repeater", "dust")


def _tapped(cand: Candidate, labels: list[int], common, modes=TAP_MODES):
    """Every way to feed H's common levers from G's (`compose.wire`, a tapped line, repeater or dust at the
    lever: a wall lever of a drivable PLA mostly needs the repeater), inputs in spec order."""
    from .compose import wire

    if not common:
        yield replace(cand, inputs=[cand.inputs[labels.index(i)] for i in range(len(labels))])
        return
    i, rest = common[0], common[1:]
    t = len(labels) - 1 - labels[::-1].index(i)
    for mode in modes:
        w = wire(cand, cand.inputs[labels.index(i)], cand.inputs[t], input_mode=mode)
        if w is not None:
            yield from _tapped(w, labels[:t] + labels[t + 1:], rest, modes)


# ---------------------------------------------------------------------- shared part of several outputs
@dataclass(frozen=True)
class SharedSplit:
    """Several outputs through shared signals: G computes the signals (`width` of them) and the outputs that
    depend on the bound set only (`local`), H computes the other outputs (`rest`) from the signals and the free
    inputs. A ripple-carry adder: one signal, the carry. A comparator from its high bits: two signals
    ("greater", "less"), because the low bits decide only when the high bits are equal."""
    bound: tuple[int, ...]
    free: tuple[int, ...]
    local: tuple[int, ...]  # spec output indices computed by G
    rest: tuple[int, ...]  # spec output indices computed by H
    g: Spec  # inputs = the bound inputs, outputs = the signals + local
    h: Spec  # inputs = the signals + the free inputs, outputs = rest
    width: int = 1  # number of signals from G to H

    def describe(self, spec: Spec) -> str:
        names, outs = spec.inputs, spec.outputs
        sig = ", ".join(self.g.outputs[:self.width])
        local = "".join(f", {outs[j]}" for j in self.local)
        return (f"{sig}{local} aus ({', '.join(names[i] for i in self.bound)}), "
                f"{', '.join(outs[j] for j in self.rest)} aus ({sig}, {', '.join(names[i] for i in self.free)})")


MAX_SHARED_SPLITS = 4
MAX_WIDE_SPLITS = 2  # splits with two signals, tried only when none with one works
MAX_CASCADE_INPUTS = 6  # splits with a small H first only up to this many inputs (G is designed again, deeper)


def shared_splits(spec: Spec, width: int = 1) -> list[SharedSplit]:
    """Disjoint decompositions of a multi-output spec with `width` shared signals (1 or 2): for a bound set S,
    the outputs that depend on the free inputs must together see more than 2^(width-1) and at most 2^width
    distinct columns over the assignments of S (the multi-output decomposition chart), and fewer than S has
    assignments (otherwise G would only pass its inputs on); the outputs that do not depend on the free inputs
    are computed next to the signals. One signal: bound sets that leave many outputs in G and few inputs for H
    first (a ripple-carry adder's carry). Two signals: the code of each column is chosen so that G and H need
    the fewest terms, and the cheapest splits come first (otherwise G takes almost every input and is hardly
    smaller than the spec); with three columns the unused code does not matter for H (a partial spec)."""
    n, m = len(spec.inputs), len(spec.outputs)
    if m < 2 or n < 3:
        return []
    supports = [set(support(spec, j)) for j in range(m)]
    found = []
    for size in range(2, n):
        for bound in itertools.combinations(range(n), size):
            free = tuple(i for i in range(n) if i not in bound)
            local = tuple(j for j in range(m) if supports[j] and supports[j] <= set(bound))
            rest = tuple(j for j in range(m) if j not in local)
            if not rest or any(not supports[j] for j in rest):
                continue
            columns: dict[tuple[bool, ...], tuple] = {}
            for sb in itertools.product([False, True], repeat=size):
                col = tuple(_entry(spec, _combo(n, bound, sb, free, fb), rest)
                            for fb in itertools.product([False, True], repeat=len(free)))
                if any(e is not None for e in col):
                    columns[sb] = col
            columns = _merged(columns)
            count = len(set(columns.values()))
            # as many classes as assignments that matter: G would only pass its inputs on
            if not 2 ** (width - 1) < count <= 2 ** width or count == len(columns):
                continue
            sp, cost = _shared_split(spec, bound, free, local, rest, columns, width)
            found.append(((-len(local), len(free), size) if width == 1 else (cost, -len(local), size), sp))
    found.sort(key=lambda f: f[0])
    if width == 1:
        return [f[1] for f in found[:MAX_SHARED_SPLITS]]
    # two signals: the splits with the smallest H (at least two free inputs) first, a stage of a cascade that
    # a template may cover; then the cheapest ones
    # (a partial spec gets only these, so no input limit there: the rest of a long cascade is a partial spec)
    small = sorted(found if n <= MAX_CASCADE_INPUTS or spec.partial else [],
                   key=lambda f: (len(f[1].free) < 2, len(f[1].free), f[0]))
    out: list[SharedSplit] = []
    for f in small[:MAX_WIDE_SPLITS] + ([] if spec.partial else found[:MAX_WIDE_SPLITS]):
        if f[1] not in out:
            out.append(f[1])
    return out


def _entry(spec: Spec, combo, outs) -> tuple[bool, ...] | None:
    """The outputs `outs` of a combination, None when it does not matter (partial spec)."""
    row = spec.table.get(combo)
    return None if row is None else tuple(row[j] for j in outs)


def _merged(columns: dict) -> dict:
    """Columns of a partial spec (None: does not matter) grouped into compatible classes (greedy, the most
    specified columns first); every assignment maps to its class's merged column. A full spec's columns
    stay as they are."""
    classes: list[list] = []
    owner = {}
    for sb in sorted(columns, key=lambda sb: (-sum(e is not None for e in columns[sb]), sb)):
        col = columns[sb]
        for k, cls in enumerate(classes):
            if all(a is None or b is None or a == b for a, b in zip(col, cls)):
                classes[k] = [a if a is not None else b for a, b in zip(cls, col)]
                owner[sb] = k
                break
        else:
            owner[sb] = len(classes)
            classes.append(list(col))
    return {sb: tuple(classes[k]) for sb, k in owner.items()}


def _combo(n: int, bound, sb, free, fb) -> tuple[bool, ...]:
    x = [False] * n
    for i, v in zip(bound, sb):
        x[i] = v
    for i, v in zip(free, fb):
        x[i] = v
    return tuple(x)


# ---------------------------------------------------------------------- Shannon expansion into a multiplexer
@dataclass(frozen=True)
class ShannonSplit:
    """f = mux2(s, f|s=0, f|s=1): the select input s drives the select lever of a 2:1 multiplexer template
    directly (its select input cannot take a line), the cofactors G0 and G1 drive its data inputs. Inputs of
    both cofactors (`common`, at most MAX_COMMON) have one lever, its line tapped for the other part. An 8:1
    multiplexer: two 4:1 multiplexers (each again two 2:1 multiplexers) and one 2:1 multiplexer."""
    select: int
    low: tuple[int, ...]  # spec inputs of G0 = f|s=0 (its support), spec order
    high: tuple[int, ...]  # spec inputs of G1 = f|s=1
    g0: Spec
    g1: Spec

    @property
    def common(self) -> tuple[int, ...]:
        return tuple(i for i in self.low if i in self.high)

    def describe(self, names: list[str]) -> str:
        lo, hi = (", ".join(names[i] for i in part) for part in (self.low, self.high))
        return f"Multiplexer mit Auswahl {names[self.select]}: g0({lo}), g1({hi})"


MUX_TEMPLATE = "mux2-comparator-select"  # inputs s, a, b: y = b if s else a; s may take a tapped line
MAX_SHANNON_SPLITS = 2
SHANNON_LOW = 3  # working G0 → multiplexer joints kept per G0 design
# a tapped select lever of the multiplexer feeds a comparator's side input, which must be as strong as the data
# signal behind it: dust fed by a repeater first
SHANNON_TAP_MODES = ("repeater+dust", "dust", "repeater")


def _cofactor(spec: Spec, out: int, s: int, value: bool) -> tuple[tuple[int, ...], Spec]:
    """f with input s fixed, over the inputs it still depends on (spec order)."""
    n = len(spec.inputs)
    others = [i for i in range(n) if i != s]
    table = {}
    for combo in itertools.product([False, True], repeat=n - 1):
        x = dict(zip(others, combo)) | {s: value}
        table[combo] = (spec.table[tuple(x[i] for i in range(n))][out],)
    full = Spec([spec.inputs[i] for i in others], [spec.outputs[out]], table, source="Zerlegung")
    keep = tuple(others[k] for k in support(full, 0))
    proj = _project(full, [others.index(i) for i in keep], [0])
    return keep, replace(proj, source="Zerlegung")


def shannon_splits(spec: Spec, out: int = 0) -> list[ShannonSplit]:
    """Shannon expansions of a full single-output spec whose cofactors each depend on at least two inputs and
    share at most MAX_COMMON of them; the smallest larger cofactor first, then fewer common inputs."""
    n = len(spec.inputs)
    if spec.partial or n < 4 or len(spec.outputs) != 1 or len(support(spec, out)) != n:
        return []
    found = []
    for s in range(n):
        (low, g0), (high, g1) = _cofactor(spec, out, s, False), _cofactor(spec, out, s, True)
        if len(low) < 2 or len(high) < 2:
            continue  # a constant or a single input: not worth a multiplexer
        sp = ShannonSplit(s, low, high, g0, g1)
        if len(sp.common) <= MAX_COMMON:
            found.append(((max(len(low), len(high)), len(sp.common), s), sp))
    found.sort(key=lambda f: f[0])
    return [f[1] for f in found[:MAX_SHANNON_SPLITS]]


def _chain_spec(n: int, fn, output: str) -> Spec:
    """The spec of a composite with n separate levers computing fn(combo); wide ones only on a sample of
    APART_SAMPLE combinations (all off, every single lever, the rest drawn with a fixed seed), like `_apart`."""
    import random

    if 2 ** n <= APART_SAMPLE:
        combos = list(itertools.product([False, True], repeat=n))
    else:
        rng = random.Random(0)
        picked = {(False,) * n} | {tuple(k == j for k in range(n)) for j in range(n)}
        while len(picked) < APART_SAMPLE:
            picked.add(tuple(rng.random() < 0.5 for _ in range(n)))
        combos = sorted(picked)
    table = {x: (fn(x),) for x in combos}
    return Spec([f"i{k}" for k in range(n)], [output], table, source="Zerlegung",
                care=None if len(table) == 2 ** n else set(table))


def _shannon(spec: Spec, sps: list[ShannonSplit], depth: int, log: list[str] | None,
             driven: bool) -> list[Candidate]:
    """Candidates from `shannon_splits`: G0 → data input a of the multiplexer template (`compose.chains`),
    then G1 → its data input b, then the common levers of G0 fed from G1's (`_tapped`). Each joint is checked
    with separate levers before the next one is made."""
    from .compose import chains
    from .evaluate import evaluate_any
    from .search import template_candidates
    from .templates import TEMPLATES

    mux_t = next(t for t in TEMPLATES if t.name == MUX_TEMPLATE)
    mux = mux_t.build()

    def parts(sub: Spec, drv: bool) -> list[Candidate]:
        # a 2:1 multiplexer as a part is the select-drivable template first: its select lever is tapped for
        # the other part here, and in a larger expansion the lever that stays may be tapped again; then the
        # fewest blocks first (a cascade of small parts has much air in its box, but shrinks when compacted)
        return (template_candidates(sub, [mux_t])
                + sorted(_best(sub, depth, drv), key=lambda c: c.block_count))

    out = []
    for sp in sps:
        if driven and (sp.select == 0 or 0 in sp.common):
            continue  # the select lever and a tapped lever cannot take a line from another part
        g0s, g1s = parts(sp.g0, driven and 0 in sp.low), parts(sp.g1, driven and 0 in sp.high)
        nl, nh = len(sp.low), len(sp.high)
        g0t, g1t = sp.g0.table, sp.g1.table
        # stage 1: inputs low…, s, b
        low_spec = _chain_spec(nl + 2, lambda x: x[nl + 1] if x[nl] else g0t[x[:nl]][0], "y")
        # stage 2: inputs high…, low…, s
        both_spec = _chain_spec(nh + nl + 1, lambda x: (g1t[x[:nh]][0] if x[nh + nl]
                                                         else g0t[x[nh:nh + nl]][0]), "y")
        lows: list[Candidate] = []
        for g0 in g0s:
            kept = 0
            for k, (_, c) in enumerate(chains(g0, 0, mux, 1)):
                if kept >= SHANNON_LOW or k >= CHAINS_SEEN:
                    break
                if evaluate_any(c, low_spec, quick=True).correct:
                    lows.append(c)
                    kept += 1
        labels = list(sp.high) + list(sp.low) + [sp.select]
        found = None
        for g1, low in itertools.product(g1s, lows):  # in the order of the parts (see `parts`)
            tries = 0
            for k, (_, chained) in enumerate(chains(g1, 0, low, nl + 1)):
                if tries >= TRIES or k >= CHAINS_SEEN:
                    break
                if not evaluate_any(chained, both_spec, quick=True).correct:
                    continue
                tries += 1
                for cand in _tapped(chained, labels, sp.common, SHANNON_TAP_MODES):
                    cand = replace(cand, name=f"mux2({spec.inputs[sp.select]}; {_g0_name(low)}, {g1.name})",
                                   origin=f"zerlegt: {sp.describe(spec.inputs)}; {cand.origin}")
                    if evaluate_any(cand, spec, quick=True).correct:
                        found = cand
                        break
                if found is not None:
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


def _g0_name(low: Candidate) -> str:
    """Name of G0 in a stage-1 composition "G0 → mux2-comparator"."""
    return low.name.rsplit(" → ", 1)[0]


def _column_key(col) -> tuple:
    """Sort key of a column whose entries may be None (does not matter in a partial spec)."""
    return tuple((e is not None, e or ()) for e in col)


def _shared_split(spec: Spec, bound, free, local, rest, columns, width: int) -> tuple[SharedSplit, int]:
    """The split for one bound set and its cost (terms of G and H; 0 for one signal, nothing to choose) with
    the cheapest code for the columns (the column of the all-off assignment gets code 0, so the signals rest
    off when all levers are off)."""
    from .synth import minimize_multi, minimize_partial

    n = len(spec.inputs)
    # bound assignments without any combination that matters are missing from `columns` (G does not care)
    zero = columns.get((False,) * len(bound), min(columns.values(), key=_column_key))
    others = sorted(set(columns.values()) - {zero}, key=_column_key)
    codes = list(itertools.product([False, True], repeat=width))
    names = ["g"] if width == 1 else [f"g{k}" for k in range(width)]
    best = None
    for perm in itertools.permutations(codes[1:], len(others)):
        if width == 2 and len(others) == 3 and perm[0] > perm[1]:
            continue  # all four codes used: swapping g0 and g1 gives the same parts
        code = {zero: codes[0]} | dict(zip(others, perm))
        g_table = {}
        for sb, col in columns.items():
            row = next(r for fb in itertools.product([False, True], repeat=len(free))
                       if (r := spec.table.get(_combo(n, bound, sb, free, fb))) is not None)
            g_table[sb] = (*code[col], *(row[j] for j in local))
        h_table = {}
        for col, c in code.items():
            for k, fb in enumerate(itertools.product([False, True], repeat=len(free))):
                if col[k] is not None:
                    h_table[(*c, *fb)] = col[k]
        full = len(h_table) == 2 ** (width + len(free))
        g = Spec([spec.inputs[i] for i in bound], names + [spec.outputs[j] for j in local], g_table,
                 source="Zerlegung", care=None if len(g_table) == 2 ** len(bound) else set(g_table))
        h = Spec(names + [spec.inputs[i] for i in free], [spec.outputs[j] for j in rest], h_table,
                 source="Zerlegung", care=None if full else set(h_table))
        if width == 1:
            return SharedSplit(bound, free, local, rest, g, h, width), 0
        g_ones = [[c for c, v in g.table.items() if v[j]] for j in range(len(g.outputs))]
        if g.partial:
            cost = sum(len(minimize_partial(len(g.inputs), g_ones[j], [c for c, v in g.table.items() if not v[j]]))
                       for j in range(len(g.outputs)))
        else:
            cost = sum(len(t) for t in minimize_multi(len(g.inputs), g_ones))
        for j in range(len(h.outputs)):
            ones = [c for c, v in h.table.items() if v[j]]
            cost += len(minimize_partial(len(h.inputs), ones, [c for c, v in h.table.items() if not v[j]]))
        if best is None or cost < best[0]:
            best = (cost, g, h)
    return SharedSplit(bound, free, local, rest, best[1], best[2], width), best[0]


def shared(spec: Spec, depth: int = 3, log: list[str] | None = None, driven: bool = False) -> list[Candidate]:
    """Working candidates for a multi-output spec built from `shared_splits`: G's signals drive H's first
    inputs (the first over `compose.chains`, a second over a line inside the result, `compose.wire`); G's
    other outputs stay outputs. Inputs and outputs in spec order. Splits with two signals only when none with
    one works."""
    # a partial spec is the H of a split with two signals (a stage of a cascade): only two signals again,
    # one signal there merges G's signals and the free inputs into a PLA that is never smaller
    out = [] if spec.partial else _shared(spec, shared_splits(spec), depth, log, driven)
    if not out:
        out = _shared(spec, shared_splits(spec, width=2), depth, log, driven)
    if not out and not spec.partial:
        out = _shared_common(spec, shared_common_splits(spec), depth, log, driven)
    return out


WIRE_MODES = [(o, i) for o in ("stone", "repeater", "dust", "top") for i in ("repeater", "dust")]


def _second_lines(cand: Candidate, source, target):
    """Every way to lay a line from the lamp `source` to the lever `target` (`compose.wire`); the simulation
    decides which one works (a lamp lit from above needs "stone", a wall lever mostly a repeater)."""
    from .compose import wire

    for out_mode, in_mode in WIRE_MODES:
        c = wire(cand, source, target, out_mode, in_mode)
        if c is not None:
            yield c


def _shared(spec: Spec, sps: list[SharedSplit], depth: int, log: list[str] | None,
            driven: bool) -> list[Candidate]:
    from .compose import chains
    from .evaluate import evaluate_any

    out = []
    for sp in sps:
        gs, hs = _best(sp.g, depth, driven and 0 in sp.bound), _best(sp.h, depth, True) + _drivable_pla(sp.h)
        found = None
        for gc, hc in _pairs(gs, hs):
            tries = 0
            for _, chained in chains(gc, 0, hc, 0):
                tries += 1
                if tries > TRIES:
                    break
                # two signals: G's second one (the first output after H's) to H's second input
                ways = ([chained] if sp.width == 1 else
                        _second_lines(chained, chained.outputs[len(sp.rest)], chained.inputs[len(sp.bound)]))
                for cand in ways:
                    # composite: inputs bound (G order) + free (H order); outputs rest (H order) + local (G order)
                    ins = [None] * len(spec.inputs)
                    for pos, i in zip(cand.inputs, list(sp.bound) + list(sp.free)):
                        ins[i] = pos
                    outs = [None] * len(spec.outputs)
                    for pos, j in zip(cand.outputs, list(sp.rest) + list(sp.local)):
                        outs[j] = pos
                    cand = replace(cand, inputs=ins, outputs=outs, name=f"{gc.name} → {hc.name}",
                                   origin=f"zerlegt: {sp.describe(spec)}; {cand.origin}")
                    if evaluate_any(cand, spec, quick=True).correct:
                        found = cand
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if log is not None:
            from .report import COMPOSE_PREFIX

            what = "gemeinsamem Teil" if sp.width == 1 else f"{sp.width} gemeinsamen Signalen"
            log.append(f"{COMPOSE_PREFIX}Zerlegung mit {what} {sp.describe(spec)}: "
                       + (f"{found.name}, {found.block_count} Blöcke" if found
                          else "keine funktionierende Verbindung gefunden"))
        if found is not None:
            out.append(found)
    return out


# ---------------------------------------------------------------------- shared signal with common inputs
@dataclass(frozen=True)
class SharedCommonSplit:
    """Several outputs through one shared signal g, with common inputs C in both parts (one lever, its line
    tapped for H, as `CommonSplit`): G computes g and the outputs that depend on C ∪ S only (`local`) from
    C ∪ S, H the other outputs (`rest`) from g and C ∪ F. It exists when, for every assignment of C, the rest
    outputs over S × F have at most two distinct columns. An adder/subtractor: C = the operation, which every
    bit needs, g = the carry of the low bit."""
    bound: tuple[int, ...]  # S
    common: tuple[int, ...]  # C
    free: tuple[int, ...]  # F
    local: tuple[int, ...]  # spec output indices computed by G
    rest: tuple[int, ...]  # spec output indices computed by H
    g: Spec  # inputs = C ∪ S in spec order, outputs = ["g"] + local
    h: Spec  # inputs = ["g"] + C ∪ F in spec order, outputs = rest

    def describe(self, spec: Spec) -> str:
        names, outs = spec.inputs, spec.outputs
        gi = ", ".join(names[i] for i in sorted(self.bound + self.common))
        hi = ", ".join(names[i] for i in sorted(self.common + self.free))
        local = "".join(f", {outs[j]}" for j in self.local)
        return (f"g{local} aus ({gi}), {', '.join(outs[j] for j in self.rest)} aus (g, {hi}) "
                f"mit gemeinsamen {', '.join(names[i] for i in self.common)}")


MAX_SHARED_COMMON_SPLITS = 2


def shared_common_splits(spec: Spec) -> list[SharedCommonSplit]:
    """Decompositions of a full multi-output spec with one shared signal and 1 to MAX_COMMON common inputs
    (`SharedCommonSplit`); like `shared_splits(width=1)` many local outputs and a small F first, then fewer
    common inputs. In every slice of C the column of S all off gets g = 0 or 1, whichever needs fewer terms
    in G and H (only the slice of C all off must keep g = 0, so that g rests off with all levers off)."""
    n, m = len(spec.inputs), len(spec.outputs)
    if m < 2 or n < 4 or spec.partial:
        return []
    supports = [set(support(spec, j)) for j in range(m)]
    used = set().union(*supports)
    combos = list(itertools.product([False, True], repeat=n))
    rows = [spec.table[c] for c in combos]
    found = []
    for k in range(1, MAX_COMMON + 1):
        for common in itertools.combinations(sorted(used), k):
            others = [i for i in range(n) if i not in common]
            for size in range(2, len(others)):
                for bound in itertools.combinations(others, size):
                    if not set(bound) <= used:
                        continue  # a dead lever
                    free = tuple(i for i in others if i not in bound)
                    gin = set(common) | set(bound)
                    local = tuple(j for j in range(m) if supports[j] and supports[j] <= gin)
                    rest = tuple(j for j in range(m) if j not in local)
                    if not rest or any(not supports[j] for j in rest) or any(not supports[j] & set(free) for j in rest):
                        continue  # H would only pass g on
                    slices = _common_slices(n, rows, common, bound, free, rest)
                    if slices is None:
                        continue
                    found.append(((-len(local), len(free), k, size), common, bound, free, local, rest, slices))
    found.sort(key=lambda f: f[0])
    out = []
    for _, common, bound, free, local, rest, slices in found:
        sp = _shared_common_split(spec, common, bound, free, local, rest, slices)
        if sp is not None:
            out.append(sp)
        if len(out) >= MAX_SHARED_COMMON_SPLITS:
            break
    return out


def _common_slices(n: int, rows, common, bound, free, rest) -> list[list[tuple]] | None:
    """Per assignment of C the columns (rest outputs over F) of every assignment of S; None when a slice has
    more than two distinct columns or no slice has two (g would be constant)."""
    perm = _perm(n, tuple(common) + tuple(bound))
    nb, w = 2 ** len(bound), 2 ** len(free)
    slices, two = [], False
    for c in range(2 ** len(common)):
        cols = []
        for s in range(nb):
            base = (c * nb + s) * w
            cols.append(tuple(tuple(rows[perm[base + f]][j] for j in rest) for f in range(w)))
        distinct = len(set(cols))
        if distinct > 2:
            return None
        two |= distinct == 2
        slices.append(cols)
    return slices if two else None


def _shared_common_split(spec: Spec, common, bound, free, local, rest, slices) -> SharedCommonSplit | None:
    from .synth import minimize_partial

    n = len(spec.inputs)
    gi, hi = sorted(common + bound), sorted(common + free)
    names = spec.inputs
    cbits_all = list(itertools.product([False, True], repeat=len(common)))
    best = None
    # flip[c]: in slice c, the column of S all off gets g = 1 (never in the slice of C all off)
    for flips in itertools.product([False, True], repeat=len(cbits_all) - 1):
        flip = (False, *flips)
        g_table, h_table = {}, {}
        for c, cbits in enumerate(cbits_all):
            cols = slices[c]
            zero = cols[0]
            other = next((col for col in cols if col != zero), zero)
            low, high = (other, zero) if flip[c] else (zero, other)
            for s, sbits in enumerate(itertools.product([False, True], repeat=len(bound))):
                x = dict(zip(common, cbits)) | dict(zip(bound, sbits))
                full = [False] * n
                for i, v in x.items():
                    full[i] = v
                row = spec.table[tuple(full)]
                g_table[tuple(x[i] for i in gi)] = (cols[s] == high and high != low, *(row[j] for j in local))
            for gv in (False, True):
                col = high if gv else low
                for f, fbits in enumerate(itertools.product([False, True], repeat=len(free))):
                    x = dict(zip(common, cbits)) | dict(zip(free, fbits))
                    h_table[(gv, *(x[i] for i in hi))] = col[f]
        g = Spec([names[i] for i in gi], ["g"] + [spec.outputs[j] for j in local], g_table, source="Zerlegung")
        h = Spec(["g"] + [names[i] for i in hi], [spec.outputs[j] for j in rest], h_table, source="Zerlegung")
        cost = 0
        for part in (g, h):
            for j in range(len(part.outputs)):
                ones = [c for c, v in part.table.items() if v[j]]
                cost += len(minimize_partial(len(part.inputs), ones, [c for c, v in part.table.items() if not v[j]]))
        if best is None or cost < best[0]:
            best = (cost, g, h)
    _, g, h = best
    g_sup = set().union(*(support(g, j) for j in range(len(g.outputs))))
    h_sup = set().union(*(support(h, j) for j in range(len(h.outputs))))
    if not {gi.index(i) for i in bound + common} <= g_sup or not {1 + hi.index(i) for i in common} <= h_sup:
        return None  # an input of S or C changes nothing in G, or one of C nothing in H: a dead lever
    return SharedCommonSplit(tuple(bound), tuple(common), tuple(free), local, rest, g, h)


def _shared_common(spec: Spec, sps: list[SharedCommonSplit], depth: int, log: list[str] | None,
                   driven: bool) -> list[Candidate]:
    """Candidates from `shared_common_splits`: g drives H's first input (`compose.chains`), the chain is
    checked with H's common levers still separate (`_apart`), then their lines are fed from G's levers
    (`_tapped`). Inputs and outputs in spec order."""
    from .compose import chains
    from .evaluate import evaluate_any

    out = []
    for sp in sps:
        if driven and 0 in sp.common:
            continue  # a tapped lever cannot take a line from another part
        gi, hi = sorted(sp.common + sp.bound), sorted(sp.common + sp.free)
        gs = _best(sp.g, depth, driven and 0 in gi)
        hs = _best(sp.h, depth, True) + _drivable_pla(sp.h)
        apart = _apart(sp, gi, hi)
        found, seen, tried = None, 0, 0
        for gc, hc in _pairs(gs, hs):
            tries = 0
            for k, (_, chained) in enumerate(chains(gc, 0, hc, 0)):
                if tries >= TRIES or k >= CHAINS_SEEN:
                    break
                seen += 1
                if not evaluate_any(chained, apart, quick=True).correct:
                    continue
                tries += 1
                for cand in _tapped(chained, gi + hi, sp.common):
                    tried += 1
                    outs = [None] * len(spec.outputs)
                    for pos, j in zip(cand.outputs, list(sp.rest) + list(sp.local)):
                        outs[j] = pos
                    cand = replace(cand, outputs=outs, name=f"{gc.name} → {hc.name}",
                                   origin=f"zerlegt: {sp.describe(spec)}; {cand.origin}")
                    if evaluate_any(cand, spec, quick=True).correct:
                        found = cand
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if log is not None:
            from .report import COMPOSE_PREFIX

            log.append(f"{COMPOSE_PREFIX}Zerlegung mit gemeinsamem Teil {sp.describe(spec)}: "
                       + (f"{found.name}, {found.block_count} Blöcke" if found
                          else "keine funktionierende Verbindung gefunden")
                       + f" ({seen} Verbindungen, {tried} angezapft geprüft)")
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
            if flipped in spec.table and row[out] != spec.table[flipped][out]:
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
