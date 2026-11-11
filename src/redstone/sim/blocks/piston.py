"""Pistons: piston, sticky_piston, piston_head, moving_piston and the moving block entity.

References (26.3, Mojang names): PistonBaseBlock, PistonHeadBlock, MovingPistonBlock,
PistonMovingBlockEntity, PistonStructureResolver (net.minecraft.world.level.block.piston).
Entity movement (moveCollidedEntities, moveStuckEntities) is out of scope.
"""

from __future__ import annotations

from typing import Any

from ...model import AIR, BlockState, Direction, Pos
from .. import blockdata
from ..block import REGISTRY, Block
from ..constants import UPDATE_ALL, UPDATE_LIMIT
from ..notes import note, register_state_check
from ..world import UPDATE_SHAPE_ORDER, World

D = Direction
ALL_DIRECTIONS = tuple(D)  # Direction.values()

TRIGGER_EXTEND = 0
TRIGGER_CONTRACT = 1
TRIGGER_DROP = 2
MAX_PUSH_DEPTH = 12

# World positions are absolute (the runner places scenarios at the oracle origin). They matter for the
# build height check in isPushable and the HashMap iteration order in moveBlocks (BlockPos#hashCode).
MIN_Y, MAX_Y = -64, 319  # overworld build limits


def data_value(direction: Direction) -> int:
    """Direction#get3DDataValue (D, U, N, S, W, E = 0..5)."""
    return ALL_DIRECTIONS.index(direction)


def facing(state: BlockState) -> Direction:
    return Direction.from_name(state.get("facing", "north"))


def is_piston_base(state: BlockState) -> bool:
    return state.id in ("piston", "sticky_piston")


def get_piston_be(world: World, pos: Pos) -> PistonMovingBlockEntity | None:
    be = world.get_block_entity(pos)
    return be if isinstance(be, PistonMovingBlockEntity) else None


def push_reaction(world: World, state: BlockState) -> str:
    return world.block(state).get_piston_push_reaction(state)


def update_from_neighbour_shapes(world: World, state: BlockState, pos: Pos) -> BlockState:
    """Block#updateFromNeighbourShapes"""
    new = state
    for d in UPDATE_SHAPE_ORDER:
        npos = pos.offset(d)
        new = world.block(new).update_shape(world, pos, new, d, npos, world.get(npos))
    return new


class PosHashMap:
    """java.util.HashMap<BlockPos, BlockState> iteration order (no treeification; <= 13 entries in practice)."""

    def __init__(self) -> None:
        self.cap = 16
        self.buckets: list[list[list[Any]]] = [[] for _ in range(self.cap)]
        self.size = 0

    @staticmethod
    def _hash(pos: Pos) -> int:
        x, y, z = pos
        h = ((y + z * 31) * 31 + x) & 0xFFFFFFFF  # Vec3i#hashCode as int32 bits
        return h ^ (h >> 16)

    def _bucket(self, pos: Pos) -> list[list[Any]]:
        return self.buckets[self._hash(pos) & (self.cap - 1)]

    def _resize(self) -> None:
        old = [e for b in self.buckets for e in b]
        self.cap *= 2
        self.buckets = [[] for _ in range(self.cap)]
        for e in old:  # split keeps relative order within each new bucket
            self._bucket(e[0]).append(e)

    def put(self, pos: Pos, value: Any) -> None:
        bucket = self._bucket(pos)
        for e in bucket:
            if e[0] == pos:
                e[1] = value
                return
        bucket.append([pos, value])
        if len(bucket) >= 9 and self.cap < 64:  # treeifyBin resizes small tables instead
            self._resize()
        self.size += 1
        if self.size > self.cap * 3 // 4:
            self._resize()

    def remove(self, pos: Pos) -> None:
        bucket = self._bucket(pos)
        for i, e in enumerate(bucket):
            if e[0] == pos:
                del bucket[i]
                self.size -= 1
                return

    def items(self) -> list[tuple[Pos, Any]]:
        return [(e[0], e[1]) for b in self.buckets for e in b]


