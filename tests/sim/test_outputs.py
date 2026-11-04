"""Unit tests for sim/blocks/outputs.py (behaviour read from the 26.3 code; scenarios cover the game itself)."""

from redstone.model import BlockState, Pos
from redstone.sim import World
from redstone.sim.blocks.outputs import LecternBlockEntity, _instrument
from redstone.sim.constants import UPDATE_ALL

S = BlockState.parse


def _world(blocks: dict[tuple[int, int, int], str]) -> World:
    w = World()
    for p, s in blocks.items():
        w.blocks[Pos(*p)] = S(s)
    return w


def _lever_use(w: World, pos: tuple[int, int, int]) -> None:
    p = Pos(*pos)
    st = w.get(p)
    w.block(st).use_without_item(w, p, st)


def test_copper_bulb_toggles_only_on_rising_edge():
    w = _world({(0, 0, 0): "stone", (1, 0, 0): "stone",
                (0, 1, 0): "lever[face=floor,facing=east,powered=false]",
                (1, 1, 0): "copper_bulb[lit=false,powered=false]"})
    seen = []
    for _ in range(4):
        _lever_use(w, (0, 1, 0))
        seen.append(w.get(Pos(1, 1, 0)))
    assert [(s.get("lit"), s.get("powered")) for s in seen] == [
        ("true", "true"), ("true", "false"), ("false", "true"), ("false", "false")]


def test_powered_rail_reaches_eight_rails_beyond_the_source():
    blocks = {(x, 0, 0): "stone" for x in range(0, 14)}
    blocks[(0, 1, 0)] = "lever[face=floor,facing=east,powered=false]"
    for x in range(1, 14):
        blocks[(x, 1, 0)] = "powered_rail[powered=false,shape=east_west,waterlogged=false]"
    w = _world(blocks)
    _lever_use(w, (0, 1, 0))
    powered = [x for x in range(1, 14) if w.get(Pos(x, 1, 0)).get_bool("powered")]
    assert powered == list(range(1, 10))


def test_target_placed_with_power_resets_without_scheduled_tick():
    w = _world({})
    w.set_block(Pos(0, 0, 0), S("target[power=9]"), UPDATE_ALL)
    assert w.get(Pos(0, 0, 0)).get_int("power") == 0


def test_door_half_copies_state_of_other_half():
    w = _world({(0, 0, 0): "stone",
                (0, 1, 0): "oak_door[facing=east,half=lower,hinge=left,open=false,powered=false]",
                (0, 2, 0): "oak_door[facing=east,half=upper,hinge=left,open=false,powered=false]"})
    st = w.get(Pos(0, 1, 0))
    w.block(st).use_without_item(w, Pos(0, 1, 0), st)
    assert w.get(Pos(0, 2, 0)).get_bool("open")


def test_lectern_signal():
    be = LecternBlockEntity()
    be.load({"Page": 2, "Book": {"id": "minecraft:writable_book",
                                 "components": {"minecraft:writable_book_content": {"pages": list("abcde")}}}})
    assert be.redstone_signal() == 8
    empty = LecternBlockEntity()
    empty.load({})
    assert empty.redstone_signal() == 14  # only reachable with has_book=true and an empty block entity


def test_instrument_heuristic():
    assert _instrument(S("stone")) == "basedrum"
    assert _instrument(S("oak_planks")) == "bass"
    assert _instrument(S("sand")) == "snare"
    assert _instrument(S("sandstone")) == "basedrum"
    assert _instrument(S("air")) == "harp"
