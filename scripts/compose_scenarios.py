"""Write one oracle scenario per composed example: the best design `rsx redesign` finds for it, as
scenarios/cmp-<name>.yaml.

* examples/behaviour/*.yaml with `gate:` (logic in front of a timing/memory block),
* examples/specs/composed/*.yaml (truth tables split into chains of gates, `design/decompose.py`); these
  scenarios walk through all lever combinations like scripts/template_scenarios.py.

The designs are compacted like in `rsx redesign` (`design/compact.py`), so the real game checks the moved parts
and rerouted lines as well.

All trials run one after another in one scenario (as in seq_template_scenarios.py). Gated trials leave the
setup levers on, so every lever that is on at the end of a trial is switched off again before the next one.
`check_trace` compares a recorded trace with the spec, trial by trial.

uv run python scripts/compose_scenarios.py [name ...] && uv run rsx oracle scenarios/cmp-*.yaml --golden
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

from redstone.design import behaviour as bh
from redstone.design.search import redesign
from redstone.io.nbtutil import to_nbt

ROOT = Path(__file__).parents[1]
GAP = 30
COMPACT = 100  # evaluations for compacting, as `rsx redesign` (no time limit, so the result is reproducible)
COMPACTED = "kompaktiert aus "
COMPOSED = ("zerlegt", "komponiert", "nebeneinander")  # origins of composed designs


def examples() -> list[Path]:
    return sorted(p for p in (ROOT / "examples" / "behaviour").glob("*.yaml")
                  if "gate" in yaml.safe_load(p.read_text(encoding="utf-8")))


def spec_of(path: Path) -> bh.BehaviourSpec:
    return bh.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")), source=path.name)


@cache
def design(path: Path):
    """The best working composed design, compacted as in `rsx redesign` (the scenarios check compositions in
    the game, so a plain PLA or template that happens to rank higher is skipped)."""
    for ev in redesign(spec_of(path), compact_budget=COMPACT):
        if ev.ok and ev.candidate.origin.removeprefix(COMPACTED).startswith(COMPOSED):
            return ev.candidate
    raise RuntimeError(f"{path.name}: no working composed design")


def _trial_length(trial: bh.Trial) -> int:
    ticks = [a for a, _ in trial.actions] + [b for iv in trial.expected for a, b in iv if b is not None]
    return max(ticks, default=0) + 20


def _resets(trial: bh.Trial) -> list[int]:
    """Levers that are on after the trial."""
    on: dict[int, bool] = {}
    for _, i in trial.actions:
        on[i] = not on.get(i, False)
    return sorted(i for i, v in on.items() if v)


def trial_starts(spec: bh.BehaviourSpec) -> list[int]:
    starts, t = [], 0
    for trial in spec.trials:
        starts.append(t)
        t += _trial_length(trial) + GAP
    return starts


def scenario_for(path: Path) -> dict:
    spec, c = spec_of(path), design(path)
    starts = trial_starts(spec)
    inputs = []
    for s, trial in zip(starts, spec.trials):
        inputs += [{"tick": s + a, "pos": list(c.inputs[i]), "action": "use"} for a, i in trial.actions]
        inputs += [{"tick": s + _trial_length(trial), "pos": list(c.inputs[i]), "action": "use"}
                   for i in _resets(trial)]
    probes = {n: list(p) for n, p in zip(spec.inputs, c.inputs)} | {spec.outputs[0]: list(c.outputs[0])}
    trials = "; ".join(f"{trial.name} ab Tick {s}" for s, trial in zip(starts, spec.trials))
    d = {
        "name": f"cmp-{path.stem}",
        "description": f"Komposition für {path.name} ({spec.kind}): {c.name}. Testabläufe nacheinander, "
                       f"danach werden eingeschaltete Hebel wieder ausgeschaltet: {trials}.",
        "build": {"size": list(c.grid.size),
                  "blocks": [[*p, str(s).removeprefix("minecraft:")] for p, s in sorted(c.grid.items())]},
        "ticks": starts[-1] + _trial_length(spec.trials[-1]) + GAP,
        "inputs": inputs,
        "probes": probes,
    }
    if c.grid.block_entities:
        d["build"]["block_entities"] = [[*p, to_nbt(be).snbt()] for p, be in sorted(c.grid.block_entities.items())]
    return d


def check_trace(path: Path, trace) -> list[str]:
    """German errors if a trace of scenario_for(path) does not show the spec's behaviour."""
    from redstone.analysis.experiment import is_on
    from redstone.analysis.patterns import OFF_DELAY

    spec, c = spec_of(path), design(path)
    off = OFF_DELAY.get(c.grid.get(c.outputs[0]).id, 0)
    iv, start = [], None
    for t, v in trace.samples[spec.outputs[0]]:
        if is_on(v) and start is None:
            start = t
        elif not is_on(v) and start is not None:
            iv.append((start, t))
            start = None
    if start is not None:
        iv.append((start, None))
    errors = []
    starts = trial_starts(spec)
    for k, (s, trial) in enumerate(zip(starts, spec.trials)):
        end = starts[k + 1] if k + 1 < len(starts) else trace.ticks + 1
        got = [(a - s, None if b is None else b - s - off) for a, b in iv if s <= a < end]
        reason = bh._match_intervals(got, trial.expected[0], spec)
        if reason:
            errors.append(f"{trial.name}: {reason}")
    return errors


