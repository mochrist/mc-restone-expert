"""A candidate circuit: a grid plus the positions of its inputs and outputs.

Inputs are levers (stored off). Outputs are blocks whose on/off state is read (usually redstone lamps).
The order of `inputs` and `outputs` matches the names in the specification (a, b, c, ... / y, z, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Grid, Pos


@dataclass
class Candidate:
    name: str
    grid: Grid
    inputs: list[Pos]
    outputs: list[Pos]
    description: str = ""  # German, shown to the user
    origin: str = ""  # e.g. "template:and-torch", "search"
    tags: set[str] = field(default_factory=set)  # e.g. {"qc"} when the design relies on quasi-connectivity

    @property
    def size(self) -> tuple[int, int, int]:
        return tuple(self.grid.size)

    @property
    def volume(self) -> int:
        x, y, z = self.grid.size
        return x * y * z

    @property
    def block_count(self) -> int:
        return len(self.grid)
