"""Generic synthesis of any truth table as a torch PLA (sum of products, NAND-NOR style).

Layout (x east, y up, z south). Term k is column x = 2k; rows along z hold the input rails.

AND plane (rows 0 .. z_end-1):
    y=3  literal rails along x (dust on blocks at y=2). Rails take every other row; the rows between are
         slot rows. The lever of input i stands in the row of its true rail, near the middle of the
         columns that use the input. The inverted rail follows two rows further south, fed by a wall
         torch on the lever's support block (in the slot row) and a block above that torch. If only the
         inverted rail is used, the lever has its own row and the inverted rail is the next row; the
         block above the inverter torch then sits in the rail itself.
    y=2  rail supports. A wall torch on the north or south side of a rail support, at a term column,
         is a crossing: it is on while the rail is off. Both neighbouring slot rows of a rail can take
         its crossings, so a and not a share one slot row.
    y=1  one collector per term along z (dust on blocks at y=0), right below the crossing torches:
         collector = OR(NOT literals) = NAND(literals). It ends in a block at z = z_end.

OR plane (rows z_end+1, z_end+3, ...; one output line per output, several lines per row if they do not
overlap in x):
    row z_end+1: wall torches on the east or west side of the collector's end block are on while the
         collector is off, i.e. they carry the term; each feeds the output line (dust at y=1 on blocks at
         y=0) south of it. A term shared by two outputs can use both sides.
         At an end of a line the torch may instead hang on the south side of the end block, in the line
         itself (saves a column; a line of only that torch lights the lamp right below it).
    deeper rows: the collector climbs onto its end block and runs on at y=3 along z (dust on blocks at
         y=2); wall torches on the sides of those blocks feed the output lines below them (y=1).
    The output lamp is the support block of one dust of its line.
Torches are diodes, so a term column can feed any number of output lines without connecting them.

Signal strength: rails, collectors and output lines get repeaters where 15 blocks of dust are not
enough. Each repeater adds 2 gt for the literals or terms behind it; levers sit in the middle of their
rails so that up to 14 columns need none.

The circuit is correct by construction only on paper; like every candidate it is accepted only after the
simulation in `evaluate` confirms it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from ..model import Grid, Pos
from .candidate import Candidate
from .spec import Spec

Implicant = tuple[bool | None, ...]  # per input: True = literal x, False = literal not x, None = unused

MAX_INPUTS = 6  # same limit as the full truth table of the analysis; 5-6 inputs give large PLAs (400-2500 blocks)
MAX_PARTIAL_INPUTS = 16  # partial specs (most combinations "egal") have few, short terms
MAX_ORDERS = 24  # output orders tried per term selection (all of them for up to 4 outputs)


# ---------------------------------------------------------------------- logic minimisation
def _combine(a: Implicant, b: Implicant) -> Implicant | None:
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) != 1 or a[diff[0]] is None or b[diff[0]] is None:
        return None
    return tuple(None if i == diff[0] else x for i, x in enumerate(a))


def _covers(imp: Implicant, combo: tuple[bool, ...]) -> bool:
    return all(v is None or v == c for v, c in zip(imp, combo))


def _primes(ones) -> set[Implicant]:
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
    return primes


def _size(p: Implicant) -> int:
    return sum(v is None for v in p)


def minimize(n: int, ones: list[tuple[bool, ...]]) -> list[Implicant]:
    """Quine-McCluskey prime implicants plus a greedy cover (essential primes first)."""
    if not ones:
        return []
    primes = _primes(ones)
    remaining = set(map(tuple, ones))
    chosen: list[Implicant] = []
    for m in sorted(remaining):
        covering = [p for p in primes if _covers(p, m)]
        if len(covering) == 1 and covering[0] not in chosen:
            chosen.append(covering[0])
    for p in chosen:
        remaining -= {m for m in remaining if _covers(p, m)}
    while remaining:
        best = max(sorted(primes, key=str), key=lambda p: (sum(_covers(p, m) for m in remaining), _size(p)))
        chosen.append(best)
        remaining -= {m for m in remaining if _covers(best, m)}
    return chosen


def minimize_partial(n: int, ones: list[tuple[bool, ...]], offs: list[tuple[bool, ...]]) -> list[Implicant]:
    """Cover `ones` with terms that cover none of `offs`; every other combination does not matter.

    Espresso-like expand instead of Quine-McCluskey (the don't-cares can be almost all 2^n combinations):
    each still uncovered on-combination is grown by dropping literals, negative ones first (they need an
    inverted rail), as long as no off-combination gets covered."""
    chosen: list[Implicant] = []
    for m in sorted(ones, key=lambda c: (-sum(c), c)):
        if any(_covers(p, m) for p in chosen):
            continue
        imp = list(m)
        for i in sorted(range(n), key=lambda i: (m[i], i)):
            trial = imp[:i] + [None] + imp[i + 1:]
            if not any(_covers(trial, o) for o in offs):
                imp = trial
        chosen.append(tuple(imp))
    # drop terms the others make redundant
    for p in list(chosen):
        rest = [q for q in chosen if q != p]
        if all(any(_covers(q, m) for q in rest) for m in ones if _covers(p, m)):
            chosen = rest
    return chosen


def minimize_multi(n: int, ones: list[list[tuple[bool, ...]]]) -> list[list[Implicant]]:
    """Cover all outputs together, preferring terms that several outputs can use.

    Candidates are the prime implicants of every AND of a set of outputs (multi-output primes). Greedy:
    take the candidate that covers the most still uncovered (output, combination) pairs, then drop uses
    that turned out to be redundant. Returns the implicants per output."""
    m = len(ones)
    sets = [set(map(tuple, o)) for o in ones]
    cands: set[Implicant] = set()
    for r in range(1, m + 1):
        for group in itertools.combinations(range(m), r):
            common = set.intersection(*(sets[j] for j in group))
            if common:
                cands |= _primes(common)
    combos = list(itertools.product([False, True], repeat=n))
    usable = {p: [j for j in range(m) if all(c in sets[j] for c in combos if _covers(p, c))]
              for p in sorted(cands, key=str)}
    remaining = {(j, c) for j in range(m) for c in sets[j]}
    uses: dict[Implicant, set[int]] = {}

    def gain(p):
        return sum(1 for j, c in remaining if j in usable[p] and _covers(p, c))

    while remaining:
        best = max(usable, key=lambda p: (gain(p), p in uses, _size(p)))
        new = {j for j, c in remaining if j in usable[best] and _covers(best, c)}
        uses.setdefault(best, set()).update(new)
        remaining -= {(j, c) for j, c in remaining if j in new and _covers(best, c)}
    # drop redundant uses, smallest terms first
    for p in sorted(uses, key=lambda p: (_size(p), str(p))):
        for j in sorted(uses[p]):
            others = [q for q in uses if q != p and j in uses[q]]
            if all(any(_covers(q, c) for q in others) for c in sets[j] if _covers(p, c)):
                uses[p].discard(j)
    order = sorted((p for p in uses if uses[p]), key=str)
    return [[p for p in order if j in uses[p]] for j in range(m)]


# ---------------------------------------------------------------------- block states
_STONE = "stone"
_DUST_X = "redstone_wire[east=side,north=none,power=0,south=none,west=side]"
_DUST_Z = "redstone_wire[east=none,north=side,power=0,south=side,west=none]"
_LEVER = "lever[face=floor,facing=east,powered=false]"
_WALL_LEVER = "lever[face=wall,facing=west,powered=false]"  # on the west face of the input block (drivable)
_LAMP = "redstone_lamp[lit=false]"


def _torch(facing: str) -> str:
    return f"redstone_wall_torch[facing={facing},lit=true]"


def _repeater(facing: str) -> str:
    return f"repeater[delay=1,facing={facing},locked=false,powered=false]"


# ---------------------------------------------------------------------- signal strength along a line
_REP = 99


def _simulate(length: int, source: int, strength: int, reps: set[int]) -> list[int]:
    """Power of each cell (dust) with a single source injecting `strength` at cell `source`."""
    vals = []
    for i in range(length):
        prev = vals[i - 1] if i else 0
        if i in reps:
            vals.append(_REP if prev == _REP or prev >= 1 else -1)
            continue
        inc = 15 if prev == _REP else max(prev - 1, 0)
        vals.append(max(strength if i == source else 0, inc) if i >= source else 0)
    return vals


def _plan_line(length: int, sources: dict[int, int], need: set[int], allowed: set[int]) -> set[int] | None:
    """Repeaters for a line of `length` cells in flow direction (the power flows from cell 0 on).

    sources: cell -> injected strength; every source alone must power every needed cell behind it.
    allowed: cells where a repeater may replace the dust. Greedy, each repeater as late as possible.
    Returns the repeater cells or None."""
    reps: set[int] = set()

    def ok(upto: int, check_end: bool) -> bool:
        for s, st in sources.items():
            if s >= upto:
                continue
            vals = _simulate(length, s, st, reps)
            if any(vals[i] == -1 for i in range(s, upto)):
                return False
            if any(vals[i] < 1 for i in need if s <= i < upto):
                return False
            if check_end and vals[upto - 1] != _REP and vals[upto - 1] < 1:
                return False
        return True

    cand = sorted(i for i in allowed if 0 < i < length)
    for a, nxt in zip(cand, cand[1:] + [None]):
        if nxt is None:
            if ok(length, False):
                break
        elif ok(nxt, True):
            continue
        if not ok(a, True):
            return None
        reps.add(a)
    return reps if ok(length, False) else None


# ---------------------------------------------------------------------- layout
class _Conflict(Exception):
    pass


@dataclass
class _Col:
    imp: Implicant
    outs: tuple[int, ...]


def _assign_lines(cols: list[_Col], order: list[int], no_south: set[int]) -> tuple[dict, dict] | None:
    """Place the output lines in OR rows.

    A line is a list of torch cells along x: odd x = wall torch on the east/west side of a column, even x
    (first OR row only, at an end of the line) = wall torch on the south side of that column's end block,
    standing in the line itself. Returns ({output: (row, cells)}, {(col, output): (row, cell)})."""
    spans: dict[int, list[tuple[int, int]]] = {}
    lines, conns = {}, {}
    for j in order:
        ks = [k for k, c in enumerate(cols) if j in c.outs]
        if not ks:
            continue
        for q in itertools.count():
            placed = None
            for reverse in (False, True):
                cells, last = [], None
                seq = list(reversed(ks)) if reverse else ks
                for a, k in enumerate(seq):
                    opts = [2 * k + 1, 2 * k - 1] if reverse else [2 * k - 1, 2 * k + 1]
                    if a == 0 and q == 0 and k not in no_south:
                        opts.insert(0, 2 * k)
                    pick = next((c for c in opts if last is None or (c < last if reverse else c > last)), None)
                    if pick is None:
                        break
                    cells.append((k, pick))
                    last = pick
                else:
                    xs = [c for _, c in cells]
                    lo, hi = min(xs), max(xs)
                    if all(hi < a - 1 or b < lo - 1 for a, b in spans.get(q, [])):
                        placed = cells
                        break
            if placed is not None:
                spans.setdefault(q, []).append((min(c for _, c in placed), max(c for _, c in placed)))
                lines[j] = (q, sorted(c for _, c in placed))
                for k, c in placed:
                    conns[(k, j)] = (q, c)
                break
            if q > len(order) + 1:
                return None
    # a south torch sits below the block where a climbing collector continues: not allowed
    climbing = {k for (k, _), (q, _) in conns.items() if q > 0}
    clash = {k for (k, _), (q, c) in conns.items() if q == 0 and c % 2 == 0 and k in climbing}
    if clash:
        return _assign_lines(cols, order, no_south | clash)
    return lines, conns


def _rows(n: int, cols: list[_Col], trail: bool) -> tuple[list, dict]:
    """Row kinds of the AND plane: ('rail', (input, polarity)), ('slot', input or None), ('lever', input).

    Inputs whose levers need a row of their own (only the inverted rail is used, or the input is unused)
    go to the ends, where their lever row needs no separating slot row."""
    groups = {"unused": [], "neg": [], "rest": []}
    for i in range(n):
        t = any(c.imp[i] is True for c in cols)
        f = any(c.imp[i] is False for c in cols)
        if t and f:
            groups["rest"].append([("rail", (i, True)), ("slot", i), ("rail", (i, False))])
        elif t:
            groups["rest"].append([("rail", (i, True))])
        elif f:
            groups["neg"].append([("lever", i), ("rail", (i, False))])
        else:
            groups["unused"].append([("lever", i)])
    neg = groups["neg"]
    if len(neg) >= 2:  # the last one with its lever south of the rail
        neg[-1] = neg[-1][::-1]
    ordered = groups["unused"] + neg[:1] + groups["rest"] + neg[1:]
    rows: list[tuple[str, object]] = []
    for group in ordered:
        if rows and (rows[-1][0] == "rail" or (rows[-1][0] == "lever" and group[0][0] == "rail")):
            rows.append(("slot", None))
        rows.extend(group)
    if trail and rows and rows[-1][0] == "rail":
        rows.append(("slot", None))
    rail_row = {kind[1]: r for r, kind in enumerate(rows) if kind[0] == "rail"}
    return rows, rail_row


def _slot_ok(rows, r: int) -> bool:
    if not 0 <= r < len(rows):
        return False
    kind, what = rows[r]
    if kind == "slot":
        return True
    # the lever row of an input with only the inverted rail takes that rail's crossings
    return kind == "lever" and ("rail", (what, False)) in (rows[r - 1] if r else None,
                                                          rows[r + 1] if r + 1 < len(rows) else None)


def _crossings(rows, rail_row, imp: Implicant) -> dict[tuple[int, bool], int] | None:
    """Slot row per used literal of a term (north or south of its rail), without two in one row."""
    lits = [(i, v) for i, v in enumerate(imp) if v is not None]
    if not lits:
        return {}
    best = None
    for choice in itertools.product((1, -1), repeat=len(lits)):
        slots = [rail_row[lit] + d for lit, d in zip(lits, choice)]
        if len(set(slots)) != len(slots) or not all(_slot_ok(rows, s) for s in slots):
            continue
        if best is None or min(slots) > min(best.values()):
            best = dict(zip(lits, slots))
    return best


def _build(n: int, m: int, cols: list[_Col], order: list[int], trail: bool = False, drivable: bool = False):
    """Place everything; returns (cells, lever positions, lamp positions, delay notes) or None.

    drivable: every input is a wall lever on the west face of an input block P at the west end of its rails
    (see `pla`), so that another part can replace the lever by a repeater facing P."""
    assigned = _assign_lines(cols, order, set())
    if assigned is None:
        return None
    lines, conns = assigned
    rows, rail_row = _rows(n, cols, trail)
    cross = []
    for c in cols:
        x = _crossings(rows, rail_row, c.imp)
        if x is None:
            if not trail:
                return _build(n, m, cols, order, trail=True, drivable=drivable)
            return None
        cross.append(x)
    z_end = len(rows)

    def orow(q: int) -> int:
        return z_end + 1 + 2 * q

    cells: dict[tuple[int, int, int], str] = {}

    def put(x, y, z, s):
        old = cells.get((x, y, z))
        if old is not None and old != s:
            raise _Conflict((x, y, z), old, s)
        cells[(x, y, z)] = s

    # levers and rails
    def drivable_cells(i: int):
        """Input i as wall lever L at x=-3 on block P at x=-2; P carries the true rail (dust from x=-1 on),
        a wall torch on P's side feeds the inverted rail directly (no block above the torch next to the
        input, so a repeater or dust that replaces L sees no feedback). L comes first."""
        t_row = rail_row.get((i, True))
        f_row = rail_row.get((i, False))
        r = t_row if t_row is not None else rows.index(("lever", i))
        out = [(-3, 3, r, _WALL_LEVER), (-2, 3, r, _STONE)]
        for pol, row in ((True, t_row), (False, f_row)):
            if row is None:
                continue
            need_x = {2 * k for k, c in enumerate(cols) if c.imp[i] is pol}
            x0 = -1
            if not pol:
                side = row - 1 if t_row is not None else row  # slot row between the rails / the rail itself
                out.append((-2, 3, side, _torch("south" if side > r else "north")))
                x0 = -2 if t_row is not None else -1
            xs = list(range(x0, max(need_x) + 1))
            idx = {x: a for a, x in enumerate(xs)}
            reps = _plan_line(len(xs), {0: 15}, {idx[x] for x in need_x},
                              {a for a, x in enumerate(xs) if x not in need_x and a > 0})
            if reps is None:
                return None
            for a, x in enumerate(xs):
                out += [(x, 2, row, _STONE), (x, 3, row, _repeater("west") if a in reps else _DUST_X)]
        return out

    def rail_cells(i: int, xc: int):
        """Blocks of input i's lever and rails with the lever at x = xc, or None if out of reach."""
        out = []
        t_row = rail_row.get((i, True))
        f_row = rail_row.get((i, False))
        lever_row = t_row if t_row is not None else rows.index(("lever", i))
        out += [(xc, 2, lever_row, _STONE), (xc, 3, lever_row, _LEVER)]
        for pol, row in ((True, t_row), (False, f_row)):
            if row is None:
                continue
            need_x = {2 * k for k, c in enumerate(cols) if c.imp[i] is pol}
            start = 1  # first dust next to the lever / the block above the inverter torch
            if not pol and t_row is not None:  # inverter in the slot row, dust right next to its block
                out += [(xc, 2, row - 1, _torch("south")), (xc, 3, row - 1, _STONE),
                        (xc, 2, row, _STONE), (xc, 3, row, _DUST_X)]
                start = 0
            elif not pol:  # own lever row north or south of the rail; the block above the inverter is in the rail
                out += [(xc, 2, row, _torch("south" if lever_row < row else "north")), (xc, 3, row, _STONE)]
            for d, facing in ((1, "west"), (-1, "east")):
                far = [x for x in need_x if (x - xc) * d > 0]
                if not far:
                    continue
                end = max(far) if d > 0 else min(far)
                xs = list(range(xc + d * start, end + d, d))
                idx = {x: a for a, x in enumerate(xs)}
                reps = _plan_line(len(xs), {0: 15}, {idx[x] for x in far},
                                  {a for a, x in enumerate(xs) if x not in need_x and x != xc})
                if reps is None:
                    return None
                for a, x in enumerate(xs):
                    out += [(x, 2, row, _STONE), (x, 3, row, _repeater(facing) if a in reps else _DUST_X)]
        return out

    levers = []
    width = 2 * len(cols) - 1
    for i in range(n):
        if drivable:
            got = drivable_cells(i)
            if got is None:
                return None
            for x, y, z, st in got:
                put(x, y, z, st)
            levers.append(got[0][:3])
            continue
        users = [2 * k for k, c in enumerate(cols) if c.imp[i] is not None]
        lo, hi = (min(users), max(users)) if users else (0, width - 1)
        opts = [x for x in range(lo - 1, hi + 2) if x % 2 and -1 <= x <= width] or [1]
        best = None
        for xc in opts:
            got = rail_cells(i, xc)
            if got is None:
                continue
            key = (not 0 < xc < width - 1, sum(s.startswith("repeater") for *_, s in got), len(got),
                   abs(2 * xc - lo - hi))
            if best is None or key < best[0]:
                best = (key, xc, got)
        if best is None:
            return None
        _, xc, got = best
        for x, y, z, st in got:
            put(x, y, z, st)
        levers.append(next((x, y, z) for x, y, z, st in got if st == _LEVER))
    rail_dust = {(x, z) for (x, y, z), st in cells.items() if y == 3 and st == _DUST_X}

    # term columns: crossings, collector, end block, OR plane
    for k, c in enumerate(cols):
        x = 2 * k
        my = {jq: v for jq, v in conns.items() if jq[0] == k}
        qmax = max(q for q, _ in my.values())
        for (i, v), slot in cross[k].items():
            put(x, 2, slot, _torch("south" if slot > rail_row[(i, v)] else "north"))
        put(x, 1, z_end, _STONE)
        tops = sorted(cross[k].values())
        if tops:
            far = orow(qmax) + 1 if qmax else z_end  # collector cells counted up to the farthest target
            # cells along the collector path: rows tops[0] .. z_end-1, then (climb) z_end .. orow(qmax)
            path = list(range(tops[0], far))
            idx = {z: a for a, z in enumerate(path)}
            target = len(path) - 1
            sources = {idx[t]: 15 for t in tops}
            allowed = {idx[z] for z in range(tops[0], z_end - 1) if z not in tops}
            reps = _plan_line(len(path), sources, {target}, allowed)
            if reps is None:
                return None
            for z in range(tops[0], z_end):
                put(x, 0, z, _STONE)
                put(x, 1, z, _repeater("north") if idx[z] in reps else _DUST_Z)
        if qmax:
            if (x, z_end - 1) in rail_dust:  # the climbing dust would connect to the last rail
                return _build(n, m, cols, order, trail=True, drivable=drivable) if not trail else None
            put(x, 2, z_end, _DUST_Z)
            for z in range(z_end + 1, orow(qmax) + 1):
                put(x, 2, z, _STONE)
                put(x, 3, z, _DUST_Z)
        for (q, cell) in my.values():
            facing = "east" if cell > x else "west" if cell < x else "south"
            if q == 0 and cell == x:
                put(cell, 1, z_end + 1, _torch("south"))
            elif q == 0:
                put(cell, 1, z_end, _torch(facing))
            else:
                put(cell, 2, orow(q), _torch(facing))

    # output lines
    lamps: list[tuple[int, int, int] | None] = [None] * m
    for j, (q, tcells) in lines.items():
        z = orow(q)
        lo, hi = tcells[0], tcells[-1]
        south = {c for c in tcells if c % 2 == 0}  # torch in the line: no dust there, 15 next to it
        if tcells == [lo] and south:  # a single south torch lights the lamp below it directly
            lamps[j] = (lo, 0, z)
            put(lo, 0, z, _LAMP)
            continue
        best = None
        for xl in range(lo, hi + 1):
            if xl in south:
                continue
            plan = []
            for d, facing in ((1, "west"), (-1, "east")):
                xs = list(range(lo, xl + 1)) if d > 0 else list(range(hi, xl - 1, -1))
                srcs = {a: 16 if xx in south else 15 for a, xx in enumerate(xs) if xx in tcells}
                reps = _plan_line(len(xs), srcs, {len(xs) - 1},
                                  {a for a, xx in enumerate(xs) if xx not in tcells and xx != xl})
                if reps is None:
                    break
                plan.append((facing, {xs[a] for a in reps}))
            else:
                key = (sum(len(r) for _, r in plan), abs(2 * xl - lo - hi))
                if best is None or key < best[0]:
                    best = (key, xl, plan)
        if best is None:
            return None
        _, xl, plan = best
        rep_at = {xx: f for f, r in plan for xx in r}
        for xx in range(lo, hi + 1):
            if xx in south:
                continue
            put(xx, 0, z, _LAMP if xx == xl else _STONE)
            put(xx, 1, z, _repeater(rep_at[xx]) if xx in rep_at else _DUST_X)
        lamps[j] = (xl, 0, z)
    # constant-off outputs: a lone lamp beside the first OR row
    for j in range(m):
        if lamps[j] is None:
            z = orow(0)
            used = [x for (x, y, zz) in cells if zz in (z - 1, z, z + 1)] or [0]
            x = max(used) + 2
            put(x, 0, z, _LAMP)
            lamps[j] = (x, 0, z)
    return cells, levers, lamps


