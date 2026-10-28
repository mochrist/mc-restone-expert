"""Find the inputs and outputs of a circuit.

Inputs are blocks a player operates (levers, buttons, pressure plates). Outputs are blocks that act on
the world (lamps, pistons, droppers, doors, ...) plus diodes, torches and observers whose output points
out of the schematic. Both lists can be overridden by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import BlockState, Direction, Grid, Pos

INPUT_BLOCKS = ("lever",)
INPUT_SUFFIXES = ("_button", "_pressure_plate")
OUTPUT_BLOCKS = {
    "redstone_lamp", "piston", "sticky_piston", "dropper", "dispenser", "note_block", "hopper", "crafter",
    "tnt", "powered_rail", "activator_rail", "bell",
}
OUTPUT_SUFFIXES = ("_door", "_trapdoor", "_fence_gate", "copper_bulb")
_FACING_IS_INPUT = {"repeater", "comparator", "observer"}


@dataclass(frozen=True)
class Port:
    name: str
    pos: Pos
    kind: str  # "lever", "button", "plate", or the output block id
    state: BlockState

    def __str__(self) -> str:
        return f"{self.name} ({self.kind} {self.pos})"


def input_kind(state: BlockState) -> str | None:
    if state.id in INPUT_BLOCKS:
        return "lever"
    if state.id.endswith("_button"):
        return "button"
    if state.id.endswith("_pressure_plate"):
        return "plate"
    return None


def _output_leaves_grid(grid: Grid, pos: Pos, state: BlockState) -> bool:
    facing = state.get("facing")
    if facing is None:
        return False
    d = Direction.from_name(facing)
    out = d.opposite if state.id in _FACING_IS_INPUT else d
    target = pos.offset(out)
    return not grid.in_bounds(target)


def is_output(grid: Grid, pos: Pos, state: BlockState) -> bool:
    if state.id in OUTPUT_BLOCKS or state.id.endswith(OUTPUT_SUFFIXES):
        return True
    if state.id in ("repeater", "comparator", "observer", "redstone_wall_torch"):
        return _output_leaves_grid(grid, pos, state)
    return False


def find_ports(grid: Grid) -> tuple[list[Port], list[Port]]:
    inputs: list[Port] = []
    outputs: list[Port] = []
    counters: dict[str, int] = {}

    def name_for(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}{counters[prefix]}"

    for pos, state in grid.items():
        kind = input_kind(state)
        if kind:
            inputs.append(Port(name_for("in"), pos, kind, state))
        elif is_output(grid, pos, state):
            outputs.append(Port(name_for("out"), pos, state.id, state))
    return inputs, outputs
