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
    assert small.volume <= 4 * 2 * 1, (small.grid.size, log)  # as small as the straight line (or a turned part)


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


def stair_buffer() -> Candidate:
    """Lever - dust - a staircase of dust up four blocks - dust - lamp: the lamp sits high above and far from
    the lever. Shifting half-spaces does not help (the stair steps collide), moving the lamp part does."""
    g = Grid((10, 6, 1))
    g[0, 0, 0] = "stone"
    g[0, 1, 0] = "lever[face=floor,facing=east,powered=false]"
    dust = "redstone_wire[east=none,north=none,power=0,south=none,west=none]"
    for x, y in ((1, 1), (2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, 5), (8, 5)):
        g[x, y, 0] = dust
        g[x, y - 1, 0] = "stone"
    g[9, 5, 0] = "redstone_lamp[lit=false]"
    return normalize(Candidate("stair", g, [Pos(0, 1, 0)], [Pos(9, 5, 0)]))


def test_parts_are_split_at_plain_lines():
    from redstone.design.compact import parts

    groups, found, _ = parts(stair_buffer())
    assert len(found) == 1 and len(found[0][1]) == 6, found
    assert sorted(len(g) for g in groups) == [3, 4]  # lamp, dust and its floor; lever, dust and two floors


def test_relocations_are_smaller_and_one_still_works():
    from redstone.design.compact import relocations

    spec = from_functions(["a"], {"y": "a"})
    c = stair_buffer()
    assert evaluate(c, spec).ok
    found = list(relocations(c))
    assert found and all(cand.volume < c.volume for _, cand in found)
    assert [m for m, _ in found] == [m for m, _ in relocations(c)]  # deterministic
    assert any(evaluate(normalize(cand), spec).ok for _, cand in found[:3])


def test_relocations_turn_blocks():
    """The lamp part placed beside the lever needs a turn when it ends up on another side."""
    from redstone.design.compact import relocations

    assert any("gedreht" in m for m, _ in relocations(stair_buffer()))


def test_compact_moves_a_building_block():
    spec = from_functions(["a"], {"y": "a"})
    c = stair_buffer()
    small, log = compact(c, spec)
    assert evaluate(small, spec).ok
    assert any("Baustein" in s for s in log), log
    assert small.volume <= 10, (small.grid.size, log)


def test_dust_path_does_not_cut_itself():
    """Climbing in place (up, up, back) would put the floor of the top dust right over the bottom one, which
    cuts the step between them: the search must not lay such a path."""
    from redstone.design.compact import _clashes

    a, b, c = Pos(0, 0, 0), Pos(0, 1, 1), Pos(0, 2, 0)
    prev = {a: None, b: a}
    assert _clashes(c, b, prev)  # c's floor (0,1,0) lies right over a
    assert not _clashes(Pos(0, 2, 2), b, prev)  # straight on up the stairs
    assert _clashes(Pos(1, 1, 0), b, prev)  # beside a: a shortcut


def test_boosts_put_repeaters_on_long_lines():
    from redstone.design.compact import FULL_RUN, _boosts

    straight = [Pos(x, 0, 0) for x in range(30)]
    assert _boosts(straight[:10], 12, 12, False) == []
    reps = _boosts(straight, 12, 12, False)
    assert reps and reps[0] <= 12 and all(j - i - 1 <= FULL_RUN for i, j in zip(reps, reps[1:]))
    assert len(straight) - 1 - reps[-1] <= 12
    assert _boosts(straight[:5], 12, 12, True) == [3]  # a repeater is needed: as late as possible
    bent = [Pos(0, 0, 0), Pos(1, 0, 0), Pos(1, 0, 1), Pos(2, 0, 1)]
    assert _boosts(bent, 12, 12, True) is None  # no straight cell for a repeater