def _columns(terms: list[list[Implicant]], shared: bool, order: list[int]) -> list[_Col]:
    rank = {j: r for r, j in enumerate(order)}
    if shared:
        users: dict[Implicant, list[int]] = {}
        for j, ts in enumerate(terms):
            for t in ts:
                users.setdefault(t, []).append(j)
        cols = [_Col(t, tuple(sorted(js, key=rank.get))) for t, js in users.items()]
    else:
        cols = [_Col(t, (j,)) for j, ts in enumerate(terms) for t in ts]
    return sorted(cols, key=lambda c: (min(rank[j] for j in c.outs), max(rank[j] for j in c.outs), str(c.imp)))


def _to_candidate(name: str, built, spec: Spec, terms, shared: bool) -> Candidate:
    cells, levers, lamps = built
    lo = [min(p[a] for p in cells) for a in range(3)]
    hi = [max(p[a] for p in cells) for a in range(3)]
    g = Grid(tuple(h - l + 1 for h, l in zip(hi, lo)))
    for p, s in cells.items():
        g[p[0] - lo[0], p[1] - lo[1], p[2] - lo[2]] = s

    def rel(p):
        return Pos(p[0] - lo[0], p[1] - lo[1], p[2] - lo[2])

    desc = "; ".join(f"{o} = " + (" ∨ ".join(_term_text(spec.inputs, t) for t in ts) if ts else "aus")
                     for o, ts in zip(spec.outputs, terms))
    distinct = len({t for ts in terms for t in ts}) if shared else sum(len(ts) for ts in terms)
    text = (f"Fackel-PLA (Summe von Produkten): {desc}. {distinct} Termspalten mit Wandfackeln an den "
            f"Leitungen; Sammelleitung und Term-Fackel bilden das AND, Fackeln an der Sammelleitung "
            f"speisen die Ausgangsleitungen (OR)")
    if shared and distinct < sum(len(ts) for ts in terms):
        text += "; gemeinsame Terme belegen nur eine Spalte"
    if any("repeater" in s for s in cells.values()):
        text += "; Repeater frischen lange Leitungen auf"
    return Candidate(name, g, [rel(p) for p in levers], [rel(p) for p in lamps], description=text + ".",
                     origin="synthese:pla")


