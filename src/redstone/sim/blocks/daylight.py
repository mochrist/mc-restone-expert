"""Daylight detector (26.3): DaylightDetectorBlock, DaylightDetectorBlockEntity.

The detector samples the sky every 20 game ticks (block entity ticker, ``gameTime % 20 == 0``) and when a
player right-clicks it (toggles ``inverted`` and updates at once).

Model of the sky in the oracle world (docs/scenario-format.md, "Daylight detector"):

* The oracle freezes the overworld clock (``advance_time`` false) and resets it to ``total_ticks = 0`` when it
  builds a scenario; the scenario action ``time`` sets it (like ``/time set``). The simulator keeps it in
  ``world.day_time``. Timeline ``minecraft:day`` (data/minecraft/timeline/day.json, period 24000) gives
  ``visual/sun_angle`` (cubic bezier eased, 0 degrees at 6000) and ``gameplay/sky_light_level`` (15 times a
  linear track); ``Level#skyDarken`` = (int)(15 - sky light level). Both are computed in float exactly like
  ``KeyframeTrackSampler``/``EasingType.CubicBezier`` (``sun_angle``, ``sky_darken_at``).
* ``Level#updateSkyBrightness`` runs at the start of each server tick, so a ``time`` action changes
  ``skyDarken`` only from the next tick on (``world.sky_darken``, refreshed in ``World.tick``); the sun angle
  is read fresh (``ServerClockManager#modifyClock`` invalidates the attribute cache).
* Clear weather (the oracle clears it; rain would lower the sky light level).
* ASSUMPTION: the sky light at the detector is 15 minus the distance (through cells without a redstone
  conductor) to the nearest cell with open sky above. Opaque blocks are approximated by redstone conductors
  (full cubes); slabs, stairs, leaves and so on are not modeled. Proven in the game: a detector under one
  stone block between open columns reads like sky 14, one 3 blocks inside a plate like sky 12.
"""

from __future__ import annotations

import math
import struct
from functools import lru_cache

from ...model import BlockState, Direction, Pos
from ..block import REGISTRY, Block
from ..constants import UPDATE_ALL, UPDATE_CLIENTS
from ..world import World

DAY_PERIOD = 24000
_DIRS = tuple(Direction)
MAX_Y = 319  # highest block position of the overworld (world height 384, min y -64)


def _f(x: float) -> float:
    """Round to float32 (Java float). Exact for one +, -, * or / of float32 operands."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _curve(v1: float, v2: float) -> tuple[float, float, float]:
    """EasingType.CubicBezier#curveFromControls"""
    return (_f(_f(_f(3.0 * v1) - _f(3.0 * v2)) + 1.0), _f(_f(-6.0 * v1) + _f(3.0 * v2)), _f(3.0 * v1))


def _sample(c: tuple[float, float, float], t: float) -> float:
    a, b, cc = c
    return _f(_f(_f(_f(_f(a * t) + b) * t) + cc) * t)


def _gradient(c: tuple[float, float, float], t: float) -> float:
    a, b, cc = c
    return _f(_f(_f(_f(_f(3.0 * a) * t) + _f(2.0 * b)) * t) + cc)


# Timeline minecraft:day, track visual/sun_angle: ease cubic_bezier [0.362, 0.241, 0.638, 0.759]
_X_CURVE = _curve(_f(0.362), _f(0.638))
_Y_CURVE = _curve(_f(0.241), _f(0.759))
_EPS = _f(1.0e-5)


def _ease(x: float) -> float:
    """EasingType.CubicBezier#apply"""
    t = x
    for _ in range(4):  # solveT, Newton-Raphson
        error = _f(_sample(_X_CURVE, t) - x)
        if abs(error) < _EPS:
            return _sample(_Y_CURVE, t)
        gradient = _gradient(_X_CURVE, t)
        if gradient < _EPS:
            break
        t = _f(t - min(max(_f(error / gradient), -0.25), 0.25))
    t0, t1 = 0.0, 1.0  # solveTBisect
    while t0 < t1:
        error = _f(_sample(_X_CURVE, t) - x)
        if abs(error) < _EPS:
            break
        if error < 0.0:
            t0 = t
        else:
            t1 = t
        t = _f(_f(t1 + t0) / 2.0)
    return _sample(_Y_CURVE, t)


def _lerp(alpha: float, a: float, b: float) -> float:
    """Mth.lerp (float)"""
    return _f(a + _f(alpha * _f(b - a)))


@lru_cache(maxsize=4096)
def sun_angle(day_time: int) -> float:
    """visual/sun_angle in degrees (float) at overworld clock ``day_time``: keyframes 6000 -> 360 and
    6000 -> 0, so the segment runs from 0 degrees at 6000 to 360 degrees at 30000 (KeyframeTrackSampler)."""
    t = day_time % DAY_PERIOD
    start = 6000 if t >= 6000 else 6000 - DAY_PERIOD
    if t <= start:
        return 0.0
    alpha = _f(_f(float(t - start)) / float(DAY_PERIOD))
    return _lerp(_ease(alpha), 0.0, 360.0)


# Timeline minecraft:day, track gameplay/sky_light_level (modifier multiply, linear): (ticks, value)
_SKY_KEYS = ((133, 1.0), (11867, 1.0), (13670, _f(0.26666668)), (22330, _f(0.26666668)))


@lru_cache(maxsize=4096)
def sky_darken_at(day_time: int) -> int:
    """Level#updateSkyBrightness: (int)(15 - 15 * track value) at overworld clock ``day_time``."""
    t = day_time % DAY_PERIOD
    keys = [(_SKY_KEYS[-1][0] - DAY_PERIOD, _SKY_KEYS[-1][1]), *_SKY_KEYS, (_SKY_KEYS[0][0] + DAY_PERIOD, _SKY_KEYS[0][1])]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t < t1:
            break
    if t <= t0:
        value = v0
    elif t >= t1:
        value = v1
    else:
        value = _lerp(_f(_f(float(t - t0)) / float(t1 - t0)), v0, v1)
    level = min(max(_f(15.0 * value), 0.0), 15.0)
    return int(_f(15.0 - level))


# Mth.SIN: 65536 float sines
_SIN = [_f(math.sin(i / 10430.378350470453)) for i in range(65536)]


def _mth_cos(x: float) -> float:
    return _SIN[int(x * 10430.378350470453 + 16384.0) & 65535]


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


_PI_OVER_180 = _f(math.pi / 180.0)
_PI_F = _f(math.pi)
_TWO_PI_F = _f(math.pi * 2)


def target_power(world: World, pos: Pos, state: BlockState) -> int:
    """The signal strength DaylightDetectorBlock#updateSignalStrength would set."""
    target = max(sky_light(world, pos) - world.sky_darken, 0)  # LevelReader#getEffectiveSkyBrightness
    if state.get_bool("inverted"):
        target = 15 - target
    elif target > 0:
        sun = _f(sun_angle(world.day_time) * _PI_OVER_180)
        offset = 0.0 if sun < _PI_F else _TWO_PI_F
        sun = _f(sun + _f(_f(offset - sun) * _f(0.2)))
        # Math.round(float): floor(x + 0.5)
        target = math.floor(_f(target * _mth_cos(sun)) + 0.5)
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
        if state.id != "daylight_detector":
            return True
        if world.sky_darken != sky_darken_at(world.day_time):  # refreshed at the next tick
            return False
        return state.get_int("power") == target_power(world, self.pos, state)


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
