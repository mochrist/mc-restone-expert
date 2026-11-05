"""Run controlled experiments on a circuit in the simulator and record every block change.

Every statement the analysis makes is derived from such recordings, never from the layout alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import BlockState, Grid, Pos
from ..sim.constants import UPDATE_ALL
from ..sim.runner import ORACLE_ORIGIN, apply_input, probe_value
from ..sim.world import World
from ..verify.trace import _is_on

Action = tuple[int, Pos, str]  # (tick, position relative to the grid, "use")


@dataclass
class Change:
    tick: int
    pos: Pos
    old: str
    new: str


@dataclass
class Recording:
    ticks: int
    changes: list[Change] = field(default_factory=list)
    # position -> list of (tick, value) change points, first at tick 0
    series: dict[Pos, list[tuple[int, str]]] = field(default_factory=dict)
    settled_at: int | None = None  # first tick after the last action from which the world stayed idle
    warnings: list[str] = field(default_factory=list)

    def value_at(self, pos: Pos, tick: int) -> str:
        current = self.series[pos][0][1]
        for t, v in self.series[pos]:
            if t > tick:
                break
            current = v
        return current

    def on_at(self, pos: Pos, tick: int) -> bool:
        return is_on(self.value_at(pos, tick))

    def on_intervals(self, pos: Pos) -> list[tuple[int, int | None]]:
        """[start, end) tick intervals in which the block is on; end None = still on at the end."""
        intervals: list[tuple[int, int | None]] = []
        start = None
        for t, v in self.series[pos]:
            if is_on(v) and start is None:
                start = t
            elif not is_on(v) and start is not None:
                intervals.append((start, t))
                start = None
        if start is not None:
            intervals.append((start, None))
        return intervals

    def first_change_after(self, pos: Pos, tick: int) -> int | None:
        for t, _ in self.series.get(pos, [])[1:]:
            if t >= tick:
                return t
        return None


def is_on(value: str) -> bool:
    return _is_on(value, None)


def _ticker_busy(wrapper) -> bool:
    ticker = getattr(wrapper, "ticker", wrapper)
    if ticker is None or getattr(ticker, "removed", False):
        return False
    is_idle = getattr(ticker, "is_idle", None)
    return not (is_idle and is_idle())


def world_is_idle(world: World) -> bool:
    """No scheduled ticks, no block events and no block entity with pending work.

    Hoppers tick every game tick; one without cooldown has found nothing to move and only changes when
    something else in the world changes (there are no item entities in the simulator)."""
    return not world._ticks and not world.block_events and not any(
        _ticker_busy(w) for w in world._be_tickers + world._pending_be_tickers)


class Circuit:
    """A schematic placed in a fresh simulator world at the oracle origin."""

    def __init__(self, grid: Grid, origin: Pos = ORACLE_ORIGIN) -> None:
        self.grid = grid
        self.origin = origin
        self.positions = [p for p, _ in grid.items()]

    def new_world(self, kick: bool = False) -> World:
        world = World()
        world.place_grid(self.grid, self.origin)
        if kick:
            # Give every block one neighbour update and its neighbours one shape update from it, as if each
            # block had just been placed. Starts circuits (e.g. clocks) that a schematic stores in a frozen
            # state; observers only react to shape updates.
            for p in self.positions:
                state = world.get(p + self.origin)
                world.neighbor_changed_with_state(state, p + self.origin, world.block(state), False)
            for p in self.positions:
                world.update_neighbour_shapes(p + self.origin, world.get(p + self.origin), UPDATE_ALL)
        return world

    def run(self, actions: list[Action], max_ticks: int, kick: bool = False, quiet: int = 10,
            world: World | None = None) -> Recording:
        """Apply actions and simulate until the world has been idle for `quiet` ticks after the last action."""
        world = world or self.new_world(kick)
        rec = Recording(0, warnings=list(world.warnings))
        last_action = max((t for t, _, _ in actions), default=0)
        current = self._snapshot(world)
        rec.series = {p: [(0, v)] for p, v in current.items()}
        idle_since: int | None = None
        t = 0
        while True:
            for at, pos, action in actions:
                if at == t:
                    apply_input(world, action, pos + self.origin, None)
            snap = self._snapshot(world)
            for p in snap.keys() | current.keys():
                old, new = current.get(p, "minecraft:air"), snap.get(p, "minecraft:air")
                if old != new:
                    rec.changes.append(Change(t, p, old, new))
                    rec.series.setdefault(p, [(0, old)]).append((t, new))
            current = snap
            idle = world_is_idle(world)
            if t >= last_action and idle:
                idle_since = t if idle_since is None else idle_since
                if t - idle_since >= quiet:
                    rec.settled_at = idle_since
                    break
            else:
                idle_since = None
            if t >= max_ticks:
                break
            world.tick()
            t += 1
        rec.ticks = t
        return rec

    def _snapshot(self, world: World) -> dict[Pos, str]:
        """Probe values of all non-air blocks inside the schematic box plus a 1-block margin."""
        lo = self.origin - (1, 1, 1)
        hi = self.origin + tuple(self.grid.size)
        out = {}
        for p in world.blocks:
            if lo.x <= p.x <= hi.x and lo.y <= p.y <= hi.y and lo.z <= p.z <= hi.z:
                out[p - self.origin] = probe_value(world, p)
        return out

    def state(self, rec: Recording, pos: Pos, tick: int) -> BlockState:
        return BlockState.parse(rec.value_at(pos, tick).partition("|")[0])
