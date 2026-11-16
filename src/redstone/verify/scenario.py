"""Scenarios: a circuit, timed inputs and probes. See docs/scenario-format.md."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import nbtlib
import yaml

from .. import io
from ..io.nbtutil import to_nbt
from ..model import BlockState, Grid, Pos

FORMAT = 1
Action = Literal["use", "setblock", "step", "time"]
ACTIONS = ("use", "setblock", "step", "time")
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Input:
    tick: int
    pos: Pos
    action: Action
    state: BlockState | None = None
    # action "time": the new overworld clock time (like /time set; the position is ignored)
    time: int | None = None

    def to_json(self) -> dict:
        d: dict = {"tick": self.tick, "pos": list(self.pos), "action": self.action}
        if self.state is not None:
            d["state"] = str(self.state)
        if self.time is not None:
            d["time"] = self.time
        return d


@dataclass
class Scenario:
    name: str
    grid: Grid
    ticks: int
    inputs: list[Input] = field(default_factory=list)
    probes: dict[str, Pos] = field(default_factory=dict)
    description: str = ""
    # Game time at the start (simulator and oracle; see docs/scenario-format.md, "Game time")
    game_time: int = 0
    # Absolute position of the min corner (simulator and oracle); None = the oracle origin (0, 200, 0)
    origin: Pos | None = None

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ValueError(f"scenario name {self.name!r} must match [a-z0-9-]+")
        if self.ticks < 0:
            raise ValueError("ticks must be >= 0")
        for inp in self.inputs:
            if not 0 <= inp.tick <= self.ticks:
                raise ValueError(f"input at tick {inp.tick} outside 0..{self.ticks}")
            if not self.grid.in_bounds(inp.pos):
                raise ValueError(f"input position {inp.pos} outside the circuit")
            if inp.action == "setblock" and inp.state is None:
                raise ValueError("setblock needs a state")
            if inp.action not in ACTIONS:
                raise ValueError(f"unknown action {inp.action!r}")
            if inp.action == "time" and (inp.time is None or inp.time < 0):
                raise ValueError("time needs a value >= 0")
        for name, pos in self.probes.items():
            if not self.grid.in_bounds(pos):
                raise ValueError(f"probe {name} at {pos} outside the circuit")

    def inputs_at(self, tick: int) -> list[Input]:
        return [i for i in self.inputs if i.tick == tick]

    def compile(self) -> dict:
        """The JSON form consumed by the oracle."""
        return {
            "format": FORMAT,
            "name": self.name,
            "size": list(self.grid.size),
            "blocks": [{"pos": list(p), "state": str(s)} for p, s in self.grid.items()],
            "block_entities": [
                {"pos": list(p), "snbt": to_nbt(data).snbt()} for p, data in sorted(self.grid.block_entities.items())
            ],
            "ticks": self.ticks,
            "inputs": [i.to_json() for i in self.inputs],
            "probes": [{"name": n, "pos": list(p)} for n, p in self.probes.items()],
            "game_time": self.game_time,
            **({"origin": list(self.origin)} if self.origin is not None else {}),
        }


def _pos(value) -> Pos:
    if len(value) != 3:
        raise ValueError(f"position needs 3 coordinates, got {value!r}")
    return Pos(*(int(v) for v in value))


def from_dict(data: dict, base_dir: Path | None = None) -> Scenario:
    if ("schematic" in data) == ("build" in data):
        raise ValueError("scenario needs exactly one of 'schematic' or 'build'")
    if "schematic" in data:
        grid = io.load((base_dir or Path.cwd()) / data["schematic"])
    else:
        build = data["build"]
        grid = Grid(tuple(build["size"]))
        for entry in build.get("fill", []):
            *corners, state = entry
            lo = [min(a, b) for a, b in zip(corners[:3], corners[3:])]
            hi = [max(a, b) for a, b in zip(corners[:3], corners[3:])]
            parsed = BlockState.parse(state)
            for x in range(lo[0], hi[0] + 1):
                for y in range(lo[1], hi[1] + 1):
                    for z in range(lo[2], hi[2] + 1):
                        grid.set((x, y, z), parsed)
        for entry in build.get("blocks", []):
            *xyz, state = entry
            grid.set(_pos(xyz), BlockState.parse(state))
        for entry in build.get("block_entities", []):
            *xyz, snbt = entry
            grid.block_entities[_pos(xyz)] = nbtlib.parse_nbt(snbt)
    grid.meta.name = data["name"]
    inputs = [
        Input(int(i["tick"]), _pos(i.get("pos", (0, 0, 0))), i["action"],
              BlockState.parse(i["state"]) if "state" in i else None,
              int(i["time"]) if i.get("time") is not None else None)
        for i in data.get("inputs", [])
    ]
    probes = {str(k): _pos(v) for k, v in (data.get("probes") or {}).items()}
    return Scenario(data["name"], grid, int(data["ticks"]), inputs, probes, data.get("description", ""),
                    int(data.get("game_time", 0)), _pos(data["origin"]) if data.get("origin") is not None else None)


def load(path: str | Path) -> Scenario:
    path = Path(path)
    return from_dict(yaml.safe_load(path.read_text(encoding="utf-8")), path.parent)


def write_compiled(scenario: Scenario, path: str | Path) -> None:
    Path(path).write_text(json.dumps(scenario.compile(), indent=1), encoding="utf-8")
