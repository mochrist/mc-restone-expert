"""Shrink a correct candidate step by step; every step is kept only if the simulation still meets the spec.

Moves (greedy, repeated until nothing helps):
1. cut a whole plane (x = k, y = k or z = k) out of the grid and close the gap,
2. move one part of the design (a half-space of its blocks) by 1 to 3 blocks, so that the bounding box
   gets smaller: parts of a composition move together, or one part slides along the other (partial plane
   cut); equal blocks that land on each other are merged, which shortens straight lines (`shifts`),
3. move a whole building block elsewhere, turned in any of four ways, and lay its lines anew (`parts`:
   the parts a composition recorded (`candidate.Assembly`), also where they touch, or else the groups of
   blocks left between plain dust lines; `relocations`),
4. lay a stretch of dust anew on a shorter way (`lines`, `rerouted`),
5. remove single blocks that are not inputs or outputs (loosely attached ones first),
6. crop the grid to the bounding box of its blocks.
Moves 1 to 3 shrink the box and are repeated until none helps before 4 and 5 are tried; move 3 goes first
when it promises a smaller box than any single shift (shifts may join the building blocks). Edits whose
surroundings look like those of an edit that failed before are not simulated again (`_local_key`).

Edits change block connections (dust shapes, attachments). Dust and other shape-dependent states are
recomputed by placing the grid in the simulator and letting shape updates run (`normalize`).
"""

from __future__ import annotations

from dataclasses import replace

from ..model import BlockState, Grid, Pos
from ..sim import blockdata
from ..sim.constants import UPDATE_ALL
from ..sim.core import World
from ..sim.runner import ORACLE_ORIGIN
from .candidate import Assembly, Candidate, is_line, under
from .evaluate import Constraints, evaluate_any
from .spec import Spec

MAX_EVALUATIONS = 400
CUT_SHARE = 0.2  # share of the evaluations one pass of plane cuts may use (sparse planes first)
MIN_CUTS = 12
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
    return replace(c, grid=g, inputs=[p - lo for p in c.inputs], outputs=[p - lo for p in c.outputs],
                   assembly=c.moved_assembly(lambda p: p - lo))


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
    return replace(c, grid=g, inputs=[move(p) for p in c.inputs], outputs=[move(p) for p in c.outputs],
                   assembly=c.moved_assembly(lambda p: None if p[axis] == k else move(p)))


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
    return replace(c, grid=g, inputs=[move(p) - lo for p in c.inputs], outputs=[move(p) - lo for p in c.outputs],
                   assembly=c.moved_assembly(lambda p: move(p) - lo if p in blocks else None))


AXES = "xyz"
UNIT = [Pos(1, 0, 0), Pos(-1, 0, 0), Pos(0, 1, 0), Pos(0, -1, 0), Pos(0, 0, 1), Pos(0, 0, -1)]
MAX_SHIFT = 3  # a part is moved by up to this many blocks at once


def _box_volume(lo, hi) -> int:
    v = 1
    for a, b in zip(lo, hi):
        v *= b - a + 1
    return v


def shifts(c: Candidate) -> list[tuple[str, frozenset[Pos], Pos]]:
    return [m[1:] for m in _shift_list(c)]


def _shift_list(c: Candidate) -> list[tuple[tuple, str, frozenset[Pos], Pos]]:
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
    return out


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
    return replace(c, grid=g, assembly=c.moved_assembly(lambda p: None if p == pos else p))


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


def _line_floors(states: dict, a: Pos, inner: list[Pos], b: Pos) -> set[Pos]:
    """Floors of the inner dust that carry nothing else: no torch, lever, diode, dust ... next to them."""
    cells = set(inner)
    floors = set()
    for w in inner:
        f = w + DOWN
        if f not in (a + DOWN, b + DOWN) and all(
                q not in states or q in cells or blockdata.is_conductor(states[q])
                for q in (f + u for u in UNIT if u != UP)):
            floors.add(f)
    return floors


