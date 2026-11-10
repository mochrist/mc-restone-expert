"""Shrink a correct candidate step by step; every step is kept only if the simulation still meets the spec.

Moves (greedy, repeated until nothing helps):
1. cut a whole plane (x = k, y = k or z = k) out of the grid and close the gap,
2. remove single blocks that are not inputs or outputs,
3. crop the grid to the bounding box of its blocks.

Cutting planes changes block connections (dust shapes, attachments). Dust and other shape-dependent
states are recomputed by placing the grid in the simulator and letting shape updates run (`normalize`).
"""

from __future__ import annotations

from dataclasses import replace

from ..model import Grid, Pos
from ..sim.constants import UPDATE_ALL
from ..sim.runner import ORACLE_ORIGIN
from ..sim.core import World
from .candidate import Candidate
from .evaluate import Constraints, evaluate_any
from .spec import Spec

MAX_EVALUATIONS = 400


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


def _without(c: Candidate, pos: Pos) -> Candidate:
    g = Grid(tuple(c.grid.size), c.grid.meta)
    for p, s in c.grid.items():
        if p != pos:
            g[p] = s
    g.block_entities = {p: be for p, be in c.grid.block_entities.items() if p != pos}
    return replace(c, grid=g)


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

    def works(cand: Candidate) -> bool:
        if deadline is not None and time.perf_counter() > deadline:
            budget[0] = 0
        if budget[0] <= 0:
            return False
        budget[0] -= 1
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
    improved = True
    while improved and budget[0] > 0:
        improved = False
        for axis, label in ((1, "y"), (0, "x"), (2, "z")):
            k = current.grid.size[axis] - 1
            while k >= 0 and budget[0] > 0:
                cut = _cut(current, axis, k)
                if cut is not None:
                    cut = normalize(cut)
                    if works(cut):
                        log.append(f"Ebene {label}={k} entfernt")
                        current, improved = cut, True
                k -= 1
        for p, s in sorted(current.grid.items()):
            if budget[0] <= 0:
                break
            if p in current.inputs or p in current.outputs:
                continue
            cand = normalize(_without(current, p))
            if works(cand):
                log.append(f"{s.id} bei {p} entfernt")
                current, improved = cand, True
        cropped = crop(current)
        if cropped is not current:
            current = cropped
    if budget[0] <= 0:
        log.append("Abbruch: Zeit- oder Bewertungslimit erreicht")
    return replace(current, name=f"{c.name}-kompakt", origin=f"kompaktiert aus {c.origin or c.name}"), log
