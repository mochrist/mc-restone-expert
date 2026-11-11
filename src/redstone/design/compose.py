"""Compose two candidates: the output of one drives an input of the other (milestone M4, place and route).

`connect(src, j, dst, i)` lays both side by side and joins src output j to dst input i with a straight line:

    src ... [lamp q -> stone] [repeater, reads q] [dust ...] [repeater] [dst input p: dust]   (along d)

* The output lamp becomes a stone block. Everything that lit the lamp (dust pointing at it, a repeater, a
  torch below) powers the stone strongly, and a repeater next to it reads it.
* The input lever of dst becomes dust (or a repeater) fed from behind, so it powers its support block and its
  neighbours like the lever did, at full strength.
* dst is moved so that p lies on the line, on the height of q, with at least one block of air between the
  two parts. Dust runs on stone; every 15 blocks a repeater refreshes the signal.

Several layouts (direction, gap, input adapter) come out; none is assumed to work. The caller keeps only what
the simulation accepts (`search.compose_candidates`). Results are normalised (`compact.normalize`), so dust
shapes and the stored state are consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Direction, Grid, Pos
from .candidate import Assembly, Candidate

HORIZONTAL = (Direction.EAST, Direction.SOUTH, Direction.WEST, Direction.NORTH)
STONE = "stone"
WIRE = "redstone_wire[east=none,north=none,power=0,south=none,west=none]"
INPUT_MODES = ("dust", "repeater", "repeater+dust")
OUTPUT_MODES = ("repeater", "dust", "stone")
SUPPORTS = {"stone", "glass"}  # blocks a line component may stand on inside src


def _repeater(reads_from: Direction) -> str:
    return f"repeater[delay=1,facing={reads_from.label},locked=false,powered=false]"


@dataclass(frozen=True)
class Layout:
    direction: Direction
    gap: int  # dust blocks between the output adapter and the input adapter
    input_mode: str  # see INPUT_MODES
    output_mode: str = "stone"  # see OUTPUT_MODES

    def describe(self) -> str:
        out = {"stone": "Lampe → Block + Verstärker", "repeater": "Lampe → Verstärker",
               "dust": "Lampe → Staub"}[self.output_mode]
        return f"{out}, Leitung nach {self.direction.label}, {self.gap} Staub, Eingang als {self.input_mode}"


def _near(p: Pos, blocks) -> bool:
    """Any block of `blocks` within one block of p (also diagonally)."""
    return any(Pos(p.x + dx, p.y + dy, p.z + dz) in blocks
               for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1))


_AROUND = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]


def _halo(blocks) -> set[tuple[int, int, int]]:
    """All positions within one block of `blocks` (also diagonally), as plain tuples (a Pos compares and
    hashes like its tuple): `_near(p, blocks)` is `p in _halo(blocks)`."""
    return {(x + dx, y + dy, z + dz) for x, y, z in blocks for dx, dy, dz in _AROUND}


DOWN = Pos(0, -1, 0)
_CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
UNROTATABLE = {"rail", "powered_rail", "detector_rail", "activator_rail"}  # shapes not handled


def turn_state(st, turns: int):
    """A block state turned clockwise (seen from above) by `turns` quarter turns: facing, dust sides, axis."""
    from ..model import BlockState

    turns %= 4
    if turns == 0:
        return st
    props = dict(st.properties)
    for _ in range(turns):
        new = {}
        for k, v in props.items():
            if k in _CW and st.id == "redstone_wire":
                new[_CW[k]] = v
            elif k == "facing" and v in _CW:
                new[k] = _CW[v]
            elif k == "axis" and v in ("x", "z"):
                new[k] = "z" if v == "x" else "x"
            else:
                new[k] = v
        props = new
    return BlockState.of(st.name, props)


def turn_pos(p: Pos, sx: int, sz: int, turns: int) -> Pos:
    """Where p of a box sx wide (x) and sz deep (z), corner at the origin, lands when the box is turned
    clockwise by `turns` quarter turns (the turned box again starts at the origin)."""
    x, z, w, d = p[0], p[2], sx, sz
    for _ in range(turns % 4):
        x, z, w, d = d - 1 - z, x, d, w
    return Pos(x, p[1], z)


def rotate(c: Candidate, turns: int) -> Candidate | None:
    """The candidate turned clockwise (seen from above) by `turns` quarter turns; None if a block cannot be
    turned. Directional properties (facing, dust sides, axis) are turned with it."""
    from dataclasses import replace

    turns %= 4
    if turns == 0:
        return c
    if any(s.id in UNROTATABLE for _, s in c.grid.items()):
        return None
    sx, sy, sz = c.grid.size

    def pos(p: Pos) -> Pos:
        return turn_pos(p, sx, sz, turns)

    size = (sz, sy, sx) if turns % 2 else (sx, sy, sz)
    g = Grid(size, c.grid.meta)
    for p, st in c.grid.items():
        g.set(pos(p), turn_state(st, turns))
    g.block_entities = {pos(p): be for p, be in c.grid.block_entities.items()}
    return replace(c, grid=g, inputs=[pos(p) for p in c.inputs], outputs=[pos(p) for p in c.outputs],
                   assembly=c.moved_assembly(pos))


_FACES = [Pos(1, 0, 0), Pos(-1, 0, 0), Pos(0, 1, 0), Pos(0, -1, 0), Pos(0, 0, 1), Pos(0, 0, -1)]
_STEPS = [Pos(dx, dy, dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)) for dy in (1, -1)]


def _touches(p: Pos, states: dict, skip: set) -> bool:
    """A block beside p (six faces), or dust one step up or down next to p (route dust would join it);
    positions in `skip` do not count. The looser test of `connect(tight=True)`."""
    if any(p + f in states and p + f not in skip for f in _FACES):
        return True
    return any(p + s in states and p + s not in skip and states[p + s].id == "redstone_wire" for s in _STEPS)


def connect(src: Candidate, out_index: int, dst: Candidate, in_index: int, layout: Layout,
            tight: bool = False) -> Candidate | None:
    """src output `out_index` drives dst input `in_index`. None if the layout does not fit.

    The line keeps one block of air to both parts, also diagonally. With tight=True it only must not touch
    them (`_touches`): that reaches outputs enclosed by their own part, e.g. the full adder's lamps.

    The result has the inputs of src followed by the other inputs of dst, and the outputs of dst followed by
    the other outputs of src."""
    d = layout.direction
    v = Pos(*d.vec)
    rep = _repeater(d.opposite)
    q = src.outputs[out_index]
    p_dst = dst.inputs[in_index]
    a = {p: s for p, s in src.grid.items()}
    if a[q].id != "redstone_lamp":
        return None
    # the line from the output to the input adapter, as (position, block)
    line: list[tuple[Pos, str]] = []
    k = 1
    if layout.output_mode == "stone":
        line.append((q + v, rep))
        k = 2
    for j in range(layout.gap):
        line.append((Pos(q.x + v.x * (k + j), q.y, q.z + v.z * (k + j)), WIRE))
    k += layout.gap
    if layout.input_mode == "repeater+dust":
        line.append((Pos(q.x + v.x * k, q.y, q.z + v.z * k), rep))
        k += 1
    p = Pos(q.x + v.x * k, q.y, q.z + v.z * k)
    line = [(c, rep if (n % 15 == 14 and blk == WIRE) else blk) for n, (c, blk) in enumerate(line)]
    shift = p - p_dst
    b = {x + shift: s for x, s in dst.grid.items()}
    if any(x in a for x in b):
        return None
    # parts must not touch (one block of air in every direction), apart from the joints
    b_body = {x for x in b if x not in (p, p + DOWN)}
    a_body = {x for x in a if x != q}
    small, large = (a_body, b_body) if len(a_body) <= len(b_body) else (b_body, a_body)
    if not _halo(small).isdisjoint(large):  # some block of b within one block of a
        return None
    cells: dict[Pos, str] = {}
    for n, (c, blk) in enumerate(line):
        if c in a or c in b:
            return None
        cells[c] = blk
        floor = c + DOWN
        if floor in b and floor != p + DOWN:
            return None
        if floor in a and a[floor].id not in SUPPORTS:
            return None
        if floor not in a and floor not in b:
            cells[floor] = STONE
        # route cells (not the joint next to the output) must stay clear of both parts
        joint = n == 0 and layout.output_mode == "stone"
        if joint:
            continue
        if tight:
            if _touches(c, a, {q, floor}) or _touches(c, b, {p, p + DOWN}):
                return None
        elif _near(c, a_body - {floor}) or _near(c, b_body):
            return None
    merged: dict[Pos, object] = dict(a)
    if layout.output_mode == "stone":
        merged[q] = STONE
    else:
        merged[q] = rep if layout.output_mode == "repeater" else WIRE
        if q + DOWN not in a:
            merged[q + DOWN] = STONE
        elif a[q + DOWN].id not in SUPPORTS:
            return None
    merged.update(b)
    merged.update(cells)
    merged[p] = rep if layout.input_mode == "repeater" else WIRE
    if p + DOWN not in merged:
        merged[p + DOWN] = STONE
    # parts: the repeater reading the stone belongs to src, a repeater in front of the input to dst
    asm = Assembly.of(src, "0").merged(Assembly.of(dst, "1").shifted(shift))
    head = [c for c, _ in line[:1]] if layout.output_mode == "stone" else []
    tail = [c for c, _ in line[-1:]] if layout.input_mode == "repeater+dust" else []
    labels = dict(asm.labels)
    lq, lp = labels.get(q, "0"), labels.get(p, "1")
    side = {c: lq for c in head} | {c: lp for c in tail}
    for c in cells:
        labels[c] = side.get(c, side.get(c + UP, "~0"))  # a floor goes with the cell above it
    labels.setdefault(q + DOWN, lq)
    labels.setdefault(p + DOWN, lp)
    asm = Assembly({x: lab for x, lab in labels.items() if x in merged},
                   asm.ends | {"~0": (head[0] if head else q, tail[0] if tail else p)})
    return _assemble(src, out_index, dst, in_index, shift, merged, layout.describe(), assembly=asm)


def _assemble(src: Candidate, out_index: int, dst: Candidate, in_index: int, shift: Pos, merged: dict,
              how: str, settle: bool = True, assembly: Assembly | None = None) -> Candidate:
    """Grid of all `merged` blocks (src coordinates; dst moved by `shift`) with the block entities and ports
    of both parts and their labels (`assembly`, src coordinates), normalised."""
    q, p_dst = src.outputs[out_index], dst.inputs[in_index]
    lo = Pos(*(min(x[i] for x in merged) for i in range(3)))
    hi = Pos(*(max(x[i] for x in merged) for i in range(3)))
    grid = Grid(tuple(h - l + 1 for h, l in zip(hi, lo)))
    for x, s in merged.items():
        grid.set(x - lo, s)
    for x, be in src.grid.block_entities.items():
        if x != q:
            grid.block_entities[x - lo] = be
    for x, be in dst.grid.block_entities.items():
        if x != p_dst:
            grid.block_entities[x + shift - lo] = be
    inputs = [x - lo for x in src.inputs] + [x + shift - lo for k, x in enumerate(dst.inputs) if k != in_index]
    outputs = [x + shift - lo for x in dst.outputs] + [x - lo for k, x in enumerate(src.outputs) if k != out_index]
    from .compact import normalize

    c = Candidate(
        name=f"{src.name} → {dst.name}", grid=grid, inputs=inputs, outputs=outputs,
        description=f"{src.description} Dahinter: {dst.description} ({how})",
        origin=f"komponiert: {src.origin} → {dst.origin}", tags=set(src.tags) | set(dst.tags),
        assembly=None if assembly is None else assembly.shifted(Pos(0, 0, 0) - lo))
    return normalize(c) if settle else c


# ---------------------------------------------------------------------- routed connections
UP = Pos(0, 1, 0)
SPACING = 3  # default air blocks between the bounding boxes of two parts placed side by side
SPACINGS = (1, 2, 3)  # tried by the searches; the simulation decides whether parts this close still work
MARGIN = 3  # the route may leave the joint bounding box by this much
SIGNAL = 15


def _box(blocks) -> tuple[Pos, Pos]:
    blocks = list(blocks)
    return (Pos(*(min(x[i] for x in blocks) for i in range(3))),
            Pos(*(max(x[i] for x in blocks) for i in range(3))))


def _route(start: Pos, goals: set[Pos], solid: set[Pos], keep_clear: set[Pos], lo: Pos, hi: Pos) -> list[Pos] | None:
    """Shortest dust path (the cells the dust stands in) from `start` to one of `goals`, by breadth-first search.

    Moves: flat; one up (the block in front becomes the new floor, the cell above the current dust stays
    empty); one down (the cell in front stays empty). Goals are entered flat. Every cell and its floor keep
    one block of air (also diagonally) to `keep_clear`, except the goal cells; `solid` is never entered.
    The start cell is not checked (it is the joint at the output)."""
    from collections import deque

    (x0, y0, z0), (x1, y1, z1) = lo, hi

    def inside(c: Pos) -> bool:
        return x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and z0 <= c[2] <= z1

    near = _halo(keep_clear)

    def ok(c: Pos) -> bool:
        if not inside(c) or c in solid or c + DOWN in solid:
            return False
        return c in goals or not (c in near or c + DOWN in near)

    prev: dict[Pos, Pos | None] = {start: None}
    queue = deque([start])
    while queue:
        c = queue.popleft()
        if c in goals:
            path = [c]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            return path[::-1]
        for d in HORIZONTAL:
            h = c + Pos(*d.vec)
            steps = [h]
            if c != start:
                if c + UP not in solid:
                    steps.append(h + UP)
                if h not in solid:
                    steps.append(h + DOWN)
            for n in steps:
                if n in prev or (n.y != c.y and n in goals):
                    continue
                if ok(n):
                    prev[n] = c
                    queue.append(n)
    return None


def _direction(a: Pos, b: Pos) -> Direction:
    """Horizontal direction of the step from a to b (b may be one higher or lower)."""
    return next(d for d in HORIZONTAL if (b.x - a.x, b.z - a.z) == (d.vec[0], d.vec[2]))


def _line_blocks(path: list[Pos]) -> dict[Pos, str] | None:
    """Dust along the path (full signal at its first cell), with a repeater on a straight flat cell wherever
    the signal would run out. None if no such cell comes in time."""
    out: dict[Pos, str] = {}
    power = SIGNAL + 1
    for k, c in enumerate(path):
        power -= 1
        prv = path[k - 1] if k > 0 else None
        nxt = path[k + 1] if k + 1 < len(path) else None
        straight = (prv is not None and nxt is not None and prv.y == c.y == nxt.y
                    and _direction(prv, c) == _direction(c, nxt))
        if power <= 2 and straight:
            out[c] = _repeater(_direction(prv, c).opposite)
            power = SIGNAL + 1
        elif power <= 0:
            return None
        else:
            out[c] = WIRE
    return out


def routed(src: Candidate, out_index: int, dst: Candidate, in_index: int, side: Direction, output_mode: str,
           input_mode: str, settle: bool = True, spacing: int = SPACING) -> Candidate | None:
    """dst is placed beside src (on `side`, `spacing` blocks of air between the boxes, same floor height) and
    the output is routed through the free space to the input. None if no route exists.

    output_mode "repeater": a repeater replaces the lamp, reading from one side (all four are tried); the
    dust starts in front of it. "dust": dust replaces the lamp and starts there."""
    q, p_dst = src.outputs[out_index], dst.inputs[in_index]
    a = {x: s for x, s in src.grid.items()}
    if a[q].id != "redstone_lamp":
        return None
    if q + DOWN in a and a[q + DOWN].id not in SUPPORTS:
        return None
    alo, ahi = _box(a)
    sx, _, sz = dst.grid.size
    v = side.vec
    shift = Pos(alo.x if v[0] == 0 else (ahi.x + spacing + 1 if v[0] > 0 else alo.x - spacing - sx),
                alo.y,
                alo.z if v[2] == 0 else (ahi.z + spacing + 1 if v[2] > 0 else alo.z - spacing - sz))
    b = {x + shift: s for x, s in dst.grid.items()}
    p = p_dst + shift
    goals = {p - Pos(*d.vec) for d in HORIZONTAL}
    goals = {g for g in goals if g not in a and g not in b and g + DOWN not in b}
    solid = (set(a) - {q}) | set(b)
    keep = {x for x in a if x not in (q, q + DOWN)} | {x for x in b if x not in (p, p + DOWN)}
    lo, hi = _box(list(a) + list(b))
    lo, hi = lo - Pos(MARGIN, 1, MARGIN), hi + Pos(MARGIN, MARGIN, MARGIN)
    best = None
    starts = [(q, None)] if output_mode == "dust" else [(q + Pos(*d.vec), d) for d in HORIZONTAL]
    for st, d_out in starts:
        if st != q and (st in solid or st + DOWN in solid):
            continue
        path = _route(st, goals, solid | ({q} if st != q else set()), keep, lo, hi)
        if path is not None and (best is None or len(path) < len(best[0])):
            best = (path, d_out)
    if best is None:
        return None
    path, d_out = best
    line = _line_blocks(path)
    if line is None:
        return None
    m: dict[Pos, object] = dict(a)
    m.update(b)
    if d_out is not None:
        m[q] = _repeater(d_out.opposite)
    if q + DOWN not in m:
        m[q + DOWN] = STONE
    for c, blk in line.items():
        m[c] = blk
        if c + DOWN not in m:
            m[c + DOWN] = STONE
    d_in = _direction(path[-1], p)
    m[p] = _repeater(d_in.opposite) if input_mode == "repeater" else WIRE
    if p + DOWN not in m:
        m[p + DOWN] = STONE
    how = (f"Leitung über {len(path)} Blöcke geführt, Lampe → {'Staub' if output_mode == 'dust' else 'Verstärker'}, "
           f"Eingang als {input_mode}")
    asm = Assembly.of(src, "0").merged(Assembly.of(dst, "1").shifted(shift))
    return _assemble(src, out_index, dst, in_index, shift, m, how, settle,
                     assembly=_line_labels(asm, m, q, path, p, "~0"))


def _line_labels(asm: Assembly, blocks: dict, a: Pos, path: list[Pos], b: Pos, name: str) -> Assembly:
    """asm with the line `name` from block a over the cells `path` (a itself may be the first one) to block b:
    the cells and the floors laid for them get the line's label; floors laid under a and b go with them."""
    labels = dict(asm.labels)
    la, lb = labels.get(a), labels.get(b)
    for c in path:
        if c != a:
            labels[c] = name
            labels.setdefault(c + DOWN, name)
    for end, lab in ((a, la), (b, lb)):
        if lab is not None:
            labels.setdefault(end + DOWN, lab)
    return Assembly({x: lab for x, lab in labels.items() if x in blocks}, asm.ends | {name: (a, b)})


