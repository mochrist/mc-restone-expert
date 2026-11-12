"""Simple sources and outputs: lever, buttons, pressure plates, redstone block, redstone lamp.

References: LeverBlock, ButtonBlock, BasePressurePlateBlock, FaceAttachedHorizontalDirectionalBlock, PoweredBlock, RedstoneLampBlock (26.3).
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
        world.game_event("block_activate" if state.get_bool("powered") else "block_deactivate", pos)

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
        world.game_event("block_activate", pos)
        return True

    def tick(self, world, pos, state):
        if state.get_bool("powered"):  # checkPressed with no arrow inside: release
            world.set_block(pos, state.with_(powered=False))
            self._update_neighbours(world, pos, state)
            world.game_event("block_deactivate", pos)


class PressurePlateBlock(Block):
    """BasePressurePlateBlock. Entities are not simulated: action "step" emulates one entity stepping on the
    plate and leaving again right away (a right click, action "use", does nothing, as in the game) (entityInside -> checkPressed); the scheduled tick then releases it.
    ASSUMPTION: a weighted plate sees exactly one entity (light: ceil(1/15*15) = 1, heavy: ceil(1/150*15) = 1)."""

    def __init__(self, pressed_time: int, weighted: bool) -> None:
        super().__init__()
        self.pressed_time = pressed_time
        self.weighted = weighted

    def _signal(self, state: BlockState) -> int:
        return int(state.get("power")) if self.weighted else (15 if state.get_bool("powered") else 0)

    def _with_signal(self, state: BlockState, signal: int) -> BlockState:
        return state.with_(power=str(signal)) if self.weighted else state.with_(powered=signal > 0)

    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return self._signal(state)

    def get_direct_signal(self, world, pos, state, direction):
        return self._signal(state) if direction is Direction.UP else 0

    def step_on(self, world, pos, state):
        if self._signal(state) == 0:
            self._check_pressed(world, pos, state, 1 if self.weighted else 15)
        return True

    def tick(self, world, pos, state):
        if self._signal(state) > 0:
            self._check_pressed(world, pos, state, 0)  # nobody on the plate any more

    def _check_pressed(self, world: World, pos: Pos, state: BlockState, signal: int) -> None:
        old_signal = self._signal(state)
        if old_signal != signal:
            world.set_block(pos, self._with_signal(state, signal), UPDATE_CLIENTS)
            self._update_neighbours(world, pos)
        if old_signal > 0 and signal == 0:
            world.game_event("block_deactivate", pos)
        elif old_signal == 0 and signal > 0:
            world.game_event("block_activate", pos)
        if signal > 0:
            world.schedule_tick(pos, self, self.pressed_time)

    def _update_neighbours(self, world: World, pos: Pos) -> None:
        world.update_neighbors_at(pos, self)
        world.update_neighbors_at(pos.offset(Direction.DOWN), self)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if not moved_by_piston and self._signal(state) > 0:
            self._update_neighbours(world, pos)

    def can_survive(self, world, pos, state):
        below = pos.offset(Direction.DOWN)
        return world.is_face_sturdy(below, Direction.UP, "rigid") or world.is_face_sturdy(below, Direction.UP, "center")

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction is Direction.DOWN and not self.can_survive(world, pos, state):
            return BlockState.of("air")
        return state


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
for _name in ("stone", "polished_blackstone") + tuple(_w for _w in (
        "oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak", "bamboo",
        "crimson", "warped")):
    REGISTRY.register(PressurePlateBlock(20, False), f"{_name}_pressure_plate")
REGISTRY.register(PressurePlateBlock(10, True), "light_weighted_pressure_plate")
REGISTRY.register(PressurePlateBlock(10, True), "heavy_weighted_pressure_plate")
REGISTRY.register(RedstoneBlock(), "redstone_block")
REGISTRY.register(RedstoneLampBlock(), "redstone_lamp")
