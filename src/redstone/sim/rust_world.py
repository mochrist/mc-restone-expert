"""The Rust simulator core (``rust/rsx-core``, module ``rsx_core``) behind the interface of ``world.World``.

The Python simulator in ``world.py`` and ``blocks/`` stays the reference; this wrapper only converts between
the model classes (``BlockState``, ``Pos``, ``Direction``) and the core. Besides the methods of ``World`` it
offers views for the attributes other code reads directly: ``blocks``, ``block_entities``, ``dirty``,
``warnings``, ``block_events``, ``registry`` and the block objects returned by ``block()``.
"""

from __future__ import annotations

import weakref

from collections.abc import Iterator
from typing import Any

import rsx_core

from ..model import AIR, BlockState, Direction, Grid, Pos
from . import blockdata
from .blocks.container import STACK_SIZE_FILE
from .constants import UPDATE_ALL, UPDATE_LIMIT, TickPriority
from .notes import Note
from .world import BlockEvent, ScheduledTick

API_VERSION = 1
if getattr(rsx_core, "API_VERSION", None) != API_VERSION:
    raise ImportError("rsx_core is out of date; rebuild it with: uv sync --reinstall-package rsx-core")

if not rsx_core.is_initialized():
    rsx_core.init(blockdata.DATA_FILE.read_text(encoding="utf-8"), STACK_SIZE_FILE.read_text(encoding="utf-8"))

_DIR_INDEX = {d: i for i, d in enumerate(Direction)}
_DIRECTIONS = tuple(Direction)
_SUPPORT_INDEX = {"full": 0, "rigid": 1, "center": 2}
_PUSH_NAMES = ("PUSH_PULL", "PUSH", "POPPED", "IMMOVEABLE", "IGNORE_ENTITY")
_AIR_NAMES = ("minecraft:air", "minecraft:cave_air", "minecraft:void_air")

_STATES: dict[str, BlockState] = {}


def _make_state(text: str) -> BlockState:
    state = _STATES.get(text)
    if state is None:
        state = _STATES[text] = BlockState.parse(text)
        blockdata._lookup(state)  # same warnings for unknown blocks and properties as the Python core
    return state


def _name(block: Any) -> str:
    return block if type(block) is str else block.name


# ---------------------------------------------------------------------- block objects
class RustBlock:
    """Stand-in for a ``Block`` behaviour object of the Python core: identified by its name, methods run in
    the Rust core. Only what analysis, design and the tests call is available."""

    def __init__(self, name: str) -> None:
        self.name = "minecraft:air" if name in _AIR_NAMES else name
        self._facts: dict[BlockState, dict] = {}

    def __repr__(self) -> str:
        return f"<RustBlock {self.name}>"

    def _fact(self, state: BlockState, key: str) -> Any:
        facts = self._facts.get(state)
        if facts is None:
            facts = self._facts[state] = _scratch_world()._c.state_facts(state)
        return facts[key]

    @property
    def modeled(self) -> bool:
        return self._fact(BlockState(self.name), "kind") not in ("Unmodeled", "Air")

    # --- static properties
    def is_conductor(self, state: BlockState) -> bool:
        return self._fact(state, "conductor")

    def is_face_sturdy(self, state: BlockState, face: Direction, support: str = "full") -> bool:
        return bool(self._fact(state, "sturdy")[_SUPPORT_INDEX[support]] >> _DIR_INDEX[face] & 1)

    def is_signal_source(self, state: BlockState) -> bool:
        return self._fact(state, "signal_source")

    def has_block_entity(self, state: BlockState) -> bool:
        return self._fact(state, "has_block_entity")

    def has_analog_output_signal(self, state: BlockState) -> bool:
        return self._fact(state, "analog_output")

    def get_piston_push_reaction(self, state: BlockState) -> str:
        return _PUSH_NAMES[self._fact(state, "push")]

    # --- behaviour
    def use_without_item(self, world: RustWorld, pos: Pos, state: BlockState) -> bool:
        return world._c.use_without_item(pos, state)

    # --- redstone wire
    def default_state(self, power: int = 0) -> BlockState:
        return BlockState.of("redstone_wire", east="none", north="none", power=power, south="none", west="none")

    def cross_state(self, power: int = 0) -> BlockState:
        return BlockState.of("redstone_wire", east="side", north="side", power=power, south="side", west="side")

    def get_connection_state(self, world: RustWorld, state: BlockState, pos: Pos) -> BlockState:
        return world._c.wire_get_connection_state(state, pos)

    def update_power_strength(self, world: RustWorld, pos: Pos, state: BlockState) -> None:
        world._c.wire_update_power_strength(pos, state)

    def calculate_target_strength(self, world: RustWorld, pos: Pos) -> int:
        return world._c.wire_calculate_target_strength(pos)

    # --- pistons
    def has_direct_signal(self, world: RustWorld, pos: Pos, push_direction: Direction) -> bool:
        return world._c.piston_has_direct_signal(pos, _DIR_INDEX[push_direction])

    def has_qc_signal(self, world: RustWorld, pos: Pos) -> bool:
        return world._c.piston_has_qc_signal(pos)

    def get_neighbor_signal(self, world: RustWorld, pos: Pos, push_direction: Direction) -> bool:
        return self.has_direct_signal(world, pos, push_direction) or self.has_qc_signal(world, pos)