# ---------------------------------------------------------------------- PistonStructureResolver
def is_pushable(world: World, state: BlockState, pos: Pos, direction: Direction, allow_destroyable: bool,
                connection_direction: Direction) -> bool:
    """PistonBaseBlock#isPushable"""
    y = pos.y
    if y < MIN_Y or y > MAX_Y:
        return False
    if state.is_air:
        return True
    if direction is D.DOWN and y == MIN_Y:
        return False
    if direction is D.UP and y == MAX_Y:
        return False
    if not is_piston_base(state):
        if blockdata.is_unbreakable(state):  # getDestroySpeed == -1
            return False
        reaction = push_reaction(world, state)
        if reaction == "IMMOVEABLE":
            return False
        if reaction == "POPPED":
            return allow_destroyable
        if reaction == "PUSH":
            return direction is connection_direction
    elif state.get_bool("extended"):
        return False
    return not (world.block(state).has_block_entity(state) or blockdata.has_block_entity(state))


def _is_sticky(state: BlockState) -> bool:
    return state.id in ("slime_block", "honey_block")


def _can_stick_to_each_other(a: BlockState, b: BlockState) -> bool:
    if a.id == "honey_block" and b.id == "slime_block":
        return False
    if a.id == "slime_block" and b.id == "honey_block":
        return False
    return _is_sticky(a) or _is_sticky(b)


class PistonStructureResolver:
    def __init__(self, world: World, piston_pos: Pos, direction: Direction, extending: bool) -> None:
        self.world = world
        self.piston_pos = piston_pos
        self.piston_direction = direction
        self.extending = extending
        if extending:
            self.push_direction = direction
            self.start_pos = piston_pos.offset(direction)
        else:
            self.push_direction = direction.opposite
            self.start_pos = piston_pos.offset(direction, 2)
        self.to_push: list[Pos] = []
        self.to_destroy: list[Pos] = []

    def resolve(self) -> bool:
        self.to_push.clear()
        self.to_destroy.clear()
        w = self.world
        next_state = w.get(self.start_pos)
        if not is_pushable(w, next_state, self.start_pos, self.push_direction, False, self.piston_direction):
            if self.extending and push_reaction(w, next_state) == "POPPED":
                self.to_destroy.append(self.start_pos)
                return True
            return False
        if not self.add_block_line(self.start_pos, self.push_direction):
            return False
        i = 0
        while i < len(self.to_push):
            pos = self.to_push[i]
            if _is_sticky(w.get(pos)) and not self.add_branching_blocks(pos):
                return False
            i += 1
        return True

    def add_block_line(self, start: Pos, direction: Direction) -> bool:
        w = self.world
        back = self.push_direction.opposite
        next_state = w.get(start)
        if next_state.is_air:
            return True
        if not is_pushable(w, next_state, start, self.push_direction, False, direction):
            return True
        if start == self.piston_pos:
            return True
        if start in self.to_push:
            return True
        block_count = 1
        if block_count + len(self.to_push) > MAX_PUSH_DEPTH:
            return False
        while _is_sticky(next_state):
            pos = start.offset(back, block_count)
            previous = next_state
            next_state = w.get(pos)
            if (next_state.is_air or not _can_stick_to_each_other(previous, next_state)
                    or not is_pushable(w, next_state, pos, self.push_direction, False, back)
                    or pos == self.piston_pos):
                break
            block_count += 1
            if block_count + len(self.to_push) > MAX_PUSH_DEPTH:
                return False
        blocks_added = 0
        for i in range(block_count - 1, -1, -1):
            self.to_push.append(start.offset(back, i))
            blocks_added += 1
        i = 1
        while True:
            pos = start.offset(self.push_direction, i)
            collision = self.to_push.index(pos) if pos in self.to_push else -1
            if collision > -1:
                self.reorder_list_at_collision(blocks_added, collision)
                for j in range(collision + blocks_added + 1):
                    p = self.to_push[j]
                    if _is_sticky(w.get(p)) and not self.add_branching_blocks(p):
                        return False
                return True
            next_state = w.get(pos)
            if next_state.is_air:
                return True
            if not is_pushable(w, next_state, pos, self.push_direction, True, self.push_direction) \
                    or pos == self.piston_pos:
                return False
            if push_reaction(w, next_state) == "POPPED":
                self.to_destroy.append(pos)
                return True
            if len(self.to_push) >= MAX_PUSH_DEPTH:
                return False
            self.to_push.append(pos)
            blocks_added += 1
            i += 1

    def reorder_list_at_collision(self, blocks_added: int, collision: int) -> None:
        n = len(self.to_push)
        head = self.to_push[:collision]
        last_line = self.to_push[n - blocks_added:]
        collision_to_line = self.to_push[collision:n - blocks_added]
        self.to_push[:] = head + last_line + collision_to_line

    def add_branching_blocks(self, from_pos: Pos) -> bool:
        w = self.world
        from_state = w.get(from_pos)
        for d in ALL_DIRECTIONS:
            if _same_axis(d, self.push_direction):
                continue
            npos = from_pos.offset(d)
            if _can_stick_to_each_other(w.get(npos), from_state) and not self.add_block_line(npos, d):
                return False
        return True


