"""Unit tests for redstone wire (knowledge/components/redstone-wire.md, DUST-xxx), read from the 26.3 code."""

import pytest

from redstone.model import BlockState, Direction, Pos
from redstone.sim import World, core
from redstone.sim.blocks.wire import JavaHashSet, block_pos_hash, update_order
from redstone.sim.constants import UPDATE_ALL

python_core_only = pytest.mark.skipif(
    core.active() != "python", reason="needs Python internals (own Block subclasses / monkeypatching); Rust is covered by the golden traces")

D = Direction
STONE = BlockState.parse("stone")


def _wire_block(world: World):
    return world.registry.get("minecraft:redstone_wire")


def _floor(world: World, x0: int, x1: int, z0: int = 0, z1: int = 0, y: int = 0) -> None:
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            world.blocks[Pos(x, y, z)] = STONE


def place_dust(world: World, pos: Pos) -> BlockState:
    """Like a player placing dust: getStateForPlacement = getConnectionState(crossState), then setBlock(3)."""
    wire = _wire_block(world)
    state = wire.get_connection_state(world, wire.cross_state(), pos)
    world.set_block(pos, state, UPDATE_ALL)
    return world.get(pos)


def power(world: World, pos: Pos) -> int:
    return world.get(pos).get_int("power")


def sides(state: BlockState) -> dict[str, str]:
    return {d: state.get(d) for d in ("north", "east", "south", "west")}


# ---------------------------------------------------------------------- DUST-018: HashSet order
# Expected orders computed by hand from java.util.HashMap: bucket = (h ^ (h >>> 16)) & 15 with
# h = Vec3i#hashCode = (y + 31 * z) * 31 + x, ties in insertion order (self, D, U, N, S, W, E).
SELF, DOWN, UP, NORTH, SOUTH, WEST, EAST = "self", "D", "U", "N", "S", "W", "E"
_OFFSETS = {SELF: (0, 0, 0), DOWN: (0, -1, 0), UP: (0, 1, 0), NORTH: (0, 0, -1), SOUTH: (0, 0, 1),
            WEST: (-1, 0, 0), EAST: (1, 0, 0)}


@pytest.mark.parametrize("pos, expected", [
    # self 1984 -> 0; D 1953, S 2945, E 1985 -> 1; U 2015, N 1023, W 1983 -> 15 (knowledge DUST-018)
    ((0, 64, 0), [SELF, DOWN, SOUTH, EAST, UP, NORTH, WEST]),
    # everything shifted by one: U, N, W -> 0; self -> 1; D, S, E -> 2 (knowledge DUST-018)
    ((1, 64, 0), [UP, NORTH, WEST, SELF, DOWN, SOUTH, EAST]),
    # oracle origin: U 6231, N 5239, W 6199 -> 7; self 6200 -> 8; D 6169, S 7161, E 6201 -> 9
    ((0, 200, 0), [UP, NORTH, WEST, SELF, DOWN, SOUTH, EAST]),
    # negative coordinates, positive hashes: U 1053, N 61, W 1021 -> 13; self 1022 -> 14; D 991, S 1983, E 1023 -> 15
    ((-1, 64, -1), [UP, NORTH, WEST, SELF, DOWN, SOUTH, EAST]),
    # negative hashes (upper 16 bits all ones, spread flips the low bits): self -1984 = 0xFFFFF840 -> 0x07BF -> 15;
    # D -2015 -> 0x07DE -> 14; U -1953 -> 0x07A0 -> 0; N -2945 -> 0x0B80 -> 0; S -1023 -> 0x03FE -> 14;
    # W -1985 -> 0x07C0 -> 0; E -1983 -> 0x07BE -> 14
    ((0, -64, 0), [UP, NORTH, WEST, DOWN, SOUTH, EAST, SELF]),
    # large x, the spread (h >>> 16 = 0xF) changes the buckets: self 0xF4240 -> 0xF424F -> 15;
    # D 0xF4221 -> 14; U 0xF425F -> 0; N 0xF3E7F -> 0; S 0xF4601 -> 14; W 0xF423F -> 0; E 0xF4241 -> 14
    # (without the spread it would be self, D, S, E, U, N, W)
    ((1000000, 0, 0), [UP, NORTH, WEST, DOWN, SOUTH, EAST, SELF]),
])
def test_update_order_matches_java_hashset(pos, expected):
    p = Pos(*pos)
    assert update_order(p) == [p + _OFFSETS[k] for k in expected]


