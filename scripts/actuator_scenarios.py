"""Write one oracle scenario per actuator (scenarios/act-<actuator>.yaml): the XOR design (two levers) with the
actuator instead of the lamp, from `design.actuators.with_output`.

All lever combinations in Gray code, 30 gt apart (as in scripts/template_scenarios.py). Probes: both levers, the
actuator and, for doors and pistons, the block above it (upper door half, piston head).

uv run python scripts/actuator_scenarios.py && uv run rsx oracle scenarios/act-*.yaml --golden
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from redstone.design.actuators import ACTUATORS, with_output
from redstone.design.templates import TEMPLATES

ROOT = Path(__file__).parents[1]
STEP = 30
HAS_ABOVE = {"iron_door", "piston", "sticky_piston"}


def _template_gen():
    spec = importlib.util.spec_from_file_location("template_scenarios", ROOT / "scripts" / "template_scenarios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scenario_for(kind: str) -> dict:
    base = next(t for t in TEMPLATES if t.name == "xor2-comparator").build()
    cand, why = with_output(base, kind)
    if cand is None:
        raise RuntimeError(f"{kind}: {why}")
    label = ACTUATORS[kind][0]
    d = _template_gen().candidate_scenario(
        cand, f"act-{kind.replace('_', '-')}", ["a", "b"], ["out"],
        f"XOR-Entwurf (xor2-comparator) mit {label} statt der Lampe ({why})", step=STEP)
    if kind in HAS_ABOVE:
        x, y, z = cand.outputs[0]
        d["probes"]["oben"] = [x, y + 1, z]
    return d


def main() -> None:
    for kind in ACTUATORS:
        d = scenario_for(kind)
        (ROOT / "scenarios" / f"{d['name']}.yaml").write_text(
            yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
            encoding="utf-8", newline="\n")
        print("wrote", d["name"])


if __name__ == "__main__":
    main()
