from pathlib import Path

from redstone.gui.materials import (_support, build_order, format_materials, items_for_state, label_for, materials,
                                    stacks)
from redstone.model import Grid, Pos
from redstone.verify import load_scenario

ROOT = Path(__file__).parents[2]


def _grid(blocks: dict[tuple[int, int, int], str], size=(6, 6, 6)) -> Grid:
    g = Grid(size)
    for p, s in blocks.items():
        g.set(p, s)
    return g


def _counts(g: Grid) -> dict[str, int]:
    return {m["item"]: m["count"] for m in materials(g)}


def test_basic_mapping_and_sorting():
    g = _grid({(0, 0, 0): "stone", (1, 0, 0): "stone", (0, 1, 0): "redstone_wire[power=0]",
               (1, 1, 0): "redstone_wall_torch[facing=east,lit=true]", (2, 1, 0): "redstone_torch[lit=true]"})
    m = materials(g)
    assert [(x["item"], x["count"]) for x in m] == [("redstone_torch", 2), ("stone", 2), ("redstone", 1)]
    assert m[1]["label"] == "Stein"
    assert _counts(g) == {"stone": 2, "redstone": 1, "redstone_torch": 2}


def test_slabs_pistons_fluids_and_counts():
    g = _grid({
        (0, 0, 0): "stone_slab[type=double]", (1, 0, 0): "stone_slab[type=bottom]",
        (0, 1, 0): "piston[extended=true,facing=up]", (0, 2, 0): "piston_head[facing=up,type=normal]",
        (1, 1, 0): "water[level=0]", (2, 1, 0): "water[level=3]", (3, 1, 0): "lava[level=0]",
        (4, 1, 0): "fire", (0, 3, 0): "candle[candles=3]", (1, 3, 0): "snow[layers=4]",
        (2, 3, 0): "sea_pickle[pickles=2]", (3, 3, 0): "wall_torch[facing=north]",
        (0, 4, 0): "oak_wall_sign[facing=south]", (4, 3, 0): "moving_piston",
        (0, 5, 0): "oak_door[half=lower]", (1, 5, 0): "oak_door[half=upper]",
        (2, 5, 0): "red_bed[part=foot]", (3, 5, 0): "red_bed[part=head]",
    })
    c = _counts(g)
    assert c["stone_slab"] == 3
    assert c["piston"] == 1 and "piston_head" not in c and "moving_piston" not in c
    assert c["water_bucket"] == 1 and c["lava_bucket"] == 1 and "fire" not in c
    assert c["candle"] == 3 and c["snow"] == 4 and c["sea_pickle"] == 2
    assert c["torch"] == 1 and c["oak_sign"] == 1
    assert c["oak_door"] == 1 and c["red_bed"] == 1
    labels = {m["item"]: m["label"] for m in materials(g)}
    assert labels["water_bucket"] == "Wassereimer" and labels["lava_bucket"] == "Lavaeimer"
    assert labels["red_bed"] == "Rotes Bett"


def test_container_contents():
    g = _grid({(0, 0, 0): "hopper[facing=down]"})
    g.block_entities[Pos(0, 0, 0)] = {"id": "minecraft:hopper",
                                      "Items": [{"Slot": 0, "id": "minecraft:stone", "count": 64},
                                                {"Slot": 1, "id": "minecraft:stone", "count": 3}]}
    assert _counts(g) == {"stone": 67, "hopper": 1}


def test_stacks():
    assert stacks(133) == "2 × 64 + 5" and stacks(128) == "2 × 64" and stacks(5) == "5"
    assert stacks(33, 16) == "2 × 16 + 1"
    assert "Gesamt" in format_materials(_grid({(0, 0, 0): "stone"}))


