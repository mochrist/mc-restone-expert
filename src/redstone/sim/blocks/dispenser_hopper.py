"""Dispenser, dropper and hopper.

References (26.3): DispenserBlock, DropperBlock, DispenserBlockEntity, HopperBlock, HopperBlockEntity;
knowledge/components/dropper-dispenser-hopper.md (DDH-*), knowledge/mechanics/quasi-connectivity.md (QC-002, QC-009).

Item entities are out of scope: an item that would be thrown into the world simply leaves the inventory,
and hoppers never pick up item entities.
"""

from __future__ import annotations

from ...model import Direction, Pos
from ..block import REGISTRY
from ..constants import UPDATE_CLIENTS
from ..world import World
from .container import ContainerBlock, ContainerBlockEntity, add_item, facing, get_container_at, item_max_stack_size

D = Direction

TRIGGER_DURATION = 4  # DispenserBlock.TRIGGER_DURATION
MOVE_ITEM_SPEED = 8  # HopperBlockEntity.MOVE_ITEM_SPEED


# ---------------------------------------------------------------------- dispenser / dropper
class DispenserBlockEntity(ContainerBlockEntity):
    def get_random_slot(self) -> int:
        """DispenserBlockEntity#getRandomSlot picks a uniformly random non-empty slot with the level random.

        ASSUMPTION: the simulator takes the first non-empty slot. With one item type per inventory this does
        not change the comparator output.
        """
        return min(self.items) if self.items else -1


class DispenserBlock(ContainerBlock):
    def __init__(self, dropper: bool) -> None:
        super().__init__(9)
        self.dropper = dropper

    def new_block_entity(self, pos, state):
        return DispenserBlockEntity(self.size, pos)

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        """DispenserBlock#neighborChanged, including quasi-connectivity (DDH-001, DDH-002, QC-002)."""
        should_trigger = world.has_neighbor_signal(pos) or world.has_neighbor_signal(pos.offset(D.UP))
        is_triggered = state.get_bool("triggered")
        if should_trigger and not is_triggered:
            world.schedule_tick(pos, self, TRIGGER_DURATION)
            world.set_block(pos, state.with_(triggered=True), UPDATE_CLIENTS)
        elif not should_trigger and is_triggered:
            world.set_block(pos, state.with_(triggered=False), UPDATE_CLIENTS)

    def tick(self, world, pos, state):
        """DispenserBlock#tick: dispense without re-checking power (DDH-003)."""
        self.dispense_from(world, pos, state)

    def dispense_from(self, world: World, pos: Pos, state) -> None:
        be = world.get_block_entity(pos)
        if not isinstance(be, DispenserBlockEntity):
            return
        slot = be.get_random_slot()
        if slot < 0:
            # level event 1001 (click sound); DispenserBlock also posts BLOCK_ACTIVATE, DropperBlock does not
            if not self.dropper:
                world.game_event("block_activate", pos, state)
            return
        item, count = be.items[slot]
        if self.dropper:
            # DropperBlock#dispenseFrom: insert one item into a container in front, otherwise drop it (DDH-006)
            direction = facing(world.get(pos))
            into = get_container_at(world, pos.offset(direction))
            if into is None or add_item(world, be, into, item, 1) == 0:
                count -= 1
        else:
            # ASSUMPTION: every item uses DefaultDispenseItemBehavior (throws one item). Item-specific
            # behaviours (buckets, bone meal, shulker boxes, arrows, armour on entities ...) are not modeled.
            count -= 1
        # BaseContainerBlockEntity#setItem (always notifies comparators)
        if count > 0:
            be.items[slot] = [item, count]
        else:
            del be.items[slot]
        be.set_changed(world)


