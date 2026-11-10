"""Shrink a correct candidate step by step; every step is kept only if the simulation still meets the spec.

Moves (greedy, repeated until nothing helps):
1. cut a whole plane (x = k, y = k or z = k) out of the grid and close the gap,
2. move one part of the design (a half-space of its blocks) by 1 to 3 blocks, so that the bounding box
   gets smaller: parts of a composition move together, or one part slides along the other (partial plane
   cut); equal blocks that land on each other are merged, which shortens straight lines (`shifts`),
3. lay a stretch of dust anew on a shorter way (`lines`, `rerouted`),
4. remove single blocks that are not inputs or outputs (loosely attached ones first),
5. crop the grid to the bounding box of its blocks.
Moves 1 and 2 shrink the box and are repeated until neither helps before 3 and 4 are tried. Edits whose
surroundings look like those of an edit that failed before are not simulated again (`_local_key`).

Edits change block connections (dust shapes, attachments). Dust and other shape-dependent states are
recomputed by placing the grid in the simulator and letting shape updates run (`normalize`).
"""

from __future__ import annotations

from dataclasses import replace

from ..model import Grid, Pos
from ..sim import blockdata
from ..sim.constants import UPDATE_ALL
from ..sim.core import World
from ..sim.runner import ORACLE_ORIGIN
from .candidate import Candidate
from .evaluate import Constraints, evaluate_any
from .spec import Spec

MAX_EVALUATIONS = 400
DOWN = Pos(0, -1, 0)
UP = Pos(0, 1, 0)


def crop(c: Candidate) -> Candidate:
    blocks = [p for p, _ in c.grid.items()]
    if not blocks:
        return c
    lo = Pos(*(min(p[i] for p in blocks) for i in range(3)))
    hi = Pos(*(max(p[i] for p in blocks) for i in range(3)))
    size = tuple(h - l + 1 for h, l in zip(hi, lo))
    if size == tuple(c.grid.size):
        return c
    g = Grid(size, c.grid.meta)
    for p, s in c.grid.items():
        g[p - lo] = s
    for p, be in c.grid.block_entities.items():
        g.block_entities[p - lo] = be
    return replace(c, grid=g, inputs=[p - lo for p in c.inputs], outputs=[p - lo for p in c.outputs])


def _cut(c: Candidate, axis: int, k: int) -> Candidate | None:
    ports = c.inputs + c.outputs
    if any(p[axis] == k for p in ports):
        return None
    size = list(c.grid.size)
    if size[axis] <= 1:
        return None
    size[axis] -= 1

    def move(p: Pos) -> Pos:
        if p[axis] < k:
            return p
        q = list(p)
        q[axis] -= 1
        return Pos(*q)

    g = Grid(tuple(size), c.grid.meta)
    for p, s in c.grid.items():
        if p[axis] != k:
            g[move(p)] = s
    for p, be in c.grid.block_entities.items():
        if p[axis] != k:
            g.block_entities[move(p)] = be
    return replace(c, grid=g, inputs=[move(p) for p in c.inputs], outputs=[move(p) for p in c.outputs])


def _rebuild(c: Candidate, blocks: dict, move) -> Candidate:
    """Candidate with `blocks` (old position -> state) placed at move(old position), cropped to their box.
    Block entities and ports follow their blocks."""
    placed = {move(p): s for p, s in blocks.items()}
    lo = Pos(*(min(p[i] for p in placed) for i in range(3)))
    hi = Pos(*(max(p[i] for p in placed) for i in range(3)))
    g = Grid(tuple(h - l + 1 for h, l in zip(hi, lo)), c.grid.meta)
    for p, s in placed.items():
        g[p - lo] = s
    for p, be in c.grid.block_entities.items():
        if p in blocks:
            g.block_entities[move(p) - lo] = be
    return replace(c, grid=g, inputs=[move(p) - lo for p in c.inputs], outputs=[move(p) - lo for p in c.outputs])


AXES = "xyz"
UNIT = [Pos(1, 0, 0), Pos(-1, 0, 0), Pos(0, 1, 0), Pos(0, -1, 0), Pos(0, 0, 1), Pos(0, 0, -1)]
MAX_SHIFT = 3  # a part is moved by up to this many blocks at once


def _box_volume(lo, hi) -> int:
    v = 1
    for a, b in zip(lo, hi):
        v *= b - a + 1
    return v


