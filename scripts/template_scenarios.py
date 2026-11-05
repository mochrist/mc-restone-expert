"""Write one oracle scenario per design template: scenarios/tpl-<name>.yaml.

Each scenario walks through all lever combinations in Gray-code order (one lever per step, 20 gt apart)
and back to all-off, so the real game can confirm the template. Probes: every input and output.

uv run python scripts/template_scenarios.py && uv run rsx oracle scenarios/tpl-*.yaml --golden
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
    c = t.build()
    blocks = [[*p, str(s).removeprefix("minecraft:")] for p, s in sorted(c.grid.items())]
    tick = 2
    inputs = []
    for i in gray_sequence(len(c.inputs)):
        inputs.append({"tick": tick, "pos": list(c.inputs[i]), "action": "use"})
        tick += STEP
    probes = {name: list(p) for name, p in zip(t.inputs, c.inputs)}
    probes |= {name: list(p) for name, p in zip(t.outputs, c.outputs)}
    d = {
        "name": f"tpl-{t.name}",
        "description": f"Vorlage {t.name} aus src/redstone/design/templates.py ({t.description}) "
                       f"Alle Hebel-Kombinationen im Gray-Code, je {STEP} gt Abstand.",
        "build": {"size": list(c.grid.size), "blocks": blocks},
        "ticks": tick,
        "inputs": inputs,
        "probes": probes,
    }
    if c.grid.block_entities:
        d["build"]["block_entities"] = [[*p, to_nbt(be).snbt()] for p, be in sorted(c.grid.block_entities.items())]
    return d


def main() -> None:
    for t in TEMPLATES:
        path = ROOT / "scenarios" / f"tpl-{t.name}.yaml"
        path.write_text(yaml.safe_dump(scenario_for(t), allow_unicode=True, sort_keys=False, width=120,
                                       default_flow_style=None),
                        encoding="utf-8", newline="\n")
    print(f"wrote {len(TEMPLATES)} scenarios")


if __name__ == "__main__":
    main()
