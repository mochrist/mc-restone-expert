"""Write one oracle scenario per actuator (scenarios/act-<actuator>.yaml): the XOR design (two levers) with the
actuator instead of the lamp, from `design.actuators.with_output`. Plus scenarios/act-and-<actuator>.yaml for the
torch AND, whose lamp is lit by a torch beside it and becomes dust in front of a repeater (DUST_KINDS).

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
DUST_KINDS = ["iron_door", "piston", "dispenser"]


def _template_gen():
    spec = importlib.util.spec_from_file_location("template_scenarios", ROOT / "scripts" / "template_scenarios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scenario_for(kind: str, template: str = "xor2-comparator") -> dict:
    base = next(t for t in TEMPLATES if t.name == template).build()
    cand, why = with_output(base, kind)
    if cand is None:
        raise RuntimeError(f"{kind}: {why}")
    label = ACTUATORS[kind][0]
    what, prefix = ("XOR", "act") if template == "xor2-comparator" else ("UND", "act-and")
    d = _template_gen().candidate_scenario(
        cand, f"{prefix}-{kind.replace('_', '-')}", ["a", "b"], ["out"],
        f"{what}-Entwurf ({template}) mit {label} statt der Lampe ({why})", step=STEP)
    if kind in HAS_ABOVE:
        x, y, z = cand.outputs[0]
        d["probes"]["oben"] = [x, y + 1, z]
    return d


def main() -> None:
    for d in [scenario_for(k) for k in ACTUATORS] + [scenario_for(k, "and2-torch") for k in DUST_KINDS]:
        (ROOT / "scenarios" / f"{d['name']}.yaml").write_text(
            yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
            encoding="utf-8", newline="\n")
        print("wrote", d["name"])


if __name__ == "__main__":
    main()
