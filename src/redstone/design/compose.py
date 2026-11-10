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
        description=f"{src.description} Dahinter: {dst.description} ({layout.describe()})",
        origin=f"komponiert: {src.origin} → {dst.origin}", tags=set(src.tags) | set(dst.tags)))


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
