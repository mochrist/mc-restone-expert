"""Redstone-controlled outputs and simple sources: copper bulb, note block, target block, doors, trapdoors,
fence gates, rails (powered, activator, plain) and the lectern.

References (26.3): CopperBulbBlock, NoteBlock, TargetBlock, DoorBlock, TrapDoorBlock, FenceGateBlock,
BaseRailBlock, PoweredRailBlock, RailBlock, RailState, LecternBlock, LecternBlockEntity.

Not modeled here: sounds/particles, oxidation (random ticks), projectiles hitting a target block, minecarts
(detector rail), the lectern menu (page turning), daylight detector, pressure plates, sculk.
"""

from __future__ import annotations

import math

from ...model import AIR, BlockState, Direction, Pos
from .. import blockdata
from ..block import REGISTRY, Block
from ..constants import UPDATE_ALL, UPDATE_CLIENTS, UPDATE_IMMEDIATE, UPDATE_KNOWN_SHAPE
from ..world import World

D = Direction
_ALL_NAMES = tuple(n.split(":", 1)[1] for n in blockdata._table())


def _names(predicate) -> list[str]:
    return [n for n in _ALL_NAMES if predicate(n)]


# ---------------------------------------------------------------------- copper bulb
class CopperBulbBlock(Block):
    """CopperBulbBlock (all oxidation and waxed variants behave identically for redstone)."""

    def on_place(self, world, pos, state, old, moved_by_piston):
        if old.name != state.name:
            self.check_and_flip(world, pos, state)

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        self.check_and_flip(world, pos, state)

    def check_and_flip(self, world: World, pos: Pos, state: BlockState) -> None:
        signal = world.has_neighbor_signal(pos)
        if signal != state.get_bool("powered"):
            new = state
            if not state.get_bool("powered"):
                new = new.with_(lit=not state.get_bool("lit"))
            world.set_block(pos, new.with_(powered=signal), UPDATE_ALL)

    def has_analog_output_signal(self, state):
        return True

    def get_analog_output_signal(self, world, pos, state, direction):
        return 15 if world.get(pos).get_bool("lit") else 0


# ---------------------------------------------------------------------- note block
_MOB_HEADS = {"zombie": "zombie", "skeleton": "skeleton", "creeper": "creeper", "dragon": "dragon",
              "wither_skeleton": "wither_skeleton", "piglin": "piglin", "player": "custom_head"}


def _instrument(state: BlockState) -> str:
    """BlockState#instrument for the blocks a note block typically sits on.

    ASSUMPTION: name heuristic. The game reads BlockBehaviour.Properties#instrument, which is not in
    blocks_26.3.json yet; unknown blocks give harp.
    """
    n = state.id
    for head, inst in _MOB_HEADS.items():
        if n in (f"{head}_head", f"{head}_wall_head", f"{head}_skull", f"{head}_wall_skull"):
            return inst
    table = (
        (("wool", "carpet"), "guitar"), (("glass", "sea_lantern", "beacon"), "hat"),
        (("concrete_powder", "sand", "gravel"), "snare"), (("clay",), "flute"), (("gold_block",), "bell"),
        (("packed_ice",), "chime"), (("bone_block",), "xylophone"), (("iron_block",), "iron_xylophone"),
        (("soul_sand",), "cow_bell"), (("pumpkin",), "didgeridoo"), (("emerald_block",), "bit"),
        (("hay_block",), "banjo"), (("glowstone",), "pling"),
    )
    for keys, inst in table:
        if any(k in n for k in keys) and "sandstone" not in n:
            return inst
    if "copper" in n and not any(k in n for k in ("bulb", "door", "grate", "bars", "chain", "lantern")):
        for stage in ("exposed", "weathered", "oxidized"):
            if stage in n:
                return f"trumpet_{stage}"
        return "trumpet"
    if any(k in n for k in ("planks", "_log", "_wood", "stem", "hyphae", "note_block", "bookshelf", "chest",
                            "barrel", "crafting_table", "lectern", "fence", "mushroom_block", "bamboo_block")):
        return "bass"
    if blockdata.is_conductor(state) and any(k in n for k in ("stone", "cobble", "deepslate", "ore", "bricks",
                                                             "obsidian", "netherrack", "terracotta", "concrete",
                                                             "quartz", "basalt", "blackstone", "tuff", "prismarine",
                                                             "end_stone", "purpur", "andesite", "diorite",
                                                             "granite", "calcite", "dripstone", "observer",
                                                             "dispenser", "dropper", "furnace", "bedrock")):
        return "basedrum"
    return "harp"