# ---------------------------------------------------------------------- hopper
class HopperBlockEntity(ContainerBlockEntity):
    ticks = True

    def __init__(self, pos: Pos) -> None:
        super().__init__(5, pos)
        self.cooldown_time = -1
        self.ticked_game_time = 0

    def load(self, data: dict) -> None:
        super().load(data)
        self.cooldown_time = int(data.get("TransferCooldown", -1))

    def is_on_cooldown(self) -> bool:
        return self.cooldown_time > 0

    def is_on_custom_cooldown(self) -> bool:
        return self.cooldown_time > MOVE_ITEM_SPEED

    def on_item_received(self, source: ContainerBlockEntity | None) -> None:
        """HopperBlockEntity#tryMoveInItem: an empty hopper that receives an item waits (DDH-011)."""
        if self.is_on_custom_cooldown():
            return
        skip = 1 if isinstance(source, HopperBlockEntity) and self.ticked_game_time >= source.ticked_game_time else 0
        self.cooldown_time = MOVE_ITEM_SPEED - skip

    def is_idle(self) -> bool:
        """Not part of the game: true when the hopper has no cooldown running (used to detect a world at rest)."""
        return self.cooldown_time <= 0

    def inventory_full(self) -> bool:
        return len(self.items) == self.size and all(c == item_max_stack_size(i) for i, c in self.items.values())

    def tick(self, world: World) -> None:
        """HopperBlockEntity#pushItemsTick (DDH-009, DDH-012)."""
        state = world.get(self.pos)
        if state.id != "hopper":
            return
        self.cooldown_time -= 1
        self.ticked_game_time = world.game_time
        if not self.is_on_cooldown():
            self.cooldown_time = 0
            self.try_move_items(world, state)

    def try_move_items(self, world: World, state) -> bool:
        """HopperBlockEntity#tryMoveItems (DDH-008, DDH-010, DDH-013)."""
        if self.is_on_cooldown() or not state.get_bool("enabled"):
            return False
        changed = False
        if not self.is_empty():
            changed = self.eject_items(world, state)
        if not self.inventory_full():
            changed |= self.suck_in_items(world)
        if changed:
            self.cooldown_time = MOVE_ITEM_SPEED
            world.update_neighbour_for_output_signal(self.pos, world.block(state))
            return True
        return False

    def eject_items(self, world: World, state) -> bool:
        """HopperBlockEntity#ejectItems"""
        target = get_container_at(world, self.pos.offset(facing(state)))
        if target is None or self._is_full_container(target):
            return False
        for slot in range(self.size):
            stack = self.items.get(slot)
            if stack is None:
                continue
            item = stack[0]
            self.shrink(slot)  # HopperBlockEntity#removeItem does not call setChanged
            if add_item(world, self, target, item, 1) == 0:
                target.set_changed(world)
                return True
            # restore the original stack
            if slot in self.items:
                self.items[slot][1] += 1
            else:
                self.items[slot] = [item, 1]
        return False

    @staticmethod
    def _is_full_container(container: ContainerBlockEntity) -> bool:
        """HopperBlockEntity#isFullContainer"""
        for slot in range(container.size):
            stack = container.items.get(slot)
            if stack is None or stack[1] < item_max_stack_size(stack[0]):
                return False
        return True

    def suck_in_items(self, world: World) -> bool:
        """HopperBlockEntity#suckInItems from a container above; item entities are not modeled."""
        source = get_container_at(world, self.pos.offset(D.UP))
        if source is None:
            return False
        for slot in range(source.size):
            stack = source.items.get(slot)
            if stack is None:
                continue
            item = stack[0]
            if isinstance(source, HopperBlockEntity):
                source.shrink(slot)  # HopperBlockEntity#removeItem does not call setChanged
            else:
                source.remove_item(world, slot)
            if add_item(world, source, self, item, 1) == 0:
                source.set_changed(world)
                return True
            if slot in source.items:
                source.items[slot][1] += 1
            else:
                source.items[slot] = [item, 1]
                if not isinstance(source, HopperBlockEntity):
                    source.set_changed(world)
        return False


class HopperBlock(ContainerBlock):
    def __init__(self) -> None:
        super().__init__(5)

    def new_block_entity(self, pos, state):
        return HopperBlockEntity(pos)

    def on_place(self, world, pos, state, old, moved_by_piston):
        if old.name != state.name:
            self.check_powered_state(world, pos, state)

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        self.check_powered_state(world, pos, state)

    def check_powered_state(self, world: World, pos: Pos, state) -> None:
        """HopperBlock#checkPoweredState: no quasi-connectivity, no delay (DDH-007, QC-009)."""
        should_be_on = not world.has_neighbor_signal(pos)
        if should_be_on != state.get_bool("enabled"):
            world.set_block(pos, state.with_(enabled=should_be_on), UPDATE_CLIENTS)


REGISTRY.register(DispenserBlock(dropper=False), "dispenser")
REGISTRY.register(DispenserBlock(dropper=True), "dropper")
REGISTRY.register(HopperBlock(), "hopper")
