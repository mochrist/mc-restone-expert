"""Generic synthesis of any truth table as a torch PLA (sum of products).

Layout (x east, y up, z south); n inputs, T product terms in total:

    y=3  literal rails along x (dust on blocks at y=2). Input i: lever at x=0 on the true rail's row;
         the inverted rail (only if needed) starts at x=0 two rows further south, fed by a wall torch on
         the lever's support block and a block above that torch.
    y=2  rail supports. A wall torch on the south side of a rail support, at a term column, is a crossing:
         it is on while the rail is off.
    y=1  one collector per term along z (dust on blocks at y=0), right below the crossing torches:
         collector = OR(NOT rails) = NAND(literals). It ends in a block with a wall torch:
         term = AND(literals).
    y=1  the term torches of one output feed an output line along x; the output lamp is the support block
         of that line (dust powers the block below). Lines of different outputs are separated by air.

Rows: every rail takes two z rows (rail, crossing torches). Columns: every term takes two x columns.
Limits: rails must reach all columns (T <= 7) and collectors must be <= 15 long (n <= 4).

The circuit is correct by construction only on paper; like every candidate it is accepted only after the
simulation in `evaluate` confirms it.
"""

from __future__ import annotations

import itertools

from ..model import Grid, Pos
from .candidate import Candidate
from .spec import Spec

Implicant = tuple[bool | None, ...]  # per input: True = literal x, False = literal not x, None = unused

MAX_TERMS = 7
MAX_INPUTS = 4


# ---------------------------------------------------------------------- logic minimisation
def _combine(a: Implicant, b: Implicant) -> Implicant | None:
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) != 1 or a[diff[0]] is None or b[diff[0]] is None:
        return None
    return tuple(None if i == diff[0] else x for i, x in enumerate(a))


def _covers(imp: Implicant, combo: tuple[bool, ...]) -> bool:
    return all(v is None or v == c for v, c in zip(imp, combo))


def minimize(n: int, ones: list[tuple[bool, ...]]) -> list[Implicant]:
    """Quine-McCluskey prime implicants plus a greedy cover (essential primes first)."""
    if not ones:
        return []
    current = {tuple(c) for c in ones}
    primes: set[Implicant] = set()
    while current:
        nxt, used = set(), set()
        for a, b in itertools.combinations(sorted(current, key=str), 2):
            c = _combine(a, b)
            if c is not None:
                nxt.add(c)
                used |= {a, b}
        primes |= current - used
        current = nxt
    remaining = set(map(tuple, ones))
    chosen: list[Implicant] = []
    for m in sorted(remaining):
        covering = [p for p in primes if _covers(p, m)]
        if len(covering) == 1 and covering[0] not in chosen:
            chosen.append(covering[0])
    for p in chosen:
        remaining -= {m for m in remaining if _covers(p, m)}
    while remaining:
        best = max(sorted(primes, key=str), key=lambda p: (sum(_covers(p, m) for m in remaining),
                                                           sum(v is None for v in p)))
        chosen.append(best)
        remaining -= {m for m in remaining if _covers(best, m)}
    return chosen


# ---------------------------------------------------------------------- layout
_RAIL = "redstone_wire[east=side,north=none,power=0,south=none,west=side]"
_COLLECTOR = "redstone_wire[east=none,north=side,power=0,south=side,west=none]"


def pla(spec: Spec, name: str = "pla") -> Candidate | None:
    """Build the PLA for the spec, or None if it exceeds the layout limits."""
    n, m = len(spec.inputs), len(spec.outputs)
    if n > MAX_INPUTS:
        return None
    combos = list(itertools.product([False, True], repeat=n))
    terms: list[list[Implicant]] = [minimize(n, [c for c in combos if spec.table[c][j]]) for j in range(m)]
    total = sum(max(len(t), 1) for t in terms)
    if total > MAX_TERMS:
        return None

    # rails: z rows per input
    rail_z: dict[tuple[int, bool], int] = {}
    z = 0
    lever_z = []
    for i in range(n):
        lever_z.append(z)
        rail_z[(i, True)] = z
        z += 2
        if any(imp[i] is False for ts in terms for imp in ts):
            rail_z[(i, False)] = z
            z += 2
    z_end = max(z, 2)  # collector runs over z in [0, z_end)
    width = 2 * total + 1
    size = (width, 4, z_end + 3)
    g = Grid(size)

    def put(x, y, zz, state):
        g[x, y, zz] = state

    # inputs and rails
    inputs = []
    for i in range(n):
        lz = rail_z[(i, True)]
        put(0, 2, lz, "stone")
        put(0, 3, lz, "lever[face=floor,facing=east,powered=false]")
        inputs.append(Pos(0, 3, lz))
        used_true = any(imp[i] is True for ts in terms for imp in ts)
        if used_true:
            for x in range(1, width):
                put(x, 2, lz, "stone")
                put(x, 3, lz, _RAIL)
        if (i, False) in rail_z:
            cz = rail_z[(i, False)]
            put(0, 2, lz + 1, "redstone_wall_torch[facing=south,lit=true]")
            put(0, 3, lz + 1, "stone")
            for x in range(0, width):
                put(x, 2, cz, "stone")
                put(x, 3, cz, _RAIL)

    # term columns
    outputs = []
    col = 0
    out_z = z_end + 2
    for j in range(m):
        first_x = 2 + 2 * col
        imps = terms[j]
        if not imps:  # constant off: a lone lamp
            put(first_x, 0, out_z, "redstone_lamp[lit=false]")
            outputs.append(Pos(first_x, 0, out_z))
            col += 1
            continue
        for k, imp in enumerate(imps):
            x = 2 + 2 * col
            for zz in range(z_end):
                put(x, 0, zz, "stone")
                put(x, 1, zz, _COLLECTOR)
            for i, v in enumerate(imp):
                if v is not None:
                    put(x, 2, rail_z[(i, v)] + 1, "redstone_wall_torch[facing=south,lit=true]")
            put(x, 1, z_end, "stone")
            put(x, 1, z_end + 1, "redstone_wall_torch[facing=south,lit=true]")
            last = k == len(imps) - 1
            for xx in range(x, x + (1 if last else 2)):
                put(xx, 0, out_z, "stone")
                put(xx, 1, out_z, _RAIL)
            col += 1
        put(first_x, 0, out_z, "redstone_lamp[lit=false]")
        outputs.append(Pos(first_x, 0, out_z))

    desc = "; ".join(f"{o} = " + (" ∨ ".join(_term_text(spec.inputs, t) for t in ts) if ts else "aus")
                     for o, ts in zip(spec.outputs, terms))
    cand = Candidate(name, g, inputs, outputs,
                     description=f"Fackel-PLA (Summe von Produkten): {desc}. Je Term eine Spalte mit "
                                 f"Wandfackeln an den Leitungen; Sammelleitung und Term-Fackel bilden das AND.",
                     origin="synthese:pla")
    from .compact import crop, normalize

    return normalize(crop(cand))


def _term_text(names: list[str], imp: Implicant) -> str:
    lits = [n if v else f"¬{n}" for n, v in zip(names, imp) if v is not None]
    return "(" + " ∧ ".join(lits) + ")" if lits else "1"