_WORKS_ABOVE = set(_MOB_HEADS.values())


class NoteBlock(Block):
    def _set_instrument(self, world: World, pos: Pos, state: BlockState) -> BlockState:
        above = _instrument(world.get(pos.offset(D.UP)))
        if above in _WORKS_ABOVE:
            return state.with_(instrument=above)
        below = _instrument(world.get(pos.offset(D.DOWN)))
        return state.with_(instrument="harp" if below in _WORKS_ABOVE else below)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction in (D.UP, D.DOWN):
            return self._set_instrument(world, pos, state)
        return state

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        signal = world.has_neighbor_signal(pos)
        if signal != state.get_bool("powered"):
            if signal:
                self.play_note(world, pos, state)
            world.set_block(pos, state.with_(powered=signal), UPDATE_ALL)

    def play_note(self, world: World, pos: Pos, state: BlockState) -> None:
        if state.get("instrument") in _WORKS_ABOVE or world.get(pos.offset(D.UP)).is_air:
            world.block_event(pos, self, 0, 0)

    def use_without_item(self, world, pos, state):
        state = state.with_(note=(state.get_int("note") + 1) % 25)
        world.set_block(pos, state, UPDATE_ALL)
        self.play_note(world, pos, state)
        return True

    def trigger_event(self, world, pos, state, a, b):
        return True  # sound and particles only


# ---------------------------------------------------------------------- target block
class TargetBlock(Block):
    """TargetBlock: weak signal ``power``. Projectile hits are not modeled; a target placed with power > 0
    and no pending tick is reset to 0 in onPlace (flags 18, no updates)."""

    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return state.get_int("power")

    def tick(self, world, pos, state):
        if state.get_int("power") != 0:
            world.set_block(pos, state.with_(power=0), UPDATE_ALL)

    def on_place(self, world, pos, state, old, moved_by_piston):
        if state.name != old.name and state.get_int("power") > 0 and not world.has_scheduled_tick(pos, self):
            world.set_block(pos, state.with_(power=0), UPDATE_CLIENTS | UPDATE_KNOWN_SHAPE)


# ---------------------------------------------------------------------- doors, trapdoors, fence gates
class DoorBlock(Block):
    def __init__(self, open_by_hand: bool) -> None:
        super().__init__()
        self.open_by_hand = open_by_hand

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        other = D.UP if state.get("half") == "lower" else D.DOWN
        signal = world.has_neighbor_signal(pos) or world.has_neighbor_signal(pos.offset(other))
        if source is not self and signal != state.get_bool("powered"):
            world.set_block(pos, state.with_(powered=signal, open=signal), UPDATE_CLIENTS)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        half = state.get("half")
        if direction not in (D.UP, D.DOWN) or (half == "lower") != (direction is D.UP):
            if half == "lower" and direction is D.DOWN and not self.can_survive(world, pos, state):
                return AIR
            return state
        if isinstance(world.block(neighbor_state), DoorBlock) and neighbor_state.get("half") != half:
            return neighbor_state.with_(half=half)
        return AIR

    def can_survive(self, world, pos, state):
        below = pos.offset(D.DOWN)
        if state.get("half") == "lower":
            return world.is_face_sturdy(below, D.UP)
        return world.get(below).name == state.name

    def use_without_item(self, world, pos, state):
        if not self.open_by_hand:
            return False
        world.set_block(pos, state.with_(open=not state.get_bool("open")), UPDATE_CLIENTS | UPDATE_IMMEDIATE)
        return True


class TrapDoorBlock(Block):
    def __init__(self, open_by_hand: bool) -> None:
        super().__init__()
        self.open_by_hand = open_by_hand

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        signal = world.has_neighbor_signal(pos)
        if signal != state.get_bool("powered"):
            if state.get_bool("open") != signal:
                state = state.with_(open=signal)
            world.set_block(pos, state.with_(powered=signal), UPDATE_CLIENTS)

    def use_without_item(self, world, pos, state):
        if not self.open_by_hand:
            return False
        world.set_block(pos, state.with_(open=not state.get_bool("open")), UPDATE_CLIENTS)
        return True


