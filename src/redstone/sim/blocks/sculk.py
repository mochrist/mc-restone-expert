"""Sculk sensor and calibrated sculk sensor (26.3): SculkSensorBlock, CalibratedSculkSensorBlock,
SculkSensorBlockEntity, VibrationSystem (listener, selector, ticker). Knowledge: SCULK-*.

Only vibrations caused by blocks exist in the simulator (no entities). Blocks announce them with
``World.game_event(event, pos, affected_state)``; every sensor in range selects the nearest vibration of a
game tick, lets it travel ``floor(distance)`` game ticks and then activates (30 gt, calibrated 10 gt) and
cools down for 10 gt.

Not modeled (ASSUMPTION: no influence on scenarios of the oracle world): entities (stepping, projectiles),
sounds, particles, waterlogging and fluid ticks, the unloaded-chunk rule (``areAdjacentChunksTicking``: the
oracle forces all chunks around the build), the shrieker and warden. The vibration travels in a straight line
through the air; the sculk sensor's own activation and the click event are not vibrations (the click event
``sculk_sensor_tendrils_clicking`` is not in the ``vibrations`` tag).
"""

from __future__ import annotations

import math
import struct

from ...model import BlockState, Direction, Pos
from ..block import REGISTRY, Block
from ..constants import UPDATE_ALL
from ..world import World

# VibrationSystem#VIBRATION_FREQUENCY_FOR_EVENT (game events without an entry have frequency 0 and are ignored)
FREQUENCY = {
    "step": 1, "swim": 1, "flap": 1,
    "projectile_land": 2, "hit_ground": 2, "splash": 2, "bounce": 2,
    "item_interact_finish": 3, "projectile_shoot": 3, "instrument_play": 3,
    "entity_action": 4, "elytra_glide": 4, "unequip": 4,
    "entity_dismount": 5, "equip": 5,
    "entity_interact": 6, "shear": 6, "entity_mount": 6,
    "entity_damage": 7,
    "drink": 8, "eat": 8,
    "container_close": 9, "block_close": 9, "block_deactivate": 9, "block_detach": 9,
    "container_open": 10, "block_open": 10, "block_activate": 10, "block_attach": 10, "prime_fuse": 10,
    "note_block_play": 10,
    "block_change": 11,
    "block_destroy": 12, "fluid_pickup": 12,
    "block_place": 13, "fluid_place": 13,
    "entity_place": 14, "lightning_strike": 14, "teleport": 14,
    "entity_die": 15, "explode": 15,
    **{f"resonate_{i}": i for i in range(1, 16)},
}

_COLORS = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan",
           "purple", "blue", "brown", "green", "red", "black")
# #minecraft:occludes_vibration_signals = #wool; #minecraft:dampens_vibrations = wool, wool carpets (the tags
# wool_slabs and wool_stairs are empty in vanilla)
WOOL = frozenset(f"minecraft:{c}_wool" for c in _COLORS)
DAMPENS = WOOL | frozenset(f"minecraft:{c}_carpet" for c in _COLORS)
# #minecraft:vibration_resonators
RESONATORS = frozenset({"minecraft:amethyst_block"})

SENSOR_RADIUS = 8
CALIBRATED_RADIUS = 16
COOLDOWN_TICKS = 10
_ALL_DIRECTIONS = tuple(Direction)


def f32(x: float) -> float:
    """Round to a Java float."""
    return struct.unpack("f", struct.pack("f", x))[0]


def distance_between(a: Pos, b: Pos) -> float:
    """VibrationSystem.Listener#distanceBetweenInBlocks: (float) sqrt(BlockPos#distSqr)."""
    return f32(math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2))


def redstone_strength_for_distance(distance: float, radius: int) -> int:
    """VibrationSystem#getRedstoneStrengthForDistance"""
    return max(1, 15 - math.floor(15.0 / radius * distance))


