"""Block-entity containers: inventory, comparator output and the item transfer helpers of HopperBlockEntity.

References (26.3): BaseContainerBlockEntity, AbstractContainerMenu#getRedstoneSignalFromContainer,
Containers#updateNeighboursAfterDestroy, HopperBlockEntity#addItem / #tryMoveInItem / #getContainerAt.

Items are kept as ``slot -> [item id, count]``. Item components (custom names, enchantments, a custom
``max_stack_size`` ...) are ignored: two stacks merge if their ids match (ASSUMPTION).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from ...model import BlockState, Direction, Pos
from ..block import REGISTRY, Block

if TYPE_CHECKING:
    from ..world import World

# Container#getMaxStackSize (Container.LARGE_MAX_STACK_SIZE); the effective limit is min(99, item max).
CONTAINER_MAX_STACK = 99
DEFAULT_MAX_STACK = 64
STACK_SIZE_FILE = Path(__file__).resolve().parent.parent / "data" / "item_stack_sizes_26.3.json"


@lru_cache(maxsize=1)
def _stack_table() -> dict[str, int]:
    with STACK_SIZE_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    return {f"minecraft:{name}": int(size) for size, names in data.items() if size.isdigit() for name in names}


def item_max_stack_size(item: str) -> int:
    """Default max stack size of an item (1, 16 or 64), from the 26.3 Items class.

    ASSUMPTION: items missing from the generated table stack to 64; data components are ignored.
    """
    if ":" not in item:
        item = f"minecraft:{item}"
    return _stack_table().get(item, DEFAULT_MAX_STACK)


def container_max_stack(item: str) -> int:
    """Container#getMaxStackSize(ItemStack)"""
    return min(CONTAINER_MAX_STACK, item_max_stack_size(item))


def redstone_signal_of(stacks, size: int) -> int:
    """AbstractContainerMenu#getRedstoneSignalFromContainer over the given ``[item, count]`` stacks."""
    if not size:
        return 0
    fullness = sum(count / container_max_stack(item) for item, count in stacks) / size
    # Mth.lerpDiscrete(fullness, 0, 15) = floor(f * 14) + (f > 0 ? 1 : 0)
    return math.floor(fullness * 14) + (1 if fullness > 0 else 0)


class ContainerBlockEntity:
    ticks = False

    def __init__(self, size: int, pos: Pos | None = None) -> None:
        self.size = size
        self.pos = pos
        self.items: dict[int, list] = {}  # slot -> [item id, count]
        self.removed = False

    def load(self, data: dict) -> None:
        self.items = {}
        for item in data.get("Items", []):
            slot = int(item.get("Slot", 0))
            count = int(item.get("count", 1))
            item_id = str(item.get("id", ""))
            if ":" not in item_id:
                item_id = f"minecraft:{item_id}"
            if 0 <= slot < self.size and count > 0:
                self.items[slot] = [item_id, count]

    # --- Container ------------------------------------------------------------------
    def is_empty(self) -> bool:
        return not self.items

    def get_item(self, slot: int) -> list | None:
        return self.items.get(slot)

    def shrink(self, slot: int, n: int = 1) -> None:
        stack = self.items[slot]
        stack[1] -= n
        if stack[1] <= 0:
            del self.items[slot]

    def set_changed(self, world: World) -> None:
        """BlockEntity#setChanged: comparators next to the container re-read it."""
        if self.pos is None:
            return
        state = world.get(self.pos)
        if not state.is_air:
            world.update_neighbour_for_output_signal(self.pos, world.block(state))

    def remove_item(self, world: World, slot: int, n: int = 1) -> None:
        """BaseContainerBlockEntity#removeItem (notifies comparators)."""
        self.shrink(slot, n)
        self.set_changed(world)

    def redstone_signal(self) -> int:
        """AbstractContainerMenu#getRedstoneSignalFromContainer"""
        return redstone_signal_of(self.items.values(), self.size)


def get_container_at(world: World, pos: Pos) -> ContainerBlockEntity | None:
    """HopperBlockEntity#getContainerAt; container entities (minecarts) are not modeled."""
    state = world.get(pos)
    if not world.block(state).has_block_entity(state):
        return None
    be = world.get_block_entity(pos)
    if not isinstance(be, ContainerBlockEntity):
        return None
    as_container = getattr(be, "as_container", None)  # chests: a double chest is a CompoundContainer
    return as_container(world, state) if as_container is not None else be


def add_item(world: World, source: ContainerBlockEntity | None, container: ContainerBlockEntity, item: str,
             count: int = 1) -> int:
    """HopperBlockEntity#addItem for plain (non-worldly) containers. Returns the count that did not fit."""
    for slot in range(container.size):
        if count <= 0:
            break
        count = _try_move_in_item(world, source, container, item, count, slot)
    return count


def _try_move_in_item(world: World, source: ContainerBlockEntity | None, container: ContainerBlockEntity,
                      item: str, count: int, slot: int) -> int:
    """HopperBlockEntity#tryMoveInItem (canPlaceItem is true for every modeled container)."""
    current = container.items.get(slot)
    was_empty = container.is_empty()
    success = False
    if current is None:
        container.items[slot] = [item, min(count, container_max_stack(item))]  # setItem + limitSize
        count = 0
        success = True
    elif current[0] == item and current[1] <= item_max_stack_size(item):  # canMergeItems
        moved = min(count, item_max_stack_size(item) - current[1])
        count -= moved
        current[1] += moved
        success = moved > 0
    if success:
        on_receive = getattr(container, "on_item_received", None)
        if was_empty and on_receive is not None:
            on_receive(source)
        container.set_changed(world)
    return count


class ContainerBlock(Block):
    def __init__(self, size: int) -> None:
        super().__init__()
        self.size = size

    def has_block_entity(self, state):
        return True

    def new_block_entity(self, pos, state):
        return ContainerBlockEntity(self.size, pos)

    def has_analog_output_signal(self, state):
        return True

    def get_analog_output_signal(self, world, pos, state, direction):
        be = world.block_entities.get(pos)
        return be.redstone_signal() if isinstance(be, ContainerBlockEntity) else 0

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        """Containers#updateNeighboursAfterDestroy"""
        world.update_neighbour_for_output_signal(pos, self)


def facing(state: BlockState) -> Direction:
    return Direction.from_name(state.get("facing", "north"))


REGISTRY.register(ContainerBlock(27), "barrel")