# Direction the oracle's FakePlayer looks at (yRot 0 = south), used by FenceGateBlock#useWithoutItem.
PLAYER_DIRECTION = D.SOUTH


def _is_wall(state: BlockState) -> bool:
    """#walls block tag (approximation by name)."""
    return state.id.endswith("_wall") and "wall_" not in state.id


class FenceGateBlock(Block):
    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        signal = world.has_neighbor_signal(pos)
        if state.get_bool("powered") != signal:
            world.set_block(pos, state.with_(powered=signal, open=signal), UPDATE_CLIENTS)

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        facing = D.from_name(state.get("facing", "north"))
        if direction.is_horizontal and facing.clockwise() in (direction, direction.opposite):
            in_wall = _is_wall(neighbor_state) or _is_wall(world.get(pos.offset(direction.opposite)))
            return state.with_(in_wall=in_wall)
        return state

    def use_without_item(self, world, pos, state):
        if state.get_bool("open"):
            state = state.with_(open=False)
        else:
            if D.from_name(state.get("facing", "north")) is PLAYER_DIRECTION.opposite:
                state = state.with_(facing=PLAYER_DIRECTION.label)
            state = state.with_(open=True)
        world.set_block(pos, state, UPDATE_CLIENTS | UPDATE_IMMEDIATE)
        return True


# ---------------------------------------------------------------------- rails
_RAILS = ("rail", "powered_rail", "detector_rail", "activator_rail")


def is_rail(state: BlockState) -> bool:
    """BaseRailBlock#isRail (#rails tag)."""
    return state.id in _RAILS


def _can_support_rigid(world: World, pos: Pos) -> bool:
    """Block#canSupportRigidBlock"""
    return world.is_face_sturdy(pos, D.UP, "rigid")


def _is_slope(shape: str) -> bool:
    return shape.startswith("ascending_")


def _straight(state: BlockState) -> bool:
    return state.id != "rail"