def _same_axis(a: Direction, b: Direction) -> bool:
    return a is b or a is b.opposite


# ---------------------------------------------------------------------- PistonBaseBlock
class PistonBaseBlock(Block):
    def __init__(self, sticky: bool) -> None:
        super().__init__()
        self.is_sticky = sticky

    def is_conductor(self, state):
        return False

    def get_piston_push_reaction(self, state):
        return "IMMOVEABLE"

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        self.check_if_extend(world, pos, state, source)

    def on_place(self, world, pos, state, old, moved_by_piston):
        if old.name != state.name and world.get_block_entity(pos) is None:
            self.check_if_extend(world, pos, state)

    def check_if_extend(self, world: World, pos: Pos, state: BlockState, source: Block | None = None) -> None:
        direction = facing(state)
        extend = self.get_neighbor_signal(world, pos, direction)
        extended = state.get_bool("extended")
        if extend and not extended:
            if PistonStructureResolver(world, pos, direction, True).resolve():
                world.block_event(pos, self, TRIGGER_EXTEND, data_value(direction))
                self._note_activation(world, pos, direction, source)
        elif not extend and extended:
            if source is not None and not _can_remove_power(source):
                note(world, "bud", pos, "blieb unbestromt ausgefahren, bis ein Block-Update kam")
            pushed_pos = pos.offset(direction, 2)
            pushed_state = world.get(pushed_pos)
            event = TRIGGER_CONTRACT
            if pushed_state.id == "moving_piston" and facing(pushed_state) is direction:
                be = get_piston_be(world, pushed_pos)
                if be is not None and be.extending and (
                        be.get_progress(0.0) < 0.5 or world.game_time == be.last_ticked or world.handling_tick):
                    event = TRIGGER_DROP
            world.block_event(pos, self, event, data_value(direction))

    def get_neighbor_signal(self, world: World, pos: Pos, push_direction: Direction) -> bool:
        return self.has_direct_signal(world, pos, push_direction) or self.has_qc_signal(world, pos)

    @staticmethod
    def has_direct_signal(world: World, pos: Pos, push_direction: Direction) -> bool:
        """First part of PistonBaseBlock#getNeighborSignal: the five sides except the front."""
        return any(d is not push_direction and world.has_signal(pos.offset(d), d) for d in ALL_DIRECTIONS)

    @staticmethod
    def has_qc_signal(world: World, pos: Pos) -> bool:
        """Second part of getNeighborSignal (quasi-connectivity): the position above counts like the piston."""
        if world.has_signal(pos, D.DOWN):
            return True
        above = pos.offset(D.UP)
        return any(d is not D.DOWN and world.has_signal(above.offset(d), d) for d in ALL_DIRECTIONS)

    # --- mechanics notes (analysis only, no influence on the simulation) ------------------
    def _note_activation(self, world: World, pos: Pos, direction: Direction, source: Block | None) -> None:
        if self.has_direct_signal(world, pos, direction):
            return
        note(world, "quasi_connectivity", pos)
        if source is not None and not _can_change_power(source):
            # The update came from a block that cannot have produced the power, so the piston was already
            # quasi-powered before and only reacts now (knowledge BUD-004, QC-007).
            note(world, "bud", pos, "fuhr erst nach einem Block-Update ohne Leistungsänderung aus")

    def trigger_event(self, world, pos, state, b0, b1):
        direction = facing(state)
        extended_state = state.with_(extended=True)
        extend = self.get_neighbor_signal(world, pos, direction)
        if extend and b0 in (TRIGGER_CONTRACT, TRIGGER_DROP):
            world.set_block(pos, extended_state, 2)
            return False
        if not extend and b0 == TRIGGER_EXTEND:
            return False

        if b0 == TRIGGER_EXTEND:
            if not self.move_blocks(world, pos, direction, True):
                return False
            world.set_block(pos, extended_state, 67)
            world.game_event("block_activate", pos, extended_state)
        elif b0 in (TRIGGER_CONTRACT, TRIGGER_DROP):
            head_be = get_piston_be(world, pos.offset(direction))
            if head_be is not None:
                if (world.handling_tick and head_be.extending and head_be.is_source_piston
                        and head_be.progress == 0.0 and head_be.progress_o == 0.0):
                    # the head was created by an extend event earlier in this block-event phase (ZT-003)
                    note(world, "zero_tick", pos)
                head_be.final_tick(world)
            moving_state = BlockState.of("moving_piston", facing=direction.label,
                                         type="sticky" if self.is_sticky else "normal")
            world.set_block(pos, moving_state, 276)
            moved = BlockState.of(self.name, extended=False, facing=ALL_DIRECTIONS[b1 & 7].label)
            world.set_block_entity(PistonMovingBlockEntity(pos, moved, direction, False, True))
            world.update_neighbors_at(pos, world.block(moving_state))
            world.update_neighbour_shapes(pos, moving_state, 2)
            if self.is_sticky:
                two_pos = pos.offset(direction, 2)
                moving = world.get(two_pos)
                piston_piece = False
                if moving.id == "moving_piston":
                    be = get_piston_be(world, two_pos)
                    if be is not None and be.direction is direction and be.extending:
                        be.final_tick(world)
                        piston_piece = True
                        # the pushed block stays at the extended position (PIS-010, PIS-012)
                        note(world, "piston_spit", pos, be.moved_state.id)
                if not piston_piece:
                    if (b0 != TRIGGER_CONTRACT or moving.is_air
                            or not is_pushable(world, moving, two_pos, direction.opposite, False, direction)
                            or (push_reaction(world, moving) != "PUSH_PULL" and not is_piston_base(moving))):
                        world.remove_block(pos.offset(direction))
                    else:
                        self.move_blocks(world, pos, direction, False)
            else:
                world.remove_block(pos.offset(direction))
            world.game_event("block_deactivate", pos, moving_state)
        return True

    def move_blocks(self, world: World, piston_pos: Pos, direction: Direction, extending: bool) -> bool:
        arm_pos = piston_pos.offset(direction)
        if not extending and world.get(arm_pos).id == "piston_head":
            world.set_block(arm_pos, AIR, 276)
        resolver = PistonStructureResolver(world, piston_pos, direction, extending)
        if not resolver.resolve():
            return False
        delete_after_move = PosHashMap()
        to_push = resolver.to_push
        to_push_shapes: list[BlockState] = []
        for p in to_push:
            st = world.get(p)
            to_push_shapes.append(st)
            delete_after_move.put(p, st)
        to_destroy = resolver.to_destroy
        to_update: list[BlockState] = []
        push_direction = direction if extending else direction.opposite

        for p in reversed(to_destroy):
            st = world.get(p)
            # dropResources: items are not simulated
            world.set_block(p, AIR, 18)
            world.game_event("block_destroy", p, st)
            to_update.append(st)

        for i in range(len(to_push) - 1, -1, -1):
            p = to_push[i]
            st = world.get(p)
            p = p.offset(push_direction)
            delete_after_move.remove(p)
            actual = BlockState.of("moving_piston", facing=direction.label, type="normal")
            world.set_block(p, actual, 324)
            world.set_block_entity(PistonMovingBlockEntity(p, to_push_shapes[i], direction, extending, False))
            to_update.append(st)

        if extending:
            ptype = "sticky" if self.is_sticky else "normal"
            head = BlockState.of("piston_head", facing=direction.label, short=False, type=ptype)
            moving = BlockState.of("moving_piston", facing=direction.label, type=ptype)
            delete_after_move.remove(arm_pos)
            world.set_block(arm_pos, moving, 324)
            world.set_block_entity(PistonMovingBlockEntity(arm_pos, head, direction, True, True))

        entries = delete_after_move.items()
        for p, _ in entries:
            world.set_block(p, AIR, 82)
        for p, old in entries:
            world.block(old).update_indirect_neighbour_shapes(world, p, old, 2, UPDATE_LIMIT)
            world.update_neighbour_shapes(p, AIR, 2)
            world.block(AIR).update_indirect_neighbour_shapes(world, p, AIR, 2, UPDATE_LIMIT)

        idx = 0
        for p in reversed(to_destroy):
            st = to_update[idx]
            idx += 1
            blk = world.block(st)
            blk.affect_neighbors_after_removal(world, p, st, False)
            blk.update_indirect_neighbour_shapes(world, p, st, 2, UPDATE_LIMIT)
            world.update_neighbors_at(p, blk)
        for i in range(len(to_push) - 1, -1, -1):
            world.update_neighbors_at(to_push[i], world.block(to_update[idx]))
            idx += 1
        if extending:
            world.update_neighbors_at(arm_pos, PISTON_HEAD)
        return True


