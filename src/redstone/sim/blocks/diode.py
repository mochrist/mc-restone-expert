"""Repeater and comparator: DiodeBlock, RepeaterBlock, ComparatorBlock, ComparatorBlockEntity (26.3).

`facing` points to the input side; the output goes to facing.opposite (knowledge REP-001, verified
in scenarios/repeater-delay-2.yaml).
"""

from __future__ import annotations

from ...model import AIR, BlockState, Direction, Pos
from ..block import REGISTRY, Block
from ..constants import UPDATE_CLIENTS, TickPriority
from ..notes import note
from ..world import ALL_DIRECTIONS, World

DIODES = ("minecraft:repeater", "minecraft:comparator")


def facing(state: BlockState) -> Direction:
    return Direction.from_name(state.get("facing", "north"))


def is_diode(state: BlockState) -> bool:
    return state.name in DIODES


class DiodeBlock(Block):
    side_input_diodes_only = False

    def is_signal_source(self, state):
        return True

    def get_delay(self, state: BlockState) -> int:
        raise NotImplementedError

    # --- survival ----------------------------------------------------------------
    def can_survive_on(self, world: World, below: Pos) -> bool:
        return world.is_face_sturdy(below, Direction.UP, "rigid")

    def can_survive(self, world, pos, state):
        return self.can_survive_on(world, pos.offset(Direction.DOWN))

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction is Direction.DOWN and not self.can_survive_on(world, neighbor_pos):
            return AIR
        return state

    # --- signals -------------------------------------------------------------------
    def own_signal(self, world, pos, state):
        return self.get_output_signal(world, pos, state) if state.get_bool("powered") else 0

    def get_signal(self, world, pos, state, direction):
        return self.own_signal(world, pos, state) if facing(state) is direction else 0

    def get_direct_signal(self, world, pos, state, direction):
        return self.get_signal(world, pos, state, direction)

    def get_output_signal(self, world: World, pos: Pos, state: BlockState) -> int:
        return 15

    def get_input_signal(self, world: World, pos: Pos, state: BlockState) -> int:
        d = facing(state)
        target = pos.offset(d)
        signal = world.get_signal(target, d)
        if signal >= 15:
            return signal
        t = world.get(target)
        return max(signal, t.get_int("power") if t.id == "redstone_wire" else 0)

    def get_alternate_signal(self, world: World, pos: Pos, state: BlockState) -> int:
        d = facing(state)
        cw, ccw = d.clockwise(), d.counter_clockwise()
        return max(
            world.get_control_input_signal(pos.offset(cw), cw, self.side_input_diodes_only),
            world.get_control_input_signal(pos.offset(ccw), ccw, self.side_input_diodes_only),
        )

    def should_turn_on(self, world: World, pos: Pos, state: BlockState) -> bool:
        return self.get_input_signal(world, pos, state) > 0

    def is_locked(self, world: World, pos: Pos, state: BlockState) -> bool:
        return False

    def should_prioritize(self, world: World, pos: Pos, state: BlockState) -> bool:
        d = facing(state).opposite
        other = world.get(pos.offset(d))
        return is_diode(other) and facing(other) is not d

    # --- updates -------------------------------------------------------------------
    def tick(self, world, pos, state):
        if self.is_locked(world, pos, state):
            note(world, "repeater_lock", pos)
            return
        on = state.get_bool("powered")
        should = self.should_turn_on(world, pos, state)
        if on and not should:
            world.set_block(pos, state.with_(powered=False), UPDATE_CLIENTS)
        elif not on:
            world.set_block(pos, state.with_(powered=True), UPDATE_CLIENTS)
            if not should:
                note(world, "repeater_pulse_extend", pos)
                world.schedule_tick(pos, self, self.get_delay(state), TickPriority.VERY_HIGH)

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        if world.get(pos).name != self.name:
            return
        if self.can_survive(world, pos, state):
            self.check_tick_on_neighbor(world, pos, state)
        else:
            world.remove_block(pos, False)
            for d in ALL_DIRECTIONS:
                world.update_neighbors_at(pos.offset(d), self)

    def check_tick_on_neighbor(self, world: World, pos: Pos, state: BlockState) -> None:
        if self.is_locked(world, pos, state):
            if state.get_bool("powered") != self.should_turn_on(world, pos, state):
                note(world, "repeater_lock", pos)
            return
        on = state.get_bool("powered")
        if on != self.should_turn_on(world, pos, state) and not world.will_tick_this_tick(pos, self):
            priority = TickPriority.HIGH
            if self.should_prioritize(world, pos, state):
                priority = TickPriority.EXTREMELY_HIGH
            elif on:
                priority = TickPriority.VERY_HIGH
            world.schedule_tick(pos, self, self.get_delay(state), priority)

    def on_place(self, world, pos, state, old, moved_by_piston):
        self.update_neighbors_in_front(world, pos, state)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if not moved_by_piston:
            self.update_neighbors_in_front(world, pos, state)

    def update_neighbors_in_front(self, world: World, pos: Pos, state: BlockState) -> None:
        d = facing(state)
        front = pos.offset(d.opposite)
        world.neighbor_changed(front, self)
        world.update_neighbors_at_except_from_facing(front, self, d)