def _frac(x: float) -> float:
    return x - math.floor(x)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def block_in_line(from_: tuple[float, float, float], to: tuple[float, float, float], world: World,
                  names: frozenset[str]) -> bool:
    """BlockGetter#isBlockInLine + traverseBlocks: does the segment pass through a block named in ``names``?"""
    if from_ == to:
        return False

    def lerp(delta: float, start: float, end: float) -> float:
        return start + delta * (end - start)

    to_x, to_y, to_z = (lerp(-1.0e-7, to[i], from_[i]) for i in range(3))
    from_x, from_y, from_z = (lerp(-1.0e-7, from_[i], to[i]) for i in range(3))
    cx, cy, cz = math.floor(from_x), math.floor(from_y), math.floor(from_z)

    def hit(x: int, y: int, z: int) -> bool:
        return world.get(Pos(x, y, z)).name in names

    if hit(cx, cy, cz):
        return True
    dx, dy, dz = to_x - from_x, to_y - from_y, to_z - from_z
    sx, sy, sz = _sign(dx), _sign(dy), _sign(dz)
    big = 1.7976931348623157e308
    t_dx = big if sx == 0 else sx / dx
    t_dy = big if sy == 0 else sy / dy
    t_dz = big if sz == 0 else sz / dz
    tx = t_dx * ((1.0 - _frac(from_x)) if sx > 0 else _frac(from_x))
    ty = t_dy * ((1.0 - _frac(from_y)) if sy > 0 else _frac(from_y))
    tz = t_dz * ((1.0 - _frac(from_z)) if sz > 0 else _frac(from_z))
    while tx <= 1.0 or ty <= 1.0 or tz <= 1.0:
        if tx < ty:
            if tx < tz:
                cx += sx
                tx += t_dx
            else:
                cz += sz
                tz += t_dz
        elif ty < tz:
            cy += sy
            ty += t_dy
        else:
            cz += sz
            tz += t_dz
        if hit(cx, cy, cz):
            return True
    return False


# Float 1.0E-5F as a double (Vec3#relative(direction, 1.0E-5F))
_NUDGE = struct.unpack("f", struct.pack("f", 1.0e-5))[0]


def is_occluded(world: World, origin: Pos, dest: Pos) -> bool:
    """VibrationSystem.Listener#isOccluded: blocked only when a wool block is in the way for each of the six
    start points nudged by 1e-5 from the center of the source block."""
    to = (dest.x + 0.5, dest.y + 0.5, dest.z + 0.5)
    for d in _ALL_DIRECTIONS:
        start = (origin.x + 0.5 + _NUDGE * d.vec[0], origin.y + 0.5 + _NUDGE * d.vec[1],
                 origin.z + 0.5 + _NUDGE * d.vec[2])
        if not block_in_line(start, to, world, WOOL):
            return False
    return True


class SculkSensorBlockEntity:
    ticks = True
    listens = True

    def __init__(self, pos: Pos, radius: int = SENSOR_RADIUS) -> None:
        self.pos = pos
        self.removed = False
        self.radius = radius
        self.last_vibration_frequency = 0
        # VibrationSystem.Data: current vibration (frequency, distance, origin) and remaining travel time
        self.current: tuple[int, float, Pos] | None = None
        self.travel_time = 0
        # VibrationSelector: (frequency, distance, origin) and the game tick it was announced in
        self.candidate: tuple[int, float, Pos] | None = None
        self.candidate_tick = -1

    def load(self, data: dict) -> None:
        pass

    # --- VibrationSystem.Listener#handleGameEvent ----------------------------------------------------
    def on_game_event(self, world: World, event: str, origin: Pos, affected: BlockState | None) -> None:
        if self.current is not None:
            return
        frequency = FREQUENCY.get(event, 0)
        if frequency == 0:  # not in #vibrations, or no frequency: canReceiveVibration
            return
        if affected is not None and affected.name in DAMPENS:  # User#isValidVibration
            return
        dest = self.pos
        d2 = (origin.x - dest.x) ** 2 + (origin.y - dest.y) ** 2 + (origin.z - dest.z) ** 2
        if d2 > self.radius * self.radius:  # EuclideanGameEventListenerRegistry#getPostableListenerPosition
            return
        state = world.get(dest)
        if origin == dest and event in ("block_destroy", "block_place"):  # the sensor's own block
            return
        if not SculkSensorBlock.can_activate(state):  # SculkSensorBlock#canActivate
            return
        if self.radius == CALIBRATED_RADIUS:
            back = Direction.from_name(state.get("facing", "north")).opposite
            wanted = world.get_signal(dest.offset(back), back)
            if wanted != 0 and frequency != wanted:
                return
        if is_occluded(world, origin, dest):
            return
        distance = f32(math.sqrt(d2))
        self._add_candidate((frequency, distance, origin), world.game_time)

    def _add_candidate(self, vib: tuple[int, float, Pos], tick: int) -> None:
        """VibrationSelector#addCandidate"""
        if self.candidate is not None:
            if tick != self.candidate_tick:
                return
            frequency, distance, _ = vib
            if not (distance < self.candidate[1] or (distance == self.candidate[1] and frequency > self.candidate[0])):
                return
        self.candidate = vib
        self.candidate_tick = tick

    # --- VibrationSystem.Ticker#tick -----------------------------------------------------------------
    def tick(self, world: World) -> None:
        if self.current is None and self.candidate is not None and self.candidate_tick < world.game_time:
            self.current = self.candidate
            self.travel_time = math.floor(self.current[1])  # User#calculateTravelTimeInTicks
            self.candidate = None
        if self.current is not None:
            self.travel_time = max(0, self.travel_time - 1)
            if self.travel_time <= 0:
                self._receive(world)

    def _receive(self, world: World) -> None:
        frequency, _, origin = self.current
        distance = distance_between(origin, self.pos)
        state = world.get(self.pos)
        block = world.block(state)
        if isinstance(block, SculkSensorBlock) and block.can_activate(state):
            self.last_vibration_frequency = frequency
            power = redstone_strength_for_distance(distance, self.radius)
            block.activate(world, self.pos, state, power, frequency)
        self.current = None

    def is_idle(self) -> bool:
        """Not part of the game: no vibration on its way and none waiting to be selected."""
        return self.current is None and self.candidate is None