def shifts(c: Candidate) -> list[tuple[str, frozenset[Pos], Pos]]:
    """Moves of one part of the design: every half-space {p[axis] < t} or {p[axis] >= t} moved by 1 to
    MAX_SHIFT blocks in any of the six directions, such that the bounding box of the whole design gets
    smaller. Moving along `axis` closes the gap between two parts; moving across it slides one part along
    the other (a partial plane cut), which can empty a border plane. A moved block may only land on a free
    cell or on a block of the same kind (`_same_kind`, not a port); the two become one, so a straight line
    between two parts gets shorter when they move together.

    Returns (description, moved positions, vector): short moves first, then the smallest resulting box,
    then the parts that touch the rest least (parts joined only by a line come first). Nothing is
    simulated here."""
    states = dict(c.grid.items())
    blocks = list(states)
    occupied = set(blocks)
    ports = set(c.inputs) | set(c.outputs)
    volume = c.volume
    out = []
    seen = set()
    for axis in range(3):
        for t in range(1, c.grid.size[axis]):
            low = frozenset(p for p in blocks if p[axis] < t)
            for part, side in ((low, "<"), (frozenset(occupied - low), "≥")):
                if not part or len(part) == len(blocks) or part in seen:
                    continue
                seen.add(part)
                rest = occupied - part
                contacts = sum(1 for x, y, z in part for dx, dy, dz in UNIT if (x + dx, y + dy, z + dz) in rest)
                plo = [min(p[i] for p in part) for i in range(3)]
                phi = [max(p[i] for p in part) for i in range(3)]
                rlo = [min(p[i] for p in rest) for i in range(3)]
                rhi = [max(p[i] for p in rest) for i in range(3)]
                for u in UNIT:
                    for d in range(1, MAX_SHIFT + 1):
                        v = Pos(u.x * d, u.y * d, u.z * d)
                        merged = _landing(part, v, rest, states, ports)
                        if merged is None:
                            break  # a part that collides now mostly collides farther on as well
                        lo = [min(plo[i] + v[i], rlo[i]) for i in range(3)]
                        hi = [max(phi[i] + v[i], rhi[i]) for i in range(3)]
                        new_volume = _box_volume(lo, hi)
                        if new_volume < volume:
                            what = f"Teil {AXES[axis]}{side}{t} um {d} nach {_dir_name(u)} verschoben"
                            if merged:
                                what += f", {merged} gleiche Blöcke zusammengelegt"
                            out.append(((d, new_volume, contacts, len(part)), what, part, v))
    out.sort(key=lambda m: m[0])
    return [m[1:] for m in out]


# properties that the simulation recomputes (power, connections); blocks that differ only in these are the same
_DERIVED = {"power", "powered", "lit", "locked", "north", "south", "east", "west", "up", "down"}


def _same_kind(a, b) -> bool:
    """Two blocks that may be merged into one when a part is moved onto the other (a straight line pushed
    into itself gets shorter): same block, same orientation and settings."""
    if a.id != b.id:
        return False
    pa = {k: v for k, v in a.properties.items() if k not in _DERIVED}
    pb = {k: v for k, v in b.properties.items() if k not in _DERIVED}
    return pa == pb


def _landing(part, v: Pos, rest, states, ports) -> int | None:
    """Number of blocks of `part` that land on a block of the same kind when moved by v; None if one lands
    on anything else."""
    merged = 0
    vx, vy, vz = v
    for p in part:
        q = (p[0] + vx, p[1] + vy, p[2] + vz)
        if q in rest:
            if p in ports or q in ports or not _same_kind(states[p], states[q]):
                return None
            merged += 1
    return merged


def _local_key(c: Candidate, cells, radius: int = 2) -> frozenset:
    """The blocks within `radius` of `cells`, relative to the lowest corner of `cells`: two edits whose
    surroundings look the same are expected to work out the same (used to skip repeating failed edits)."""
    cells = list(cells)
    lo = Pos(*(min(p[i] for p in cells) for i in range(3)))
    near = set()
    for x, y, z in cells:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    near.add((x + dx, y + dy, z + dz))
    return frozenset((p - lo, s) for p, s in c.grid.items() if tuple(p) in near)


def _dir_name(u: Pos) -> str:
    return {(1, 0, 0): "Osten", (-1, 0, 0): "Westen", (0, 1, 0): "oben", (0, -1, 0): "unten",
            (0, 0, 1): "Süden", (0, 0, -1): "Norden"}[tuple(u)]


