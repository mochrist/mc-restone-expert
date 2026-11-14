"""Benchmark of `design/compact.py`: compact the composed designs of `examples/specs/composed` (and the PLA of
some specs) with a given budget and print volume, blocks and how the evaluations were spent.

    uv run python scripts/bench_compact.py [--budget 100] [--only xor4,and5]

The uncompacted designs are cached in .cache/bench_compact.pickle (delete it after changing the composition).
"""

from __future__ import annotations

import argparse
import pickle
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CACHE = ROOT / ".cache" / "bench_compact.pickle"


def designs(only: set[str] = frozenset()) -> dict[str, tuple]:
    """name -> (spec, candidate): the best uncompacted decomposition of every composed example (cached; designs
    missing from the cache are added)."""
    from redstone.design.search import redesign
    from redstone.design.spec import load

    out = pickle.loads(CACHE.read_bytes()) if CACHE.exists() else {}
    wanted = lambda name: (not only or name in only) and name not in out  # noqa: E731
    for path in sorted((ROOT / "examples" / "specs" / "composed").glob("*.yaml")):
        if not wanted(path.stem):
            continue
        spec = load(path)
        for ev in redesign(spec):
            if ev.ok and ev.candidate.origin.startswith(("zerlegt", "nebeneinander")):
                out[path.stem] = (spec, ev.candidate)
                break
    for name in ("xor", "fulladder", "majority"):
        if not wanted(f"pla-{name}"):
            continue
        spec = load(ROOT / "examples" / "specs" / f"{name}.yaml")
        ev = next(e for e in redesign(spec) if e.ok and e.candidate.origin.startswith("synthese"))
        out[f"pla-{name}"] = (spec, ev.candidate)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_bytes(pickle.dumps(out))
    return out


def main() -> None:
    from redstone.design.compact import compact
    from redstone.design.evaluate import Constraints

    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = set(filter(None, args.only.split(",")))
    total = [0, 0, 0, 0]
    for name, (spec, cand) in designs(only).items():
        if only and name not in only:
            continue
        t = time.perf_counter()
        small, log = compact(cand, spec, Constraints(max_delay=spec.max_delay), args.budget)
        dt = time.perf_counter() - t
        spent = log[-1].removeprefix("simulierte Varianten: ")
        kinds = {}
        for line in log[:-1]:
            k = ("Baustein" if "umgesetzt" in line or "gedreht" in line else
                 "Ebene" if line.startswith("Ebene") else
                 "Leitung" if line.startswith("Leitung") else
                 "Einzel" if " entfernt" in line else
                 "Verschiebung" if re.search(r"verschoben|um \d", line) else "sonst")
            kinds[k] = kinds.get(k, 0) + 1
        print(f"{name:16} vol {cand.volume:5} -> {small.volume:5}  blocks {cand.block_count:4} -> "
              f"{small.block_count:4}  {dt:5.1f}s  [{spent}]  ok: {kinds}")
        total[0] += cand.volume
        total[1] += small.volume
        total[2] += cand.block_count
        total[3] += small.block_count
    print(f"{'total':16} vol {total[0]:5} -> {total[1]:5}  blocks {total[2]:4} -> {total[3]:4}")


if __name__ == "__main__":
    main()
