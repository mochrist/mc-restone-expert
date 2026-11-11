"""The crafter.

References (26.3): CrafterBlock, CrafterBlockEntity, CraftingInput#of, ShapedRecipe / ShapelessRecipe (recipes from
data/minecraft/recipe in the server jar), HopperBlockEntity#addItem; knowledge/components/crafter.md (CRAFTER-*).

Modeled: the redstone trigger (rising edge, 4 gt scheduled tick, ``triggered``), the ``crafting`` property
(6 gt after a successful craft), ``disabled_slots`` and the comparator output (slots with an item plus disabled
slots), hopper/dropper insertion (``canPlaceItem``: disabled slots refuse, items are spread over the slots) and
the craft itself: every non-empty slot loses one item, the result goes into the container in front.

ASSUMPTION: only a small set of recipes is known (``RECIPES`` below). Any other grid counts as "no recipe"
(nothing happens, ``crafting`` stays false). Recipe remainders (buckets, bottles ...) are not modeled. Tags are
reduced to the members listed in ``TAGS``. A result that does not fit into the container in front is thrown as
an item entity; entities are not modeled, so the rest simply vanishes (as for droppers).
"""

from __future__ import annotations

from ...model import Direction
from ..block import REGISTRY
from ..constants import UPDATE_ALL, UPDATE_CLIENTS
from ..world import World
from .container import (ContainerBlock, ContainerBlockEntity, add_item, container_max_stack, get_container_at,
                        item_max_stack_size)

TRIGGER_DELAY = 4  # CrafterBlock: scheduleTick(pos, this, 4)
CRAFTING_TICKS = 6  # CrafterBlock.MAX_CRAFTING_TICKS
SIZE = 9

# Tags used by RECIPES: "#name" in a pattern. (ASSUMPTION: only these members; the game tags have more.)
TAGS = {
    "planks": frozenset(f"minecraft:{w}_planks" for w in (
        "oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak", "bamboo",
        "crimson", "warped")),
    "oak_logs": frozenset(f"minecraft:{n}" for n in ("oak_log", "oak_wood", "stripped_oak_log", "stripped_oak_wood")),
}

# (kind, pattern, result item, result count). shaped: rows of ingredients, "#tag" or item id; shapeless: list.
RECIPES = (
    ("shaped", (("#planks", "#planks"), ("#planks", "#planks")), "minecraft:crafting_table", 1),  # crafting_table
    ("shaped", (("#planks",), ("#planks",)), "minecraft:stick", 4),  # stick
    ("shaped", (("minecraft:iron_ingot",) * 3,) * 3, "minecraft:iron_block", 1),  # iron_block
    ("shaped", (("minecraft:redstone",) * 3,) * 3, "minecraft:redstone_block", 1),  # redstone_block
    ("shapeless", ("#oak_logs",), "minecraft:oak_planks", 4),  # oak_planks
    ("shapeless", ("minecraft:iron_block",), "minecraft:iron_ingot", 9),  # iron_ingot_from_iron_block
    ("shapeless", ("minecraft:redstone_block",), "minecraft:redstone", 9),  # redstone_from_redstone_block
)


def _matches(ingredient: str, item: str) -> bool:
    return item in TAGS[ingredient[1:]] if ingredient.startswith("#") else ingredient == item


