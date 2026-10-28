"""Simple sources and outputs: lever, redstone block, redstone lamp.

References: LeverBlock, FaceAttachedHorizontalDirectionalBlock, PoweredBlock, RedstoneLampBlock (26.3).
"""

from __future__ import annotations

from ...model import BlockState, Direction, Pos
from ..block import REGISTRY, Block
from ..constants import UPDATE_CLIENTS
from ..world import World


def attached_direction(state: BlockState) -> Direction:
    """FaceAttachedHorizontalDirectionalBlock#getConnectedDirection: points from the support to the block."""
    face = state.get("face")
    if face == "ceiling":
        return Direction.DOWN
    if face == "floor":
        return Direction.UP
    return Direction.from_name(state.get("facing", "north"))


class LeverBlock(Block):
    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return 15 if state.get_bool("powered") else 0

    def get_direct_signal(self, world, pos, state, direction):
        return 15 if state.get_bool("powered") and attached_direction(state) is direction else 0

    def use_without_item(self, world, pos, state):
        self.pull(world, pos, state)
        return True

    def pull(self, world: World, pos: Pos, state: BlockState) -> None:
        state = state.with_(powered=not state.get_bool("powered"))
        world.set_block(pos, state)  # setBlockAndUpdate = flags 3
        self._update_neighbours(world, pos, state)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if not moved_by_piston and state.get_bool("powered"):
            self._update_neighbours(world, pos, state)

    def _update_neighbours(self, world: World, pos: Pos, state: BlockState) -> None:
        front = attached_direction(state).opposite
        world.update_neighbors_at(pos, self)
        world.update_neighbors_at(pos.offset(front), self)

    def can_survive(self, world, pos, state):
        d = attached_direction(state).opposite
        return world.is_face_sturdy(pos.offset(d), d.opposite)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if attached_direction(state).opposite is direction and not self.can_survive(world, pos, state):
            return BlockState.of("air")
        return state


class ButtonBlock(LeverBlock):
    """ButtonBlock: stone 20 gt, wooden 30 gt. Arrows/entities pressing it are not modeled."""

    def __init__(self, ticks_to_stay_pressed: int) -> None:
        super().__init__()
        self.ticks_to_stay_pressed = ticks_to_stay_pressed

    def use_without_item(self, world, pos, state):
        if state.get_bool("powered"):
            return True
        world.set_block(pos, state.with_(powered=True))
        self._update_neighbours(world, pos, state)
        world.schedule_tick(pos, self, self.ticks_to_stay_pressed)
        return True

    def tick(self, world, pos, state):
        if state.get_bool("powered"):  # checkPressed with no arrow inside: release
            world.set_block(pos, state.with_(powered=False))
            self._update_neighbours(world, pos, state)


class RedstoneBlock(Block):
    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return 15


class RedstoneLampBlock(Block):
    def on_place(self, world, pos, state, old, moved_by_piston):
        # RedstoneLampBlock has no onPlace override; placement state comes from getStateForPlacement.
        pass

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        lit = state.get_bool("lit")
        if lit != world.has_neighbor_signal(pos):
            if lit:
                world.schedule_tick(pos, self, 4)
            else:
                world.set_block(pos, state.with_(lit=True), UPDATE_CLIENTS)

    def tick(self, world, pos, state):
        if state.get_bool("lit") and not world.has_neighbor_signal(pos):
            world.set_block(pos, state.with_(lit=False), UPDATE_CLIENTS)


REGISTRY.register(LeverBlock(), "lever")
# One behaviour object per block type: scheduled ticks are keyed by block identity, as in the game.
for _name in ("stone_button", "polished_blackstone_button"):
    REGISTRY.register(ButtonBlock(20), _name)
for _wood in ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak",
              "bamboo", "crimson", "warped"):
    REGISTRY.register(ButtonBlock(30), f"{_wood}_button")
REGISTRY.register(RedstoneBlock(), "redstone_block")
REGISTRY.register(RedstoneLampBlock(), "redstone_lamp")