# Blocks whose update can come with a change of the power a piston sees (signal sources and blocks that move
# one). The source of an update is the block that was at the updating position before (Level#setBlock passes
# oldState.getBlock()), and that position is next to the piston. An update from any other block cannot have
# produced the quasi-connected power, so a reaction to it means the piston was in a BUD state before.
_POWER_SOURCES = {
    "redstone_wire", "lever", "redstone_torch", "redstone_wall_torch", "repeater", "comparator", "observer",
    "redstone_block", "daylight_detector", "target", "tripwire_hook", "trapped_chest", "lectern",
    "sculk_sensor", "calibrated_sculk_sensor", "detector_rail", "lightning_rod", "moving_piston",
    "piston", "sticky_piston", "piston_head",
}


def _can_change_power(source: Block) -> bool:
    name = source.name.removeprefix("minecraft:")
    return name in _POWER_SOURCES or name.endswith(("_button", "_pressure_plate"))


def _can_remove_power(source: Block) -> bool:
    """Like _can_change_power, but a removed conductor next to the piston may also have carried its power."""
    if _can_change_power(source):
        return True
    try:
        return blockdata.is_conductor(blockdata.default_state(source.name))
    except KeyError:
        return True  # unknown block: do not claim a BUD


def check_bud_states(world: World) -> None:
    """Note pistons resting in a BUD state: quasi-powered but retracted, or unpowered but extended."""
    events = {ev.pos for ev in world.block_events}
    for pos, state in list(world.blocks.items()):
        if not is_piston_base(state) or pos in events:
            continue
        block = world.block(state)
        direction = facing(state)
        powered = block.get_neighbor_signal(world, pos, direction)
        if state.get_bool("extended"):
            if not powered and world.get(pos.offset(direction)).id == "piston_head":
                note(world, "bud", pos, "unbestromt, aber ausgefahren")
        elif powered and not block.has_direct_signal(world, pos, direction) \
                and PistonStructureResolver(world, pos, direction, True).resolve():
            note(world, "bud", pos, "per Quasi-Connectivity bestromt, aber eingefahren")


