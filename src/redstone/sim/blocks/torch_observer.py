"""Redstone torches (standing and wall) and the observer.

References: RedstoneTorchBlock, RedstoneWallTorchBlock, BaseTorchBlock, ObserverBlock (26.3).
"""

from __future__ import annotations

from ...model import AIR, BlockState, Direction, Pos
from ..block import REGISTRY, Block
from ..constants import UPDATE_CLIENTS, UPDATE_KNOWN_SHAPE
from ..notes import note
from ..world import ALL_DIRECTIONS, World

RECENT_TOGGLE_TIMER = 60
MAX_RECENT_TOGGLES = 8
RESTART_DELAY = 160


def _toggles(world: World) -> list[tuple[Pos, int]]:
    """RedstoneTorchBlock.RECENT_TOGGLES: one list per level, shared by all torches."""
    if not hasattr(world, "torch_toggles"):
        world.torch_toggles = []
    return world.torch_toggles


def _toggled_too_frequently(world: World, pos: Pos, add: bool) -> bool:
    toggles = _toggles(world)
    if add:
        toggles.append((pos, world.game_time))
    return sum(1 for p, _ in toggles if p == pos) >= MAX_RECENT_TOGGLES


class RedstoneTorchBlock(Block):
    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return 15 if state.get_bool("lit") else 0

    def get_signal(self, world, pos, state, direction):
        return self.own_signal(world, pos, state) if direction is not Direction.UP else 0

    def get_direct_signal(self, world, pos, state, direction):
        return self.get_signal(world, pos, state, direction) if direction is Direction.DOWN else 0

    def has_neighbor_signal(self, world: World, pos: Pos, state: BlockState) -> bool:
        return world.has_signal(pos.offset(Direction.DOWN), Direction.DOWN)

    def can_survive(self, world, pos, state):
        # BaseTorchBlock: canSupportCenter(below, UP)
        return world.is_face_sturdy(pos.offset(Direction.DOWN), Direction.UP, "center")

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction is Direction.DOWN and not self.can_survive(world, pos, state):
            return AIR
        return state

    def notify_neighbors(self, world: World, pos: Pos) -> None:
        for d in ALL_DIRECTIONS:
            world.update_neighbors_at(pos.offset(d), self)

    def on_place(self, world, pos, state, old, moved_by_piston):
        self.notify_neighbors(world, pos)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if not moved_by_piston:
            self.notify_neighbors(world, pos)

    def tick(self, world, pos, state):
        signal = self.has_neighbor_signal(world, pos, state)
        toggles = _toggles(world)
        while toggles and world.game_time - toggles[0][1] > RECENT_TOGGLE_TIMER:
            toggles.pop(0)
        if state.get_bool("lit"):
            if signal:
                world.set_block(pos, state.with_(lit=False))
                if _toggled_too_frequently(world, pos, True):
                    note(world, "torch_burnout", pos)
                    world.schedule_tick(pos, world.get(pos).name, RESTART_DELAY)
        elif not signal and not _toggled_too_frequently(world, pos, False):
            world.set_block(pos, state.with_(lit=True))

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        if state.get_bool("lit") == self.has_neighbor_signal(world, pos, state) and not world.will_tick_this_tick(pos, self):
            world.schedule_tick(pos, self, 2)


class RedstoneWallTorchBlock(RedstoneTorchBlock):
    @staticmethod
    def _facing(state: BlockState) -> Direction:
        return Direction.from_name(state.get("facing", "north"))

    def has_neighbor_signal(self, world, pos, state):
        opp = self._facing(state).opposite
        return world.has_signal(pos.offset(opp), opp)

    def get_signal(self, world, pos, state, direction):
        return self.own_signal(world, pos, state) if self._facing(state) is not direction else 0

    def can_survive(self, world, pos, state):
        f = self._facing(state)
        return world.is_face_sturdy(pos.offset(f.opposite), f)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction.opposite is self._facing(state) and not self.can_survive(world, pos, state):
            return AIR
        return state


class ObserverBlock(Block):
    def should_redstone_wire_connect_to(self, world, pos, state, direction):
        # ObserverBlock#shouldRedstoneWireConnectTo: only at the output (back) side
        return direction is Direction.from_name(state.get("facing", "north"))

    @staticmethod
    def _facing(state: BlockState) -> Direction:
        return Direction.from_name(state.get("facing", "south"))

    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return 15 if state.get_bool("powered") else 0

    def get_signal(self, world, pos, state, direction):
        return self.own_signal(world, pos, state) if self._facing(state) is direction else 0

    def get_direct_signal(self, world, pos, state, direction):
        return self.get_signal(world, pos, state, direction)

    def tick(self, world, pos, state):
        if state.get_bool("powered"):
            world.set_block(pos, state.with_(powered=False), UPDATE_CLIENTS)
        else:
            world.set_block(pos, state.with_(powered=True), UPDATE_CLIENTS)
            world.schedule_tick(pos, self, 2)
        self.update_neighbors_in_front(world, pos, state)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if self._facing(state) is direction and not state.get_bool("powered"):
            if not world.has_scheduled_tick(pos, self):
                note(world, "observer_pulse", pos)
                world.schedule_tick(pos, self, 2)
        return state

    def update_neighbors_in_front(self, world: World, pos: Pos, state: BlockState) -> None:
        d = self._facing(state)
        front = pos.offset(d.opposite)
        world.neighbor_changed(front, self)
        world.update_neighbors_at_except_from_facing(front, self, d)

    def on_place(self, world, pos, state, old, moved_by_piston):
        if state.name != old.name and state.get_bool("powered") and not world.has_scheduled_tick(pos, self):
            new = state.with_(powered=False)
            world.set_block(pos, new, UPDATE_CLIENTS | UPDATE_KNOWN_SHAPE)
            self.update_neighbors_in_front(world, pos, new)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if state.get_bool("powered") and world.has_scheduled_tick(pos, self):
            self.update_neighbors_in_front(world, pos, state.with_(powered=False))


REGISTRY.register(RedstoneTorchBlock(), "redstone_torch")
REGISTRY.register(RedstoneWallTorchBlock(), "redstone_wall_torch")
REGISTRY.register(ObserverBlock(), "observer")