class RailState:
    """net.minecraft.world.level.block.RailState"""

    def __init__(self, world: World, pos: Pos, state: BlockState) -> None:
        self.world, self.pos, self.state = world, pos, state
        self.is_straight = _straight(state)
        self.connections: list[Pos] = []
        self._update_connections(state.get("shape", "north_south"))

    def _update_connections(self, shape: str) -> None:
        p = self.pos
        n, s, w, e = p.offset(D.NORTH), p.offset(D.SOUTH), p.offset(D.WEST), p.offset(D.EAST)
        up = D.UP
        self.connections = {
            "north_south": [n, s], "east_west": [w, e],
            "ascending_east": [w, e.offset(up)], "ascending_west": [w.offset(up), e],
            "ascending_north": [n.offset(up), s], "ascending_south": [n, s.offset(up)],
            "south_east": [e, s], "south_west": [w, s], "north_west": [w, n], "north_east": [e, n],
        }[shape]

    def _remove_soft_connections(self) -> None:
        i = 0
        while i < len(self.connections):
            rail = self._get_rail(self.connections[i])
            if rail is not None and rail._connects_to(self):
                self.connections[i] = rail.pos
                i += 1
            else:
                del self.connections[i]

    def _has_rail(self, pos: Pos) -> bool:
        return any(is_rail(self.world.get(p)) for p in (pos, pos.offset(D.UP), pos.offset(D.DOWN)))

    def _get_rail(self, pos: Pos) -> RailState | None:
        for p in (pos, pos.offset(D.UP), pos.offset(D.DOWN)):
            st = self.world.get(p)
            if is_rail(st):
                return RailState(self.world, p, st)
        return None

    def _connects_to(self, rail: RailState) -> bool:
        return self._has_connection(rail.pos)

    def _has_connection(self, rail_pos: Pos) -> bool:
        return any(p.x == rail_pos.x and p.z == rail_pos.z for p in self.connections)

    def count_potential_connections(self) -> int:
        return sum(1 for d in (D.NORTH, D.EAST, D.SOUTH, D.WEST) if self._has_rail(self.pos.offset(d)))

    def _can_connect_to(self, rail: RailState) -> bool:
        return self._connects_to(rail) or len(self.connections) != 2

    def _slope(self, shape: str | None) -> str | None:
        p, w = self.pos, self.world
        if shape == "north_south":
            if is_rail(w.get(p.offset(D.NORTH).offset(D.UP))):
                shape = "ascending_north"
            if is_rail(w.get(p.offset(D.SOUTH).offset(D.UP))):
                shape = "ascending_south"
        if shape == "east_west":
            if is_rail(w.get(p.offset(D.EAST).offset(D.UP))):
                shape = "ascending_east"
            if is_rail(w.get(p.offset(D.WEST).offset(D.UP))):
                shape = "ascending_west"
        return shape

    def _connect_to(self, rail: RailState) -> None:
        self.connections.append(rail.pos)
        p = self.pos
        n = self._has_connection(p.offset(D.NORTH))
        s = self._has_connection(p.offset(D.SOUTH))
        w = self._has_connection(p.offset(D.WEST))
        e = self._has_connection(p.offset(D.EAST))
        shape = None
        if n or s:
            shape = "north_south"
        if w or e:
            shape = "east_west"
        if not self.is_straight:
            if s and e and not n and not w:
                shape = "south_east"
            if s and w and not n and not e:
                shape = "south_west"
            if n and w and not s and not e:
                shape = "north_west"
            if n and e and not s and not w:
                shape = "north_east"
        shape = self._slope(shape) or "north_south"
        self.state = self.state.with_(shape=shape)
        self.world.set_block(self.pos, self.state, UPDATE_ALL)

    def _has_neighbor_rail(self, pos: Pos) -> bool:
        neighbor = self._get_rail(pos)
        if neighbor is None:
            return False
        neighbor._remove_soft_connections()
        return neighbor._can_connect_to(self)

    def place(self, has_signal: bool, first: bool, default_shape: str) -> RailState:
        p = self.pos
        n = self._has_neighbor_rail(p.offset(D.NORTH))
        s = self._has_neighbor_rail(p.offset(D.SOUTH))
        w = self._has_neighbor_rail(p.offset(D.WEST))
        e = self._has_neighbor_rail(p.offset(D.EAST))
        shape = None
        ns, we = n or s, w or e
        if ns and not we:
            shape = "north_south"
        if we and not ns:
            shape = "east_west"
        se, sw, ne, nw = s and e, s and w, n and e, n and w
        if not self.is_straight:
            if se and not n and not w:
                shape = "south_east"
            if sw and not n and not e:
                shape = "south_west"
            if nw and not s and not e:
                shape = "north_west"
            if ne and not s and not w:
                shape = "north_east"
        if shape is None:
            if ns and we:
                shape = default_shape
            elif ns:
                shape = "north_south"
            elif we:
                shape = "east_west"
            if not self.is_straight:
                order = ((se, "south_east"), (sw, "south_west"), (ne, "north_east"), (nw, "north_west")) \
                    if has_signal else ((nw, "north_west"), (ne, "north_east"), (sw, "south_west"), (se, "south_east"))
                for cond, sh in order:
                    if cond:
                        shape = sh
        shape = self._slope(shape) or default_shape
        self._update_connections(shape)
        self.state = self.state.with_(shape=shape)
        if first or self.world.get(p) != self.state:
            self.world.set_block(p, self.state, UPDATE_ALL)
            for c in list(self.connections):
                neighbor = self._get_rail(c)
                if neighbor is not None:
                    neighbor._remove_soft_connections()
                    if neighbor._can_connect_to(self):
                        neighbor._connect_to(self)
        return self