register_state_check(check_bud_states)


# ---------------------------------------------------------------------- PistonHeadBlock
class PistonHeadBlock(Block):
    def is_conductor(self, state):
        return False

    def is_face_sturdy(self, state, face, support="full"):
        return face is facing(state)  # the 16x16 platform

    def get_piston_push_reaction(self, state):
        return "IMMOVEABLE"

    @staticmethod
    def is_fitting_base(arm: BlockState, base: BlockState) -> bool:
        base_id = "piston" if arm.get("type") == "normal" else "sticky_piston"
        return base.id == base_id and base.get_bool("extended") and base.get("facing") == arm.get("facing")

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        base_pos = pos.offset(facing(state).opposite)
        if self.is_fitting_base(state, world.get(base_pos)):
            world.destroy_block(base_pos)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction.opposite is facing(state) and not self.can_survive(world, pos, state):
            return AIR
        return state

    def can_survive(self, world, pos, state):
        base = world.get(pos.offset(facing(state).opposite))
        return self.is_fitting_base(state, base) or (base.id == "moving_piston" and base.get("facing") == state.get("facing"))

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        if self.can_survive(world, pos, state):
            world.neighbor_changed(pos.offset(facing(state).opposite), source)


# ---------------------------------------------------------------------- MovingPistonBlock
class MovingPistonBlock(Block):
    def is_conductor(self, state):
        return False

    def is_face_sturdy(self, state, face, support="full"):
        return False

    def get_piston_push_reaction(self, state):
        return "IMMOVEABLE"  # strength -1

    def has_block_entity(self, state):
        return True

    def new_block_entity(self, pos, state):
        return None  # only created through newMovingBlockEntity

    def use_without_item(self, world, pos, state):
        if world.get_block_entity(pos) is None:
            world.remove_block(pos)
            return True
        return False


