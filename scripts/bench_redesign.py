"""Benchmark of `design/search.py: redesign` on the examples: best design (size, blocks, delay), number of evaluated
candidates and simulator work (runs and ticks summed over all evaluations), one line per spec.

    uv run python scripts/bench_redesign.py [--only xor4,mux8] [--skip cmp5,mux8] [--compact 100] [--time 0]
                                            [--json out.json] [--compare-transitions]

--time 0 (default) means no time limit for shrinking, so the results do not depend on the speed of the machine.
--compare-transitions evaluates every full check a second time with all transitions (`evaluate.TRANSITIONS`
set to "all") and prints candidates whose verdict or delay differs between the two.
Run with PYTHONHASHSEED=0 for comparable runs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def specs(only: set[str], skip: set[str]) -> list[Path]:
    paths = (sorted((ROOT / "examples" / "specs").glob("*.yaml"))
             + sorted((ROOT / "examples" / "specs" / "composed").glob("*.yaml"))
             + sorted((ROOT / "examples" / "behaviour").glob("*.yaml")))
    return [p for p in paths if (not only or p.stem in only) and p.stem not in skip]


def main() -> None:
    import yaml

    from redstone.design import evaluate as evmod
    from redstone.design.behaviour import from_dict as behaviour_from_dict
    from redstone.design.search import redesign
    from redstone.design.spec import from_dict

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--compact", type=int, default=100)
    ap.add_argument("--time", type=float, default=0)
    ap.add_argument("--json")
    ap.add_argument("--compare-transitions", action="store_true")
    args = ap.parse_args()

    counts = {"evaluations": 0, "runs": 0, "ticks": 0, "full": 0, "differ": 0}
    original = evmod.evaluate

    def counted(candidate, spec, constraints=None, full=True, **kw):
        ev = original(candidate, spec, constraints, full=full, **kw)
        counts["evaluations"] += 1
        counts["runs"] += ev.runs
        counts["ticks"] += ev.ticks
        if full and not kw.get("stop_early"):
            counts["full"] += 1
            if args.compare_transitions:
                mode = evmod.TRANSITIONS
                evmod.TRANSITIONS = "all"
                try:
                    other = original(candidate, spec, constraints, full=full, **kw)
                finally:
                    evmod.TRANSITIONS = mode
                if (other.correct, other.max_delay) != (ev.correct, ev.max_delay):
                    counts["differ"] += 1
                    print(f"  DIFFERS {candidate.name}: {mode} {ev.correct} {ev.max_delay} {ev.errors[:1]}"
                          f" / all {other.correct} {other.max_delay} {other.errors[:1]}", flush=True)
        return ev

    evmod.evaluate = counted
    out = {}
    for path in specs(set(filter(None, args.only.split(","))), set(filter(None, args.skip.split(",")))):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        spec = behaviour_from_dict(raw, source=path.name) if "behaviour" in raw else from_dict(raw, source=path.name)
        for k in counts:
            counts[k] = 0
        t = time.perf_counter()
        results = redesign(spec, compact_budget=args.compact, log=[], time_limit=args.time or None)
        dt = time.perf_counter() - t
        ok = [r for r in results if r.ok]
        best = ok[0] if ok else None
        row = {
            "best": best.candidate.name if best else None,
            "size": list(best.candidate.size) if best else None,
            "blocks": best.candidate.block_count if best else None,
            "delay": best.max_delay if best else None,
            "candidates": len(results), "working": len(ok),
            "all": sorted([r.candidate.name, list(r.candidate.size), r.candidate.block_count, r.ok]
                          for r in results),
            **counts, "seconds": round(dt, 1),
        }
        out[path.stem] = row
        size = "×".join(map(str, row["size"])) if best else "-"
        print(f"{path.stem:20} {size:9} {row['blocks'] or '-':>4} blocks  {row['delay'] if best else '-':>3} gt  "
              f"{row['candidates']:3} cand ({row['working']} ok)  {counts['evaluations']:5} eval  "
              f"{counts['runs']:7} runs  {counts['ticks']:9} ticks  {dt:7.1f}s"
              + (f"  differ {counts['differ']}/{counts['full']}" if args.compare_transitions else ""), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