class BaseRailBlock(Block):
    is_straight = True

    def can_survive(self, world, pos, state):
        return _can_support_rigid(world, pos.offset(D.DOWN))

    def on_place(self, world, pos, state, old, moved_by_piston):
        if old.name != state.name:
            self.update_state_on_place(world, pos, state, moved_by_piston)

    def update_state_on_place(self, world: World, pos: Pos, state: BlockState, moved: bool) -> BlockState:
        """BaseRailBlock#updateState(state, level, pos, movedByPiston)"""
        state = self.update_dir(world, pos, state, True)
        if self.is_straight:
            world.neighbor_changed_with_state(state, pos, self, moved)
        return state

    def update_dir(self, world: World, pos: Pos, state: BlockState, first: bool) -> BlockState:
        return RailState(world, pos, state).place(world.has_neighbor_signal(pos), first, state.get("shape")).state

    def neighbor_changed(self, world, pos, state, source, moved_by_piston):
        if world.get(pos).name != self.name:
            return
        if self._should_be_removed(world, pos, state.get("shape")):
            world.remove_block(pos, moved_by_piston)
        else:
            self.update_state(world, pos, state, source)

    @staticmethod
    def _should_be_removed(world: World, pos: Pos, shape: str) -> bool:
        if not _can_support_rigid(world, pos.offset(D.DOWN)):
            return True
        if _is_slope(shape):
            return not _can_support_rigid(world, pos.offset(D.from_name(shape.removeprefix("ascending_"))))
        return False

    def update_state(self, world: World, pos: Pos, state: BlockState, source: Block) -> None:
        pass

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if not moved_by_piston:
            if _is_slope(state.get("shape", "")):
                world.update_neighbors_at(pos.offset(D.UP), self)
            if self.is_straight:
                world.update_neighbors_at(pos, self)
                world.update_neighbors_at(pos.offset(D.DOWN), self)


class RailBlock(BaseRailBlock):
    is_straight = False

    def update_state(self, world, pos, state, source):
        if source.is_signal_source(BlockState.of(source.name)) and \
                RailState(world, pos, state).count_potential_connections() == 3:
            self.update_dir(world, pos, state, False)


class PoweredRailBlock(BaseRailBlock):
    """Powered rail and activator rail (both PoweredRailBlock in 26.3)."""

    MAX_SEARCH_DEPTH = 8

    def find_powered_rail_signal(self, world: World, pos: Pos, state: BlockState, forward: bool, depth: int) -> bool:
        if depth >= self.MAX_SEARCH_DEPTH:
            return False
        x, y, z = pos
        check_below = True
        shape = state.get("shape")
        if shape == "north_south":
            z += 1 if forward else -1
        elif shape == "east_west":
            x += -1 if forward else 1
        elif shape == "ascending_east":
            if forward:
                x -= 1
            else:
                x, y, check_below = x + 1, y + 1, False
            shape = "east_west"
        elif shape == "ascending_west":
            if forward:
                x, y, check_below = x - 1, y + 1, False
            else:
                x += 1
            shape = "east_west"
        elif shape == "ascending_north":
            if forward:
                z += 1
            else:
                z, y, check_below = z - 1, y + 1, False
            shape = "north_south"
        elif shape == "ascending_south":
            if forward:
                z, y, check_below = z + 1, y + 1, False
            else:
                z -= 1
            shape = "north_south"
        return self._is_same_rail_with_power(world, Pos(x, y, z), forward, depth, shape) or (
            check_below and self._is_same_rail_with_power(world, Pos(x, y - 1, z), forward, depth, shape))

    def _is_same_rail_with_power(self, world: World, pos: Pos, forward: bool, depth: int, direction: str) -> bool:
        state = world.get(pos)
        if state.name != self.name:
            return False
        mine = state.get("shape")
        if direction == "east_west" and mine in ("north_south", "ascending_north", "ascending_south"):
            return False
        if direction == "north_south" and mine in ("east_west", "ascending_east", "ascending_west"):
            return False
        if not state.get_bool("powered"):
            return False
        return world.has_neighbor_signal(pos) or self.find_powered_rail_signal(world, pos, state, forward, depth + 1)

    def update_state(self, world, pos, state, source):
        powered = state.get_bool("powered")
        should = (world.has_neighbor_signal(pos) or self.find_powered_rail_signal(world, pos, state, True, 0)
                  or self.find_powered_rail_signal(world, pos, state, False, 0))
        if should != powered:
            world.set_block(pos, state.with_(powered=should), UPDATE_ALL)
            world.update_neighbors_at(pos.offset(D.DOWN), self)
            if _is_slope(state.get("shape", "")):
                world.update_neighbors_at(pos.offset(D.UP), self)


