"""Static block properties the simulator needs for arbitrary (non-redstone) blocks.

The values come from ``data/blocks_26.3.json``, dumped from the 26.3 server by the oracle mod
(``oracle/src/main/java/redstone/oracle/BlockDump.java``; regenerate with ``uv run rsx oracle --dump-blocks``).
It holds, for every state of every registered block, what ``BlockBehaviour.BlockStateBase`` answers for:
``isRedstoneConductor``, ``isSignalSource``, ``hasAnalogOutputSignal``, ``isFaceSturdy`` (all six faces for
``SupportType`` FULL, RIGID and CENTER), ``getPistonPushReaction``, ``isAir``, ``canBeReplaced()``,
``hasBlockEntity``, ``isCollisionShapeFullBlock``, ``isSolid``, ``isSolidRender``,
``shouldRedstoneWireConnectTo`` (per direction and for ``null``), ``getDestroySpeed == -1``, ``instanceof
TrapDoorBlock``, the ``#unstable_bottom_center`` tag and ``instrument()`` (note block instrument). Level-dependent predicates were evaluated in an empty
block getter at the origin.

File format (see BlockDump.java): ``blocks[id] = {"props": {name: [values]}, "default": index, "v": {key: value
or [value per state]}}``; the state index is mixed radix over ``props`` in listed order (first = most
significant). Face sets are bit masks in ``Direction`` order (down, up, north, south, west, east).

States with missing properties take them from the block's default state; states with unknown properties or
values fall back to the default state, and unknown blocks to name-based heuristics (both with a warning).
"""

from __future__ import annotations

import json
import warnings
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

from ..model import BlockState, Direction

DATA_FILE = Path(__file__).resolve().parent / "data" / "blocks_26.3.json"
SUPPORT_TYPES = ("full", "rigid", "center")

# Effective piston behaviour in the legacy names used by the simulator, see push_reaction().
_LEGACY_PUSH = {"push_pull": "normal", "push": "push_only", "popped": "destroy", "immoveable": "block",
                "ignore_entity": "normal"}


@cache
def _table() -> dict[str, Any]:
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)["blocks"]


@cache
def _warn_once(message: str) -> None:
    warnings.warn(message, stacklevel=3)


