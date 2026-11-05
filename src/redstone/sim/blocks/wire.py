"""Redstone wire (dust) with the default (non-experimental) wire evaluator.

References (26.3): RedstoneWireBlock, RedstoneWireEvaluator, DefaultRedstoneWireEvaluator, Vec3i#hashCode,
java.util.HashMap (iteration order of the HashSet used for the neighbor updates). Orientation is always
null in vanilla, the experimental evaluator is not modeled.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ...model import AIR, BlockState, Direction, Pos
from ..block import REGISTRY, Block
from ..constants import UPDATE_ALL, UPDATE_CLIENTS
from ..world import ALL_DIRECTIONS, HORIZONTAL, World

D = Direction
NONE, SIDE, UP = "none", "side", "up"
# Direction.Plane.VERTICAL
VERTICAL = (D.UP, D.DOWN)


# ---------------------------------------------------------------------- Java hashing
def _int32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x1_0000_0000 if v & 0x8000_0000 else v


def block_pos_hash(pos: tuple[int, int, int]) -> int:
    """Vec3i#hashCode: (y + z * 31) * 31 + x in 32-bit int arithmetic (BlockPos does not override it)."""
    x, y, z = pos
    return _int32((_int32(y + _int32(z * 31)) * 31) + x)


def _spread(h: int) -> int:
    """HashMap#hash: h ^ (h >>> 16), as an unsigned 32-bit value."""
    h &= 0xFFFFFFFF
    return h ^ (h >> 16)


class JavaHashSet:
    """Insertion and iteration order of ``new HashSet<>()`` (java.util.HashMap) for keys with a Java hashCode.

    Models the lazily allocated 16-bucket table, load factor 0.75 with resize (lo/hi split keeping order) and
    the resize instead of treeification for bins of 8+ entries while the table is smaller than 64. Real tree
    bins (table >= 64 and a bin of 8+) are not modeled; they cannot occur for the small sets used by dust.
    """

    TREEIFY_THRESHOLD = 8
    MIN_TREEIFY_CAPACITY = 64

    def __init__(self, items: Iterable[Pos] = (), hash_fn=block_pos_hash) -> None:
        self._hash_fn = hash_fn
        self._table: list[list[tuple[int, Pos]]] | None = None
        self._size = 0
        self._threshold = 0
        for item in items:
            self.add(item)

    def _resize(self) -> None:
        if self._table is None:
            self._table = [[] for _ in range(16)]
            self._threshold = 12
            return
        old = self._table
        n = len(old)
        new: list[list[tuple[int, Pos]]] = [[] for _ in range(2 * n)]
        for j, bucket in enumerate(old):
            for node in bucket:  # split preserving relative order
                (new[j + n] if node[0] & n else new[j]).append(node)
        self._table = new
        self._threshold *= 2

    def add(self, item: Pos) -> bool:
        if self._table is None:
            self._resize()
        assert self._table is not None
        h = _spread(self._hash_fn(item))
        bucket = self._table[h & (len(self._table) - 1)]
        for nh, key in bucket:
            if nh == h and key == item:
                return False
        bucket.append((h, item))
        if len(bucket) >= self.TREEIFY_THRESHOLD + 1:  # binCount >= TREEIFY_THRESHOLD - 1 -> treeifyBin
            if len(self._table) < self.MIN_TREEIFY_CAPACITY:
                self._resize()
            else:
                raise NotImplementedError("HashMap tree bins are not modeled")
        self._size += 1
        if self._size > self._threshold:
            self._resize()
        return True

    def __contains__(self, item: object) -> bool:
        return any(key == item for key in self)

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[Pos]:
        for bucket in self._table or ():
            for _, key in bucket:
                yield key

    @property
    def capacity(self) -> int:
        return len(self._table) if self._table else 0


def update_order(pos: Pos) -> list[Pos]:
    """Order in which dust that changed power calls updateNeighborsAt (knowledge DUST-017, DUST-018).

    DefaultRedstoneWireEvaluator#updatePowerStrength collects the wire position and its six neighbours
    (Direction.values(): D, U, N, S, W, E) in a ``new HashSet<BlockPos>()`` and iterates it.
    """
    to_update = JavaHashSet()
    to_update.add(pos)
    for d in ALL_DIRECTIONS:
        to_update.add(pos.offset(d))
    return list(to_update)


# ---------------------------------------------------------------------- helpers
def is_connected(side: str | None) -> bool:
    """RedstoneSide#isConnected"""
    return side is not None and side != NONE


def _side(state: BlockState, direction: Direction) -> str:
    return state.get(direction.label, NONE)


def is_cross(state: BlockState) -> bool:
    return all(is_connected(_side(state, d)) for d in HORIZONTAL)


def is_dot(state: BlockState) -> bool:
    return not any(is_connected(_side(state, d)) for d in HORIZONTAL)


def _above(pos: Pos) -> Pos:
    return pos.offset(D.UP)


