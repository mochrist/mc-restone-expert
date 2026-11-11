"""Write one oracle scenario per design template (scenarios/tpl-<name>.yaml) and per example spec as torch
PLA (scenarios/pla-<spec>.yaml).

Each scenario walks through all lever combinations in Gray-code order (one lever per step, 20 gt apart)
and back to all-off, so the real game can confirm the template. Probes: every input and output.

uv run python scripts/template_scenarios.py && uv run rsx oracle scenarios/tpl-*.yaml scenarios/pla-*.yaml --golden
"""

from __future__ import annotations

from pathlib import Path

import yaml

from redstone.design.templates import TEMPLATES
from redstone.io.nbtutil import to_nbt

ROOT = Path(__file__).parents[1]
STEP = 20


def gray_sequence(n: int) -> list[int]:
    """Index of the lever to toggle at each step: Gray code over all 2^n combinations, then back to 0."""
    codes = [i ^ (i >> 1) for i in range(2 ** n)]
    seq = [(a ^ b).bit_length() - 1 for a, b in zip(codes, codes[1:])]
    last = codes[-1]
    return seq + [last.bit_length() - 1] if last else seq


def scenario_for(t) -> dict:
    return candidate_scenario(t.build(), f"tpl-{t.name}", list(t.inputs), list(t.outputs),
                              f"Vorlage {t.name} aus src/redstone/design/templates.py ({t.description})")


def pla_scenario(spec_path: Path) -> dict:
    from redstone.design.spec import load
    from redstone.design.synth import pla

    spec = load(spec_path)
    c = pla(spec)
    groups = None
    if spec.partial:  # only the combinations that matter: switch each one on and off again
        groups = [[i for i, b in enumerate(combo) if b] for combo in spec.combos() if any(combo)]
        groups = [g for g in groups for _ in (0, 1)]
    return candidate_scenario(c, f"pla-{spec_path.stem}", spec.inputs, spec.outputs,
                              f"Fackel-PLA aus examples/specs/{spec_path.name} ({c.description})", groups)


def candidate_scenario(c, name: str, in_names: list[str], out_names: list[str], text: str,
                       groups: list[list[int]] | None = None, step: int = STEP) -> dict:
    """groups: levers switched together per step; default all combinations in Gray code. step: ticks
    between the steps (more than the design's delay)."""
    blocks = [[*p, str(s).removeprefix("minecraft:")] for p, s in sorted(c.grid.items())]
    tick = 2
    inputs = []
    for group in groups if groups is not None else [[i] for i in gray_sequence(len(c.inputs))]:
        inputs += [{"tick": tick, "pos": list(c.inputs[i]), "action": "use"} for i in group]
        tick += step
    probes = {n: list(p) for n, p in zip(in_names, c.inputs)}
    probes |= {n: list(p) for n, p in zip(out_names, c.outputs)}
    d = {
        "name": name,
        "description": f"{text} " + ("Alle Hebel-Kombinationen im Gray-Code" if groups is None else
                                     "Jede verlangte Hebel-Kombination an und wieder aus") + f", je {step} gt Abstand.",
        "build": {"size": list(c.grid.size), "blocks": blocks},
        "ticks": tick,
        "inputs": inputs,
        "probes": probes,
    }
    if c.grid.block_entities:
        d["build"]["block_entities"] = [[*p, to_nbt(be).snbt()] for p, be in sorted(c.grid.block_entities.items())]
    return d


def _write(d: dict) -> None:
    path = ROOT / "scenarios" / f"{d['name']}.yaml"
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
                    encoding="utf-8", newline="\n")


def main() -> None:
    for t in TEMPLATES:
        _write(scenario_for(t))
    specs = sorted((ROOT / "examples" / "specs").glob("*.yaml"))
    for p in specs:
        _write(pla_scenario(p))
    print(f"wrote {len(TEMPLATES)} template and {len(specs)} PLA scenarios")


if __name__ == "__main__":
    main()