class RepeaterBlock(DiodeBlock):
    side_input_diodes_only = True

    def should_redstone_wire_connect_to(self, world, pos, state, direction):
        # RepeaterBlock#shouldRedstoneWireConnectTo: only along the repeater's axis
        facing = Direction.from_name(state.get("facing", "north"))
        return direction is facing or direction is facing.opposite

    def get_delay(self, state):
        return state.get_int("delay", 1) * 2

    def is_locked(self, world, pos, state):
        return self.get_alternate_signal(world, pos, state) > 0

    def use_without_item(self, world, pos, state):
        delay = state.get_int("delay", 1) % 4 + 1
        world.set_block(pos, state.with_(delay=delay))  # setBlockAndUpdate
        return True

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction is Direction.DOWN and not self.can_survive_on(world, neighbor_pos):
            return AIR
        if direction.is_horizontal and direction not in (facing(state), facing(state).opposite):
            return state.with_(locked=self.is_locked(world, pos, state))
        return state


class ComparatorBlockEntity:
    ticks = False

    def __init__(self) -> None:
        self.output_signal = 0
        self.removed = False

    def load(self, data: dict) -> None:
        self.output_signal = int(data.get("OutputSignal", 0))


class ComparatorBlock(DiodeBlock):
    def get_delay(self, state):
        return 2

    def has_block_entity(self, state):
        return True

    def new_block_entity(self, pos, state):
        return ComparatorBlockEntity()

    def _be(self, world: World, pos: Pos) -> ComparatorBlockEntity | None:
        be = world.block_entities.get(pos)
        return be if isinstance(be, ComparatorBlockEntity) else None

    def get_output_signal(self, world, pos, state):
        be = self._be(world, pos)
        return be.output_signal if be else 0

    def get_input_signal(self, world, pos, state):
        result = super().get_input_signal(world, pos, state)
        d = facing(state)
        target = pos.offset(d)
        t = world.get(target)
        tb = world.block(t)
        if tb.has_analog_output_signal(t):
            note(world, "comparator_container", pos, t.id)
            return tb.get_analog_output_signal(world, target, t, d.opposite)
        if result < 15 and tb.is_conductor(t):
            target = target.offset(d)
            t = world.get(target)
            tb = world.block(t)
            # Item frames (entities) are not modeled.
            if tb.has_analog_output_signal(t):
                note(world, "comparator_through_block", pos, t.id)
                result = tb.get_analog_output_signal(world, target, t, d.opposite)
        return result

    def calculate_output_signal(self, world: World, pos: Pos, state: BlockState) -> int:
        inp = self.get_input_signal(world, pos, state)
        if inp == 0:
            return 0
        alt = self.get_alternate_signal(world, pos, state)
        if alt > inp:
            if state.get("mode") == "compare":
                note(world, "comparator_compare_block", pos)
            return 0
        if state.get("mode") == "subtract" and alt > 0:
            note(world, "comparator_subtract", pos)
        return inp - alt if state.get("mode") == "subtract" else inp

    def should_turn_on(self, world, pos, state):
        inp = self.get_input_signal(world, pos, state)
        if inp == 0:
            return False
        side = self.get_alternate_signal(world, pos, state)
        return inp > side or (inp == side and state.get("mode") == "compare")

    def use_without_item(self, world, pos, state):
        state = state.with_(mode="subtract" if state.get("mode") == "compare" else "compare")
        world.set_block(pos, state, UPDATE_CLIENTS)
        if world.get(pos).name == self.name:
            self.refresh_output_state(world, pos, state)
        return True

    def check_tick_on_neighbor(self, world, pos, state):
        if world.will_tick_this_tick(pos, self):
            return
        out = self.calculate_output_signal(world, pos, state)
        be = self._be(world, pos)
        old = be.output_signal if be else 0
        if out != old or state.get_bool("powered") != self.should_turn_on(world, pos, state):
            priority = TickPriority.HIGH if self.should_prioritize(world, pos, state) else TickPriority.NORMAL
            world.schedule_tick(pos, self, 2, priority)

    def refresh_output_state(self, world: World, pos: Pos, state: BlockState) -> None:
        out = self.calculate_output_signal(world, pos, state)
        be = self._be(world, pos)
        old = 0
        if be:
            old = be.output_signal
            be.output_signal = out
        if old != out or state.get("mode") == "compare":
            source_on = self.should_turn_on(world, pos, state)
            is_on = state.get_bool("powered")
            if is_on and not source_on:
                world.set_block(pos, state.with_(powered=False), UPDATE_CLIENTS)
            elif not is_on and source_on:
                world.set_block(pos, state.with_(powered=True), UPDATE_CLIENTS)
            self.update_neighbors_in_front(world, pos, state)

    def tick(self, world, pos, state):
        self.refresh_output_state(world, pos, state)


REGISTRY.register(RepeaterBlock(), "repeater")
REGISTRY.register(ComparatorBlock(), "comparator")