def shifted(c: Candidate, part: set[Pos], v: Pos) -> Candidate:
    """The candidate with the blocks at `part` moved by v (the caller made sure the cells are free)."""
    return _rebuild(c, dict(c.grid.items()), lambda p: p + v if p in part else p)


def _normalized(c: Candidate | None) -> Candidate | None:
    return None if c is None else normalize(c)


def _without(c: Candidate, pos: Pos) -> Candidate:
    g = Grid(tuple(c.grid.size), c.grid.meta)
    for p, s in c.grid.items():
        if p != pos:
            g[p] = s
    g.block_entities = {p: be for p, be in c.grid.block_entities.items() if p != pos}
    return replace(c, grid=g)


# ---------------------------------------------------------------------- shorter dust lines
WIRE_ID = "redstone_wire"
DUST = "redstone_wire[east=none,north=none,power=0,south=none,west=none]"
FLOOR = "stone"
_FLAT = [(1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]


def _plain(s) -> bool:
    """A block that only carries or supports (stone and the like): no source, no output, no block entity."""
    return (blockdata.is_conductor(s) and not blockdata.is_signal_source(s) and s.id != "redstone_lamp"
            and not blockdata.has_block_entity(s))


def _dust_links(states: dict, w: Pos) -> list[Pos]:
    """Dust joined to the dust at w: beside it, or one block higher or lower diagonally (a step)."""
    out = []
    for dx, _, dz in _FLAT:
        for dy in (0, 1, -1):
            q = Pos(w.x + dx, w.y + dy, w.z + dz)
            s = states.get(q)
            if s is not None and s.id == WIRE_ID:
                out.append(q)
    return out


def lines(c: Candidate) -> list[tuple[Pos, list[Pos], Pos]]:
    """Plain stretches of dust: (a, inner cells, b) where the inner cells form a path of dust from dust a to
    dust b, each inner cell joined to exactly two dust cells and touching nothing else than its own floor
    (a plain block) and the floors of its neighbours. Rerouting replaces the inner cells."""
    states = dict(c.grid.items())
    ports = set(c.inputs) | set(c.outputs)
    links = {p: _dust_links(states, p) for p, s in states.items() if s.id == WIRE_ID}

    def clean(w: Pos) -> bool:
        if len(links[w]) != 2 or w in ports:
            return False
        floor = states.get(w + DOWN)
        if floor is None or not _plain(floor) or (w + UP) in states:
            return False
        allowed = set(links[w]) | {q + DOWN for q in links[w]}
        for dx, _, dz in _FLAT:
            q = Pos(w.x + dx, w.y, w.z + dz)
            if q in states and q not in allowed:
                return False
        return True

    inner = {w for w in links if clean(w)}
    out, seen = [], set()
    for w in sorted(inner):
        if w in seen:
            continue
        comp, todo = {w}, [w]
        while todo:
            for q in links[todo.pop()]:
                if q in inner and q not in comp:
                    comp.add(q)
                    todo.append(q)
        seen |= comp
        ends = sorted(q for q in comp if sum(r in comp for r in links[q]) < 2)
        if not ends:
            continue  # a ring
        path, prev = [ends[0]], None
        while True:
            nxt = [q for q in links[path[-1]] if q in comp and q != prev]
            if not nxt:
                break
            prev = path[-1]
            path.append(nxt[0])
        first = [q for q in links[path[0]] if q not in comp]
        last = [q for q in links[path[-1]] if q not in comp]
        a = first[0]
        b = last[-1] if len(path) > 1 else first[1]
        if a != b:
            out.append((a, path, b))
    return out


def _dust_route(states: dict, a: Pos, b: Pos, limit: int) -> list[Pos] | None:
    """Shortest new dust path (cells between a and b) of at most `limit` cells, by breadth-first search.

    Steps as in `compose._route`: flat, one up (the cell above the current dust stays empty) or one down
    (the cell in front stays empty). A cell is free; its floor is free (stone is put there) or a plain block;
    its horizontal neighbours are free, plain, a or b. a and b keep their own floors."""
    from collections import deque

    def ok(c: Pos) -> bool:
        if c in states or (c + UP) in states:
            return False
        floor = states.get(c + DOWN)
        if floor is not None and not _plain(floor):
            return False
        for dx, _, dz in _FLAT:
            q = Pos(c.x + dx, c.y, c.z + dz)
            s = states.get(q)
            if s is not None and q not in (a, b) and not _plain(s):
                return False
        return True

    def joined(c: Pos, d: Pos) -> bool:  # dust at c and d connect (flat or a step)
        return abs(c.x - d.x) + abs(c.z - d.z) == 1 and abs(c.y - d.y) <= 1

    prev: dict[Pos, Pos | None] = {a: None}
    queue = deque([(a, 0)])
    while queue:
        c, n = queue.popleft()
        if c != a and joined(c, b):
            path = [c]
            while prev[path[-1]] != a:
                path.append(prev[path[-1]])
            return path[::-1]
        if n >= limit:
            continue
        for dx, _, dz in _FLAT:
            h = Pos(c.x + dx, c.y, c.z + dz)
            steps = [h]
            if (c + UP) not in states:
                steps.append(h + UP)
            if h not in states:
                steps.append(h + DOWN)
            for q in steps:
                if q not in prev and q != b and ok(q):
                    prev[q] = c
                    queue.append((q, n + 1))
    return None


def rerouted(c: Candidate, a: Pos, inner: list[Pos], b: Pos) -> Candidate | None:
    """The dust between a and b laid anew on the shortest way, if that needs fewer blocks (dust plus floors
    that only carried this dust); None otherwise."""
    states = dict(c.grid.items())
    cells = set(inner)
    floors = set()  # floors that carry nothing else: no torch, lever, diode, dust ... next to them
    for w in inner:
        f = w + DOWN
        if f not in (a + DOWN, b + DOWN) and all(
                q not in states or q in cells or blockdata.is_conductor(states[q])
                for q in (f + u for u in UNIT if u != UP)):
            floors.add(f)
    removed = cells | floors
    rest = {p: s for p, s in states.items() if p not in removed}
    path = _dust_route(rest, a, b, len(inner))
    if path is None:
        return None
    added = {p: DUST for p in path}
    added.update({p + DOWN: FLOOR for p in path if (p + DOWN) not in rest})
    if len(added) >= len(removed):
        return None
    rest.update(added)
    return _rebuild(c, rest, lambda p: p)


def normalize(c: Candidate, max_ticks: int = 200) -> Candidate:
    """Make the stored state consistent again after an edit.

    The grid is placed in the simulator; every position (also the now empty ones) sends shape updates and
    every block gets a neighbour update, as if it had just been placed. Then the world runs until it is
    idle, and the settled states are read back. Levers keep their stored state."""
    from ..analysis.experiment import world_is_idle

    world = World()
    world.place_grid(c.grid, ORACLE_ORIGIN)
    sx, sy, sz = c.grid.size
    every = [Pos(x, y, z) for x in range(sx) for y in range(sy) for z in range(sz)]
    for p in every:
        wp = p + ORACLE_ORIGIN
        world.update_neighbour_shapes(wp, world.get(wp), UPDATE_ALL)
    for p in every:
        wp = p + ORACLE_ORIGIN
        st = world.get(wp)
        if not st.is_air:
            world.neighbor_changed_with_state(st, wp, world.block(st), False)
    for _ in range(max_ticks):
        if world_is_idle(world):
            break
        world.tick()
    g = Grid(tuple(c.grid.size), c.grid.meta)
    for p in every:
        st = world.get(p + ORACLE_ORIGIN)
        if not st.is_air:
            g[p] = st
    g.block_entities = {p: be for p, be in c.grid.block_entities.items() if not g.get(p).is_air}
    return replace(c, grid=g)


def compact(c: Candidate, spec: Spec, constraints: Constraints | None = None,
            max_evaluations: int = MAX_EVALUATIONS, time_limit: float | None = None) -> tuple[Candidate, list[str]]:
    """Return the smallest correct variant found and a German log of the accepted steps.

    Stops after max_evaluations simulated variants or time_limit seconds, whichever comes first."""
    import time

    constraints = constraints or Constraints()
    budget = [max_evaluations]
    deadline = None if time_limit is None else time.perf_counter() + time_limit
    log: list[str] = []

    tried = {"Ebenen": 0, "Verschiebungen": 0, "Leitungen": 0, "Einzelblöcke": 0}

    def works(cand: Candidate, kind: str | None = None) -> bool:
        if deadline is not None and time.perf_counter() > deadline:
            budget[0] = 0
        if budget[0] <= 0:
            return False
        budget[0] -= 1
        if kind is not None:
            tried[kind] += 1
        quick = evaluate_any(cand, spec, constraints, quick=True)
        if not quick.correct:
            return False
        full = evaluate_any(cand, spec, constraints) if hasattr(spec, "table") else quick
        return full.correct and not [v for v in full.violations if v.startswith("Verzögerung")]

    if not works(c):
        return c, ["Ausgangsentwurf erfüllt die Spezifikation nicht; nichts verkleinert"]
    current = crop(c)
    if current is not c:
        log.append("auf die Bounding Box zugeschnitten")
    failed: set = set()  # surroundings of edits that did not work (see _local_key)

    def attempt(kind: str, key, make) -> bool:
        """Simulate the edit made by make() unless an edit with the same surroundings failed before."""
        nonlocal current
        if budget[0] <= 0 or key in failed:
            return False
        cand = make()
        if cand is not None and works(cand, kind):
            current = cand
            return True
        if budget[0] > 0:  # a variant that was not simulated (limit reached) did not fail
            failed.add(key)
        return False

    def cuts() -> bool:
        found = False
        for axis in (1, 0, 2):
            k = current.grid.size[axis] - 1
            while k >= 0 and budget[0] > 0:
                if any(p[axis] == k for p in current.inputs + current.outputs):
                    k -= 1
                    continue
                plane = [p for p, _ in current.grid.items() if k - 1 <= p[axis] <= k + 1] or [Pos(0, 0, 0)]
                key = ("cut", axis, k == 0, k == current.grid.size[axis] - 1, _local_key(current, plane, 0))
                if attempt("Ebenen", key, lambda: _normalized(_cut(current, axis, k))):
                    log.append(f"Ebene {AXES[axis]}={k} entfernt")
                    found = True
                k -= 1
        return found

    def moves() -> bool:
        dead = set()  # (part, direction) that failed at a shorter distance
        for what, part, v in shifts(current):
            if budget[0] <= 0:
                return False
            u = Pos(*(int(x > 0) - int(x < 0) for x in v))
            if (part, u) in dead:
                continue
            key = ("shift", v, _local_key(current, list(part) + [p + v for p in part]))
            if attempt("Verschiebungen", key, lambda: normalize(shifted(current, part, v))):
                log.append(what)
                return True
            dead.add((part, u))
        return False

    def reroutes() -> bool:
        for a, inner, b in lines(current):
            if budget[0] <= 0:
                break
            key = ("line", _local_key(current, inner + [a, b], 1))
            if attempt("Leitungen", key, lambda: _normalized(rerouted(current, a, inner, b))):
                log.append(f"Leitung von {a} nach {b} kürzer verlegt ({len(inner)} Staub vorher)")
                return True
        return False

    def removals() -> bool:
        found = False
        occupied = {p for p, _ in current.grid.items()}
        # loosely attached blocks first (dangling dust, spare supports): they are the likely ones to go
        order = sorted(current.grid.items(), key=lambda ps: (sum(ps[0] + u in occupied for u in UNIT), ps[0]))
        for p, s in order:
            if budget[0] <= 0:
                break
            if p in current.inputs or p in current.outputs or current.grid.get(p) != s:
                continue
            if attempt("Einzelblöcke", ("remove", _local_key(current, [p])), lambda: normalize(_without(current, p))):
                log.append(f"{s.id} bei {p} entfernt")
                found = True
        return found

    # Moves that shrink the box (plane cuts, moving parts) until none helps, then single blocks; repeat while
    # anything helps. Removing blocks keeps the grid coordinates, so the log positions stay meaningful.
    improved = True
    while improved and budget[0] > 0:
        improved = False
        structural = True
        while structural and budget[0] > 0:
            structural = cuts()
            while budget[0] > 0 and moves():
                structural = True
            improved |= structural
        while budget[0] > 0 and reroutes():
            improved = True
        improved |= removals()
        current = crop(current)
    if budget[0] <= 0:
        log.append("Abbruch: Zeit- oder Bewertungslimit erreicht")
    log.append("simulierte Varianten: " + ", ".join(f"{k} {n}" for k, n in tried.items()))
    return replace(current, name=f"{c.name}-kompakt", origin=f"kompaktiert aus {c.origin or c.name}"), log