def find_recipe(grid: list[str | None]) -> tuple[str, int] | None:
    """``CrafterBlock#getPotentialResults`` for the nine slots (None = empty). Returns (result item, count)."""
    cells = [(i % 3, i // 3, item) for i, item in enumerate(grid) if item is not None]
    if not cells:
        return None
    x0, x1 = min(c[0] for c in cells), max(c[0] for c in cells)
    y0, y1 = min(c[1] for c in cells), max(c[1] for c in cells)  # CraftingInput#of trims empty rows and columns
    width, height = x1 - x0 + 1, y1 - y0 + 1
    for kind, pattern, result, count in RECIPES:
        if kind == "shapeless":
            if len(cells) != len(pattern):
                continue
            rest = [c[2] for c in cells]
            ok = True
            for ing in pattern:
                hit = next((i for i, it in enumerate(rest) if _matches(ing, it)), None)
                if hit is None:
                    ok = False
                    break
                del rest[hit]
            if ok:
                return result, count
        elif len(pattern) == height and len(pattern[0]) == width:
            by_pos = {(c[0] - x0, c[1] - y0): c[2] for c in cells}
            # ShapedRecipe#matches also tries the mirrored pattern; all patterns here are symmetric
            if len(by_pos) == width * height and all(
                    _matches(pattern[y][x], by_pos[(x, y)]) for y in range(height) for x in range(width)):
                return result, count
    return None


class CrafterBlockEntity(ContainerBlockEntity):
    ticks = True

    def __init__(self, pos=None) -> None:
        super().__init__(SIZE, pos)
        self.disabled_mask = 0  # bit i set: slot i is disabled (containerData slot states)
        self.triggered = False
        self.crafting_ticks_remaining = 0

    def load(self, data: dict) -> None:
        super().load(data)
        self.crafting_ticks_remaining = int(data.get("crafting_ticks_remaining", 0))
        self.disabled_mask = 0
        for s in data.get("disabled_slots", []):
            if 0 <= int(s) < SIZE and int(s) not in self.items:  # slotCanBeDisabled: only empty slots
                self.disabled_mask |= 1 << int(s)
        self.triggered = bool(int(data.get("triggered", 0)))

    def is_disabled(self, slot: int) -> bool:
        return bool(self.disabled_mask >> slot & 1)

    def redstone_signal(self) -> int:
        """CrafterBlockEntity#getRedstoneSignal: slots with an item plus disabled slots."""
        return sum(1 for i in range(SIZE) if i in self.items or self.is_disabled(i))

    def can_place_item(self, slot: int, item: str) -> bool:
        """CrafterBlockEntity#canPlaceItem"""
        if self.is_disabled(slot):
            return False
        stack = self.items.get(slot)
        if stack is None:
            return True
        if stack[1] >= item_max_stack_size(stack[0]):
            return False
        # smallerStackExist: a later enabled slot is empty or holds a smaller stack of the same item
        for i in range(slot + 1, SIZE):
            if self.is_disabled(i):
                continue
            other = self.items.get(i)
            if other is None or (other[1] < stack[1] and other[0] == stack[0]):
                return False
        return True

    def is_idle(self) -> bool:
        return self.crafting_ticks_remaining <= 0

    def tick(self, world: World) -> None:
        """CrafterBlockEntity#serverTick"""
        remaining = self.crafting_ticks_remaining - 1
        if remaining >= 0:
            self.crafting_ticks_remaining = remaining
            if remaining == 0:
                state = world.get(self.pos)
                world.set_block(self.pos, state.with_(crafting=False), UPDATE_ALL)  # setBlockAndUpdate


class CrafterBlock(ContainerBlock):
    def __init__(self) -> None:
        super().__init__(SIZE)

    def new_block_entity(self, pos, state):
        be = CrafterBlockEntity(pos)
        be.triggered = state.get_bool("triggered")  # CrafterBlock#newBlockEntity
        return be

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        """CrafterBlock#neighborChanged: no quasi-connectivity."""
        should_trigger = world.has_neighbor_signal(pos)
        is_triggered = state.get_bool("triggered")
        be = world.get_block_entity(pos)
        if should_trigger and not is_triggered:
            world.schedule_tick(pos, self, TRIGGER_DELAY)
            world.set_block(pos, state.with_(triggered=True), UPDATE_CLIENTS)
            if isinstance(be, CrafterBlockEntity):
                be.triggered = True
        elif not should_trigger and is_triggered:
            world.set_block(pos, state.with_(triggered=False, crafting=False), UPDATE_CLIENTS)
            if isinstance(be, CrafterBlockEntity):
                be.triggered = False

    def tick(self, world, pos, state):
        """CrafterBlock#tick: craft without re-checking power."""
        self.dispense_from(world, pos, state)

    def dispense_from(self, world: World, pos, state) -> None:
        be = world.get_block_entity(pos)
        if not isinstance(be, CrafterBlockEntity):
            return
        found = find_recipe([be.items[i][0] if i in be.items else None for i in range(SIZE)])
        if found is None:
            return  # level event 1050 (fail sound)
        result, count = found
        be.crafting_ticks_remaining = CRAFTING_TICKS
        world.set_block(pos, state.with_(crafting=True), UPDATE_CLIENTS)
        self.dispense_item(world, pos, be, result, count, state)
        for slot in list(be.items):  # getItems().forEach(shrink(1)): no setItem, no setChanged per slot
            be.shrink(slot)
        be.set_changed(world)

    def dispense_item(self, world: World, pos, be: CrafterBlockEntity, item: str, count: int, state) -> None:
        """CrafterBlock#dispenseItem: into the container in front, the rest would be thrown (not modeled)."""
        direction = Direction.from_name(state.get("orientation", "north_up").split("_")[0])
        into = get_container_at(world, pos.offset(direction))
        if into is None:
            return
        if isinstance(into, CrafterBlockEntity) or count > container_max_stack(item):
            for _ in range(count):  # one item at a time
                if add_item(world, be, into, item, 1):
                    break
        else:
            while count > 0:
                left = add_item(world, be, into, item, count)
                if left == count:
                    break
                count = left


REGISTRY.register(CrafterBlock(), "crafter")
