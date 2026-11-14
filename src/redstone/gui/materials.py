"""Material list and build order of a grid (GUI, M6).

``materials(grid)`` maps block states (and container contents) to the items a player needs;
``build_order(grid)`` returns the block positions in an order in which they can be placed.
"""

from __future__ import annotations

import heapq
from collections import Counter

from redstone.model import BlockState, Direction, Grid, Pos

# Blocks that need no item (not placeable / created by other blocks).
_NO_ITEM = {"air", "cave_air", "void_air", "piston_head", "moving_piston", "fire", "soul_fire", "bubble_column"}

_TALL_PLANTS = {"tall_grass", "large_fern", "sunflower", "lilac", "rose_bush", "peony", "tall_seagrass",
                "pitcher_plant", "pitcher_crop"}

_CAULDRONS = {"water_cauldron", "lava_cauldron", "powder_snow_cauldron"}

_HORIZONTAL = ("north", "south", "east", "west")

LABELS = {
    "stone": "Stein", "cobblestone": "Bruchstein", "smooth_stone": "Glatter Stein", "stone_bricks": "Steinziegel",
    "glass": "Glas", "glass_pane": "Glasscheibe", "redstone": "Redstone-Staub",
    "redstone_torch": "Redstone-Fackel", "torch": "Fackel", "soul_torch": "Seelenfackel",
    "repeater": "Verstärker", "comparator": "Komparator", "redstone_lamp": "Redstone-Lampe",
    "lever": "Hebel", "stone_button": "Steinknopf", "oak_button": "Eichenknopf", "piston": "Kolben",
    "sticky_piston": "Klebriger Kolben", "observer": "Beobachter", "hopper": "Trichter",
    "dispenser": "Spender", "dropper": "Werfer", "target": "Zielblock", "note_block": "Notenblock",
    "redstone_block": "Redstone-Block", "slime_block": "Schleimblock", "honey_block": "Honigblock",
    "chest": "Kiste", "trapped_chest": "Redstone-Kiste", "barrel": "Fass",
    "daylight_detector": "Tageslichtsensor", "stone_pressure_plate": "Steindruckplatte",
    "oak_pressure_plate": "Eichendruckplatte", "light_weighted_pressure_plate": "Leichte Druckplatte",
    "heavy_weighted_pressure_plate": "Schwere Druckplatte", "rail": "Schiene", "powered_rail": "Antriebsschiene",
    "detector_rail": "Sensorschiene", "activator_rail": "Aktivierungsschiene", "crafter": "Crafter",
    "tripwire_hook": "Haken", "string": "Faden", "tnt": "TNT", "obsidian": "Obsidian", "dirt": "Erde",
    "sand": "Sand", "gravel": "Kies", "oak_planks": "Eichenholzbretter", "iron_block": "Eisenblock",
    "water_bucket": "Wassereimer", "lava_bucket": "Lavaeimer", "sculk_sensor": "Sculk-Sensor",
    "calibrated_sculk_sensor": "Kalibrierter Sculk-Sensor", "cake": "Kuchen", "snow": "Schnee",
    "iron_door": "Eisentür", "oak_door": "Eichentür", "ladder": "Leiter", "cauldron": "Kessel",
    "lectern": "Lesepult", "jukebox": "Plattenspieler", "bell": "Glocke", "sea_pickle": "Meeresgurke",
    "candle": "Kerze", "flower_pot": "Blumentopf", "white_wool": "Weiße Wolle", "bone_block": "Knochenblock",
    "sculk_shrieker": "Sculk-Schreier", "lightning_rod": "Blitzableiter",
    "stone_slab": "Steinstufe", "oak_slab": "Eichenstufe",
}


def label_for(item: str) -> str:
    """German name of an item, falling back to the id with spaces and a capital first letter."""
    if item in LABELS:
        return LABELS[item]
    return item.replace("_", " ").capitalize()


def _int(state: BlockState, key: str, default: int = 1) -> int:
    try:
        return int(state.get(key, str(default)))
    except ValueError:
        return default


def _is_wall_mounted(b: str) -> bool:
    return "wall_" in b and not b.endswith("_wall")


def items_for_state(state: BlockState) -> list[tuple[str, int]]:
    """Items consumed by placing this block state: ``[(item id, count)]`` (empty: nothing to place)."""
    b = state.id
    if b in _NO_ITEM:
        return []
    if b == "redstone_wire":
        return [("redstone", 1)]
    if b in ("water", "lava"):
        return [(f"{b}_bucket", 1)] if state.get("level", "0") == "0" else []
    if b in _CAULDRONS:
        return [("cauldron", 1)]
    if b.startswith("potted_"):
        return [("flower_pot", 1), (b[len("potted_"):], 1)]
    if b.endswith("_candle_cake"):
        return [("cake", 1), (b[: -len("_cake")], 1)]
    if b == "tripwire":
        return [("string", 1)]
    if b.endswith("slab"):
        return [(b, 2 if state.get("type") == "double" else 1)]
    if b.endswith("bed") and state.get("part") == "head":
        return []
    if state.get("half") == "upper" and (b.endswith("_door") or b in _TALL_PLANTS):
        return []
    if b == "snow":
        return [("snow", _int(state, "layers"))]
    if b.endswith("candle"):
        return [(b, _int(state, "candles"))]
    if b == "sea_pickle":
        return [(b, _int(state, "pickles"))]
    if b == "turtle_egg":
        return [(b, _int(state, "eggs"))]
    if _is_wall_mounted(b):
        # redstone_wall_torch -> redstone_torch, wall_torch -> torch, oak_wall_sign -> oak_sign
        return [(b.replace("wall_", "", 1), 1)]
    return [(b, 1)]