# ---------------------------------------------------------------------- lectern
class CakeBlock(Block):
    """CakeBlock: a comparator reads (7 - bites) * 2; the cake drops when the block below is not solid.
    Eating (use) is not modeled: whether the oracle's player may eat is not checked (ASSUMPTION)."""

    def has_analog_output_signal(self, state):
        return True

    def get_analog_output_signal(self, world, pos, state, direction):
        return (7 - state.get_int("bites", 0)) * 2

    def update_shape(self, world, pos, state, direction, neighbor_pos, neighbor_state):
        if direction == D.DOWN and not blockdata.is_solid(world.get(pos.offset(D.DOWN))):
            return AIR
        return state


class LecternBlockEntity:
    ticks = False

    def __init__(self) -> None:
        self.has_book = False
        self.page = 0
        self.page_count = 0
        self.removed = False

    def load(self, data: dict) -> None:
        book = data.get("Book")
        self.has_book = bool(book) and str(book.get("id", "minecraft:air")) != "minecraft:air"
        components = (book or {}).get("components", {}) or {}
        content = components.get("minecraft:written_book_content")
        if content is None:
            content = components.get("minecraft:writable_book_content")
        self.page_count = len(content.get("pages", [])) if content else 0
        # Mth.clamp(int): min(max(value, min), max)
        self.page = min(max(int(data.get("Page", 0)), 0), self.page_count - 1)

    def redstone_signal(self) -> int:
        """LecternBlockEntity#getRedstoneSignal (float arithmetic as in the game)."""
        progress = self.page / (self.page_count - 1.0) if self.page_count > 1 else 1.0
        return math.floor(progress * 14.0) + (1 if self.has_book else 0)


class LecternBlock(Block):
    """LecternBlock: comparator output from the book page; the 2-gt pulse on page turns needs the menu
    and is not triggered here, but a lectern placed powered turns off on its scheduled tick."""

    def is_signal_source(self, state):
        return True

    def own_signal(self, world, pos, state):
        return 15 if state.get_bool("powered") else 0

    def get_direct_signal(self, world, pos, state, direction):
        return 15 if direction is D.UP and state.get_bool("powered") else 0

    def has_block_entity(self, state):
        return True

    def new_block_entity(self, pos, state):
        return LecternBlockEntity()

    def has_analog_output_signal(self, state):
        return True

    def get_analog_output_signal(self, world, pos, state, direction):
        be = world.get_block_entity(pos)
        if state.get_bool("has_book") and isinstance(be, LecternBlockEntity):
            return be.redstone_signal()
        return 0

    def _change_powered(self, world: World, pos: Pos, state: BlockState, powered: bool) -> None:
        world.set_block(pos, state.with_(powered=powered), UPDATE_ALL)
        world.update_neighbors_at(pos.offset(D.DOWN), self)

    def tick(self, world, pos, state):
        self._change_powered(world, pos, state, False)

    def affect_neighbors_after_removal(self, world, pos, state, moved_by_piston):
        if state.get_bool("powered"):
            world.update_neighbors_at(pos.offset(D.DOWN), self)


# ---------------------------------------------------------------------- registration
# One behaviour object per block type (ticks, "same block" checks and rail chains are per type).
for _n in _names(lambda n: n.endswith("copper_bulb")):
    REGISTRY.register(CopperBulbBlock(), _n)
REGISTRY.register(NoteBlock(), "note_block")
REGISTRY.register(TargetBlock(), "target")
# BlockSetType#canOpenByHand is false only for iron.
for _n in _names(lambda n: n.endswith("_door") and not n.endswith("_trapdoor")):
    REGISTRY.register(DoorBlock(open_by_hand=_n != "iron_door"), _n)
for _n in _names(lambda n: n.endswith("_trapdoor")):
    REGISTRY.register(TrapDoorBlock(open_by_hand=_n != "iron_trapdoor"), _n)
for _n in _names(lambda n: n.endswith("_fence_gate")):
    REGISTRY.register(FenceGateBlock(), _n)
REGISTRY.register(RailBlock(), "rail")
REGISTRY.register(PoweredRailBlock(), "powered_rail")
REGISTRY.register(PoweredRailBlock(), "activator_rail")
REGISTRY.register(LecternBlock(), "lectern")
REGISTRY.register(CakeBlock(), "cake")
