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
from .candidate import Candidate

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


DOWN = Pos(0, -1, 0)
_CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
UNROTATABLE = {"rail", "powered_rail", "detector_rail", "activator_rail"}  # shapes not handled


def rotate(c: Candidate, turns: int) -> Candidate | None:
    """The candidate turned clockwise (seen from above) by `turns` quarter turns; None if a block cannot be
    turned. Directional properties (facing, dust sides, axis) are turned with it."""
    from dataclasses import replace

    from ..model import BlockState

    turns %= 4
    if turns == 0:
        return c
    if any(s.id in UNROTATABLE for _, s in c.grid.items()):
        return None
    sx, sy, sz = c.grid.size

    def pos(p: Pos) -> Pos:
        x, z, w, d = p.x, p.z, sx, sz
        for _ in range(turns):
            x, z, w, d = d - 1 - z, x, d, w
        return Pos(x, p.y, z)

    def state(st: BlockState) -> BlockState:
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

    size = (sz, sy, sx) if turns % 2 else (sx, sy, sz)
    g = Grid(size, c.grid.meta)
    for p, st in c.grid.items():
        g.set(pos(p), state(st))
    g.block_entities = {pos(p): be for p, be in c.grid.block_entities.items()}
    return replace(c, grid=g, inputs=[pos(p) for p in c.inputs], outputs=[pos(p) for p in c.outputs])


def connect(src: Candidate, out_index: int, dst: Candidate, in_index: int, layout: Layout) -> Candidate | None:
    """src output `out_index` drives dst input `in_index`. None if the layout does not fit.

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
    if any(_near(x, a_body) for x in b_body):
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
        if not joint and (_near(c, a_body - {floor}) or _near(c, b_body)):
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
    return _assemble(src, out_index, dst, in_index, shift, merged, layout.describe())


def _assemble(src: Candidate, out_index: int, dst: Candidate, in_index: int, shift: Pos, merged: dict,
              how: str) -> Candidate:
    """Grid of all `merged` blocks (src coordinates; dst moved by `shift`) with the block entities and ports
    of both parts, normalised."""
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

    return normalize(Candidate(
        name=f"{src.name} → {dst.name}", grid=grid, inputs=inputs, outputs=outputs,
        description=f"{src.description} Dahinter: {dst.description} ({how})",
        origin=f"komponiert: {src.origin} → {dst.origin}", tags=set(src.tags) | set(dst.tags)))


# ---------------------------------------------------------------------- routed connections
UP = Pos(0, 1, 0)
SPACING = 3  # air blocks between the bounding boxes of the two parts in a routed layout
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

    def inside(c: Pos) -> bool:
        return all(lo[i] <= c[i] <= hi[i] for i in range(3))

    def ok(c: Pos) -> bool:
        if not inside(c) or c in solid or c + DOWN in solid:
            return False
        return c in goals or not (_near(c, keep_clear) or _near(c + DOWN, keep_clear))

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
           input_mode: str) -> Candidate | None:
    """dst is placed beside src (on `side`, SPACING blocks of air between the boxes, same floor height) and
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
    shift = Pos(alo.x if v[0] == 0 else (ahi.x + SPACING + 1 if v[0] > 0 else alo.x - SPACING - sx),
                alo.y,
                alo.z if v[2] == 0 else (ahi.z + SPACING + 1 if v[2] > 0 else alo.z - SPACING - sz))
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
    return _assemble(src, out_index, dst, in_index, shift, m, how)


MAX_GAP = 8


def layouts(max_gap: int = MAX_GAP) -> list[Layout]:
    """All layouts, shortest line first."""
    return [Layout(d, g, m, o) for g in range(0, max_gap + 1) for o in OUTPUT_MODES for m in INPUT_MODES
            for d in HORIZONTAL]


def chains(src: Candidate, out_index: int, dst: Candidate, in_index: int, max_gap: int = MAX_GAP):
    """Every fitting composition (dst turned in all four ways), shortest line first. A generator, so the
    caller can stop at the first one that works."""
    turned = [t for t in (rotate(dst, k) for k in range(4)) if t is not None]
    for lay in layouts(max_gap):
        for t in turned:
            c = connect(src, out_index, t, in_index, lay)
            if c is not None:
                yield lay, c
    found = []
    for k, t in enumerate(turned):
        for side in HORIZONTAL:
            for out_mode in ("repeater", "dust"):
                for in_mode in ("dust", "repeater"):
                    c = routed(src, out_index, t, in_index, side, out_mode, in_mode)
                    if c is not None:
                        found.append(((c.volume, c.block_count), (k, side.label, out_mode, in_mode), c))
    found.sort(key=lambda f: f[:2])
    for _, how, c in found:
        yield how, c