def place_beside(c1: Candidate, c2: Candidate, side: Direction, spacing: int = SPACING) -> tuple[Candidate, Pos]:
    """Both candidates in one grid, c2 on `side` of c1 with `spacing` blocks of air between the boxes, floors
    level; nothing is connected. Inputs and outputs: those of c1, then those of c2. Also returns the shift
    of c2 (in the coordinates of the result)."""
    alo, ahi = Pos(0, 0, 0), Pos(*(s - 1 for s in c1.grid.size))
    sx, _, sz = c2.grid.size
    v = side.vec
    shift = Pos(0 if v[0] == 0 else (ahi.x + spacing + 1 if v[0] > 0 else alo.x - spacing - sx), 0,
                0 if v[2] == 0 else (ahi.z + spacing + 1 if v[2] > 0 else alo.z - spacing - sz))
    m = dict(c1.grid.items()) | {x + shift: s for x, s in c2.grid.items()}
    lo = Pos(min(0, shift.x), 0, min(0, shift.z))
    hi = Pos(max(c1.grid.size[0], shift.x + sx) - 1, max(c1.grid.size[1], c2.grid.size[1]) - 1,
             max(c1.grid.size[2], shift.z + sz) - 1)
    grid = Grid(tuple(h - l + 1 for h, l in zip(hi, lo)))
    for x, s in m.items():
        grid.set(x - lo, s)
    for x, be in c1.grid.block_entities.items():
        grid.block_entities[x - lo] = be
    for x, be in c2.grid.block_entities.items():
        grid.block_entities[x + shift - lo] = be
    return Candidate(
        name=f"{c1.name} + {c2.name}", grid=grid,
        inputs=[x - lo for x in c1.inputs] + [x + shift - lo for x in c2.inputs],
        outputs=[x - lo for x in c1.outputs] + [x + shift - lo for x in c2.outputs],
        description=f"{c1.description} Daneben: {c2.description}", origin=f"{c1.origin} + {c2.origin}",
        tags=set(c1.tags) | set(c2.tags),
        assembly=Assembly.of(c1, "0").merged(Assembly.of(c2, "1").shifted(shift)).shifted(Pos(0, 0, 0) - lo)
    ), shift - lo