def _below(pos: Pos) -> Pos:
    return pos.offset(D.DOWN)


def _wire_state(power: int, north: str = NONE, east: str = NONE, south: str = NONE, west: str = NONE) -> BlockState:
    return BlockState.of("redstone_wire", east=east, north=north, power=power, south=south, west=west)


# ---------------------------------------------------------------------- the block
class RedstoneWireBlock(Block):
    def __init__(self) -> None:
        super().__init__()
        # RedstoneWireBlock#shouldSignal: false only while the wire reads its block signal
        self.should_signal = True

    def default_state(self, power: int = 0) -> BlockState:
        return _wire_state(power)

    def cross_state(self, power: int = 0) -> BlockState:
        return _wire_state(power, SIDE, SIDE, SIDE, SIDE)

    def is_wire(self, state: BlockState) -> bool:
        return state.name == self.name

    # --- static properties ------------------------------------------------------------
    def is_conductor(self, state):
        return False

    def is_face_sturdy(self, state, face, support="full"):
        return False

    def is_signal_source(self, state):
        return self.should_signal

    def should_redstone_wire_connect_to(self, world, pos, state, direction):
        return True

    # --- connection shape -------------------------------------------------------------
    def get_connection_state(self, world: World, state: BlockState, pos: Pos) -> BlockState:
        was_dot = is_dot(state)
        state = self.get_missing_connections(world, self.default_state(state.get_int("power")), pos)
        if was_dot and is_dot(state):
            return state
        north = is_connected(state.get("north"))
        south = is_connected(state.get("south"))
        east = is_connected(state.get("east"))
        west = is_connected(state.get("west"))
        north_south_empty = not north and not south
        east_west_empty = not east and not west
        if not west and north_south_empty:
            state = state.with_(west=SIDE)
        if not east and north_south_empty:
            state = state.with_(east=SIDE)
        if not north and east_west_empty:
            state = state.with_(north=SIDE)
        if not south and east_west_empty:
            state = state.with_(south=SIDE)
        return state

    def get_missing_connections(self, world: World, state: BlockState, pos: Pos) -> BlockState:
        # isRedstoneConductor is called with the wire's own position (no position-dependent conductors here)
        can_connect_up = not world.is_conductor(_above(pos))
        for d in HORIZONTAL:
            if not is_connected(_side(state, d)):
                state = state.with_(**{d.label: self.get_connecting_side(world, pos, d, can_connect_up)})
        return state

    def get_connecting_side(self, world: World, pos: Pos, direction: Direction,
                            can_connect_up: bool | None = None) -> str:
        if can_connect_up is None:
            can_connect_up = not world.is_conductor(_above(pos))
        relative_pos = pos.offset(direction)
        relative_state = world.get(relative_pos)
        if can_connect_up:
            placeable_above = "trapdoor" in relative_state.id or self.can_survive_on(world, relative_pos, relative_state)
            if placeable_above and self.should_connect_to(world, _above(relative_pos)):
                if world.block(relative_state).is_face_sturdy(relative_state, direction.opposite):
                    return UP
                return SIDE
        if (not self.should_connect_to(world, relative_pos, relative_state, direction)
                and (world.block(relative_state).is_conductor(relative_state)
                     or not self.should_connect_to(world, _below(relative_pos)))):
            return NONE
        return SIDE

    @staticmethod
    def should_connect_to(world: World, pos: Pos, state: BlockState | None = None,
                          direction: Direction | None = None) -> bool:
        if state is None:
            state = world.get(pos)
        return world.block(state).should_redstone_wire_connect_to(world, pos, state, direction)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction is D.DOWN:
            return state if self.can_survive_on(world, neighbor_pos, neighbor_state) else AIR
        if direction is D.UP:
            return self.get_connection_state(world, state, pos)
        side = self.get_connecting_side(world, pos, direction)
        if is_connected(side) == is_connected(_side(state, direction)) and not is_cross(state):
            return state.with_(**{direction.label: side})
        return self.get_connection_state(
            world, self.cross_state(state.get_int("power")).with_(**{direction.label: side}), pos)

    def update_indirect_neighbour_shapes(self, world, pos, state, flags, limit):
        for d in HORIZONTAL:
            if _side(state, d) != NONE and not self.is_wire(world.get(pos.offset(d))):
                below = _below(pos.offset(d))
                if self.is_wire(world.get(below)):
                    npos = below.offset(d.opposite)
                    world.neighbor_shape_changed(d.opposite, below, npos, world.get(npos), flags, limit)
                above = _above(pos.offset(d))
                if self.is_wire(world.get(above)):
                    npos = above.offset(d.opposite)
                    world.neighbor_shape_changed(d.opposite, above, npos, world.get(npos), flags, limit)

    # --- survival -------------------------------------------------------------------------
    def can_survive(self, world, pos, state):
        below = _below(pos)
        return self.can_survive_on(world, below, world.get(below))

    @staticmethod
    def can_survive_on(world: World, pos: Pos, state: BlockState) -> bool:
        return world.block(state).is_face_sturdy(state, D.UP) or state.id == "hopper"

    # --- power (DefaultRedstoneWireEvaluator) --------------------------------------------
    def update_power_strength(self, world: World, pos: Pos, state: BlockState) -> None:
        """DefaultRedstoneWireEvaluator#updatePowerStrength (orientation null, skipShapeUpdates unused)."""
        target = self.calculate_target_strength(world, pos)
        if state.get_int("power") != target:
            if world.get(pos) == state:
                world.set_block(pos, state.with_(power=target), UPDATE_CLIENTS)
            for p in update_order(pos):
                world.update_neighbors_at(p, self)

    def calculate_target_strength(self, world: World, pos: Pos) -> int:
        block_signal = self.get_block_signal(world, pos)
        return block_signal if block_signal == 15 else max(block_signal, self.get_incoming_wire_signal(world, pos))

    def get_block_signal(self, world: World, pos: Pos) -> int:
        self.should_signal = False
        try:
            return world.get_best_neighbor_signal(pos)
        finally:
            self.should_signal = True

    def get_wire_signal(self, state: BlockState) -> int:
        return state.get_int("power") if self.is_wire(state) else 0

    def get_incoming_wire_signal(self, world: World, pos: Pos) -> int:
        wire_signal = 0
        above_conductor = world.is_conductor(_above(pos))
        for d in HORIZONTAL:
            npos = pos.offset(d)
            nstate = world.get(npos)
            wire_signal = max(wire_signal, self.get_wire_signal(nstate))
            n_conductor = world.block(nstate).is_conductor(nstate)
            if n_conductor and not above_conductor:
                wire_signal = max(wire_signal, self.get_wire_signal(world.get(_above(npos))))
            elif not n_conductor:
                wire_signal = max(wire_signal, self.get_wire_signal(world.get(_below(npos))))
        return max(0, wire_signal - 1)

    # --- signals --------------------------------------------------------------------------
    def own_signal(self, world, pos, state):
        return state.get_int("power")

    def get_signal(self, world, pos, state, direction):
        if not self.should_signal or direction is D.DOWN:
            return 0
        power = self.own_signal(world, pos, state)
        if power == 0:
            return 0
        if direction is not D.UP and not is_connected(
                _side(self.get_connection_state(world, state, pos), direction.opposite)):
            return 0
        return power

    def get_direct_signal(self, world, pos, state, direction):
        return self.get_signal(world, pos, state, direction) if self.should_signal else 0

    # --- placement / removal / updates -----------------------------------------------------
    def check_corner_change_at(self, world: World, pos: Pos) -> None:
        if self.is_wire(world.get(pos)):
            world.update_neighbors_at(pos, self)
            for d in ALL_DIRECTIONS:
                world.update_neighbors_at(pos.offset(d), self)

    def on_place(self, world, pos, state, old, moved_by_piston):
        if old.name != state.name:
            self.update_power_strength(world, pos, state)
            for d in VERTICAL:
                world.update_neighbors_at(pos.offset(d), self)
            self.update_neighbors_of_neighboring_wires(world, pos)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if not moved_by_piston:
            for d in ALL_DIRECTIONS:
                world.update_neighbors_at(pos.offset(d), self)
            self.update_power_strength(world, pos, state)
            self.update_neighbors_of_neighboring_wires(world, pos)

    def update_neighbors_of_neighboring_wires(self, world: World, pos: Pos) -> None:
        for d in HORIZONTAL:
            self.check_corner_change_at(world, pos.offset(d))
        for d in HORIZONTAL:
            target = pos.offset(d)
            if world.is_conductor(target):
                self.check_corner_change_at(world, _above(target))
            else:
                self.check_corner_change_at(world, _below(target))

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        if self.can_survive(world, pos, state):
            self.update_power_strength(world, pos, state)
        else:
            world.remove_block(pos, False)  # dropResources + removeBlock(pos, false); drops not modeled

    # --- interaction ----------------------------------------------------------------------
    def use_without_item(self, world, pos, state):
        if is_cross(state) or is_dot(state):
            power = state.get_int("power")
            new = self.default_state(power) if is_cross(state) else self.cross_state(power)
            new = self.get_connection_state(world, new, pos)
            if new != state:
                world.set_block(pos, new, UPDATE_ALL)
                self.updates_on_shape_change(world, pos, state, new)
                return True
        return False

    def updates_on_shape_change(self, world: World, pos: Pos, old: BlockState, new: BlockState) -> None:
        for d in HORIZONTAL:
            rel = pos.offset(d)
            if is_connected(_side(old, d)) != is_connected(_side(new, d)) and world.is_conductor(rel):
                world.update_neighbors_at_except_from_facing(rel, self, d.opposite)


REGISTRY.register(RedstoneWireBlock(), "redstone_wire")
