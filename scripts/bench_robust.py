"""Measure how many designs depend on where (origin) and how (rotation) they are built.

Checks every logic template, every variant of every sequence template and the designs of the examples as they
were recorded in the game (scenarios/cmp-*.yaml and pla-*.yaml, i.e. what `compose_scenarios.design` /
`table_design` and `template_scenarios.pla_scenario` produce) with `design.robust.check`.
Designs with more than 8 inputs get the quick check and 12 origins.

uv run python scripts/bench_robust.py [--jobs N] [--out docs/robustness.md] [--only SUBSTRING]
"""

from __future__ import annotations

import argparse
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parents[1]
BIG = 8  # more inputs: quick check, sample of origins
SAMPLE = 12


def _jobs() -> list[tuple[str, str, str]]:
    """(group, name, key) for every design; key is resolved in the worker."""
    from redstone.design.seq_templates import SEQ_TEMPLATES
    from redstone.design.templates import TEMPLATES

    out = [("Logik-Vorlage", t.name, f"tpl:{t.name}") for t in TEMPLATES]
    for t in SEQ_TEMPLATES:
        for i, (params, c) in enumerate(t.variants()):
            out.append(("Zeit-Vorlage", c.name, f"seq:{t.name}:{i}"))
    for p in sorted((ROOT / "scenarios").glob("cmp-*.yaml")) + sorted((ROOT / "scenarios").glob("pla-*.yaml")):
        if _example_of(p):
            out.append(("Beispiel" if p.name.startswith("cmp-") else "Fackel-PLA", p.stem, f"scn:{p}"))
    return out


def _example_of(path: Path) -> Path | None:
    m = re.search(r"examples/[\w/.-]+\.yaml", path.read_text(encoding="utf-8")[:3000])
    return ROOT / m.group(0) if m else None


def _resolve(key: str):
    """(candidate, spec) for a job key."""
    import yaml

    from redstone.design import behaviour as bh
    from redstone.design.candidate import Candidate
    from redstone.design.seq_templates import SEQ_TEMPLATES
    from redstone.design.spec import from_dict, from_functions
    from redstone.design.templates import TEMPLATES
    from redstone.verify.scenario import load

    kind, rest = key.split(":", 1)
    if kind == "tpl":
        t = next(t for t in TEMPLATES if t.name == rest)
        return t.build(), from_functions(list(t.inputs), dict(t.function))
    if kind == "seq":
        name, i = rest.rsplit(":", 1)
        t = next(t for t in SEQ_TEMPLATES if t.name == name)
        params, c = t.variants()[int(i)]
        return c, bh.CONSTRUCTORS[t.behaviour](**params)
    path = Path(rest)
    example = _example_of(path)
    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    spec = bh.from_dict(data, source=example.name) if "behaviour" in data else from_dict(data, source=example.name)
    scn = load(path)
    c = Candidate(name=scn.name, grid=scn.grid, inputs=[scn.probes[n] for n in spec.inputs],
                  outputs=[scn.probes[n] for n in spec.outputs], description="", origin=f"scenario:{scn.name}")
    return c, spec


def measure(job: tuple[str, str, str]) -> dict:
    from redstone.design.robust import check

    group, name, key = job
    c, spec = _resolve(key)
    big = len(c.inputs) > BIG
    t0 = time.perf_counter()
    r = check(c, spec, quick=big, sample=SAMPLE if big else None)
    return {"group": group, "name": name, "inputs": len(c.inputs), "blocks": c.grid.block_count()
            if hasattr(c.grid, "block_count") else sum(1 for _ in c.grid.items()),
            "quick": big, "placements": r.placements, "rotations": r.rotations, "origins": r.origins,
            "wrong": r.wrong, "timing": r.timing, "runs": r.runs, "seconds": time.perf_counter() - t0,
            "first": r.findings[0] if r.findings else ""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    jobs = [j for j in _jobs() if args.only is None or args.only in j[1]]
    rows = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(args.jobs) as pool:
        for row in pool.map(measure, jobs):
            rows.append(row)
            flag = "ok" if not (row["wrong"] or row["timing"]) else f"FALSCH {row['wrong']} / ZEIT {row['timing']}"
            print(f"{row['group']:13} {row['name']:42} {row['placements']:4} {row['seconds']:6.1f}s {flag} "
                  f"{row['first']}", flush=True)
    total = time.perf_counter() - t0
    if args.out:
        Path(args.out).write_text(_markdown(rows, total), encoding="utf-8", newline="\n")


def _markdown(rows: list[dict], total: float) -> str:
    bad = [r for r in rows if r["wrong"] or r["timing"]]
    lines = ["| Gruppe | Entwurf | Eingänge | Lagen | Abweichungen | Art | Zeit |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        dev = r["wrong"] + r["timing"]
        art = ("–" if not dev else "Endzustand falsch" if r["wrong"] and not r["timing"]
               else "nur Zeitpunkt anders" if not r["wrong"] else "beides")
        lages = f"{r['origins']} × {r['rotations']}" + (" (schnell)" if r["quick"] else "")
        lines.append(f"| {r['group']} | {r['name']} | {r['inputs']} | {lages} | {dev} | {art} | {r['seconds']:.1f} s |")
    head = (f"{len(rows)} Entwürfe, {sum(r['placements'] for r in rows)} Lagen, "
            f"{sum(r['runs'] for r in rows)} Simulatorläufe, {total:.0f} s; ortsabhängig: {len(bad)}.")
    return head + "\n\n" + "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
