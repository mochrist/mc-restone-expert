import pytest

from redstone.model import AIR, BlockState, Direction, Grid, Pos


def test_parse_and_format_round_trip():
    s = BlockState.parse("minecraft:repeater[facing=north,delay=2]")
    assert s.name == "minecraft:repeater"
    assert s.id == "repeater"
    assert s.get_int("delay") == 2
    assert s.get("facing") == "north"
    assert str(s) == "minecraft:repeater[delay=2,facing=north]"  # properties sorted
    assert BlockState.parse(str(s)) == s


def test_namespace_defaults_to_minecraft():
    assert BlockState.parse("stone") == BlockState.of("minecraft:stone")
    assert BlockState.parse("mymod:thing").id == "mymod:thing"


def test_property_order_does_not_matter():
    a = BlockState.parse("lever[face=floor,facing=east,powered=true]")
    b = BlockState.of("lever", powered=True, facing="east", face="floor")
    assert a == b and hash(a) == hash(b)


def test_with_returns_new_state():
    s = BlockState.of("redstone_wire", power=0)
    t = s.with_(power=15)
    assert s.get_int("power") == 0 and t.get_int("power") == 15


@pytest.mark.parametrize("bad", ["stone[", "stone[power]", "stone[a=1"])
def test_malformed(bad):
    with pytest.raises(ValueError):
        BlockState.parse(bad)


def test_air_variants():
    assert AIR.is_air
    assert BlockState.parse("cave_air").is_air
    assert not BlockState.parse("stone").is_air


def test_directions_match_minecraft_axes():
    assert Direction.NORTH.vec == (0, 0, -1)
    assert Direction.EAST.vec == (1, 0, 0)
    assert Direction.NORTH.opposite is Direction.SOUTH
    assert Direction.NORTH.clockwise() is Direction.EAST
    assert Pos(1, 2, 3).offset(Direction.UP, 2) == Pos(1, 4, 3)
    assert [d.label for d in Direction] == ["down", "up", "north", "south", "west", "east"]


def test_grid_set_get_and_air_removal():
    g = Grid((3, 2, 3))
    g[1, 0, 1] = "redstone_wire[power=0]"
    g.block_entities[Pos(1, 0, 1)] = {"id": "x"}
    assert g[1, 0, 1].id == "redstone_wire"
    assert len(g) == 1
    g[1, 0, 1] = AIR
    assert len(g) == 0 and not g.block_entities
    with pytest.raises(IndexError):
        g[3, 0, 0] = "stone"


def test_palette_has_air_first():
    g = Grid((2, 1, 1))
    g[1, 0, 0] = "stone"
    assert g.palette() == [AIR, BlockState.parse("stone")]