@pytest.mark.parametrize("pos, h", [
    ((0, 64, 0), 1984), ((1, 2, 3), (2 + 93) * 31 + 1), ((0, -64, 0), -1984), ((-1, 64, -1), 1022),
    ((30_000_000, 319, 30_000_000), -1_204_761_183),  # int overflow: 930000319 * 31 wraps around
])
def test_block_pos_hash_is_java_int_arithmetic(pos, h):
    assert block_pos_hash(pos) == h


def test_hashset_resize_keeps_bucket_order():
    """Identity hash: 13 entries exceed the threshold 12 and the table grows to 32 (lo/hi split)."""
    s = JavaHashSet(hash_fn=lambda v: v)
    for v in [16, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        s.add(v)
    assert list(s) == [16, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] and s.capacity == 16
    s.add(11)
    assert s.capacity == 32
    assert list(s) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 16]
    assert not s.add(16) and len(s) == 13


def test_hashset_long_bin_resizes_instead_of_treeifying():
    """A 9th entry in one bin of a table smaller than 64 triggers treeifyBin, which only resizes."""
    s = JavaHashSet(hash_fn=lambda v: v)
    for v in range(0, 16 * 9, 16):
        s.add(v)
    assert s.capacity == 32
    assert list(s) == [0, 32, 64, 96, 128, 16, 48, 80, 112]


@python_core_only
def test_power_change_updates_neighbors_in_hashset_order():
    """DUST-017/018: seven updateNeighborsAt calls, in the order of update_order."""
    w = World()
    pos = Pos(0, 64, 0)
    w.blocks[pos.offset(D.DOWN)] = STONE
    w.blocks[pos] = BlockState.parse("redstone_wire[east=side,north=none,power=0,south=none,west=side]")
    w.blocks[pos.offset(D.WEST)] = BlockState.parse("redstone_block")
    calls = []
    w.update_neighbors_at = lambda p, source, skip=None: calls.append(p)
    _wire_block(w).update_power_strength(w, pos, w.get(pos))
    assert power(w, pos) == 15
    assert calls == update_order(pos)
    calls.clear()
    _wire_block(w).update_power_strength(w, pos, w.get(pos))  # unchanged power: nothing (DUST-016)
    assert calls == []


# ---------------------------------------------------------------------- power
def test_power_drops_by_one_per_step():
    w = World()
    _floor(w, 0, 17)
    for x in range(1, 18):
        place_dust(w, Pos(x, 1, 0))
    w.set_block(Pos(0, 1, 0), BlockState.parse("redstone_block"))
    assert [power(w, Pos(x, 1, 0)) for x in range(1, 18)] == list(range(15, -1, -1)) + [0]
    w.set_block(Pos(0, 1, 0), BlockState.parse("air"))
    assert all(power(w, Pos(x, 1, 0)) == 0 for x in range(1, 18))


def test_dust_feeds_up_a_step_and_down_a_step():
    """DUST-013: horizontal and diagonal wire signal, minus one per dust."""
    w = World()
    _floor(w, 0, 4)
    w.blocks[Pos(2, 1, 0)] = STONE  # step up
    place_dust(w, Pos(1, 1, 0))
    place_dust(w, Pos(2, 2, 0))
    place_dust(w, Pos(3, 1, 0))
    w.set_block(Pos(0, 1, 0), BlockState.parse("redstone_block"))
    assert [power(w, Pos(1, 1, 0)), power(w, Pos(2, 2, 0)), power(w, Pos(3, 1, 0))] == [15, 14, 13]
    assert world_side(w, Pos(1, 1, 0), "east") == "up"


def world_side(w, pos, side):
    return w.get(pos).get(side)


def test_block_signal_ignores_dust_powering_a_block():
    """DUST-015: dust powers the stone it points into, but other dust does not read that power back."""
    w = World()
    _floor(w, 0, 3)
    w.blocks[Pos(2, 1, 0)] = STONE
    place_dust(w, Pos(1, 1, 0))
    place_dust(w, Pos(2, 2, 0))  # on top of the stone that dust (1,1,0) points into
    w.set_block(Pos(0, 1, 0), BlockState.parse("redstone_block"))
    assert power(w, Pos(1, 1, 0)) == 15
    assert w.get_direct_signal_to(Pos(2, 1, 0)) == 15  # the stone is powered by the dust
    assert power(w, Pos(2, 2, 0)) == 14  # only the diagonal wire signal, not 15 from the stone


