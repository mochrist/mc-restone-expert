from redstone.model import Grid
from redstone.render import render


def test_layer_layout_and_arrows():
    g = Grid((3, 1, 2))
    g[0, 0, 0] = "lever[face=floor,facing=north,powered=false]"
    # facing=west -> input from the west, output to the east
    g[1, 0, 0] = "repeater[delay=1,facing=west,locked=false,powered=false]"
    g[2, 0, 0] = "redstone_lamp[lit=false]"
    g[2, 0, 1] = "stone"
    text = render(g, components=True)
    lines = text.splitlines()
    i = lines.index("     012")
    assert lines[i + 1] == "   0 L>O"
    assert lines[i + 2] == "   1 ..#"
    assert "  >  repeater, output east" in lines
    assert "  (1,0,0)  minecraft:repeater[delay=1,facing=west,locked=false,powered=false]" in lines


def test_unknown_blocks_get_letters_and_empty_layers_are_compact():
    g = Grid((2, 2, 1))
    g[0, 0, 0] = "oak_slab[type=bottom,waterlogged=false]"
    text = render(g)
    assert "y=1: empty" in text
    assert "oak_slab" in text