# ---------------------------------------------------------------------- PistonMovingBlockEntity
class PistonMovingBlockEntity:
    ticks = True

    def __init__(self, pos: Pos, moved_state: BlockState = AIR, direction: Direction = D.DOWN,
                 extending: bool = False, is_source_piston: bool = False) -> None:
        self.pos = pos
        self.moved_state = moved_state
        self.direction = direction
        self.extending = extending
        self.is_source_piston = is_source_piston
        self.progress = 0.0
        self.progress_o = 0.0
        self.last_ticked = 0
        self.removed = False

    def load(self, nbt: dict) -> None:
        """loadAdditional (scenario setup)."""
        bs = nbt.get("blockState")
        if isinstance(bs, dict) and "Name" in bs:
            self.moved_state = BlockState.of(bs["Name"], {k: str(v) for k, v in (bs.get("Properties") or {}).items()})
        elif isinstance(bs, str):
            self.moved_state = BlockState.parse(bs)
        self.direction = ALL_DIRECTIONS[int(nbt.get("facing", 0))]
        self.progress = float(nbt.get("progress", 0.0))
        self.progress_o = self.progress
        self.extending = bool(nbt.get("extending", False))
        self.is_source_piston = bool(nbt.get("source", False))

    def get_progress(self, a: float) -> float:
        a = min(a, 1.0)
        return self.progress_o + a * (self.progress - self.progress_o)

    def get_push_direction(self) -> Direction:
        return self.direction if self.extending else self.direction.opposite

    def final_tick(self, world: World) -> None:
        if self.progress_o < 1.0:
            self.progress = 1.0
            self.progress_o = 1.0
            world.remove_block_entity(self.pos)
            self.removed = True
            if world.get(self.pos).id == "moving_piston":
                if self.is_source_piston:
                    new = AIR
                else:
                    new = update_from_neighbour_shapes(world, self.moved_state, self.pos)
                world.set_block(self.pos, new, UPDATE_ALL)
                world.neighbor_changed(self.pos, world.block(new))

    def pre_remove_side_effects(self, world: World, pos: Pos, state: BlockState) -> None:
        self.final_tick(world)

    def tick(self, world: World) -> None:
        """PistonMovingBlockEntity#tick (via BoundTickingBlockEntity, which requires a moving_piston)."""
        pos = self.pos
        if world.get(pos).id != "moving_piston":
            return
        self.last_ticked = world.game_time
        self.progress_o = self.progress
        if self.progress_o >= 1.0:
            world.remove_block_entity(pos)
            self.removed = True
            if world.get(pos).id == "moving_piston":
                new = update_from_neighbour_shapes(world, self.moved_state, pos)
                if new.is_air:
                    world.set_block(pos, self.moved_state, 340)
                    world.update_or_destroy(self.moved_state, new, pos, UPDATE_ALL, UPDATE_LIMIT)
                else:
                    if new.get("waterlogged") == "true":
                        new = new.with_(waterlogged=False)
                    world.set_block(pos, new, 67)
                    world.neighbor_changed(pos, world.block(new))
        else:
            self.progress = min(self.progress + 0.5, 1.0)


PISTON = REGISTRY.register(PistonBaseBlock(False), "piston")
STICKY_PISTON = REGISTRY.register(PistonBaseBlock(True), "sticky_piston")
PISTON_HEAD = REGISTRY.register(PistonHeadBlock(), "piston_head")
MOVING_PISTON = REGISTRY.register(MovingPistonBlock(), "moving_piston")

# Slime and honey only matter for PistonStructureResolver (by id) and entity physics (out of scope).
REGISTRY.register(Block(), "slime_block")
REGISTRY.register(Block(), "honey_block")