# ---------------------------------------------------------------------- connection shapes
def test_isolated_dust_is_cross_and_dot_stays_dot():
    """DUST-007/008"""
    w = World()
    _floor(w, 0, 2)
    st = place_dust(w, Pos(1, 1, 0))
    assert sides(st) == {"north": "side", "east": "side", "south": "side", "west": "side"}
    wire = _wire_block(w)
    dot = wire.default_state()
    assert wire.get_connection_state(w, dot, Pos(1, 1, 0)) == dot
    # right click toggles between cross and dot
    wire.use_without_item(w, Pos(1, 1, 0), w.get(Pos(1, 1, 0)))
    assert sides(w.get(Pos(1, 1, 0))) == {"north": "none", "east": "none", "south": "none", "west": "none"}


def test_single_connection_becomes_a_line():
    w = World()
    _floor(w, 0, 3)
    place_dust(w, Pos(1, 1, 0))
    place_dust(w, Pos(2, 1, 0))
    assert sides(w.get(Pos(1, 1, 0))) == {"north": "none", "east": "side", "south": "none", "west": "side"}
    assert sides(w.get(Pos(2, 1, 0))) == {"north": "none", "east": "side", "south": "none", "west": "side"}


def test_corner_is_an_l_and_three_neighbors_a_t():
    w = World()
    _floor(w, 0, 2, -1, 1)
    c = Pos(1, 1, 0)
    place_dust(w, c)
    place_dust(w, Pos(1, 1, -1))  # north
    place_dust(w, Pos(2, 1, 0))  # east
    assert sides(w.get(c)) == {"north": "side", "east": "side", "south": "none", "west": "none"}
    place_dust(w, Pos(1, 1, 1))  # south
    assert sides(w.get(c)) == {"north": "side", "east": "side", "south": "side", "west": "none"}


def test_dust_dot_connects_when_a_neighbor_appears():
    w = World()
    _floor(w, 0, 2)
    wire = _wire_block(w)
    w.blocks[Pos(1, 1, 0)] = wire.default_state()  # stored dot
    place_dust(w, Pos(2, 1, 0))
    assert sides(w.get(Pos(1, 1, 0))) == {"north": "none", "east": "side", "south": "none", "west": "side"}


def test_up_versus_side():
    """DUST-002/003: dust next to a block with dust on top shows 'up' when that face is sturdy."""
    w = World()
    _floor(w, 0, 2)
    w.blocks[Pos(1, 1, 0)] = STONE
    place_dust(w, Pos(1, 2, 0))
    st = place_dust(w, Pos(0, 1, 0))
    assert st.get("east") == "up"
    # the upper dust connects down-diagonally with 'side'
    assert w.get(Pos(1, 2, 0)).get("west") == "side"


def test_conductor_above_lower_dust_separates_both_ways():
    """DUST-005/006: a conductor above the lower dust (= beside the upper dust) cuts the diagonal."""
    w = World()
    _floor(w, 0, 3)
    w.blocks[Pos(1, 1, 0)] = STONE  # carries the upper dust
    w.blocks[Pos(0, 2, 0)] = STONE  # above the lower dust, beside the upper dust
    lower, upper = Pos(0, 1, 0), Pos(1, 2, 0)
    place_dust(w, lower)
    place_dust(w, upper)
    if core.active() == "python":  # the power checks below show the same on both cores
        wire = _wire_block(w)
        assert wire.get_connecting_side(w, lower, D.EAST) == "none"
        assert wire.get_connecting_side(w, upper, D.WEST) == "none"
    # no signal from the upper to the lower dust (upper powers the stone, DUST-015 keeps that out) ...
    w.set_block(Pos(2, 2, 0), BlockState.parse("redstone_block"))
    assert power(w, upper) == 15 and power(w, lower) == 0
    # ... and none from the lower to the upper dust
    w.set_block(Pos(2, 2, 0), BlockState.parse("air"))
    w.set_block(Pos(-1, 1, 0), BlockState.parse("redstone_block"))
    assert power(w, lower) == 15 and power(w, upper) == 0