class RustRegistry:
    """``Registry`` of the Rust core: every name has a block object."""

    def __init__(self) -> None:
        self._blocks: dict[str, RustBlock] = {}

    def get(self, name: str) -> RustBlock:
        block = self._blocks.get(name)
        if block is None:
            block = self._blocks[name] = RustBlock(name)
        return block

    def is_modeled(self, name: str) -> bool:
        return self.get(name)._fact(BlockState(name), "kind") not in ("Unmodeled", "Air")

    def needs_model(self, name: str) -> bool:
        return self.get(name)._fact(BlockState(name), "needs_model")


REGISTRY = RustRegistry()
_SCRATCH: RustWorld | None = None


def _scratch_world() -> RustWorld:
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = RustWorld()
    return _SCRATCH


# ---------------------------------------------------------------------- block entities
class RustBlockEntity:
    """A block entity of the Rust core. Attributes are named like in the Python classes (``output_signal``,
    ``items``, ``cooldown_time``, ``removed`` ...); ``kind`` is comparator, container, dispenser, hopper,
    lectern, daylight, sculk or piston. ``items`` is a copy; assign a whole dict to change it."""

    __slots__ = ("_world", "_id")

    def __init__(self, world: RustWorld, be_id: int) -> None:
        object.__setattr__(self, "_world", world)
        object.__setattr__(self, "_id", be_id)

    @property
    def kind(self) -> str:
        return self._world._c.be_kind(self._id)

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._world._c.be_get(self._id, name)
        except KeyError:
            raise AttributeError(name) from None
        return _DIRECTIONS[value] if name == "direction" else value

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "direction":
            value = _DIR_INDEX[value]
        try:
            self._world._c.be_set(self._id, name, value)
        except KeyError:
            raise AttributeError(name) from None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RustBlockEntity) and other._world is self._world and other._id == self._id

    def __hash__(self) -> int:
        return hash((id(self._world), self._id))

    def __repr__(self) -> str:
        return f"<RustBlockEntity {self.kind} #{self._id}>"

    def load(self, data: dict) -> None:
        """Load NBT-like data with the parser of the Python block entity class."""
        from .blocks.diode import ComparatorBlockEntity
        from .blocks.dispenser_hopper import HopperBlockEntity
        from .blocks.container import ContainerBlockEntity
        from .blocks.crafter import CrafterBlockEntity
        from .blocks.outputs import LecternBlockEntity
        from .blocks.piston import PistonMovingBlockEntity

        kind = self.kind
        if kind == "comparator":
            ref, fields = ComparatorBlockEntity(), ("output_signal",)
        elif kind == "hopper":
            ref, fields = HopperBlockEntity(self.pos), ("items", "cooldown_time")
        elif kind == "crafter":
            ref, fields = CrafterBlockEntity(self.pos), ("items", "disabled_mask", "triggered", "crafting_ticks_remaining")
        elif kind in ("container", "dispenser"):
            ref, fields = ContainerBlockEntity(self.size, self.pos), ("items",)
        elif kind == "lectern":
            ref, fields = LecternBlockEntity(), ("has_book", "page", "page_count")
        elif kind in ("daylight", "sculk"):
            return  # no data
        else:
            ref = PistonMovingBlockEntity(self.pos)
            fields = ("moved_state", "direction", "progress", "progress_o", "extending", "is_source_piston")
        ref.load(data)
        for field in fields:
            setattr(self, field, getattr(ref, field))

    def is_empty(self) -> bool:
        return not self.items

    def get_item(self, slot: int) -> list | None:
        return self.items.get(slot)

    def is_idle(self) -> bool:
        return self.cooldown_time <= 0

    def is_on_cooldown(self) -> bool:
        return self.cooldown_time > 0

    def redstone_signal(self) -> int:
        return self._world._c.be_get(self._id, "redstone_signal")