def rerouted(c: Candidate, a: Pos, inner: list[Pos], b: Pos) -> Candidate | None:
    """The dust between a and b laid anew on the shortest way, if that needs fewer blocks (dust plus floors
    that only carried this dust); None otherwise."""
    states = dict(c.grid.items())
    removed = set(inner) | _line_floors(states, a, inner, b)
    rest = {p: s for p, s in states.items() if p not in removed}
    path = _dust_route(rest, a, b, len(inner))
    if path is None:
        return None
    added = {p: DUST for p in path}
    added.update({p + DOWN: FLOOR for p in path if (p + DOWN) not in rest})
    if len(added) >= len(removed):
        return None
    rest.update(added)
    out = _rebuild(c, rest, lambda p: p)
    if c.assembly is not None:  # the new dust takes the label of the old one, if that had a single one
        old = {c.assembly.labels.get(p) for p in inner}
        if len(old) == 1 and None not in old:
            lo = Pos(*(min(p[i] for p in rest) for i in range(3)))
            lab = old.pop()
            labels = dict(out.assembly.labels)
            for p in added:
                labels[p - lo] = lab
            out = replace(out, assembly=Assembly(labels, out.assembly.ends))
    return out


# ---------------------------------------------------------------------- moving building blocks
_AROUND = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)]
MAX_PLACES = 4000  # placements of building blocks checked per round (no simulation, see `relocations`)
RELOCATE_POOL = 12  # routed placements collected per round; the smallest ones are simulated first
RELOCATE_TRIES = 3  # routed placements simulated per round
LINE_MAX = 12  # a line laid anew may have this many dust (the signal must still reach the other end)
LINE_SLACK = 2  # a line laid anew may be this much longer than before
_DUST_STATE = BlockState.parse(DUST)
_FLOOR_STATE = BlockState.parse(FLOOR)


def parts(c: Candidate) -> tuple[list[frozenset[Pos]], list[tuple[Pos, list[Pos], Pos]], set[Pos]]:
    """The building blocks of a design and the lines between them: (groups, lines, cells of the lines and
    their floors). See `_parts`."""
    groups, found, floors, _ = _parts(c)
    removed = set()
    for (_, inner, _), fl in zip(found, floors):
        removed |= set(inner) | fl
    return groups, found, removed - set(c.inputs) - set(c.outputs)


def _components(cells: set, around=_AROUND) -> list[set]:
    """Groups of `cells` that touch (also diagonally), in the order of their lowest cell."""
    out, seen = [], set()
    for p in sorted(cells):
        if p in seen:
            continue
        comp, todo = {p}, [p]
        seen.add(p)
        while todo:
            x, y, z = todo.pop()
            for dx, dy, dz in around:
                q = Pos(x + dx, y + dy, z + dz)
                if q in cells and q not in seen:
                    seen.add(q)
                    comp.add(q)
                    todo.append(q)
        out.append(comp)
    return out


def _parts(c: Candidate):
    """The building blocks of a design and the lines between them: (groups, lines, floors, names).

    With an assembly (the labels a composition left, `candidate.Assembly`) the groups are its parts: one per
    label and per enclosing label (a nested composition can move as a whole or part by part), even where
    parts touch. Its lines lead from block a over the cells `inner` to block b; floors[k] are the floors that
    only carry line k, names[k] its label. Parts joined directly (no line cell between them) and blocks
    without a valid label stick to what they touch. Without an assembly, or when it gives fewer than two
    groups, the plain dust lines (`lines`) and their floors are taken out and the other blocks fall apart into
    groups that touch (also diagonally). Groups are ordered by their lowest position; line ends belong to
    the groups."""
    states = dict(c.grid.items())
    if c.assembly is not None:
        found = _labelled_parts(c, states)
        if found is not None and len(found[0]) >= 2:
            return found
    found = lines(c)
    floors = [_line_floors(states, a, inner, b) for a, inner, b in found]
    removed = set()
    for (_, inner, _), fl in zip(found, floors):
        removed |= set(inner) | fl
    removed -= set(c.inputs) | set(c.outputs)
    groups = [frozenset(g) for g in _components({p for p in states if p not in removed})]
    return groups, found, floors, [None] * len(found)


