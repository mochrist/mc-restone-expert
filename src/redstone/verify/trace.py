"""Traces: per-tick probe values from the oracle or the simulator, and their diff."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..model import Pos
from ..versions import TARGET_VERSION

FORMAT = 1


@dataclass
class Trace:
    scenario: str
    source: str
    ticks: int
    probes: dict[str, Pos]
    # probe -> change points [(tick, value)], first entry at tick 0
    samples: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    version: str = TARGET_VERSION

    def record(self, probe: str, tick: int, value: str) -> None:
        points = self.samples.setdefault(probe, [])
        if not points or points[-1][1] != value:
            points.append((tick, value))

    def value_at(self, probe: str, tick: int) -> str:
        current = None
        for t, v in self.samples[probe]:
            if t > tick:
                break
            current = v
        if current is None:
            raise KeyError(f"no sample for {probe} at tick {tick}")
        return current

    def series(self, probe: str) -> list[str]:
        return [self.value_at(probe, t) for t in range(self.ticks + 1)]

    def to_json(self) -> dict:
        return {
            "format": FORMAT,
            "scenario": self.scenario,
            "source": self.source,
            "version": self.version,
            "ticks": self.ticks,
            "probes": {k: list(v) for k, v in self.probes.items()},
            "samples": {k: [[t, v] for t, v in pts] for k, pts in self.samples.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> Trace:
        if data.get("format") != FORMAT:
            raise ValueError(f"unsupported trace format {data.get('format')!r}")
        return cls(
            scenario=data["scenario"],
            source=data["source"],
            ticks=int(data["ticks"]),
            probes={k: Pos(*v) for k, v in data["probes"].items()},
            samples={k: [(int(t), str(v)) for t, v in pts] for k, pts in data["samples"].items()},
            version=data.get("version", TARGET_VERSION),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Trace:
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Mismatch:
    probe: str
    tick: int
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"tick {self.tick:>4}  {self.probe}: expected {self.expected}, got {self.actual}"


def diff(expected: Trace, actual: Trace, limit: int | None = None) -> list[Mismatch]:
    """Tick-by-tick differences. Only the first mismatching tick per run of equal values is reported."""
    if expected.ticks != actual.ticks:
        raise ValueError(f"tick counts differ: {expected.ticks} vs {actual.ticks}")
    out: list[Mismatch] = []
    for probe in expected.probes:
        if probe not in actual.samples:
            out.append(Mismatch(probe, 0, "<probe>", "<missing>"))
            continue
        last = None
        for t in range(expected.ticks + 1):
            e, a = expected.value_at(probe, t), actual.value_at(probe, t)
            if e != a and (e, a) != last:
                out.append(Mismatch(probe, t, e, a))
            last = (e, a) if e != a else None
    out.sort(key=lambda m: (m.tick, m.probe))
    return out[:limit] if limit else out


def timing_diagram(trace: Trace, prop: str | None = None, width: int | None = None) -> str:
    """ASCII timing diagram: one row per probe, '#' when the probe is 'on'.

    'On' means: the given property (or the first of powered/lit/extended/power>0) is true/non-zero.
    """
    ticks = trace.ticks + 1 if width is None else min(width, trace.ticks + 1)
    name_w = max((len(p) for p in trace.probes), default=4)
    lines = [" " * name_w + " " + "".join(str(t // 10 % 10) if t % 10 == 0 else " " for t in range(ticks))]
    lines.append(" " * name_w + " " + "".join(str(t % 10) for t in range(ticks)))
    for probe in trace.probes:
        row = "".join("#" if _is_on(trace.value_at(probe, t), prop) else "_" for t in range(ticks))
        lines.append(f"{probe:>{name_w}} {row}")
    return "\n".join(lines)


def _is_on(value: str, prop: str | None) -> bool:
    from ..model import BlockState

    state_str, _, extra = value.partition("|")
    state = BlockState.parse(state_str)
    if prop:
        v = state.get(prop)
        return v == "true" or (v is not None and v.isdigit() and int(v) > 0)
    for key in ("powered", "lit", "extended", "triggered", "enabled"):
        if state.get(key) is not None:
            return state.get(key) == "true"
    if state.get("power") is not None:
        return state.get_int("power") > 0
    if extra.startswith("output="):
        return int(extra[7:]) > 0
    return False