class _BlockEntities:
    """``World.block_entities``: position -> block entity, in the insertion order of the Python dict."""

    def __init__(self, world: RustWorld) -> None:
        # weak: no reference cycle, so a world is freed (by reference counting) on the thread that owns it;
        # the Rust world is unsendable and must not be dropped by the garbage collector on another thread
        self._ref = weakref.ref(world)

    @property
    def _world(self) -> RustWorld:
        return self._ref()

    def get(self, pos: Pos, default: Any = None) -> Any:
        be = self._world._c.raw_block_entity(pos)
        return default if be is None else RustBlockEntity(self._world, be)

    def __getitem__(self, pos: Pos) -> RustBlockEntity:
        be = self._world._c.raw_block_entity(pos)
        if be is None:
            raise KeyError(pos)
        return RustBlockEntity(self._world, be)

    def __contains__(self, pos: object) -> bool:
        return self._world._c.raw_block_entity(pos) is not None

    def __len__(self) -> int:
        return self._world._c.block_entity_count()

    def __iter__(self) -> Iterator[Pos]:
        return iter([p for p, _ in self._world._c.block_entity_items()])

    def keys(self) -> list[Pos]:
        return list(self)

    def items(self) -> list[tuple[Pos, RustBlockEntity]]:
        return [(p, RustBlockEntity(self._world, be)) for p, be in self._world._c.block_entity_items()]

    def values(self) -> list[RustBlockEntity]:
        return [be for _, be in self.items()]


class _Blocks:
    """``World.blocks``: position -> state of all non-air blocks, in the insertion order of the Python dict.
    Assigning stores a state without any updates."""

    def __init__(self, world: RustWorld) -> None:
        self._c = world._c

    def get(self, pos: Pos, default: Any = None) -> Any:
        return self._c.get(pos) if self._c.contains(pos) else default

    def __getitem__(self, pos: Pos) -> BlockState:
        if not self._c.contains(pos):
            raise KeyError(pos)
        return self._c.get(pos)

    def __setitem__(self, pos: Pos, state: BlockState) -> None:
        self._c.set_raw(pos, state)

    def __delitem__(self, pos: Pos) -> None:
        if not self._c.contains(pos):
            raise KeyError(pos)
        self._c.set_raw(pos, AIR)

    def pop(self, pos: Pos, *default: Any) -> Any:
        if not self._c.contains(pos):
            if default:
                return default[0]
            raise KeyError(pos)
        state = self._c.get(pos)
        self._c.set_raw(pos, AIR)
        return state

    def __contains__(self, pos: object) -> bool:
        return self._c.contains(pos)

    def __len__(self) -> int:
        return self._c.block_count()

    def __iter__(self) -> Iterator[Pos]:
        return iter([p for p, _ in self._c.blocks_items()])

    def keys(self) -> list[Pos]:
        return list(self)

    def items(self) -> list[tuple[Pos, BlockState]]:
        return self._c.blocks_items()

    def values(self) -> list[BlockState]:
        return [s for _, s in self._c.blocks_items()]


