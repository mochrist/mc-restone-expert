"""Write one oracle scenario per sequential template (scenarios/seq-<name>.yaml) for its first variant.

Non-clock templates: all trials of the behaviour spec run one after another in a single scenario, each
starting GAP ticks after the previous one has settled. Clocks are stored without one of their blocks; that
block is placed with `setblock` at tick 2 and starts the clock (like scenarios/observer-clock.yaml).
Probes: every input and the output. `check_trace` compares a recorded trace with the spec, trial by trial.

uv run python scripts/seq_template_scenarios.py && uv run rsx oracle scenarios/seq-*.yaml --golden
"""

from __future__ import annotations

from pathlib import Path

import yaml

from redstone.design import behaviour as bh
from redstone.design.seq_templates import SEQ_TEMPLATES
from redstone.io.nbtutil import to_nbt

ROOT = Path(__file__).parents[1]
GAP = 30  # quiet ticks between two trials
START_TICK = 2  # clocks: tick of the starting setblock
CLOCK_TICKS = 200


def _spec(t):
    params, _ = t.variants()[0]
    return bh.CONSTRUCTORS[t.behaviour](**params)


def _trial_length(trial: bh.Trial) -> int:
    """Ticks from the trial start until it is surely over (last action or expected edge, plus margin)."""
    ticks = [a for a, _ in trial.actions]
    ticks += [b for iv in trial.expected for a, b in iv if b is not None]
    return max(ticks, default=0) + 20  # stone button 20 gt, lamp off delay 4 gt


def trial_starts(spec: bh.BehaviourSpec) -> list[int]:
    starts, t = [], 0
    for trial in spec.trials:
        starts.append(t)
        t += _trial_length(trial) + GAP
    return starts


def _blocks(grid, skip=None) -> list:
    return [[*p, str(s).removeprefix("minecraft:")] for p, s in sorted(grid.items()) if p != skip]


def _clock_starter(c, spec) -> tuple:
    """First block whose late placement starts the clock with the expected period and on-time."""
    from redstone.sim.runner import simulate
    from redstone.verify.scenario import from_dict

    want = bh._periodic(spec.trials[0].expected[0])
    for p, s in sorted(c.grid.items()):
        if s.id in ("stone", "redstone_lamp") or p in c.grid.block_entities or p in c.outputs:
            continue
        d = _clock_dict(c, "probe", "", p)
        trace = simulate(from_dict(d))
        if _periodic_from_trace(trace, "out", c, START_TICK) == want:
            return p
    raise RuntimeError(f"{c.name}: no block starts the clock")


def _clock_dict(c, name: str, text: str, starter) -> dict:
    d = {
        "name": name,
        "description": text,
        "build": {"size": list(c.grid.size), "blocks": _blocks(c.grid, starter)},
        "ticks": START_TICK + CLOCK_TICKS,
        "inputs": [{"tick": START_TICK, "pos": list(starter), "action": "setblock",
                    "state": str(c.grid.get(starter)).removeprefix("minecraft:")}],
        "probes": {"out": list(c.outputs[0])},
    }
    if c.grid.block_entities:
        d["build"]["block_entities"] = [[*p, to_nbt(be).snbt()] for p, be in sorted(c.grid.block_entities.items())]
    return d


def _on_intervals(trace, probe: str) -> list[tuple[int, int | None]]:
    from redstone.analysis.experiment import is_on

    out, start = [], None
    for t, v in trace.samples[probe]:
        if is_on(v) and start is None:
            start = t
        elif not is_on(v) and start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, None))
    return out


def _off_delay(c) -> int:
    from redstone.analysis.patterns import OFF_DELAY

    return OFF_DELAY.get(c.grid.get(c.outputs[0]).id, 0)


def _periodic_from_trace(trace, probe: str, c, start: int):
    off = _off_delay(c)
    iv = [(a - start, None if b is None else b - start - off) for a, b in _on_intervals(trace, probe)
          if a >= start]
    return bh._periodic([(a, b) for a, b in iv if b is None or b <= CLOCK_TICKS - off])


def scenario_for(t) -> dict:
    params, c = t.variants()[0]
    spec = bh.CONSTRUCTORS[t.behaviour](**params)
    label = ", ".join(f"{k}={v}" for k, v in params.items())
    text = f"Vorlage {t.name} ({label}) aus src/redstone/design/seq_templates.py: {t.description}"
    name = f"seq-{t.name}"
    if t.behaviour == "clock":
        starter = _clock_starter(c, spec)
        return _clock_dict(c, name, text + f" Gestartet wird sie, indem der Block bei {list(starter)} bei Tick "
                           f"{START_TICK} gesetzt wird.", starter)
    starts = trial_starts(spec)
    inputs = [{"tick": s + a, "pos": list(c.inputs[i]), "action": "use"}
              for s, trial in zip(starts, spec.trials) for a, i in trial.actions]
    probes = {n: list(p) for n, p in zip(t.inputs, c.inputs)} | {t.outputs[0]: list(c.outputs[0])}
    trials = "; ".join(f"{trial.name} ab Tick {s}" for s, trial in zip(starts, spec.trials))
    d = {
        "name": name,
        "description": f"{text} Testabläufe nacheinander: {trials}.",
        "build": {"size": list(c.grid.size), "blocks": _blocks(c.grid)},
        "ticks": starts[-1] + _trial_length(spec.trials[-1]) + GAP,
        "inputs": inputs,
        "probes": probes,
    }
    if c.grid.block_entities:
        d["build"]["block_entities"] = [[*p, to_nbt(be).snbt()] for p, be in sorted(c.grid.block_entities.items())]
    return d


def check_trace(t, trace) -> list[str]:
    """German errors if a trace of scenario_for(t) does not show the template's behaviour."""
    params, c = t.variants()[0]
    spec = bh.CONSTRUCTORS[t.behaviour](**params)
    if t.behaviour == "clock":
        got = _periodic_from_trace(trace, "out", c, START_TICK)
        want = bh._periodic(spec.trials[0].expected[0])
        return [] if got == want else [f"Takt {got} statt {want}"]
    off = _off_delay(c)
    iv = _on_intervals(trace, t.outputs[0])
    errors = []
    starts = trial_starts(spec)
    for k, (s, trial) in enumerate(zip(starts, spec.trials)):
        end = starts[k + 1] if k + 1 < len(starts) else trace.ticks + 1
        got = [(a - s, None if b is None else b - s - off) for a, b in iv if s <= a < end]
        reason = bh._match_intervals(got, trial.expected[0], spec)
        if reason:
            errors.append(f"{trial.name}: {reason}")
    return errors


def _write(d: dict) -> None:
    path = ROOT / "scenarios" / f"{d['name']}.yaml"
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
                    encoding="utf-8", newline="\n")


def main() -> None:
    for t in SEQ_TEMPLATES:
        _write(scenario_for(t))
    print(f"wrote {len(SEQ_TEMPLATES)} sequential template scenarios")


if __name__ == "__main__":
    main()
