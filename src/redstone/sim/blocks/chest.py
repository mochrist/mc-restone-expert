"""Chests, trapped chests and copper chests (single and double).

References (26.3): ChestBlock, TrappedChestBlock, CopperChestBlock, ChestBlockEntity, TrappedChestBlockEntity,
DoubleBlockCombiner, CompoundContainer (not in the decompiled tree; behaviour as in the game's source: slots
of the first container, then the second; ``setChanged`` on both; max stack size of the first),
HopperBlockEntity#getBlockContainer (hoppers ignore blocking), knowledge/components/chests.md (CHEST-*).

Not modeled: players (no opener count, so a trapped chest never emits a signal), cats sitting on chests, loot
tables, waterlogging ticks, the weathering sync of copper chests (CopperChestBlock#updateShape).
"""

from __future__ import annotations

from collections.abc import MutableMapping

from ...model import BlockState, Direction
from ..block import REGISTRY
from .container import ContainerBlock, ContainerBlockEntity, redstone_signal_of

CHEST_SIZE = 27
COPPER_CHESTS = tuple(
    f"{prefix}copper_chest" for prefix in ("", "exposed_", "weathered_", "oxidized_",
                                           "waxed_", "waxed_exposed_", "waxed_weathered_", "waxed_oxidized_")
)
COPPER_CHEST_NAMES = frozenset(f"minecraft:{n}" for n in COPPER_CHESTS)


class ChestBlockEntity(ContainerBlockEntity):
    """ChestBlockEntity: 27 slots, comparator output is combined with the neighbouring half in ChestBlock."""

    def __init__(self, pos=None) -> None:
        super().__init__(CHEST_SIZE, pos)

    def as_container(self, world, state) -> ContainerBlockEntity:
        """HopperBlockEntity#getBlockContainer: ChestBlock#getContainer with ignoreBeingBlocked = true."""
        return get_container(world, self.pos, state, ignore_blocked=True) or self


class _CompoundItems(MutableMapping):
    """``slot -> [item, count]`` view over two chests (CompoundContainer slot numbering)."""

    def __init__(self, first: ChestBlockEntity, second: ChestBlockEntity) -> None:
        self.first, self.second = first, second

    def part(self, slot: int):
        if slot >= self.first.size:
            return self.second, slot - self.first.size
        return self.first, slot

    def __getitem__(self, slot):
        be, local = self.part(slot)
        return be.items[local]

    def __setitem__(self, slot, value):
        be, local = self.part(slot)
        be.items[local] = value

    def __delitem__(self, slot):
        be, local = self.part(slot)
        del be.items[local]

    def __iter__(self):
        for slot in self.first.items:
            yield slot
        for slot in self.second.items:
            yield slot + self.first.size

    def __len__(self):
        return len(self.first.items) + len(self.second.items)


class CompoundContainer(ContainerBlockEntity):
    """CompoundContainer(first, second); ``first`` is the RIGHT half, ``second`` the LEFT half."""

    def __init__(self, first: ChestBlockEntity, second: ChestBlockEntity) -> None:
        super().__init__(first.size + second.size, first.pos)
        self.first, self.second = first, second
        self.items = _CompoundItems(first, second)

    def is_empty(self) -> bool:
        return self.first.is_empty() and self.second.is_empty()

    def shrink(self, slot: int, n: int = 1) -> None:
        be, local = self.items.part(slot)
        be.shrink(local, n)

    def remove_item(self, world, slot: int, n: int = 1) -> None:
        be, local = self.items.part(slot)
        be.remove_item(world, local, n)

    def set_changed(self, world) -> None:
        self.first.set_changed(world)
        self.second.set_changed(world)

    def redstone_signal(self) -> int:
        return redstone_signal_of(self.items.values(), self.size)


def _blocked_at(world, pos) -> bool:
    """ChestBlock#isChestBlockedAt: a redstone conductor above (cats are not modeled)."""
    return world.is_conductor(pos.offset(Direction.UP))


def _connected_direction(state: BlockState) -> Direction:
    """ChestBlock#getConnectedDirection"""
    facing = Direction.from_name(state.get("facing", "north"))
    return facing.clockwise() if state.get("type") == "left" else facing.counter_clockwise()


def get_container(world, pos, state, ignore_blocked: bool) -> ContainerBlockEntity | None:
    """ChestBlock#getContainer / DoubleBlockCombiner#combineWithNeigbour"""
    be = world.get_block_entity(pos)
    if not isinstance(be, ChestBlockEntity):
        return None
    if not ignore_blocked and _blocked_at(world, pos):
        return None
    typ = state.get("type", "single")
    if typ == "single":
        return be
    neighbour_pos = pos.offset(_connected_direction(state))
    neighbour = world.get(neighbour_pos)
    if neighbour.name == state.name:
        ntyp = neighbour.get("type", "single")
        if ntyp != "single" and ntyp != typ and neighbour.get("facing") == state.get("facing"):
            if not ignore_blocked and _blocked_at(world, neighbour_pos):
                return None
            nbe = world.get_block_entity(neighbour_pos)
            if isinstance(nbe, ChestBlockEntity):
                first, second = (be, nbe) if typ == "right" else (nbe, be)
                return CompoundContainer(first, second)
    return be


class ChestBlock(ContainerBlock):
    def __init__(self, trapped: bool = False) -> None:
        super().__init__(CHEST_SIZE)
        self.trapped = trapped

    def new_block_entity(self, pos, state):
        return ChestBlockEntity(pos)

    @staticmethod
    def can_connect_to(state: BlockState, own: BlockState) -> bool:
        """ChestBlock#chestCanConnectTo (copper chests: any copper chest)."""
        if own.name in COPPER_CHEST_NAMES:
            return state.name in COPPER_CHEST_NAMES and state.get("type") is not None
        return state.name == own.name

    def get_analog_output_signal(self, world, pos, state, direction):
        container = get_container(world, pos, state, ignore_blocked=False)
        return container.redstone_signal() if container is not None else 0

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        """ChestBlock#updateShape (waterlogging ticks are not modeled)."""
        if self.can_connect_to(neighbor_state, state) and direction.is_horizontal:
            ntyp = neighbor_state.get("type", "single")
            if (state.get("type") == "single" and ntyp != "single"
                    and state.get("facing") == neighbor_state.get("facing")
                    and _connected_direction(neighbor_state) == direction.opposite):
                return state.with_(type="left" if ntyp == "right" else "right")
        elif _connected_direction(state) == direction:
            return state.with_(type="single")
        return state

    # TrappedChestBlock
    def is_signal_source(self, state):
        return self.trapped

    def get_direct_signal(self, world, pos, state, direction):
        return self.get_signal(world, pos, state, direction) if self.trapped and direction is Direction.UP else 0

    def own_signal(self, world, pos, state):
        return 0  # Mth.clamp(ChestBlockEntity.getOpenCount, 0, 15); no players, so nobody has the chest open


REGISTRY.register(ChestBlock(), "chest", *COPPER_CHESTS)
REGISTRY.register(ChestBlock(trapped=True), "trapped_chest")