class SculkSensorBlock(Block):
    active_ticks = 30
    radius = SENSOR_RADIUS

    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return state.get_int("power")

    def get_direct_signal(self, world, pos, state, direction):
        return self.get_signal(world, pos, state, direction) if direction is Direction.UP else 0

    def has_analog_output_signal(self, state):
        return True

    def get_analog_output_signal(self, world, pos, state, direction):
        be = world.get_block_entity(pos)
        if isinstance(be, SculkSensorBlockEntity) and state.get("sculk_sensor_phase") == "active":
            return be.last_vibration_frequency
        return 0

    def has_block_entity(self, state):
        return True

    def new_block_entity(self, pos, state):
        return SculkSensorBlockEntity(pos, self.radius)

    @staticmethod
    def can_activate(state: BlockState) -> bool:
        return state.get("sculk_sensor_phase", "inactive") == "inactive"

    def on_place(self, world, pos, state, old, moved_by_piston):
        if state.name != old.name and state.get_int("power") > 0 and not world.has_scheduled_tick(pos, self):
            world.set_block(pos, state.with_(power=0), 18)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if state.get("sculk_sensor_phase") == "active":
            self._update_neighbours(world, pos)

    def _update_neighbours(self, world: World, pos: Pos) -> None:
        world.update_neighbors_at(pos, self)
        world.update_neighbors_at(pos.offset(Direction.DOWN), self)

    def tick(self, world, pos, state):
        phase = state.get("sculk_sensor_phase", "inactive")
        if phase != "active":
            if phase == "cooldown":
                world.set_block(pos, state.with_(sculk_sensor_phase="inactive"))  # setBlockAndUpdate
        else:
            self.deactivate(world, pos, state)

    def deactivate(self, world: World, pos: Pos, state: BlockState) -> None:
        world.set_block(pos, state.with_(sculk_sensor_phase="cooldown", power=0))
        world.schedule_tick(pos, self, COOLDOWN_TICKS)
        self._update_neighbours(world, pos)

    def activate(self, world: World, pos: Pos, state: BlockState, power: int, frequency: int) -> None:
        world.set_block(pos, state.with_(sculk_sensor_phase="active", power=power))
        world.schedule_tick(pos, self, self.active_ticks)
        self._update_neighbours(world, pos)
        # tryResonateVibration: amethyst blocks next to the sensor repeat the vibration
        for d in _ALL_DIRECTIONS:
            rel = pos.offset(d)
            rel_state = world.get(rel)
            if rel_state.name in RESONATORS:
                world.game_event(f"resonate_{frequency}", rel, rel_state)


class CalibratedSculkSensorBlock(SculkSensorBlock):
    active_ticks = 10
    radius = CALIBRATED_RADIUS

    def get_signal(self, world, pos, state, direction):
        # CalibratedSculkSensorBlock#getSignal: no output towards the input side
        facing = Direction.from_name(state.get("facing", "north"))
        return self.own_signal(world, pos, state) if direction is not facing else 0


REGISTRY.register(SculkSensorBlock(), "sculk_sensor")
REGISTRY.register(CalibratedSculkSensorBlock(), "calibrated_sculk_sensor")
