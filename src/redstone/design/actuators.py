"""Other things than a lamp at the output of a design: door, piston, note block, dispenser ...

The search designs and proves circuits with redstone lamps as outputs. `with_output` gives every output another
block that reacts to power and checks in the simulator that it switches like the lamp did: same state after
every input change and the same number of switch-ons. Three ways are tried: the block in place of the lamp, the
block next to the lamp behind a repeater (the lamp stays as an indicator), and the lamp replaced by redstone dust
with the repeater and the block behind it. The dust is for a lamp lit by a torch beside it: such a lamp is not a
powered block, so a repeater behind it stays off, and a piston in its place is held out by the torch (quasi-
connectivity). Returns None (with a German reason) when nothing fits or follows."""

from __future__ import annotations

import itertools
import random
from dataclasses import replace

from ..model import BlockState, Grid, Pos
from .candidate import Candidate

# name -> (German label, block at the output, block above it or None, needs a solid block below)
ACTUATORS: dict[str, tuple[str, str, str | None, bool]] = {
    "note_block": ("Notenblock", "note_block[instrument=harp,note=12,powered=false]", None, False),
    "dispenser": ("Spender", "dispenser[facing=up,triggered=false]", None, False),
    "dropper": ("Werfer", "dropper[facing=up,triggered=false]", None, False),
    "iron_trapdoor": ("Eisenfalltür", "iron_trapdoor[facing=north,half=bottom,open=false,powered=false,"
                                      "waterlogged=false]", None, False),
    "iron_door": ("Eisentür", "iron_door[facing=north,half=lower,hinge=left,open=false,powered=false]",
                  "iron_door[facing=north,half=upper,hinge=left,open=false,powered=false]", True),
    "piston": ("Kolben (nach oben)", "piston[extended=false,facing=up]", "air", False),
    "sticky_piston": ("Klebriger Kolben (nach oben)", "sticky_piston[extended=false,facing=up]", "air", False),
}
ON_PROPS = ("lit", "powered", "open", "extended", "triggered")
SIDES = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
SETTLE = 80  # ticks watched after every input change
MAX_COMBOS = 16


def _on(state: BlockState) -> bool:
    return any(v == "true" for k, v in state.props if k in ON_PROPS)


class _Fit(Exception):
    """The block does not fit this way (German reason)."""


def _built(cand: Candidate, cells: dict[tuple[int, int, int], str], outputs: list[tuple[int, int, int]],
           inputs: list[tuple[int, int, int]] | None = None) -> Candidate:
    """Candidate from loose cells (any coordinates): grid at their min corner, ports moved along. `inputs`: new
    input cells (default: the old ones)."""
    lo = [min(c[i] for c in cells) for i in range(3)]
    hi = [max(c[i] for c in cells) for i in range(3)]
    grid = Grid(tuple(h - l + 1 for l, h in zip(lo, hi)))
    for c, s in cells.items():
        if s != "air":
            grid.set(Pos(c[0] - lo[0], c[1] - lo[1], c[2] - lo[2]), s)
    move = lambda c: Pos(c[0] - lo[0], c[1] - lo[1], c[2] - lo[2])  # noqa: E731
    return replace(cand, grid=grid, inputs=[move(tuple(p)) for p in (cand.inputs if inputs is None else inputs)], outputs=[move(c) for c in outputs],
                   assembly=None)


DUST = "redstone_wire[east=none,north=none,power=0,south=none,west=none]"


