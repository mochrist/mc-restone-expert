"""Run a scenario in the simulator and produce a trace (protocol: docs/scenario-format.md, section 2)."""

from __future__ import annotations

from ..model import BlockState, Pos
from ..verify.scenario import Scenario
from ..verify.trace import Trace
from . import blocks  # noqa: F401  (registers block behaviours)
from .constants import UPDATE_ALL
from .world import World


def probe_value(world: World, pos: Pos) -> str:
    state = world.get(pos)
    value = str(state)
    if state.id == "comparator":
        be = world.block_entities.get(pos)
        value += f"|output={be.output_signal if be is not None else 0}"
    return value


def apply_input(world: World, action: str, pos: Pos, state: BlockState | None) -> None:
    if action == "use":
        current = world.get(pos)
        world.block(current).use_without_item(world, pos, current)
    elif action == "setblock":
        assert state is not None
        world.set_block(pos, state, UPDATE_ALL)
    else:
        raise ValueError(f"unknown action {action!r}")


def run(scenario: Scenario) -> tuple[Trace, World]:
    world = World.from_grid(scenario.grid)
    trace = Trace(scenario.name, "sim", scenario.ticks, dict(scenario.probes))
    for t in range(scenario.ticks + 1):
        for inp in scenario.inputs_at(t):
            apply_input(world, inp.action, inp.pos, inp.state)
        for name, pos in scenario.probes.items():
            trace.record(name, t, probe_value(world, pos))
        if t < scenario.ticks:
            world.tick()
    return trace, world


def simulate(scenario: Scenario) -> Trace:
    return run(scenario)[0]