def _container_items(grid: Grid) -> Counter:
    """Items inside containers (`Items` list of the block-entity data: ``Slot``, ``id``, ``count``)."""
    extra: Counter = Counter()
    for be in grid.block_entities.values():
        for it in be.get("Items", []) or []:
            try:
                n = int(it.get("count", it.get("Count", 1)))
            except (TypeError, ValueError):
                continue
            item = str(it.get("id", ""))
            if item and n > 0:
                extra[item.removeprefix("minecraft:")] += n
    return extra


def materials(grid: Grid) -> list[dict]:
    """Items needed to build ``grid``: ``[{"item", "label", "count"}]``, count descending, then item.

    Block states map to items (wall variants to the floor item, double slabs count twice, fluid source
    blocks to buckets, candles/pickles/snow layers by their count; piston heads, moving pistons, fire, upper
    halves of doors/beds/tall plants need nothing). Items stored in containers are included as well.
    """
    total: Counter = Counter()
    for _, state in grid.items():
        for item, n in items_for_state(state):
            total[item] += n
    total.update(_container_items(grid))
    return [{"item": i, "label": label_for(i), "count": n}
            for i, n in sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))]


_BELOW_IDS = {"redstone_wire", "repeater", "comparator", "rail", "powered_rail", "detector_rail",
              "activator_rail", "redstone_torch", "torch", "soul_torch", "snow", "flower_pot", "tripwire"}
_BELOW_SUFFIX = ("_pressure_plate", "_carpet", "_door", "_sign", "_banner")


def _behind(state: BlockState, pos: Pos) -> Pos | None:
    f = state.get("facing")
    if f in _HORIZONTAL:
        return pos - Direction.from_name(f).vec
    return None


def _support(state: BlockState, pos: Pos) -> Pos | None:
    """Position of the block ``state`` at ``pos`` is attached to (None: free-standing)."""
    b = state.id
    if _is_wall_mounted(b) or b in ("ladder", "tripwire_hook"):
        return _behind(state, pos)
    if b == "lever" or b.endswith("_button") or b == "grindstone":
        face = state.get("face", "wall")
        if face == "floor":
            return Pos(pos.x, pos.y - 1, pos.z)
        if face == "ceiling":
            return Pos(pos.x, pos.y + 1, pos.z)
        return _behind(state, pos)
    if b in _BELOW_IDS or b.endswith(_BELOW_SUFFIX):
        return Pos(pos.x, pos.y - 1, pos.z)
    return None


def build_order(grid: Grid) -> list[Pos]:
    """Positions of all blocks that need an item, in a placeable order.

    Rules: y ascending is the main key, within a layer (x, z) ascending for a stable order. Support-dependent
    blocks (dust, repeaters, comparators, torches, pressure plates, rails, carpets, doors, signs, banners:
    support below; wall torches/signs/banners, ladders, tripwire hooks, levers and buttons on a wall: the
    block behind them by ``facing``; levers/buttons on the ceiling: the block above) come after their
    support, even if that lies in a higher layer (topological order, the dependency is forced first).
    Support that is itself absent or needs no item is ignored; cycles are broken by the smallest key.
    Not placed: piston heads, moving pistons, fire, flowing fluids, upper halves of doors/beds/tall plants.
    Free-floating full blocks are fine (the player places them against neighbours).
    """
    nodes = {p: s for p, s in grid.items() if items_for_state(s)}

    def key(p: Pos) -> tuple[int, int, int]:
        return (p.y, p.x, p.z)

    dep: dict[Pos, Pos] = {}
    for p, s in nodes.items():
        sup = _support(s, p)
        if sup is not None and sup in nodes and sup != p:
            dep[p] = sup
    dependents: dict[Pos, list[Pos]] = {}
    for p, sup in dep.items():
        dependents.setdefault(sup, []).append(p)

    order: list[Pos] = []
    done: set[Pos] = set()
    heap = [(key(p), p) for p in nodes if p not in dep]
    heapq.heapify(heap)
    waiting = set(dep)
    while heap or waiting:
        if not heap:  # cycle: release the smallest waiting block
            p = min(waiting, key=key)
            waiting.discard(p)
            heapq.heappush(heap, (key(p), p))
        _, p = heapq.heappop(heap)
        if p in done:
            continue
        done.add(p)
        order.append(p)
        for q in dependents.get(p, ()):
            if q in waiting:
                waiting.discard(q)
                heapq.heappush(heap, (key(q), q))
    return order


def stacks(count: int, stack_size: int = 64) -> str:
    """``"2 × 64 + 5"``-style stack notation (just the number for less than one stack)."""
    full, rest = divmod(count, stack_size)
    if not full:
        return str(rest)
    return f"{full} × {stack_size}" + (f" + {rest}" if rest else "")


def format_materials(grid: Grid) -> str:
    """German material list as text: count, stacks, label, and the total."""
    from redstone.sim.blocks.container import item_max_stack_size

    mats = materials(grid)
    lines = [f"{m['count']:>6}  {stacks(m['count'], item_max_stack_size(m['item'])):<14} {m['label']}" for m in mats]
    lines.append(f"{sum(m['count'] for m in mats):>6}  Gesamt ({len(mats)} Sorten)")
    return "\n".join(lines)