# ---------------------------------------------------------------------- truth tables (decomposition)
def table_examples() -> list[Path]:
    return sorted((ROOT / "examples" / "specs" / "composed").glob("*.yaml"))


@cache
def table_design(path: Path):
    from redstone.design.spec import load

    for ev in redesign(load(path), compact_budget=COMPACT):  # the best decomposition, even if a plain PLA ranks higher
        if ev.ok and ev.candidate.origin.removeprefix(COMPACTED).startswith(("zerlegt", "nebeneinander")):
            return ev.candidate
    raise RuntimeError(f"{path.name}: no working decomposition")


def _template_gen():
    import importlib.util

    spec = importlib.util.spec_from_file_location("template_scenarios", ROOT / "scripts" / "template_scenarios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@cache
def table_step(path: Path) -> int:
    """Ticks between lever changes: the usual step, more for slow designs (long chains of parts)."""
    from redstone.design.evaluate import evaluate_any
    from redstone.design.spec import load

    delay = evaluate_any(table_design(path), load(path), quick=True).max_delay or 0
    return max(_template_gen().STEP, 10 * ((delay + 19) // 10))


def table_scenario_for(path: Path) -> dict:
    from redstone.design.spec import load

    spec, c = load(path), table_design(path)
    return _template_gen().candidate_scenario(
        c, f"cmp-{path.stem}", spec.inputs, spec.outputs,
        f"Zerlegung für examples/specs/composed/{path.name}: {c.name} ({c.origin}).", step=table_step(path))


def check_table_trace(path: Path, trace, step: int | None = None) -> list[str]:
    """German errors if the outputs in a trace of table_scenario_for(path) differ from the truth table
    (read just before each next lever toggle). step: ticks between toggles (default: `table_step`)."""
    from redstone.analysis.experiment import is_on
    from redstone.design.spec import load

    spec = load(path)
    tgen = _template_gen()
    state = [False] * len(spec.inputs)
    tick, errors = 2, []

    def value(probe: str, t: int) -> bool:
        v = None
        for at, x in trace.samples[probe]:
            if at > t:
                break
            v = x
        return v is not None and is_on(v)

    for i in tgen.gray_sequence(len(spec.inputs)):
        state[i] = not state[i]
        tick += step or table_step(path)
        want = spec.table[tuple(state)]
        got = tuple(value(o, tick - 1) for o in spec.outputs)
        if got != want:
            errors.append(f"bei {state}: {got} statt {want}")
    return errors


def main() -> None:
    import sys

    only = set(sys.argv[1:])  # optional example names, e.g. addsub2 addsub4
    for path in table_examples():
        if only and path.stem not in only:
            continue
        d = table_scenario_for(path)
        (ROOT / "scenarios" / f"{d['name']}.yaml").write_text(
            yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
            encoding="utf-8", newline="\n")
        print("wrote", d["name"], table_design(path).name, tuple(table_design(path).grid.size))
    for path in examples():
        if only and path.stem not in only:
            continue
        d = scenario_for(path)
        (ROOT / "scenarios" / f"{d['name']}.yaml").write_text(
            yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
            encoding="utf-8", newline="\n")
        print("wrote", d["name"], design(path).name, tuple(design(path).grid.size))


if __name__ == "__main__":
    main()