def wire(c: Candidate, source: Pos, target: Pos, output_mode: str = "repeater",
         input_mode: str = "dust") -> Candidate | None:
    """Route a signal inside one candidate from `source` to the input lever at `target`.

    source is an output lamp (it is replaced: output_mode "repeater" or "dust", the output disappears) or an
    input lever (it stays; dust next to it is tapped, so one lever drives two parts). The target lever is
    replaced by dust or a repeater (`input_mode`) and is no longer an input. None if there is no route."""
    a = dict(c.grid.items())
    src_state, tgt_state = a.get(source), a.get(target)
    if src_state is None or tgt_state is None or tgt_state.id != "lever" or source == target:
        return None
    lamp = src_state.id == "redstone_lamp"
    if not lamp and src_state.id != "lever":
        return None
    if lamp and source + DOWN in a and a[source + DOWN].id not in SUPPORTS:
        return None
    goals = {target - Pos(*d.vec) for d in HORIZONTAL}
    goals = {g for g in goals if g not in a and (g + DOWN not in a or a[g + DOWN].id in SUPPORTS)}
    solid = set(a) - ({source} if lamp else set())
    keep = {x for x in a if x not in (source, source + DOWN, target, target + DOWN)}
    lo, hi = Pos(0, 0, 0) - Pos(MARGIN, 1, MARGIN), Pos(*c.grid.size) + Pos(MARGIN - 1, MARGIN, MARGIN - 1)
    if lamp and output_mode == "dust":
        starts = [(source, None)]
    else:  # a repeater on the lamp (reading from the side opposite to d), or a tap next to the lever
        starts = [(source + Pos(*d.vec), d) for d in HORIZONTAL]
    best = None
    for st, d_out in starts:
        if st != source and (st in a or (st + DOWN in a and a[st + DOWN].id not in SUPPORTS)):
            continue
        path = _route(st, goals, solid | ({source} if st != source else set()), keep, lo, hi)
        if path is not None and (best is None or len(path) < len(best[0])):
            best = (path, d_out)
    if best is None:
        return None
    path, d_out = best
    line = _line_blocks(path)
    if line is None:
        return None
    m: dict[Pos, object] = dict(a)
    if lamp:
        if d_out is not None:
            m[source] = _repeater(d_out.opposite)
        if source + DOWN not in m:
            m[source + DOWN] = STONE
    for x, blk in line.items():
        if x != source:
            m[x] = blk
        if x + DOWN not in m:
            m[x + DOWN] = STONE
    d_in = _direction(path[-1], target)
    m[target] = _repeater(d_in.opposite) if input_mode == "repeater" else WIRE
    if target + DOWN not in m:
        m[target + DOWN] = STONE
    lo = Pos(*(min(x[i] for x in m) for i in range(3)))
    hi = Pos(*(max(x[i] for x in m) for i in range(3)))
    grid = Grid(tuple(h - l + 1 for h, l in zip(hi, lo)))
    for x, s in m.items():
        grid.set(x - lo, s)
    for x, be in c.grid.block_entities.items():
        if x not in (source, target):
            grid.block_entities[x - lo] = be
    from dataclasses import replace

    from .compact import normalize

    asm = None
    if c.assembly is not None:
        asm = _line_labels(c.assembly, m, source, path, target, c.assembly.next_line()).shifted(Pos(0, 0, 0) - lo)
    how = "abgegriffen" if not lamp else ("Lampe → Staub" if output_mode == "dust" else "Lampe → Verstärker")
    return normalize(replace(
        c, grid=grid, inputs=[x - lo for x in c.inputs if x != target],
        outputs=[x - lo for x in c.outputs if not (lamp and x == source)],
        description=f"{c.description} (Leitung über {len(path)} Blöcke, {how})", assembly=asm))