# ---------------------------------------------------------------------- the world
class RustWorld:
    """Drop-in replacement for ``redstone.sim.world.World`` running in the Rust core."""

    core = "rust"

    def __init__(self, registry: Any = None) -> None:
        self._c = rsx_core.World(_make_state, Pos)
        self.registry = REGISTRY
        self.blocks = _Blocks(self)
        self.block_entities = _BlockEntities(self)
        self._dirty: set[Pos] = set()

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_grid(cls, grid: Grid, registry: Any = None) -> RustWorld:
        world = cls()
        world.place_grid(grid)
        return world

    def place_grid(self, grid: Grid, origin: Pos = Pos(0, 0, 0)) -> None:
        """Place blocks exactly as stored, without any updates (scenario setup, docs/scenario-format.md)."""
        self._c.place_blocks(grid.items(), origin)
        for pos, data in grid.block_entities.items():
            if data:
                be = self._c.raw_block_entity(pos + origin)
                if be is not None:
                    RustBlockEntity(self, be).load(data)

    # ------------------------------------------------------------------ attributes of the Python world
    @property
    def game_time(self) -> int:
        return self._c.game_time

    @game_time.setter
    def game_time(self, value: int) -> None:
        self._c.game_time = value

    @property
    def day_time(self) -> int:
        """Overworld clock (action ``time``); see sim/blocks/daylight.py."""
        return self._c.day_time

    @day_time.setter
    def day_time(self, value: int) -> None:
        self._c.day_time = value

    @property
    def sky_darken(self) -> int:
        return self._c.sky_darken

    @property
    def handling_tick(self) -> bool:
        return self._c.handling_tick

    @property
    def warnings(self) -> list[str]:
        return self._c.warnings()

    @property
    def dirty(self) -> set[Pos]:
        """Positions whose block state changed since the set was last cleared. It is a real set that is
        filled in the order of the changes, so it iterates exactly like the one of the Python world."""
        dirty = self._dirty
        for p in self._c.take_dirty():
            dirty.add(p)
        return dirty

    @property
    def block_events(self) -> list[BlockEvent]:
        return [BlockEvent(p, name, a, b) for p, name, a, b in self._c.block_events()]

    @property
    def _ticks(self) -> list[ScheduledTick]:
        return [ScheduledTick(*t) for t in self._c.scheduled_ticks()]

    @property
    def neighbor_update_count(self) -> int:
        return self._c.neighbor_update_count

    def is_idle(self) -> bool:
        """No scheduled ticks, no block events and no block entity with pending work."""
        return self._c.is_idle()

    # ------------------------------------------------------------------ block access
    def block(self, state: BlockState) -> RustBlock:
        return REGISTRY.get(state.name)

    def get(self, pos: Pos) -> BlockState:
        return self._c.get(pos)

    def get_block_entity(self, pos: Pos) -> RustBlockEntity | None:
        be = self._c.get_block_entity(pos)
        return None if be is None else RustBlockEntity(self, be)

    def remove_block_entity(self, pos: Pos) -> None:
        self._c.remove_block_entity(pos)

    def set_block(self, pos: Pos, state: BlockState, flags: int = UPDATE_ALL, limit: int = UPDATE_LIMIT) -> bool:
        return self._c.set_block(pos, state, flags, limit)

    def remove_block(self, pos: Pos, moved_by_piston: bool = False) -> bool:
        return self._c.remove_block(pos, moved_by_piston)

    def destroy_block(self, pos: Pos, limit: int = UPDATE_LIMIT) -> bool:
        return self._c.destroy_block(pos, limit)

    def update_or_destroy(self, old: BlockState, new: BlockState, pos: Pos, flags: int, limit: int) -> None:
        self._c.update_or_destroy(old, new, pos, flags, limit)

    # ------------------------------------------------------------------ neighbor updates
    def update_neighbors_at(self, pos: Pos, source: Any, skip: Direction | None = None) -> None:
        self._c.update_neighbors_at(pos, _name(source), None if skip is None else _DIR_INDEX[skip])

    def update_neighbors_at_except_from_facing(self, pos: Pos, source: Any, skip: Direction) -> None:
        self._c.update_neighbors_at(pos, _name(source), _DIR_INDEX[skip])

    def neighbor_changed(self, pos: Pos, source: Any) -> None:
        self._c.neighbor_changed(pos, _name(source))

    def neighbor_changed_with_state(self, state: BlockState, pos: Pos, source: Any, moved_by_piston: bool) -> None:
        self._c.neighbor_changed_with_state(state, pos, _name(source), moved_by_piston)

    def neighbor_shape_changed(self, direction: Direction, pos: Pos, neighbor_pos: Pos,
                               neighbor_state: BlockState, flags: int, limit: int) -> None:
        self._c.neighbor_shape_changed(_DIR_INDEX[direction], pos, neighbor_pos, neighbor_state, flags, limit)

    def update_neighbour_shapes(self, pos: Pos, state: BlockState, flags: int, limit: int = UPDATE_LIMIT) -> None:
        self._c.update_neighbour_shapes(pos, state, flags, limit)

    def update_neighbour_for_output_signal(self, pos: Pos, source: Any) -> None:
        self._c.update_neighbour_for_output_signal(pos, _name(source))

    # ------------------------------------------------------------------ signals
    def is_conductor(self, pos: Pos) -> bool:
        return self._c.is_conductor(pos)

    def is_face_sturdy(self, pos: Pos, face: Direction, support: str = "full") -> bool:
        return self._c.is_face_sturdy(pos, _DIR_INDEX[face], _SUPPORT_INDEX[support])

    def is_signal_source(self, state: BlockState) -> bool:
        return self.block(state).is_signal_source(state)

    def get_direct_signal(self, pos: Pos, direction: Direction) -> int:
        return self._c.get_direct_signal(pos, _DIR_INDEX[direction])

    def get_direct_signal_to(self, pos: Pos) -> int:
        return self._c.get_direct_signal_to(pos)

    def get_signal(self, pos: Pos, direction: Direction) -> int:
        return self._c.get_signal(pos, _DIR_INDEX[direction])

    def has_signal(self, pos: Pos, direction: Direction) -> bool:
        return self._c.get_signal(pos, _DIR_INDEX[direction]) > 0

    def has_neighbor_signal(self, pos: Pos) -> bool:
        return self._c.has_neighbor_signal(pos)

    def get_best_neighbor_signal(self, pos: Pos) -> int:
        return self._c.get_best_neighbor_signal(pos)

    def get_control_input_signal(self, pos: Pos, direction: Direction, only_diodes: bool) -> int:
        return self._c.get_control_input_signal(pos, _DIR_INDEX[direction], only_diodes)

    # ------------------------------------------------------------------ scheduled ticks, block events
    def schedule_tick(self, pos: Pos, block: Any, delay: int, priority: int = TickPriority.NORMAL) -> None:
        self._c.schedule_tick(pos, _name(block), delay, int(priority))

    def has_scheduled_tick(self, pos: Pos, block: Any) -> bool:
        return self._c.has_scheduled_tick(pos, _name(block))

    def will_tick_this_tick(self, pos: Pos, block: Any) -> bool:
        return self._c.will_tick_this_tick(pos, _name(block))

    def clear_scheduled_ticks(self) -> None:
        self._c.clear_scheduled_ticks()

    def block_event(self, pos: Pos, block: Any, a: int, b: int) -> None:
        self._c.block_event(pos, _name(block), a, b)

    # ------------------------------------------------------------------ the game tick
    def tick(self) -> None:
        """One game tick (ServerLevel#tick, redstone-relevant phases only)."""
        self._c.tick()

    # ------------------------------------------------------------------ recording helpers
    def probe_value(self, pos: Pos) -> str:
        """runner.probe_value: the state string, for comparators with ``|output=N``."""
        return self._c.probe_value(pos)

    def probe_values(self, positions: list[Pos]) -> list[str]:
        return self._c.probe_values(positions)

    def snapshot(self, lo: Pos, hi: Pos, origin: Pos) -> list[tuple[Pos, str]]:
        """``(pos - origin, probe value)`` of all non-air blocks inside ``lo..hi``, in ``blocks`` order."""
        return self._c.snapshot(lo, hi, origin)

    def run_recording(self, actions: list[tuple[int, Pos]], max_ticks: int, quiet: int, lo: Pos, hi: Pos,
                      origin: Pos) -> tuple[list[tuple[Pos, str]], list[tuple[int, Pos, str, str]], int, int | None]:
        """analysis.experiment.Circuit.run in the core: right clicks (steps on plates) at absolute positions,
        returns (snapshot before the first tick, changes (tick, pos - origin, old, new), ticks, settled_at)."""
        self._dirty.clear()
        return self._c.run_recording(actions, max_ticks, quiet, lo, hi, origin)

    def comparator_positions(self) -> list[Pos]:
        """Positions of comparators with a block entity, in ``block_entities`` order."""
        return self._c.comparator_positions()

    def use_at(self, pos: Pos) -> bool:
        """Right click on the block at ``pos`` (runner input "use")."""
        return self._c.use_at(pos)

    def step_at(self, pos: Pos) -> bool:
        """Runner input "step": an entity steps on the plate at ``pos`` and leaves again."""
        return self._c.step_at(pos)

    # ------------------------------------------------------------------ mechanics notes
    def collect_notes(self) -> list[Note]:
        """redstone.sim.notes.notes_of: run the state checks, then list all notes."""
        self._c.run_state_checks()
        return [Note(tick, kind, pos, detail) for tick, kind, pos, detail in self._c.notes()]
