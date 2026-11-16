"""The simulated level: block storage, setBlock, neighbor/shape updates, scheduled ticks and block events.

Mirrors (Java 26.3, see knowledge/basics/*.md):
- Level#setBlock + LevelChunk#setBlockState  -> World.set_block
- CollectingNeighborUpdater (depth-first stack) -> World._add_and_run
- NeighborUpdater.UPDATE_ORDER = W, E, D, U, N, S
- BlockBehaviour.UPDATE_SHAPE_ORDER = W, E, N, S, D, U
- LevelTicks: ticks drained in (trigger tick, priority, sub-tick order); one pending tick per (pos, block)
- ServerLevel#tick phase order: time++, block ticks, (fluid ticks), block events, (entities), block entities
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..model import AIR, BlockState, Direction, Grid, Pos
from .block import REGISTRY, Block, Registry
from .constants import (
    MAX_CHAINED_NEIGHBOR_UPDATES,
    UPDATE_ALL,
    UPDATE_KNOWN_SHAPE,
    UPDATE_LIMIT,
    UPDATE_MOVE_BY_PISTON,
    UPDATE_NEIGHBORS,
    UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS,
    UPDATE_SKIP_ON_PLACE,
    UPDATE_SKIP_SHAPE_UPDATE_ON_WIRE,
    UPDATE_SUPPRESS_DROPS,
    TickPriority,
)

D = Direction
UPDATE_ORDER = (D.WEST, D.EAST, D.DOWN, D.UP, D.NORTH, D.SOUTH)
UPDATE_SHAPE_ORDER = (D.WEST, D.EAST, D.NORTH, D.SOUTH, D.DOWN, D.UP)
# SignalGetter#getDirectSignalTo / hasNeighborSignal order
SIGNAL_ORDER = (D.DOWN, D.UP, D.NORTH, D.SOUTH, D.WEST, D.EAST)
# Direction.values()
ALL_DIRECTIONS = tuple(D)
# Direction.Plane.HORIZONTAL
HORIZONTAL = (D.NORTH, D.EAST, D.SOUTH, D.WEST)


@dataclass(order=True)
class ScheduledTick:
    trigger_tick: int
    priority: int
    sub_tick: int
    pos: Pos = field(compare=False)
    block: str = field(compare=False)


@dataclass(frozen=True)
class BlockEvent:
    pos: Pos
    block: str
    a: int
    b: int


class World:
    core = "python"

    def __init__(self, registry: Registry = REGISTRY) -> None:
        self.registry = registry
        self.blocks: dict[Pos, BlockState] = {}
        self.block_entities: dict[Pos, Any] = {}
        # Game event listeners (sculk sensors): block entities with ``listens``; see sim/blocks/sculk.py.
        self.listeners: dict[Pos, Any] = {}
        self.game_time = 0
        # Overworld clock (``/time set``; frozen in the oracle) and Level#skyDarken, which follows it only at
        # the start of the next tick (ServerLevel#tick -> updateSkyBrightness); see sim/blocks/daylight.py.
        self.day_time = 0
        self.sky_darken = 0
        self.handling_tick = False
        self._sub_tick = 0
        self._ticks: list[ScheduledTick] = []  # heap
        self._pending: set[tuple[Pos, str]] = set()  # LevelChunkTicks#ticksPerPosition
        self._running_this_tick: set[tuple[Pos, str]] = set()
        self.block_events: dict[BlockEvent, None] = {}  # ObjectLinkedOpenHashSet
        # Level#blockEntityTickers / pendingBlockEntityTickers, LevelChunk#tickersInLevel
        self._be_tickers: list[_TickerWrapper] = []
        self._pending_be_tickers: list[_TickerWrapper] = []
        self._tickers_in_level: dict[Pos, _TickerWrapper] = {}
        self._ticking_block_entities = False
        # CollectingNeighborUpdater state
        self._stack: list[_Updates] = []
        self._added_this_layer: list[_Updates] = []
        self._update_count = 0
        self.warnings: list[str] = []
        # Not part of the game: positions whose block state changed since the recorder last cleared it.
        self.dirty: set[Pos] = set()
        # Not part of the game: number of executed neighbor updates (benchmark statistics).
        self.neighbor_update_count = 0

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_grid(cls, grid: Grid, registry: Registry = REGISTRY) -> World:
        world = cls(registry)
        world.place_grid(grid)
        return world

    def place_grid(self, grid: Grid, origin: Pos = Pos(0, 0, 0)) -> None:
        """Place blocks exactly as stored, without any updates (scenario setup, docs/scenario-format.md)."""
        for pos, state in grid.items():
            p = pos + origin
            self.blocks[p] = state
            block = self.block(state)
            if self.registry.needs_model(state.name) and state.name not in {w.split(" ")[0] for w in self.warnings}:
                self.warnings.append(f"{state.name} is not modeled by the simulator; treated as inert block")
            if block.has_block_entity(state):
                be = block.new_block_entity(p, state)
                if be is not None:
                    be.load(grid.block_entities.get(pos, {}))
                    self.add_block_entity(p, be)

    # ------------------------------------------------------------------ block access
    def block(self, state: BlockState) -> Block:
        return self.registry.get(state.name)

    def get(self, pos: Pos) -> BlockState:
        return self.blocks.get(pos, AIR)

    def get_block_entity(self, pos: Pos) -> Any:
        """Level#getBlockEntity (removed block entities count as absent)."""
        be = self.block_entities.get(pos)
        if be is not None and getattr(be, "removed", False):
            del self.block_entities[pos]
            return None
        return be

    def add_block_entity(self, pos: Pos, be: Any) -> None:
        """Level#setBlockEntity / LevelChunk#addAndRegisterBlockEntity."""
        state = self.get(pos)
        if not self.block(state).has_block_entity(state):
            self.warnings.append(f"block entity at {pos} but {state} does not allow it")
            return
        be.removed = False
        previous = self.block_entities.get(pos)
        self.block_entities[pos] = be
        if getattr(be, "listens", False):
            self.listeners[pos] = be
        else:
            self.listeners.pop(pos, None)
        if previous is not None and previous is not be:
            previous.removed = True
        self._update_block_entity_ticker(pos, be)

    def set_block_entity(self, be: Any) -> None:
        self.add_block_entity(be.pos, be)

    def _update_block_entity_ticker(self, pos: Pos, be: Any) -> None:
        """LevelChunk#updateBlockEntityTicker: one rebindable ticker wrapper per position."""
        if not getattr(be, "ticks", False):
            self._remove_block_entity_ticker(pos)
            return
        wrapper = self._tickers_in_level.get(pos)
        if wrapper is not None:
            wrapper.ticker = be
        else:
            wrapper = self._tickers_in_level[pos] = _TickerWrapper(be)
            # Level#addBlockEntityTicker
            (self._pending_be_tickers if self._ticking_block_entities else self._be_tickers).append(wrapper)

    def _remove_block_entity_ticker(self, pos: Pos) -> None:
        wrapper = self._tickers_in_level.pop(pos, None)
        if wrapper is not None:
            wrapper.ticker = None  # NULL_TICKER: reports removed, dropped on the next iteration

    def remove_block_entity(self, pos: Pos) -> None:
        """LevelChunk#removeBlockEntity"""
        be = self.block_entities.pop(pos, None)
        if be is not None:
            be.removed = True
        self.listeners.pop(pos, None)
        self._remove_block_entity_ticker(pos)

    def set_block(self, pos: Pos, state: BlockState, flags: int = UPDATE_ALL, limit: int = UPDATE_LIMIT) -> bool:
        """Level#setBlock including LevelChunk#setBlockState."""
        old = self.get(pos)
        if old == state:
            return False
        if state.is_air:
            self.blocks.pop(pos, None)
        else:
            self.blocks[pos] = state
        self.dirty.add(pos)
        old_block, new_block = self.block(old), self.block(state)
        block_changed = old.name != state.name
        moved = bool(flags & UPDATE_MOVE_BY_PISTON)

        if block_changed and old_block.has_block_entity(old):
            if not flags & UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS:
                be = self.get_block_entity(pos)
                pre_remove = getattr(be, "pre_remove_side_effects", None)
                if pre_remove:
                    pre_remove(self, pos, old)
            self.remove_block_entity(pos)

        if (block_changed or "rail" in state.name) and (flags & UPDATE_NEIGHBORS or moved):
            old_block.affect_neighbors_after_removal(self, pos, old, moved)

        if self.get(pos).name != state.name:
            return False
        if not flags & UPDATE_SKIP_ON_PLACE:
            new_block.on_place(self, pos, state, old, moved)
        if new_block.has_block_entity(state) and self.get(pos).name == state.name:
            be = self.get_block_entity(pos)
            if be is None:
                be = new_block.new_block_entity(pos, state)
                if be is not None:
                    self.add_block_entity(pos, be)
            else:
                self._update_block_entity_ticker(pos, be)

        # Level#setBlock, after the chunk update
        if self.get(pos) != state:
            return True
        if flags & UPDATE_NEIGHBORS:
            self.update_neighbors_at(pos, old_block)
            if new_block.has_analog_output_signal(state):
                self.update_neighbour_for_output_signal(pos, new_block)
        if not flags & UPDATE_KNOWN_SHAPE and limit > 0:
            nflags = flags & ~(UPDATE_NEIGHBORS | UPDATE_SUPPRESS_DROPS)
            old_block.update_indirect_neighbour_shapes(self, pos, old, nflags, limit - 1)
            self.update_neighbour_shapes(pos, state, nflags, limit - 1)
            new_block.update_indirect_neighbour_shapes(self, pos, state, nflags, limit - 1)
        return True

    def remove_block(self, pos: Pos, moved_by_piston: bool = False) -> bool:
        return self.set_block(pos, AIR, UPDATE_ALL | (UPDATE_MOVE_BY_PISTON if moved_by_piston else 0))

    def destroy_block(self, pos: Pos, limit: int = UPDATE_LIMIT) -> bool:
        """Level#destroyBlock (drops are not simulated): setBlock, then the BLOCK_DESTROY game event."""
        old = self.get(pos)
        if old.is_air:
            return False
        destroyed = self.set_block(pos, AIR, UPDATE_ALL, limit)
        if destroyed:
            self.game_event("block_destroy", pos, old)
        return destroyed

    def game_event(self, event: str, pos: Pos, affected: BlockState | None = None) -> None:
        """LevelAccessor#gameEvent at the center of ``pos``; ``affected`` is the context's block state.

        Only vibration listeners exist in the simulator (GameEventDispatcher#post). They are independent of
        each other, so the visiting order does not matter."""
        if self.listeners:
            for be in list(self.listeners.values()):
                if not be.removed:
                    be.on_game_event(self, event, pos, affected)

    def update_or_destroy(self, old: BlockState, new: BlockState, pos: Pos, flags: int, limit: int) -> None:
        """Block#updateOrDestroy"""
        if new != old:
            if new.is_air:
                self.destroy_block(pos, limit)
            else:
                self.set_block(pos, new, flags & ~UPDATE_SUPPRESS_DROPS, limit)

    # ------------------------------------------------------------------ neighbor updates
    def update_neighbors_at(self, pos: Pos, source: Block, skip: Direction | None = None) -> None:
        self._add_and_run(_MultiNeighborUpdate(pos, source, skip))

    def update_neighbors_at_except_from_facing(self, pos: Pos, source: Block, skip: Direction) -> None:
        self._add_and_run(_MultiNeighborUpdate(pos, source, skip))

    def neighbor_changed(self, pos: Pos, source: Block) -> None:
        self._add_and_run(_SimpleNeighborUpdate(pos, source))

    def neighbor_changed_with_state(self, state: BlockState, pos: Pos, source: Block, moved_by_piston: bool) -> None:
        self._add_and_run(_FullNeighborUpdate(state, pos, source, moved_by_piston))

    def neighbor_shape_changed(self, direction: Direction, pos: Pos, neighbor_pos: Pos,
                               neighbor_state: BlockState, flags: int, limit: int) -> None:
        self._add_and_run(_ShapeUpdate(direction, neighbor_state, pos, neighbor_pos, flags, limit))

    def update_neighbour_shapes(self, pos: Pos, state: BlockState, flags: int, limit: int = UPDATE_LIMIT) -> None:
        """BlockStateBase#updateNeighbourShapes"""
        for d in UPDATE_SHAPE_ORDER:
            self.neighbor_shape_changed(d.opposite, pos.offset(d), pos, state, flags, limit)

    def update_neighbour_for_output_signal(self, pos: Pos, source: Block) -> None:
        """Level#updateNeighbourForOutputSignal: wake comparators next to or behind a conductor."""
        for d in HORIZONTAL:
            rel = pos.offset(d)
            st = self.get(rel)
            if st.id == "comparator":
                self.neighbor_changed_with_state(st, rel, source, False)
            elif self.is_conductor(rel):
                rel = rel.offset(d)
                st = self.get(rel)
                if st.id == "comparator":
                    self.neighbor_changed_with_state(st, rel, source, False)

    def _execute_update(self, state: BlockState, pos: Pos, source: Block, moved: bool) -> None:
        self.neighbor_update_count += 1
        self.block(state).neighbor_changed(self, pos, state, source, moved)

    def _execute_shape_update(self, direction: Direction, pos: Pos, neighbor_pos: Pos,
                              neighbor_state: BlockState, flags: int, limit: int) -> None:
        current = self.get(pos)
        if flags & UPDATE_SKIP_SHAPE_UPDATE_ON_WIRE and current.id == "redstone_wire":
            return
        new = self.block(current).update_shape(self, pos, current, direction, neighbor_pos, neighbor_state)
        self.update_or_destroy(current, new, pos, flags, limit)

    def _add_and_run(self, update: _Updates) -> None:
        running = self._update_count > 0
        too_many = self._update_count >= MAX_CHAINED_NEIGHBOR_UPDATES
        self._update_count += 1
        if not too_many:
            if running:
                self._added_this_layer.append(update)
            else:
                self._stack.append(update)
        if not running:
            self._run_updates()

    def _run_updates(self) -> None:
        try:
            while self._stack or self._added_this_layer:
                for u in reversed(self._added_this_layer):
                    self._stack.append(u)
                self._added_this_layer.clear()
                nxt = self._stack[-1]
                while not self._added_this_layer:
                    if not nxt.run_next(self):
                        self._stack.pop()
                        break
        finally:
            self._stack.clear()
            self._added_this_layer.clear()
            self._update_count = 0

    # ------------------------------------------------------------------ signals (SignalGetter)
    def is_conductor(self, pos: Pos) -> bool:
        st = self.get(pos)
        return self.block(st).is_conductor(st)

    def is_face_sturdy(self, pos: Pos, face: Direction, support: str = "full") -> bool:
        """BlockState#isFaceSturdy(level, pos, face, SupportType): support is full, rigid or center."""
        st = self.get(pos)
        return self.block(st).is_face_sturdy(st, face, support)

    def is_signal_source(self, state: BlockState) -> bool:
        return self.block(state).is_signal_source(state)

    def get_direct_signal(self, pos: Pos, direction: Direction) -> int:
        st = self.blocks.get(pos, AIR)
        return self.registry.get(st.name).get_direct_signal(self, pos, st, direction)

    def get_direct_signal_to(self, pos: Pos) -> int:
        result = 0
        blocks, registry = self.blocks, self.registry
        for d in SIGNAL_ORDER:
            p = pos.offset(d)
            st = blocks.get(p)
            if st is None:  # air gives no signal
                continue
            s = registry.get(st.name).get_direct_signal(self, p, st, d)
            if s > result:
                result = s
                if result >= 15:
                    return result
        return result

    def get_signal(self, pos: Pos, direction: Direction) -> int:
        st = self.blocks.get(pos, AIR)
        block = self.registry.get(st.name)
        signal = block.get_signal(self, pos, st, direction)
        if signal >= 15 or not block.is_conductor(st):
            return signal
        return max(signal, self.get_direct_signal_to(pos))

    def has_signal(self, pos: Pos, direction: Direction) -> bool:
        return self.get_signal(pos, direction) > 0

    def has_neighbor_signal(self, pos: Pos) -> bool:
        return any(self.get_signal(pos.offset(d), d) > 0 for d in SIGNAL_ORDER)

    def get_best_neighbor_signal(self, pos: Pos) -> int:
        best = 0
        for d in ALL_DIRECTIONS:
            s = self.get_signal(pos.offset(d), d)
            if s >= 15:
                return 15
            best = max(best, s)
        return best

    def get_control_input_signal(self, pos: Pos, direction: Direction, only_diodes: bool) -> int:
        st = self.get(pos)
        if only_diodes:
            return self.get_direct_signal(pos, direction) if st.id in ("repeater", "comparator") else 0
        if st.id == "redstone_block":
            return 15
        if st.id == "redstone_wire":
            return st.get_int("power")
        return self.get_direct_signal(pos, direction) if self.is_signal_source(st) else 0

    # ------------------------------------------------------------------ scheduled ticks
    def schedule_tick(self, pos: Pos, block: Block | str, delay: int, priority: int = TickPriority.NORMAL) -> None:
        name = block if isinstance(block, str) else block.name
        key = (pos, name)
        if key in self._pending:
            return
        self._pending.add(key)
        self._sub_tick += 1
        heapq.heappush(self._ticks, ScheduledTick(self.game_time + delay, int(priority), self._sub_tick, pos, name))

    def has_scheduled_tick(self, pos: Pos, block: Block | str) -> bool:
        name = block if isinstance(block, str) else block.name
        return (pos, name) in self._pending

    def will_tick_this_tick(self, pos: Pos, block: Block | str) -> bool:
        name = block if isinstance(block, str) else block.name
        return (pos, name) in self._running_this_tick

    def clear_scheduled_ticks(self) -> None:
        self._ticks.clear()
        self._pending.clear()

    def _run_block_ticks(self) -> None:
        to_run: list[ScheduledTick] = []
        while self._ticks and self._ticks[0].trigger_tick <= self.game_time:
            t = heapq.heappop(self._ticks)
            self._pending.discard((t.pos, t.block))
            to_run.append(t)
        self._running_this_tick = {(t.pos, t.block) for t in to_run}
        for t in to_run:
            self._running_this_tick.discard((t.pos, t.block))
            state = self.get(t.pos)
            if state.name == t.block:  # ServerLevel#tickBlock
                self.block(state).tick(self, t.pos, state)
        self._running_this_tick = set()

    # ------------------------------------------------------------------ block events
    def block_event(self, pos: Pos, block: Block | str, a: int, b: int) -> None:
        name = block if isinstance(block, str) else block.name
        self.block_events.setdefault(BlockEvent(pos, name, a, b), None)

    def _run_block_events(self) -> None:
        while self.block_events:
            ev = next(iter(self.block_events))
            del self.block_events[ev]
            state = self.get(ev.pos)
            if state.name == ev.block:
                self.block(state).trigger_event(self, ev.pos, state, ev.a, ev.b)

    # ------------------------------------------------------------------ block entities
    def _tick_block_entities(self) -> None:
        """Level#tickBlockEntities"""
        self._ticking_block_entities = True
        if self._pending_be_tickers:
            self._be_tickers.extend(self._pending_be_tickers)
            self._pending_be_tickers.clear()
        i = 0
        while i < len(self._be_tickers):
            wrapper = self._be_tickers[i]
            if wrapper.is_removed():
                del self._be_tickers[i]
                continue
            wrapper.tick(self)
            i += 1
        self._ticking_block_entities = False

    def is_idle(self) -> bool:
        """Not part of the game: no scheduled ticks, no block events and no block entity with pending work.

        Hoppers tick every game tick; one without cooldown has found nothing to move and only changes when
        something else in the world changes (there are no item entities in the simulator)."""
        if self._ticks or self.block_events:
            return False
        for wrapper in self._be_tickers + self._pending_be_tickers:
            ticker = wrapper.ticker
            if ticker is None or getattr(ticker, "removed", False):
                continue
            is_idle = getattr(ticker, "is_idle", None)
            if is_idle and getattr(ticker, "idle_needs_world", False):
                if is_idle(self):
                    continue
                return False
            if not (is_idle and is_idle()):
                return False
        return True

    # ------------------------------------------------------------------ the game tick
    def tick(self) -> None:
        """One game tick (ServerLevel#tick, redstone-relevant phases only)."""
        self.handling_tick = True  # ServerLevel#handlingTick: block ticks through block events
        if self.day_time:
            self.sky_darken = _sky_darken_at(self.day_time)
        else:
            self.sky_darken = 0
        self.game_time += 1
        self._run_block_ticks()
        self._run_block_events()
        self.handling_tick = False
        self._tick_block_entities()


