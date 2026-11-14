"""Write src/redstone/gui/static/demo/model.json (GUI Model format) from scenarios/cmp-cmp3.yaml.

Placeholder materials/build_order; used by the GUI with ?demo=1 when no server is running.
Run: uv run python scripts/gui_demo_data.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from redstone.verify import load_scenario

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "scenarios" / "cmp-cmp3.yaml"
OUT = ROOT / "src" / "redstone" / "gui" / "static" / "demo" / "model.json"


def main() -> None:
    sc = load_scenario(SRC)
    grid = sc.grid
    blocks = []
    for pos, state in grid.items():
        s = str(state).removeprefix("minecraft:")
        blocks.append({"p": [pos.x, pos.y, pos.z], "s": s})
    by_pos = {tuple(b["p"]): b["s"] for b in blocks}
    inputs, outputs = [], []
    for name, p in sc.probes.items():
        s = by_pos.get(tuple(p), "")
        (inputs if s.startswith(("lever", "stone_button")) else outputs).append({"name": name, "p": list(p)})
    counts = Counter(b["s"].split("[")[0] for b in blocks)
    materials = [{"item": k, "label": k, "count": v} for k, v in counts.most_common()]
    order = sorted((b["p"] for b in blocks), key=lambda p: (p[1], p[0], p[2]))
    model = {
        "name": sc.name,
        "size": list(grid.size),
        "blocks": blocks,
        "inputs": inputs,
        "outputs": outputs,
        "materials": materials,
        "build_order": order,
        "notes": ["Demodaten (Platzhalter für Material und Reihenfolge)"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({len(blocks)} blocks)")


if __name__ == "__main__":
    main()