MAX_GAP = 8


def layouts(max_gap: int = MAX_GAP) -> list[Layout]:
    """All layouts, shortest line first."""
    return [Layout(d, g, m, o) for g in range(0, max_gap + 1) for o in OUTPUT_MODES for m in INPUT_MODES
            for d in HORIZONTAL]


def chains(src: Candidate, out_index: int, dst: Candidate, in_index: int, max_gap: int = MAX_GAP):
    """Every fitting composition (dst turned in all four ways), shortest line first. A generator, so the
    caller can stop at the first one that works."""
    turned = [t for t in (rotate(dst, k) for k in range(4)) if t is not None]
    any_found = False
    for lay in layouts(max_gap):
        for t in turned:
            c = connect(src, out_index, t, in_index, lay)
            if c is not None:
                any_found = True
                yield lay, c
    if not any_found:  # the output may be enclosed by its own part: lines that only must not touch it
        for lay in layouts(max_gap):
            for t in turned:
                c = connect(src, out_index, t, in_index, lay, tight=True)
                if c is not None:
                    yield lay, c
    found = []
    for k, t in enumerate(turned):
        for side in HORIZONTAL:
            for out_mode in ("repeater", "dust"):
                for in_mode in ("dust", "repeater"):
                    for spacing in SPACINGS:
                        c = routed(src, out_index, t, in_index, side, out_mode, in_mode, settle=False,
                                   spacing=spacing)
                        if c is not None:
                            found.append(((c.volume, c.block_count),
                                          (k, side.label, out_mode, in_mode, spacing), c))
    found.sort(key=lambda f: f[:2])
    from .compact import normalize

    for _, how, c in found:  # settled only when the caller gets that far
        yield how, normalize(c)
