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


def detour_buffer() -> Candidate:
    """Lever - dust - lamp (under the last dust), but the dust makes a U-turn two rows deep instead of
    running straight."""
    g = Grid((4, 2, 3))
    g[0, 0, 0] = "stone"
    g[0, 1, 0] = "lever[face=floor,facing=east,powered=false]"
    for p in [(1, 1, 0), (1, 1, 1), (1, 1, 2), (2, 1, 2), (3, 1, 2), (3, 1, 1), (3, 1, 0)]:
        g[p] = "redstone_wire[east=none,north=none,power=0,south=none,west=none]"
        g[p[0], 0, p[2]] = "stone"
    g[3, 0, 0] = "redstone_lamp[lit=false]"
    return normalize(Candidate("detour", g, [Pos(0, 1, 0)], [Pos(3, 0, 0)]))


def test_lines_finds_the_detour_and_reroutes_it():
    from redstone.design.compact import lines, rerouted

    c = detour_buffer()
    found = lines(c)
    assert [(a, len(inner), b) for a, inner, b in found] == [(Pos(1, 1, 0), 5, Pos(3, 1, 0))]
    short = rerouted(c, *found[0])
    assert short is not None and short.block_count == 2 + 3 + 3  # lever on stone, 3 dust on stone, stone, lamp
    assert evaluate(normalize(short), from_functions(["a"], {"y": "a"})).ok


def test_compact_straightens_a_detour():
    spec = from_functions(["a"], {"y": "a"})
    small, log = compact(detour_buffer(), spec)
    assert evaluate(small, spec).ok
    assert small.grid.size.z == 1, (small.grid.size, log)


def two_inverters() -> Candidate:
    """Two independent inverters (lever, block, torch, lamp), the second one two rows away and one block up:
    no plane between them can be cut, but moving the second part closes the gap."""
    g = Grid((4, 3, 3))
    for z, y in ((0, 0), (2, 1)):
        g[0, y, z] = "lever[face=wall,facing=west,powered=false]"
        g[1, y, z] = "stone"
        g[2, y, z] = "redstone_wall_torch[facing=east,lit=true]"
        g[3, y, z] = "redstone_lamp[lit=true]"
    return normalize(Candidate("two", g, [Pos(0, 0, 0), Pos(0, 1, 2)], [Pos(3, 0, 0), Pos(3, 1, 2)]))


def test_shifts_only_list_smaller_boxes():
    from redstone.design.compact import shifted, shifts

    c = two_inverters()
    moves = shifts(c)
    assert moves and all(shifted(c, part, v).volume < c.volume for _, part, v in moves)
    second = {p for p, _ in c.grid.items() if p.z == 2}
    assert any(set(part) == second and v == Pos(0, -1, 0) for _, part, v in moves)


def test_compact_moves_parts_together():
    spec = from_functions(["a", "b"], {"y": "not a", "z": "not b"})
    c = two_inverters()
    assert evaluate(c, spec).ok
    small, log = compact(c, spec)
    assert evaluate(small, spec).ok
    assert small.volume < c.volume and any("verschoben" in s for s in log), log