_LINE_IDS = {WIRE_ID, "repeater"}


def _joined(c: Pos, d: Pos) -> bool:
    """Neighbours on a line: beside each other, at most one block higher or lower."""
    return abs(c[0] - d[0]) + abs(c[2] - d[2]) == 1 and abs(c[1] - d[1]) <= 1


def _line_path(cells: set, a: Pos, b: Pos) -> list[Pos] | None:
    """The cells in order, from the one next to a to the one next to b, if they form such a simple path."""
    if not cells:
        return []
    for s in sorted(p for p in cells if _joined(p, a)):
        path, seen = [s], {s}
        while True:
            nxt = [q for q in cells if q not in seen and _joined(path[-1], q)]
            if len(nxt) != 1:
                break
            path.append(nxt[0])
            seen.add(nxt[0])
        if len(path) == len(cells) and _joined(path[-1], b):
            return path
    return None


def _labelled_parts(c: Candidate, states: dict):
    asm = c.assembly
    labels = {p: lab for p, lab in asm.labels.items() if p in states}
    ports = set(c.inputs) | set(c.outputs)
    found, floors, names = [], [], []
    glue = {p for p in states if p not in labels}  # blocks that stick to what they touch
    parent: dict[str, str] = {}

    def root(x: str) -> str:
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    def join(x: str, y: str) -> None:
        x, y = root(x), root(y)
        if x != y:
            parent[max(x, y)] = min(x, y)

    by_label: dict[str, set] = {}
    for p, lab in labels.items():
        by_label.setdefault(lab, set()).add(p)
    for name in sorted(asm.ends):
        a, b = asm.ends[name]
        mine = by_label.get(name, set())
        cells = {p for p in mine if states[p].id in _LINE_IDS}
        path = None
        if (a in labels and b in labels and not is_line(labels[a]) and not is_line(labels[b])
                and not cells & ports):
            path = _line_path(cells, a, b)
        if path == [] and not _joined(a, b):
            path = None
        if path is None:  # a broken line: the parts it joins move together
            glue |= mine
            if a in labels and b in labels:
                join(labels[a], labels[b])
            continue
        fl = _line_floors(states, a, path, b) & mine
        glue |= mine - cells - fl
        found.append((a, path, b))
        floors.append(fl)
        names.append(name)
    for lab in by_label:
        if is_line(lab) and lab not in asm.ends:
            glue |= by_label[lab]  # cells of a line that lost an end
    removed = set()
    for (_, inner, _), fl in zip(found, floors):
        removed |= set(inner) | fl
    owner = {p: lab for p, lab in labels.items() if p not in glue and p not in removed}
    sticky: dict[str, set] = {}  # root label -> glue blocks that go with it
    loose = []
    for comp in _components(glue - removed):
        touched = sorted({owner[q] for x, y, z in comp for dx, dy, dz in _AROUND
                          if (q := Pos(x + dx, y + dy, z + dz)) in owner})
        if not touched:
            loose.append(frozenset(comp))
            continue
        for t in touched[1:]:
            join(touched[0], t)
        sticky.setdefault(touched[0], set()).update(comp)
    leaves: dict[str, set] = {}
    for p, lab in owner.items():
        leaves.setdefault(lab, set()).add(p)
    classes: dict[str, set] = {}  # root -> blocks of all labels joined to it
    for lab, blocks in leaves.items():
        classes.setdefault(root(lab), set()).update(blocks)
    for lab, blocks in sticky.items():
        classes.setdefault(root(lab), set()).update(blocks)
    prefixes = set()
    for lab in leaves:
        bits = lab.split("/")
        prefixes.update("/".join(bits[:k]) for k in range(1, len(bits) + 1))
    everything = set(owner) | (glue - removed)
    groups = set(loose)
    for pre in sorted(prefixes):
        roots = {root(lab) for lab in leaves if under(lab, pre)}
        g = frozenset().union(*(classes[r] for r in roots))
        if g and g != everything:
            groups.add(g)
    return sorted(groups, key=lambda g: (min(g), len(g))), found, floors, names