def _sky_darken_at(day_time: int) -> int:
    from .blocks.daylight import sky_darken_at

    return sky_darken_at(day_time)


class _TickerWrapper:
    """LevelChunk.RebindableTickingBlockEntityWrapper around a BoundTickingBlockEntity."""

    def __init__(self, ticker: Any) -> None:
        self.ticker = ticker

    def is_removed(self) -> bool:
        return self.ticker is None or getattr(self.ticker, "removed", False)

    def tick(self, world: World) -> None:
        if not self.is_removed():
            self.ticker.tick(world)


# ---------------------------------------------------------------------- neighbor update records
class _Updates:
    def run_next(self, world: World) -> bool:
        raise NotImplementedError


class _SimpleNeighborUpdate(_Updates):
    def __init__(self, pos: Pos, source: Block) -> None:
        self.pos, self.source = pos, source

    def run_next(self, world: World) -> bool:
        world._execute_update(world.get(self.pos), self.pos, self.source, False)
        return False


class _FullNeighborUpdate(_Updates):
    def __init__(self, state: BlockState, pos: Pos, source: Block, moved: bool) -> None:
        self.state, self.pos, self.source, self.moved = state, pos, source, moved

    def run_next(self, world: World) -> bool:
        world._execute_update(self.state, self.pos, self.source, self.moved)
        return False


class _ShapeUpdate(_Updates):
    def __init__(self, direction: Direction, neighbor_state: BlockState, pos: Pos, neighbor_pos: Pos,
                 flags: int, limit: int) -> None:
        self.args = (direction, pos, neighbor_pos, neighbor_state, flags, limit)

    def run_next(self, world: World) -> bool:
        world._execute_shape_update(*self.args)
        return False


class _MultiNeighborUpdate(_Updates):
    def __init__(self, pos: Pos, source: Block, skip: Direction | None) -> None:
        self.pos, self.source, self.skip = pos, source, skip
        self.idx = 1 if UPDATE_ORDER[0] is skip else 0

    def run_next(self, world: World) -> bool:
        d = UPDATE_ORDER[self.idx]
        self.idx += 1
        npos = self.pos.offset(d)
        world._execute_update(world.get(npos), npos, self.source, False)
        if self.idx < len(UPDATE_ORDER) and UPDATE_ORDER[self.idx] is self.skip:
            self.idx += 1
        return self.idx < len(UPDATE_ORDER)


Callback = Callable[[World], None]