def pla(spec: Spec, name: str = "pla", *, share: bool | None = None, drivable: bool = False) -> Candidate | None:
    """Build the smallest torch PLA for the spec over a few layout variants, or None beyond the limits.

    share=None tries layouts with and without shared terms and keeps the smallest (volume, then blocks);
    True/False forces one of them. drivable=True puts every lever at the west end of its rails, as a wall
    lever on an input block that also carries the inverter: the inputs can then be driven by other parts
    (`compose`), at the cost of longer rails."""
    n, m = len(spec.inputs), len(spec.outputs)
    if n > (MAX_PARTIAL_INPUTS if spec.partial else MAX_INPUTS):
        return None
    combos = spec.combos()
    ones = [[c for c in combos if spec.table[c][j]] for j in range(m)]
    if spec.partial:
        selections = [[minimize_partial(n, o, [c for c in combos if not spec.table[c][j]])
                       for j, o in enumerate(ones)]]
    else:
        selections = [[minimize(n, o) for o in ones]]
        multi = minimize_multi(n, ones)
        if multi != selections[0]:
            selections.append(multi)
    best = None
    for terms in selections:
        for shared in ((True, False) if share is None else (share,)):
            for order in itertools.islice(itertools.permutations(range(m)), MAX_ORDERS):
                cols = _columns(terms, shared, list(order))
                try:
                    built = _build(n, m, cols, list(order), drivable=drivable)
                except _Conflict:
                    built = None
                if built is None:
                    continue
                cells = built[0]
                ext = [max(p[a] for p in cells) - min(p[a] for p in cells) + 1 for a in range(3)]
                key = (ext[0] * ext[1] * ext[2], len(cells))
                if best is None or key < best[0]:
                    best = (key, built, terms, shared)
    if best is None:
        return None
    _, built, terms, shared = best
    from .compact import crop, normalize

    return normalize(crop(_to_candidate(name, built, spec, terms, shared)))


def _term_text(names: list[str], imp: Implicant) -> str:
    lits = [n if v else f"¬{n}" for n, v in zip(names, imp) if v is not None]
    return "(" + " ∧ ".join(lits) + ")" if lits else "1"