def _dust_path(states: dict, start: Pos, goal: Pos, a: Pos, b: Pos, limit: int,
               box: tuple[Pos, Pos]) -> list[Pos] | None:
    """Shortest dust path from cell `start` (joined to the dust a) to cell `goal` (joined to the dust b), both
    ends included, of at most `limit` cells inside `box` (lowest and highest corner), by breadth-first search;
    steps as in `_dust_route`.

    Every cell is free, as is the cell above it; its floor is free (stone is put there) or a plain block. The
    inner cells only have free or plain blocks beside them, no other dust a step up or down, and a new floor
    powers nothing (only free or plain blocks next to it). The two end cells may touch their own line end."""
    from collections import deque

    (x0, y0, z0), (x1, y1, z1) = box

    def ok(c: Pos, ends: tuple[Pos, ...] = ()) -> bool:
        if not (x0 <= c.x <= x1 and y0 <= c.y <= y1 and z0 <= c.z <= z1):
            return False
        if c in states or (c + UP) in states:
            return False
        f = c + DOWN
        floor = states.get(f)
        if floor is not None and not _plain(floor):
            return False
        for dx, _, dz in _FLAT:
            q = Pos(c.x + dx, c.y, c.z + dz)
            if q in ends:
                continue
            s = states.get(q)
            if s is not None and not _plain(s):
                return False
            for dy in (1, -1):
                r = states.get(Pos(q.x, q.y + dy, q.z))
                if r is not None and r.id == WIRE_ID and Pos(q.x, q.y + dy, q.z) not in ends:
                    return False
            if not ends and floor is None:
                s = states.get(Pos(f.x + dx, f.y, f.z + dz))
                if s is not None and not _plain(s):
                    return False
        if not ends and floor is None:
            s = states.get(f + DOWN)
            if s is not None and not _plain(s):
                return False
        return True

    if start == goal:
        return [start] if ok(start, (a, b)) else None
    if abs(start.x - goal.x) + abs(start.z - goal.z) >= limit:
        return None
    if not ok(start, (a,)) or not ok(goal, (b,)):
        return None
    prev: dict[Pos, Pos | None] = {start: None}
    queue = deque([(start, 1)])
    while queue:
        c, n = queue.popleft()
        if n >= limit:
            continue
        for dx, _, dz in _FLAT:
            h = Pos(c.x + dx, c.y, c.z + dz)
            steps = [h, h + UP]
            if h not in states:
                steps.append(h + DOWN)
            for q in steps:
                if q in prev:
                    continue
                if q == goal:
                    path = [q, c]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    return path[::-1]
                if ok(q):
                    prev[q] = c
                    queue.append((q, n + 1))
    return None


def _repeater_before(blocks: dict, r: Pos, b: Pos, laid: dict, name) -> Pos | None:
    """Put a repeater at r that feeds b (beside it, same height), with a floor; returns the cell behind it
    where the dust has to arrive, None if r does not fit (taken, unsuitable floor, something beside it)."""
    from ..model import Direction

    d = b - r
    if d.y != 0 or abs(d.x) + abs(d.z) != 1 or r in blocks or (r - d) in blocks:
        return None
    floor = blocks.get(r + DOWN)
    if floor is not None and not _plain(floor):
        return None
    for dx, _, dz in _FLAT:
        q = Pos(r.x + dx, r.y, r.z + dz)
        if q != b and q != r - d and q in blocks and not _plain(blocks[q]):
            return None
    back = next(x for x in Direction if x.vec == (-d.x, 0, -d.z))
    blocks[r] = BlockState.parse(f"repeater[delay=1,facing={back.label},locked=false,powered=false]")
    laid[r] = name
    if floor is None:
        blocks[r + DOWN] = _FLOOR_STATE
        laid[r + DOWN] = name
    return r - d