@lru_cache(maxsize=8192)
def _lookup(state: BlockState) -> tuple[dict[str, Any], int] | None:
    """(values, state index) of a state, or None for an unknown block."""
    entry = _table().get(state.name)
    if entry is None:
        _warn_once(f"block {state.name} is not in {DATA_FILE.name}; using name-based heuristics")
        return None
    props: dict[str, list[str]] = entry.get("props", {})
    if not props:
        return entry["v"], 0
    given = state.properties
    default = entry["default"]
    index, stride = 0, 1
    for name, values in reversed(props.items()):
        n = len(values)
        value = given.pop(name, None)
        if value is None:
            digit = (default // stride) % n
        elif value in values:
            digit = values.index(value)
        else:
            _warn_once(f"unknown value {name}={value} for {state.name}; using its default state")
            return entry["v"], default
        index += digit * stride
        stride *= n
    if given:
        _warn_once(f"unknown properties {sorted(given)} for {state.name}; using its default state")
        return entry["v"], default
    return entry["v"], index


def _value(state: BlockState, key: str) -> Any:
    """The raw table value of ``key`` for a state; None if the block is unknown."""
    found = _lookup(state)
    if found is None:
        return None
    values, index = found
    v = values[key]
    return v[index] if isinstance(v, list) else v


def is_known(state: BlockState) -> bool:
    return state.name in _table()


def properties(name: str) -> dict[str, list[str]]:
    """Property names and allowed values of a block (``minecraft:`` id), in the game's order."""
    return dict(_table()[name].get("props", {}))


def default_state(name: str) -> BlockState:
    """The block's default state (``Block.defaultBlockState()``)."""
    entry = _table()[name]
    props: dict[str, list[str]] = entry.get("props", {})
    out, index = {}, entry.get("default", 0)
    for prop, values in reversed(props.items()):
        out[prop] = values[index % len(values)]
        index //= len(values)
    return BlockState.of(name, out)


# --- predicates ------------------------------------------------------------------


def is_conductor(state: BlockState) -> bool:
    """``isRedstoneConductor``: the block is strongly/weakly powered by adjacent components."""
    v = _value(state, "conductor")
    return _guess_conductor(state) if v is None else v


def is_face_sturdy(state: BlockState, face: Direction, support: str = "full") -> bool:
    """``isFaceSturdy(face, SupportType)``; support is "full" (torches, levers, wire), "rigid" (repeaters,
    comparators: ``canSupportRigidBlock``) or "center" (``canSupportCenter``)."""
    if support not in SUPPORT_TYPES:
        raise ValueError(f"unknown support type {support!r}")
    v = _value(state, f"sturdy_{support}")
    if v is None:
        return _guess_face_sturdy(state, face)
    return bool(v >> _FACE_BIT[face] & 1)


def can_support_center(state: BlockState, face: Direction) -> bool:
    """``Block.canSupportCenter`` for the given face of ``state`` (false for the bottom of
    ``#unstable_bottom_center`` blocks)."""
    if face is Direction.DOWN and is_unstable_bottom_center(state):
        return False
    return is_face_sturdy(state, face, "center")


def piston_push_reaction(state: BlockState) -> str:
    """Raw ``getPistonPushReaction()``: push_pull, push, popped, immoveable or ignore_entity."""
    v = _value(state, "push")
    if v is None:
        return {"normal": "push_pull", "push_only": "push", "destroy": "popped", "block": "immoveable",
                "ignore": "push_pull"}[_guess_push_reaction(state)]
    return v


def push_reaction(state: BlockState) -> str:
    """Effective piston behaviour, as ``PistonBaseBlock.isPushable`` decides it (ignoring world bounds):
    "ignore" (air), "normal", "push_only" (can be pushed but not pulled), "destroy" (popped) or "block".

    Unbreakable blocks (destroy speed -1), blocks with a block entity and extended pistons are "block";
    retracted pistons are "normal" even though their raw reaction is IMMOVEABLE.
    """
    if state.is_air or is_air(state):
        return "ignore"
    if not is_known(state):
        return _guess_push_reaction(state)
    if state.id in ("piston", "sticky_piston"):
        return "block" if state.get("extended") == "true" else "normal"
    if is_unbreakable(state):
        return "block"
    reaction = _LEGACY_PUSH[piston_push_reaction(state)]
    if reaction in ("block", "destroy"):
        return reaction
    return "block" if has_block_entity(state) else reaction


def _flag(state: BlockState, key: str, default: bool = False) -> bool:
    v = _value(state, key)
    return default if v is None else bool(v)


def is_signal_source(state: BlockState) -> bool:
    return _flag(state, "signal_source")


def has_analog_output_signal(state: BlockState) -> bool:
    return _flag(state, "analog_output")


def is_air(state: BlockState) -> bool:
    return _flag(state, "air", state.is_air)


def is_replaceable(state: BlockState) -> bool:
    """``canBeReplaced()`` (the context-free variant: air, water, short grass, ...)."""
    return _flag(state, "replaceable", state.is_air)


def has_block_entity(state: BlockState) -> bool:
    return _flag(state, "block_entity")


def is_collision_shape_full_block(state: BlockState) -> bool:
    return _flag(state, "full_collision", _guess_conductor(state))


def is_solid(state: BlockState) -> bool:
    """Deprecated ``isSolid()`` (legacy "solid" flag)."""
    return _flag(state, "solid", not state.is_air)


def is_solid_render(state: BlockState) -> bool:
    return _flag(state, "solid_render", _guess_conductor(state))


def is_unbreakable(state: BlockState) -> bool:
    """``getDestroySpeed == -1`` (bedrock, barrier, command blocks, end portal frame, ...)."""
    return _flag(state, "unbreakable")


def is_trapdoor(state: BlockState) -> bool:
    """``getBlock() instanceof TrapDoorBlock`` (redstone wire may climb onto any trapdoor)."""
    return _flag(state, "trapdoor", state.id.endswith("trapdoor"))


def instrument(state: BlockState) -> str:
    """``BlockState#instrument()`` (``BlockBehaviour.Properties#instrument``, default harp) as its serialized
    name; the note block takes it from the block below (or from a mob head above)."""
    v = _value(state, "instrument")
    return "harp" if v is None else v


def is_unstable_bottom_center(state: BlockState) -> bool:
    return _flag(state, "unstable_bottom_center")


def should_wire_connect_to(state: BlockState, direction: Direction | None) -> bool:
    """``shouldRedstoneWireConnectTo(level, pos, direction)``; direction is the one passed by the wire
    (from the wire towards ``state``), or None for the up/down diagonal checks."""
    v = _value(state, "wire_connect")
    if v is None:
        return False
    return bool(v >> (6 if direction is None else _FACE_BIT[direction]) & 1)


def can_wire_survive_on(state: BlockState) -> bool:
    """``RedStoneWireBlock.canSurviveOn``: sturdy top face or a hopper."""
    return is_face_sturdy(state, Direction.UP) or state.id == "hopper"


_FACE_BIT = {d: i for i, d in enumerate(Direction)}


# --- heuristics for blocks missing from the table (e.g. other versions or mods) -----------------

_NON_CONDUCTOR_HINTS = (
    "glass", "slab", "stairs", "fence", "wall", "door", "trapdoor", "pane", "bars", "leaves", "carpet",
    "button", "pressure_plate", "rail", "torch", "sign", "banner", "ladder", "vine", "lantern", "chain",
    "candle", "head", "skull", "flower", "sapling", "grass", "fern", "bush", "coral", "kelp", "seagrass",
    "redstone", "repeater", "comparator", "observer", "piston", "lever", "lamp", "target", "daylight",
    "hopper", "chest", "slime", "honey", "ice", "snow", "cactus", "cake", "bed", "anvil", "bell",
    "lectern", "cauldron", "composter", "enchanting", "brewing", "grindstone", "stonecutter", "campfire",
    "scaffolding", "sculk_sensor", "sculk_shrieker", "dispenser", "dropper", "barrel", "note_block",
    "tnt", "beacon", "conduit", "farmland", "dirt_path", "soul_sand", "mud", "bulb", "crafter",
    "moving_piston", "spawner", "lightning_rod", "pot", "amethyst_cluster", "bud", "dripleaf", "azalea",
)
_CONDUCTOR_EXCEPTIONS = {
    "redstone_ore", "deepslate_redstone_ore", "packed_ice", "blue_ice", "snow_block", "honeycomb_block",
    "dispenser", "dropper", "note_block", "target", "redstone_lamp", "crafter", "tnt", "barrel",
    "dirt", "grass_block", "mud_bricks", "packed_mud", "copper_bulb",
}


def _guess_conductor(state: BlockState) -> bool:
    if state.is_air:
        return False
    name = state.id
    if name in _CONDUCTOR_EXCEPTIONS or name.endswith("copper_bulb"):
        return True
    return not any(h in name for h in _NON_CONDUCTOR_HINTS)


def _guess_face_sturdy(state: BlockState, face: Direction) -> bool:
    if state.is_air:
        return False
    name = state.id
    if name.endswith("_slab"):
        t = state.get("type")
        return t == "double" or (t == "top" and face is Direction.UP) or (t == "bottom" and face is Direction.DOWN)
    return _guess_conductor(state) or "glass" in name and "pane" not in name


def _guess_push_reaction(state: BlockState) -> str:
    if state.is_air:
        return "ignore"
    name = state.id
    if "command_block" in name or "chest" in name or name in ("obsidian", "crying_obsidian", "bedrock", "barrier"):
        return "block"
    if any(h in name for h in ("torch", "button", "lever", "redstone_wire", "repeater", "comparator", "carpet",
                               "flower", "sapling", "pressure_plate", "rail", "door", "sign", "banner")):
        return "destroy"
    if name.endswith("glazed_terracotta"):
        return "push_only"
    return "normal"
