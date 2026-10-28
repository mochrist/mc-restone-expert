"""Block behaviour base class and registry, mirroring net.minecraft.world.level.block.state.BlockBehaviour.

Each block type has one stateless behaviour object. Method names follow the game's
(snake_case), so behaviour can be compared side by side with the decompiled source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model import BlockState, Direction, Pos
from . import blockdata

if TYPE_CHECKING:
    from .world import World


class Block:
    name: str = ""
    # True for blocks the simulator models faithfully; others behave like inert blocks.
    modeled: bool = True

    def __init__(self, name: str | None = None) -> None:
        if name is not None:
            self.name = name

    # --- static properties -------------------------------------------------------
    def is_conductor(self, state: BlockState) -> bool:
        return blockdata.is_conductor(state)

    def is_face_sturdy(self, state: BlockState, face: Direction, support: str = "full") -> bool:
        return blockdata.is_face_sturdy(state, face, support)

    def is_signal_source(self, state: BlockState) -> bool:
        return False

    def should_redstone_wire_connect_to(self, world: World, pos: Pos, state: BlockState,
                                        direction: Direction | None) -> bool:
        """BlockBehaviour#shouldRedstoneWireConnectTo; ``direction`` points from the wire to this block."""
        return self.is_signal_source(state) and direction is not None

    def has_analog_output_signal(self, state: BlockState) -> bool:
        return False

    def has_block_entity(self, state: BlockState) -> bool:
        return False

    def get_piston_push_reaction(self, state: BlockState) -> str:
        """BlockStateBase#getPistonPushReaction (raw): PUSH_PULL, PUSH, POPPED, IMMOVEABLE or IGNORE_ENTITY."""
        return blockdata.piston_push_reaction(state).upper()

    # --- signals -------------------------------------------------------------------
    def get_signal(self, world: World, pos: Pos, state: BlockState, direction: Direction) -> int:
        return self.own_signal(world, pos, state)

    def own_signal(self, world: World, pos: Pos, state: BlockState) -> int:
        return 0

    def get_direct_signal(self, world: World, pos: Pos, state: BlockState, direction: Direction) -> int:
        return 0

    def get_analog_output_signal(self, world: World, pos: Pos, state: BlockState, direction: Direction) -> int:
        return 0

    # --- updates -------------------------------------------------------------------
    def on_place(self, world: World, pos: Pos, state: BlockState, old: BlockState, moved_by_piston: bool) -> None:
        pass

    def affect_neighbors_after_removal(self, world: World, pos: Pos, state: BlockState, moved_by_piston: bool) -> None:
        pass

    def neighbor_changed(self, world: World, pos: Pos, state: BlockState, source: Block, moved_by_piston: bool) -> None:
        pass

    def update_shape(self, world: World, pos: Pos, state: BlockState, direction: Direction,
                     neighbor_pos: Pos, neighbor_state: BlockState) -> BlockState:
        """Return the new state of this block after its neighbor in ``direction`` changed shape."""
        return state

    def update_indirect_neighbour_shapes(self, world: World, pos: Pos, state: BlockState, flags: int, limit: int) -> None:
        pass

    def tick(self, world: World, pos: Pos, state: BlockState) -> None:
        pass

    def trigger_event(self, world: World, pos: Pos, state: BlockState, a: int, b: int) -> bool:
        return False

    def use_without_item(self, world: World, pos: Pos, state: BlockState) -> bool:
        """Player right click without an item. Returns True if the block reacted."""
        return False

    def can_survive(self, world: World, pos: Pos, state: BlockState) -> bool:
        return True

    def new_block_entity(self, pos: Pos, state: BlockState):
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"


class UnmodeledBlock(Block):
    """Any block without redstone behaviour in the simulator: inert, uses the static property tables."""

    modeled = False


class AirBlock(Block):
    def is_conductor(self, state: BlockState) -> bool:
        return False

    def is_face_sturdy(self, state: BlockState, face: Direction) -> bool:
        return False


# Blocks without redstone behaviour that are known not to need modelling.
INERT_OK_HINTS = ("stone", "wool", "concrete", "planks", "log", "glass", "dirt", "slab", "terracotta",
                  "bricks", "deepslate", "cobble", "sand", "gravel", "obsidian", "ore", "quartz", "copper",
                  "wood", "iron_block", "gold_block", "diamond_block", "emerald_block", "netherrack")


class Registry:
    def __init__(self) -> None:
        self._blocks: dict[str, Block] = {}
        self._air = AirBlock("minecraft:air")
        self._unmodeled: dict[str, Block] = {}

    def register(self, block: Block, *names: str) -> Block:
        for name in names or (block.name,):
            full = name if ":" in name else f"minecraft:{name}"
            self._blocks[full] = block
            if not block.name:
                block.name = full
        return block

    def get(self, name: str) -> Block:
        block = self._blocks.get(name)
        if block is not None:
            return block
        if name in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
            return self._air
        block = self._unmodeled.get(name)
        if block is None:
            block = self._unmodeled[name] = UnmodeledBlock(name)
        return block

    def is_modeled(self, name: str) -> bool:
        return name in self._blocks

    def needs_model(self, name: str) -> bool:
        """Unknown block that may well have redstone behaviour (used for warnings)."""
        if self.is_modeled(name) or name.endswith("air"):
            return False
        short = name.split(":", 1)[1]
        return not any(h in short for h in INERT_OK_HINTS)


REGISTRY = Registry()
