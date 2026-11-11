"""Daylight detector (26.3): DaylightDetectorBlock, DaylightDetectorBlockEntity.

The detector samples the sky every 20 game ticks (block entity ticker, ``gameTime % 20 == 0``) and when a
player right-clicks it (toggles ``inverted`` and updates at once).

Model of the sky in the oracle world (docs/scenario-format.md, "Daylight detector"):

* The oracle freezes the overworld clock (``advance_time`` false) at ``total_ticks = 0`` (fresh world,
  ``world_clocks.dat``). Timeline ``minecraft:day`` (``Timelines.OVERWORLD_DAY``) then gives
  ``SUN_ANGLE`` = eased(18000 / 24000) * 360 = 282.37 degrees and ``SKY_LIGHT_LEVEL`` = 15 * 0.945 = 14.2,
  so ``Level#skyDarken`` = (int)(15 - 14.2) = 0. Proven in the game: a normal detector reads 7 under open
  sky (15 * cos(adjusted angle) = 7.02), an inverted one 0 (``15 - 15``).
* ASSUMPTION: the sky light at the detector is 15 minus the distance (through cells without a redstone
  conductor) to the nearest cell with open sky above. Opaque blocks are approximated by redstone conductors
  (full cubes); slabs, stairs, leaves and so on are not modeled. Proven in the game: a detector under one
  stone block between open columns reads like sky 14, one 3 blocks inside a plate like sky 12.
"""

from __future__ import annotations

import math

from ...model import BlockState, Direction, Pos
from ..block import REGISTRY, Block
from ..constants import UPDATE_ALL, UPDATE_CLIENTS
from ..world import World

# Sun angle in degrees at overworld clock time 0 (see the module docstring). ASSUMPTION: the easing is the
# symmetric cubic bezier (0.362, 0.241) of Timelines; the result is confirmed by the recorded game trace.
SUN_ANGLE = 282.3711
# Level#skyDarken at that time (clear weather)
SKY_DARKEN = 0
_DIRS = tuple(Direction)
MAX_Y = 319  # highest block position of the overworld (world height 384, min y -64)


def sky_light(world: World, pos: Pos) -> int:
    """LightLayer.SKY brightness at ``pos`` (ASSUMPTION: see module docstring).

    Sky light is 15 in every cell with no conductor above it and loses 1 per step through non-conductor
    cells, so it is 15 minus the distance (6 directions) to the nearest such cell."""
    tops: dict[tuple[int, int], int] = {}

    def is_open(p: Pos) -> bool:
        top = tops.get((p.x, p.z))
        if top is None:
            top = tops[(p.x, p.z)] = _conductor_top(world, p, pos.y - 15)
        return p.y > top

    seen = {pos}
    level = [pos]
    for dist in range(16):
        if any(is_open(p) for p in level):
            return 15 - dist
        if dist == 15:
            break
        nxt = []
        for p in level:
            for d in _DIRS:
                q = p.offset(d)
                if q not in seen:
                    seen.add(q)
                    state = world.get(q)
                    if not world.block(state).is_conductor(state):
                        nxt.append(q)
        level = nxt
    return 0


def _conductor_top(world: World, p: Pos, low: int) -> int:
    """Highest y >= ``low`` with a redstone conductor in the column of ``p``; ``low - 1`` if none."""
    for y in range(MAX_Y, low - 1, -1):
        state = world.get(Pos(p.x, y, p.z))
        if world.block(state).is_conductor(state):
            return y
    return low - 1


def target_power(world: World, pos: Pos, state: BlockState) -> int:
    """The signal strength DaylightDetectorBlock#updateSignalStrength would set."""
    target = max(sky_light(world, pos) - SKY_DARKEN, 0)  # LevelReader#getEffectiveSkyBrightness
    if state.get_bool("inverted"):
        target = 15 - target
    elif target > 0:
        sun = SUN_ANGLE * (math.pi / 180.0)
        offset = 0.0 if sun < math.pi else math.pi * 2
        sun += (offset - sun) * 0.2
        # Math.round(float): floor(x + 0.5)
        target = math.floor(target * math.cos(sun) + 0.5)
    return min(max(target, 0), 15)


def update_signal_strength(world: World, pos: Pos, state: BlockState) -> None:
    """DaylightDetectorBlock#updateSignalStrength"""
    target = target_power(world, pos, state)
    if state.get_int("power") != target:
        world.set_block(pos, state.with_(power=target), UPDATE_ALL)


class DaylightDetectorBlockEntity:
    ticks = True
    idle_needs_world = True

    def __init__(self, pos: Pos) -> None:
        self.pos = pos
        self.removed = False

    def load(self, data: dict) -> None:
        pass

    def tick(self, world: World) -> None:
        """DaylightDetectorBlock#tickEntity"""
        state = world.get(self.pos)
        if state.id != "daylight_detector":
            return
        if world.game_time % 20 == 0:
            update_signal_strength(world, self.pos, state)

    def is_idle(self, world: World) -> bool:
        """Not part of the game: true when the next update would not change the power."""
        state = world.get(self.pos)
        return state.id != "daylight_detector" or state.get_int("power") == target_power(world, self.pos, state)


class DaylightDetectorBlock(Block):
    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return state.get_int("power")

    def has_block_entity(self, state):
        return True

    def new_block_entity(self, pos, state):
        return DaylightDetectorBlockEntity(pos)

    def use_without_item(self, world: World, pos: Pos, state: BlockState) -> bool:
        """Toggle ``inverted`` (flags 2: no neighbor updates), then update the power at once."""
        new = state.with_(inverted=not state.get_bool("inverted"))
        world.set_block(pos, new, UPDATE_CLIENTS)
        world.game_event("block_change", pos, new)
        update_signal_strength(world, pos, new)
        return True


REGISTRY.register(DaylightDetectorBlock(), "daylight_detector")