def relocations(c: Candidate):
    """Move one building block (`parts`) elsewhere, turned in any of the four ways, and lay the lines to the
    other blocks anew (`_dust_path`, from the same cell next to each line end as before, so the line ends keep
    their shapes). The block keeps one block of air to the others, also diagonally.

    Yields (description, candidate): placements whose box (without lines) is smallest first, at most
    MAX_PLACES placements are checked. Only candidates with a smaller box than `c` come out; nothing is
    simulated here."""
    from .compose import UNROTATABLE, _halo, turn_pos, turn_state

    states = dict(c.grid.items())
    groups, found, floors, names = _parts(c)
    if len(groups) < 2:
        return
    volume = c.volume
    options = []
    setups = []
    for k, part in enumerate(groups):
        attached = [k for k, ln in enumerate(found) if (ln[0] in part) != (ln[2] in part)]
        internal = [k for k, ln in enumerate(found) if ln[0] in part and ln[2] in part]
        moved = set(part)
        for k in internal:
            moved |= set(found[k][1]) | floors[k]
        dropped = set()
        for k in attached:
            dropped |= set(found[k][1]) | floors[k]
        dropped -= set(c.inputs) | set(c.outputs)
        if moved & dropped:
            continue
        fixed = {p: s for p, s in states.items() if p not in moved and p not in dropped}
        if not fixed:
            continue
        flo, fhi = Pos(*(min(p[i] for p in fixed) for i in range(3))), Pos(*(max(p[i] for p in fixed) for i in range(3)))
        mlo, mhi = Pos(*(min(p[i] for p in moved) for i in range(3))), Pos(*(max(p[i] for p in moved) for i in range(3)))
        msize = [h - l + 1 for h, l in zip(mhi, mlo)]
        turnable = not any(states[p].id in UNROTATABLE for p in moved)
        setups.append((part, attached, moved, fixed, mlo, msize))
        for turns in range(4 if turnable else 1):
            ts = (msize[2], msize[1], msize[0]) if turns % 2 else tuple(msize)
            ranges = [range(flo[i] - ts[i] - 1, fhi[i] + 3) for i in range(3)]
            for nx in ranges[0]:
                for ny in ranges[1]:
                    for nz in ranges[2]:
                        if turns == 0 and (nx, ny, nz) == tuple(mlo):
                            continue
                        n = (nx, ny, nz)
                        v = 1
                        for i in range(3):
                            v *= max(fhi[i], n[i] + ts[i] - 1) - min(flo[i], n[i]) + 1
                        if v < volume:
                            options.append((v, turns, len(setups) - 1, n))
    options.sort()
    halos: dict[int, set] = {}
    turned: dict[tuple[int, int], list] = {}  # positions of a moved block, turned, relative to its new corner
    pool = []
    for _, turns, s, n in options[:MAX_PLACES]:
        part, attached, moved, fixed, mlo, msize = setups[s]
        lo = Pos(*n)

        def place(p: Pos) -> Pos:
            return turn_pos(p - mlo, msize[0], msize[2], turns) + lo

        if s not in halos:
            halos[s] = _halo(fixed)
        if (s, turns) not in turned:
            turned[s, turns] = [tuple(turn_pos(p - mlo, msize[0], msize[2], turns)) for p in moved]
        halo, (nx, ny, nz) = halos[s], n
        if any((x + nx, y + ny, z + nz) in halo for x, y, z in turned[s, turns]):
            continue
        new = {place(p): turn_state(states[p], turns) for p in moved}
        blocks = dict(fixed)
        blocks.update(new)
        box = (Pos(*(min(p[i] for p in blocks) - 1 for i in range(3))),
               Pos(*(max(p[i] for p in blocks) + 1 for i in range(3))))
        laid = {}  # new line cells and floors -> label of the line
        weak = 0  # lines that should end in a repeater but do not
        for k in attached:
            a, inner, b = found[k]
            # a joint without line cells (a feeds b directly) starts where b was, seen from a, and ends
            # where a was, seen from b
            first, last = (inner[0], inner[-1]) if inner else (b, a)
            ea, sa = (place(a), place(first)) if a in part else (a, first)
            eb, sb = (place(b), place(last)) if b in part else (b, last)
            limit = max(len(inner) + LINE_SLACK, LINE_MAX)
            path = None
            if states[last].id != WIRE_ID:  # b took a full signal: a repeater in front of it again if it fits
                extra: dict = {}
                goal = _repeater_before(blocks, sb, eb, extra, names[k])
                if goal is not None:
                    path = _dust_path(blocks, sa, goal, ea, sb, limit, box)
                    if path is None:
                        for w in extra:
                            del blocks[w]
                    else:
                        laid.update(extra)
            if path is None:
                weak += states[last].id != WIRE_ID
                path = _dust_path(blocks, sa, sb, ea, eb, limit, box)
            if path is None:
                break
            for w in path:
                blocks[w] = _DUST_STATE
                laid[w] = names[k]
                if (w + DOWN) not in blocks:
                    blocks[w + DOWN] = _FLOOR_STATE
                    laid[w + DOWN] = names[k]
        else:
            blo = Pos(*(min(p[i] for p in blocks) for i in range(3)))
            bhi = Pos(*(max(p[i] for p in blocks) for i in range(3)))
            if _box_volume(blo, bhi) >= volume:
                continue
            g = Grid(tuple(h - l + 1 for h, l in zip(bhi, blo)), c.grid.meta)
            for p, st in blocks.items():
                g[p - blo] = st
            for p, be in c.grid.block_entities.items():
                if p in moved:
                    g.block_entities[place(p) - blo] = be
                elif p in fixed:
                    g.block_entities[p - blo] = be

            def port(p: Pos) -> Pos:
                return (place(p) if p in moved else p) - blo

            what = (f"Baustein bei {min(part)} ({len(part)} Blöcke)"
                    + (f" um {90 * turns}° gedreht und" if turns else "")
                    + f" nach {lo} versetzt, {len(attached)} Leitungen neu verlegt")
            asm = None
            if c.assembly is not None:
                asm = c.assembly.mapped(lambda p: port(p) if p in moved or p in fixed else None)
                asm.labels.update({w - blo: name for w, name in laid.items() if name is not None})
            cand = replace(c, grid=g, inputs=[port(p) for p in c.inputs], outputs=[port(p) for p in c.outputs],
                           assembly=asm)
            if weak and sum(1 for x in pool if x[0][0]) >= RELOCATE_POOL:
                continue
            pool.append(((weak, cand.volume, cand.block_count, len(pool)), what, cand))
            if sum(1 for x in pool if not x[0][0]) >= RELOCATE_POOL:
                break
    pool.sort(key=lambda x: x[0])
    for _, what, cand in pool:
        yield what, cand


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
    return replace(c, grid=g, assembly=None if c.assembly is None else c.assembly.kept(g))