def test_build_order_layers_and_support():
    g = _grid({(2, 0, 2): "stone", (0, 0, 0): "stone", (0, 1, 0): "redstone_wire", (2, 1, 2): "repeater[facing=north]",
               (1, 0, 0): "piston_head[facing=up]"})
    o = build_order(g)
    assert Pos(1, 0, 0) not in o and len(o) == 4
    assert o.index(Pos(0, 0, 0)) < o.index(Pos(0, 1, 0))
    assert o.index(Pos(2, 0, 2)) < o.index(Pos(2, 1, 2))
    assert [p.y for p in o] == sorted(p.y for p in o)


def test_wall_torch_after_its_wall():
    # a wall torch facing west is attached to the block east of it (pos - facing vector)
    g = _grid({(0, 1, 0): "redstone_wall_torch[facing=west]", (1, 1, 0): "stone"})
    assert build_order(g) == [Pos(1, 1, 0), Pos(0, 1, 0)]
    g2 = _grid({(1, 1, 0): "redstone_wall_torch[facing=east]", (0, 1, 0): "stone"})
    assert build_order(g2) == [Pos(0, 1, 0), Pos(1, 1, 0)]


def test_ceiling_lever_after_block_above():
    g = _grid({(1, 1, 1): "lever[face=ceiling,facing=north,powered=false]", (1, 2, 1): "stone", (3, 1, 1): "stone"})
    o = build_order(g)
    assert o.index(Pos(1, 2, 1)) < o.index(Pos(1, 1, 1))
    g2 = _grid({(1, 1, 1): "stone_button[face=wall,facing=north]", (1, 1, 2): "stone"})
    assert build_order(g2) == [Pos(1, 1, 2), Pos(1, 1, 1)]


def test_real_scenario():
    grid = load_scenario(ROOT / "scenarios" / "cmp-cmp3.yaml").grid
    blocks = list(grid.items())
    expected = sum(n for _, s in blocks for _, n in items_for_state(s))
    extra = sum(int(it.get("count", 1)) for be in grid.block_entities.values() for it in be.get("Items", []))
    assert sum(m["count"] for m in materials(grid)) == expected + extra
    placed = sum(1 for _, s in blocks if items_for_state(s))
    order = build_order(grid)
    assert len(order) == len(set(order)) == placed
    idx = {p: i for i, p in enumerate(order)}
    for p in order:
        sup = _support(grid.get(p), p)
        if sup in idx:
            assert idx[sup] < idx[p]


def test_german_labels_rules():
    expected = {
        "white_wool": "Weiße Wolle", "white_concrete": "Weißer Beton", "red_bed": "Rotes Bett",
        "light_blue_concrete_powder": "Hellblauer Trockenbeton", "orange_wool": "Orange Wolle",
        "orange_concrete": "Oranger Beton", "pink_bed": "Rosa Bett", "lime_stained_glass": "Hellgrünes Glas",
        "gray_stained_glass_pane": "Graue Glasscheibe", "cyan_glazed_terracotta": "Türkise glasierte Keramik",
        "black_shulker_box": "Schwarze Shulker-Kiste", "oak_planks": "Eichenholzbretter",
        "oak_slab": "Eichenholzstufe", "spruce_stairs": "Fichtenholztreppe", "dark_oak_trapdoor": "Schwarzeichenholzfalltür",
        "birch_button": "Birkenholzknopf", "crimson_pressure_plate": "Karmesindruckplatte", "oak_log": "Eichenstamm",
        "jungle_log": "Tropenbaumstamm", "cobblestone_slab": "Bruchsteinstufe", "stone_slab": "Steinstufe",
        "smooth_stone_slab": "Glatte Steinstufe", "stone_brick_stairs": "Steinziegeltreppe",
        "waxed_exposed_copper_bulb": "Gewachste freigelegte Kupferlampe", "oxidized_copper_block": "Oxidierter Kupferblock",
        "observer": "Beobachter",
    }
    for item, label in expected.items():
        assert label_for(item) == label, item
    assert label_for("unknown_thing") == "Unknown thing"
