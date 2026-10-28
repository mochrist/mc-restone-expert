from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from redstone import io
from redstone.io import nbtutil
from redstone.model import BlockState, Grid, Pos

from ..conftest import LICENSED, external

FORMATS = [".litematic", ".schem", ".nbt"]

_STATES = [
    BlockState.parse(s)
    for s in [
        "stone",
        "redstone_wire[east=side,north=none,power=7,south=up,west=side]",
        "repeater[delay=3,facing=west,locked=false,powered=true]",
        "comparator[facing=north,mode=subtract,powered=false]",
        "sticky_piston[extended=false,facing=up]",
        "observer[facing=down,powered=false]",
        "redstone_torch[lit=true]",
        "air",
    ]
]


# --- bit packing -----------------------------------------------------------------

@given(st.integers(2, 20).flatmap(lambda bits: st.tuples(
    st.just(bits), st.lists(st.integers(0, (1 << bits) - 1), max_size=300))))
def test_tight_packing_round_trip(case):
    bits, values = case
    longs = nbtutil.pack_tight(values, bits)
    assert all(-(1 << 63) <= v < (1 << 63) for v in longs)
    assert nbtutil.unpack_tight(longs, bits, len(values)) == values


@given(st.lists(st.integers(0, 2**31 - 1), max_size=200))
def test_varint_round_trip(values):
    assert nbtutil.decode_varints(nbtutil.encode_varints(values), len(values)) == values


def test_bits_for_palette():
    assert [nbtutil.bits_for_palette(n, 2) for n in (1, 2, 4, 5, 16, 17)] == [2, 2, 2, 3, 4, 5]


# --- round trips through our own writers -----------------------------------------

@st.composite
def grids(draw):
    size = draw(st.tuples(st.integers(1, 6), st.integers(1, 4), st.integers(1, 6)))
    # Large palettes exercise bit widths that span long boundaries.
    extra = draw(st.integers(0, 40))
    states = _STATES + [BlockState.of("redstone_wire", power=i % 16, east=f"v{i}") for i in range(extra)]
    g = Grid(size)
    for x in range(size[0]):
        for y in range(size[1]):
            for z in range(size[2]):
                g[x, y, z] = draw(st.sampled_from(states))
    return g


@pytest.mark.parametrize("ext", FORMATS)
@settings(max_examples=30, deadline=None)
@given(grid=grids())
def test_round_trip(tmp_path_factory, ext, grid):
    path = tmp_path_factory.mktemp("rt") / f"g{ext}"
    io.save(grid, path)
    assert io.load(path) == grid


@pytest.mark.parametrize("ext", FORMATS)
def test_block_entities_round_trip(tmp_path, ext):
    g = Grid((2, 1, 1))
    g[0, 0, 0] = "comparator[facing=north,mode=compare,powered=true]"
    g.block_entities[Pos(0, 0, 0)] = {"id": "minecraft:comparator", "OutputSignal": 7}
    io.save(g, tmp_path / f"c{ext}")
    back = io.load(tmp_path / f"c{ext}")
    assert back.block_entities[Pos(0, 0, 0)]["OutputSignal"] == 7
    assert back.block_entities[Pos(0, 0, 0)]["id"] == "minecraft:comparator"


def test_unknown_extension():
    with pytest.raises(ValueError):
        io.load("foo.txt")


# --- real files --------------------------------------------------------------------

@pytest.mark.parametrize("name", ["piston-gate-3x3", "mux3-8", "tripple-piston-extender", "seg7"])
def test_litematic_matches_structure_nbt_export(name):
    """redstone-rs ships the same circuit as .litematic and vanilla .nbt."""
    lit = io.load(external(f"{name}.litematic"))
    nbt = io.load(external(f"{name}.nbt"))
    assert lit.size == nbt.size
    assert dict(lit.items()) == dict(nbt.items())
    assert lit.block_entities.keys() == nbt.block_entities.keys()


def test_litematic_matches_litemapy():
    litemapy = pytest.importorskip("litemapy")
    path = LICENSED / "2TickFiveLanternPrize.litematic"
    ours = io.load(path)
    schem = litemapy.Schematic.load(str(path))
    (region,) = schem.regions.values()
    theirs = {}
    for x, y, z in region.block_positions():
        b = region[x, y, z]
        if b.id not in ("minecraft:air", "minecraft:cave_air"):
            lx = x - region.min_x() if hasattr(region, "min_x") else x
            ly = y - region.min_y() if hasattr(region, "min_y") else y
            lz = z - region.min_z() if hasattr(region, "min_z") else z
            theirs[Pos(lx, ly, lz)] = BlockState.of(b.id, dict(b.properties()))
    assert dict(ours.items()) == theirs


def test_sponge_v2_file():
    g = io.load(LICENSED / "DD16bCCA.schem")
    assert g.meta.extra["sponge_version"] == 2
    assert tuple(g.size) == (14, 26, 32)
    assert any(s.id == "comparator" for _, s in g.items())
    # Block entity positions must point at blocks that carry them.
    for pos in g.block_entities:
        assert not g[pos].is_air


@pytest.mark.parametrize("src", ["2TickFiveLanternPrize.litematic", "DD16bCCA.schem"])
@pytest.mark.parametrize("ext", FORMATS)
def test_real_file_converts_losslessly(tmp_path, src, ext):
    g = io.load(LICENSED / src)
    out = Path(tmp_path) / f"out{ext}"
    io.save(g, out)
    back = io.load(out)
    assert dict(back.items()) == dict(g.items())
    assert back.block_entities.keys() == g.block_entities.keys()