def compact(c: Candidate, spec: Spec, constraints: Constraints | None = None,
            max_evaluations: int = MAX_EVALUATIONS, time_limit: float | None = None) -> tuple[Candidate, list[str]]:
    """Return the smallest correct variant found and a German log of the accepted steps.

    Stops after max_evaluations simulated variants or time_limit seconds, whichever comes first."""
    import time

    constraints = constraints or Constraints()
    budget = [max_evaluations]
    deadline = None if time_limit is None else time.perf_counter() + time_limit
    log: list[str] = []

    tried = {"Bausteine": 0, "Ebenen": 0, "Verschiebungen": 0, "Leitungen": 0, "Einzelblöcke": 0}

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

    # planes tried per pass: in a large design most planes hold blocks of every part and cannot go
    cut_limit = max(MIN_CUTS, int(CUT_SHARE * max_evaluations))

    def cuts() -> bool:
        """Planes with the fewest blocks first (an empty or nearly empty plane is the likely one to go); after
        a cut the planes are counted again."""
        found = True
        any_found = False
        while found and budget[0] > 0:
            found = False
            ports = current.inputs + current.outputs
            count: dict[tuple[int, int], int] = {}
            for p, _ in current.grid.items():
                for axis in range(3):
                    count[(axis, p[axis])] = count.get((axis, p[axis]), 0) + 1
            planes = [(count.get((axis, k), 0), (1, 0, 2).index(axis), -k, axis, k)
                      for axis in (1, 0, 2) for k in range(current.grid.size[axis])
                      if not any(p[axis] == k for p in ports)]
            for n, (*_, axis, k) in enumerate(sorted(planes)):
                if budget[0] <= 0 or n >= cut_limit:
                    break
                plane = [p for p, _ in current.grid.items() if k - 1 <= p[axis] <= k + 1] or [Pos(0, 0, 0)]
                key = ("cut", axis, k == 0, k == current.grid.size[axis] - 1, _local_key(current, plane, 0))
                if attempt("Ebenen", key, lambda: _normalized(_cut(current, axis, k))):
                    log.append(f"Ebene {AXES[axis]}={k} entfernt")
                    found = any_found = True
                    break
        return any_found

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

    placed: list = [None, []]  # the grid that relocations were searched for, and what came out

    def relocate(first: bool = False) -> bool:
        """first: only placements smaller than any single shift of a part would give (shifts may join the
        building blocks, so a large rearrangement goes first when it promises more)."""
        tries = 0
        below = None
        if placed[0] is not current.grid:  # the same design is not searched twice
            placed[:] = [current.grid, list(relocations(current))]
        for what, cand in placed[1]:
            if first and below is None:
                below = min((m[0][1] for m in _shift_list(current)), default=current.volume + 1)
            if budget[0] <= 0 or tries >= RELOCATE_TRIES or (first and cand.volume >= below):
                return False
            key = ("place", frozenset(cand.grid.items()))
            if key in failed:
                continue
            tries += 1
            if attempt("Bausteine", key, lambda: normalize(cand)):
                log.append(what)
                return True
        return False

    def reroutes() -> bool:
        for a, inner, b in lines(current):
            if budget[0] <= 0:
                break
            key = ("line", _local_key(current, inner + [a, b], 1))

            def shorter():  # only a line that does not make the design larger (box, then blocks)
                cand = _normalized(rerouted(current, a, inner, b))
                if cand is None or (crop(cand).volume, cand.block_count) >= (current.volume, current.block_count):
                    return None
                return cand

            if attempt("Leitungen", key, shorter):
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
            structural = False
            while budget[0] > 0 and relocate(first=True):
                structural = True
            structural |= cuts()
            # lines laid anew are few and cheap to try, and a shorter line often frees a whole plane
            while budget[0] > 0 and reroutes():
                structural = True
            while budget[0] > 0 and moves():
                structural = True
            while budget[0] > 0 and relocate():
                structural = True
            improved |= structural
        improved |= removals()
        current = crop(current)
    if budget[0] <= 0:
        log.append("Abbruch: Zeit- oder Bewertungslimit erreicht")
    log.append("simulierte Varianten: " + ", ".join(f"{k} {n}" for k, n in tried.items()))
    return replace(current, name=f"{c.name}-kompakt", origin=f"kompaktiert aus {c.origin or c.name}"), log
