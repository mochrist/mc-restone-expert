"""Compaction keeps the function and removes slack (M4)."""

from redstone.design.candidate import Candidate
from redstone.design.compact import compact, normalize
from redstone.design.evaluate import evaluate
from redstone.design.spec import from_functions
from redstone.model import Grid, Pos


def spaced_inverter() -> Candidate:
    """Lever - block - torch, then three dust before the lamp, with an empty row and a spare block."""
    g = Grid((8, 2, 3))
    for x in range(8):
        g[x, 0, 0] = "stone"
    g[0, 1, 0] = "lever[face=floor,facing=east,powered=false]"
    g[1, 1, 0] = "redstone_wire[east=side,north=none,power=15,south=none,west=side]"  # stale on purpose
    g[2, 1, 0] = "stone"
    g[3, 1, 0] = "redstone_wall_torch[facing=east,lit=true]"
    for x in (4, 5, 6):
        g[x, 1, 0] = "redstone_wire[east=side,north=none,power=0,south=none,west=side]"
    g[7, 1, 0] = "redstone_lamp[lit=false]"
    g[4, 0, 2] = "stone"  # unrelated block two rows away
    return Candidate("spaced", g, [Pos(0, 1, 0)], [Pos(7, 1, 0)])


def test_normalize_settles_stored_state():
    n = normalize(spaced_inverter())
    assert n.grid.get((1, 1, 0)).get("power") == "0"
    assert n.grid.get((7, 1, 0)).get_bool("lit")


def test_compact_shrinks_and_stays_correct():
    spec = from_functions(["a"], {"y": "not a"})
    c = spaced_inverter()
    small, log = compact(normalize(c), spec)
    ev = evaluate(small, spec)
    assert ev.ok, ev.errors
    assert small.volume < c.volume
    assert small.grid.size.z == 1 and small.grid.size.x <= 5, (small.grid.size, log)