def test_without_separating_conductor_signal_crosses_the_diagonal():
    w = World()
    _floor(w, 0, 3)
    w.blocks[Pos(1, 1, 0)] = STONE
    w.blocks[Pos(0, 2, 0)] = BlockState.parse("glass")  # not a conductor: does not cut (DUST-005)
    lower, upper = Pos(0, 1, 0), Pos(1, 2, 0)
    place_dust(w, lower)
    place_dust(w, upper)
    w.set_block(Pos(2, 2, 0), BlockState.parse("redstone_block"))
    assert power(w, upper) == 15 and power(w, lower) == 14


# ---------------------------------------------------------------------- DUST-010/011: powering
def _signals(w: World, pos: Pos) -> dict[str, int]:
    """Signal of the dust as seen by each neighbour (receiver at pos.offset(d) asks getSignal(pos, d.opposite))."""
    return {d.label: w.get_signal(pos, d.opposite) for d in D}


def test_cross_powers_all_sides_and_below_but_not_above():
    w = World()
    _floor(w, -1, 1, -1, 1)
    c = Pos(0, 1, 0)
    w.blocks[c] = _wire_block(w).cross_state(power=9)
    assert _signals(w, c) == {"down": 9, "up": 0, "north": 9, "south": 9, "west": 9, "east": 9}


def test_dot_powers_only_below():
    w = World()
    _floor(w, -1, 1, -1, 1)
    c = Pos(0, 1, 0)
    w.blocks[c] = _wire_block(w).default_state(power=9)
    assert _signals(w, c) == {"down": 9, "up": 0, "north": 0, "south": 0, "west": 0, "east": 0}


def test_line_powers_only_its_ends_using_the_recomputed_shape():
    """DUST-011: the stored state says cross, but with one dust to the north the shape is a N-S line."""
    w = World()
    _floor(w, -1, 1, -1, 1)
    c = Pos(0, 1, 0)
    w.blocks[c] = _wire_block(w).cross_state(power=9)
    w.blocks[Pos(0, 1, -1)] = _wire_block(w).cross_state(power=8)
    assert _signals(w, c) == {"down": 9, "up": 0, "north": 9, "south": 9, "west": 0, "east": 0}


def test_dust_lights_lamp_it_points_into_but_not_beside():
    w = World()
    _floor(w, -1, 3, -1, 1)
    lamp_front, lamp_side = Pos(2, 1, 0), Pos(1, 1, 1)
    w.blocks[lamp_front] = BlockState.parse("redstone_lamp[lit=false]")
    w.blocks[lamp_side] = BlockState.parse("redstone_lamp[lit=false]")
    place_dust(w, Pos(1, 1, 0))
    place_dust(w, Pos(0, 1, 0))
    w.set_block(Pos(-1, 1, 0), BlockState.parse("redstone_block"))
    assert power(w, Pos(1, 1, 0)) == 14
    assert w.has_neighbor_signal(lamp_front) and not w.has_neighbor_signal(lamp_side)


@pytest.mark.skipif(core.active() != "rust", reason="compares the Rust helpers with the Python reference")
@pytest.mark.parametrize("pos", [(0, 64, 0), (1, 64, 0), (0, 200, 0), (-1, 64, -1), (0, -64, 0), (1000000, 0, 0),
                                 (30_000_000, 319, -30_000_000)])
def test_rust_update_order_matches_python(pos):
    import rsx_core

    p = Pos(*pos)
    assert [Pos(*q) for q in rsx_core.update_order(pos)] == update_order(p)
    assert rsx_core.block_pos_hash(pos) == block_pos_hash(p)


@pytest.mark.skipif(core.active() != "rust", reason="Rust counterpart of the HashSet-order test")
def test_power_change_triggers_updates_rust():
    """DUST-016/017: a power change updates the neighbours (7 updateNeighborsAt), an unchanged power does not."""
    w = World()
    pos = Pos(0, 64, 0)
    w.blocks[pos.offset(D.DOWN)] = STONE
    w.blocks[pos] = BlockState.parse("redstone_wire[east=side,north=none,power=0,south=none,west=side]")
    w.blocks[pos.offset(D.WEST)] = BlockState.parse("redstone_block")
    before = w.neighbor_update_count
    _wire_block(w).update_power_strength(w, pos, w.get(pos))
    assert power(w, pos) == 15
    assert w.neighbor_update_count > before
    before = w.neighbor_update_count
    _wire_block(w).update_power_strength(w, pos, w.get(pos))
    assert w.neighbor_update_count == before
