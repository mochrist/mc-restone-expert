"""Scenarios at a shifted origin (`origin:` field, docs/scenario-format.md), to check the simulator's dust order
(DUST-018) away from (0, 200, 0) in the real game:

* pos-zero-tick-piston, pos-dust-network: copies of existing scenarios at another origin,
* pos-race-5, pos-race-7: `design.robust.piston_race` at two origins where the simulator predicts different
  winners (lamp dark at x=5, lit at x=7).

uv run python scripts/position_scenarios.py && uv run rsx oracle scenarios/pos-*.yaml --golden
"""

from __future__ import annotations

from pathlib import Path

import yaml

from redstone.design.robust import piston_race

ROOT = Path(__file__).parents[1]


def _write(d: dict) -> None:
    (ROOT / "scenarios" / f"{d['name']}.yaml").write_text(
        yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
        encoding="utf-8", newline="\n")


def moved(name: str, origin: list[int]) -> dict:
    d = yaml.safe_load((ROOT / "scenarios" / f"{name}.yaml").read_text(encoding="utf-8"))
    d["name"] = f"pos-{name}"
    d["description"] = f"Wie {name}, aber mit der Min-Ecke bei {origin}. " + d.get("description", "")
    d["origin"] = origin
    return d


def race(x: int) -> dict:
    c = piston_race()
    return {
        "name": f"pos-race-{x}",
        "description": f"{c.description} Min-Ecke bei [{x}, 200, 0]; der Simulator sagt bei x=5 den Kolben nach "
                       "unten voraus (Lampe bleibt aus), bei x=7 den nach Osten (Lampe leuchtet).",
        "origin": [x, 200, 0],
        "build": {"size": list(c.grid.size),
                  "blocks": [[*p, str(s).removeprefix("minecraft:")] for p, s in sorted(c.grid.items())]},
        "ticks": 20,
        "inputs": [{"tick": 2, "pos": list(c.inputs[0]), "action": "use"}],
        "probes": {"lever": list(c.inputs[0]), "lamp": list(c.outputs[0]), "east": [2, 0, 0], "down": [3, 1, 0]},
    }


def main() -> None:
    _write(moved("zero-tick-piston", [5, 200, 0]))
    _write(moved("dust-network", [3, 64, 9]))
    for x in (5, 7):
        _write(race(x))


if __name__ == "__main__":
    main()