def _variant(cand: Candidate, kind: str, side: str | None, flip: bool, dust: bool = False) -> Candidate:
    """side None: the block replaces the lamp. Else: lamp -> repeater -> block towards that side; dust: the
    lamp becomes redstone dust (on a solid block) in front of the repeater."""
    from ..sim import blockdata

    label, block, above, support = ACTUATORS[kind]
    cells = {tuple(p): str(s) for p, s in cand.grid.items() if s.id != "air"}
    free = lambda c: cells.get(c, "air") == "air"  # noqa: E731
    outputs = []
    for p in cand.outputs:
        x, y, z = p
        if cand.grid.get(p).id != "redstone_lamp":
            raise _Fit(f"der Ausgang bei {(x, y, z)} ist keine Lampe")
        at = (x, y, z)
        if side is not None:
            dx, dz = SIDES[side]
            rep, at = (x + dx, y, z + dz), (x + 2 * dx, y, z + 2 * dz)
            if not (free(rep) and free(at)):
                raise _Fit(f"neben dem Ausgang ist kein Platz für {label}")
            floor = (rep[0], y - 1, rep[2])
            if free(floor):
                cells[floor] = "stone"
            facing = side if flip else {"north": "south", "south": "north", "west": "east", "east": "west"}[side]
            cells[rep] = f"repeater[delay=1,facing={facing},locked=false,powered=false]"
            if dust:
                under = (x, y - 1, z)
                if free(under):
                    cells[under] = "stone"
                elif not blockdata.is_conductor(BlockState.parse(cells[under])):
                    raise _Fit("unter dem Ausgang ist kein fester Block für Redstone")
                cells[(x, y, z)] = DUST
        below = (at[0], y - 1, at[2])
        if support:
            if free(below):
                cells[below] = "stone"  # the check in the simulator tells whether this disturbs the circuit
            elif not blockdata.is_conductor(BlockState.parse(cells[below])):
                raise _Fit(f"{label} braucht einen festen Block unter sich")
        if above is not None:
            up = (at[0], y + 1, at[2])
            if not free(up):
                raise _Fit(f"über dem Ausgang ist kein Platz für {label}")
            cells[up] = above
        cells[at] = block
        outputs.append(at)
    return _built(cand, cells, outputs)


def _traces(cand: Candidate, steps: list[list[int]]) -> list[tuple[tuple[bool, ...], tuple[int, ...]]]:
    """For every step (inputs to use): the outputs' state after SETTLE ticks and how often each switched on."""
    from ..sim import blocks  # noqa: F401  (registers block behaviours)
    from ..sim.core import World
    from ..sim.runner import ORACLE_ORIGIN, apply_input

    world = World()
    world.place_grid(cand.grid, ORACLE_ORIGIN)
    outs = [p + ORACLE_ORIGIN for p in cand.outputs]
    out = []
    last = [_on(world.get(p)) for p in outs]
    for step in steps:
        for i in step:
            apply_input(world, "use", cand.inputs[i] + ORACLE_ORIGIN, None)
        rises = [0] * len(outs)
        for _ in range(SETTLE):
            world.tick()
            now = [_on(world.get(p)) for p in outs]
            for k, (a, b) in enumerate(zip(last, now)):
                rises[k] += (not a) and b
            last = now
        out.append((tuple(last), tuple(rises)))
    return out


def _steps(n: int) -> list[list[int]]:
    if n == 0:
        return [[], [], []]  # a clock: just watch
    if 2 ** n <= MAX_COMBOS:  # Gray code: every combination, one input changed at a time, and back
        gray = [i ^ (i >> 1) for i in range(2 ** n)]
        seq = [[(a ^ b).bit_length() - 1] for a, b in itertools.pairwise(gray + gray[:1])]
        return seq + seq
    rng = random.Random(1)
    return [[rng.randrange(n)] for _ in range(48)]


def with_output(cand: Candidate, kind: str) -> tuple[Candidate | None, str]:
    """cand with `kind` (a key of ACTUATORS) at its outputs, checked against the lamp version."""
    if kind not in ACTUATORS:
        return None, f"unbekannter Ausgang {kind!r}"
    label = ACTUATORS[kind][0]
    steps = _steps(len(cand.inputs))
    want = _traces(cand, steps)
    why = ""
    ways = [(None, False, False)] + [(s, f, d) for d in (False, True) for s in SIDES for f in (False, True)]
    for side, flip, dust in ways:
        try:
            new = _variant(cand, kind, side, flip, dust)
        except _Fit as e:
            why = why or str(e)
            continue
        if _traces(new, steps) == want:
            how = ("statt der Lampe" if side is None else
                   "statt der Lampe hinter Redstone und einem Verstärker" if dust else
                   "neben der Lampe hinter einem Verstärker (die Lampe bleibt als Anzeige)")
            note = f"Ausgang: {label} {how}; im Simulator gegen die Lampen-Fassung geprüft."
            return replace(new, description=f"{cand.description} {note}".strip()), note
        why = f"{label} schaltet an diesem Entwurf nicht wie die Lampe"
    return None, why
