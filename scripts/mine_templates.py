"""Offline search for smaller building blocks (task 07): simulated annealing over block layouts.

Start: the working designs `search.redesign` finds for the spec (templates, PLA, compacted). Moves: remove a
block, replace it by a part from a small alphabet, add one next to the circuit, move a block or a port by one
cell, cut a plane. A layout is re-settled (`compact.normalize`) and scored by blocks + volume/20 + 3 per wrong
combination of the fresh-world truth table; only layouts with at most one wrong combination live on. Every new
best working layout is checked in full (transitions), for position robustness (`design.robust`) and whether
its first input can be driven by a line (`decompose.drivable_first`), then written to .cache/mined/.

uv run python scripts/mine_templates.py examples/specs/xor.yaml --minutes 10 [--seed 1] [--max-volume 80]
"""

from __future__ import annotations

import argparse
import math
import pickle
import random
import time
from dataclasses import replace
from pathlib import Path

from redstone.design.candidate import Candidate
from redstone.design.compact import normalize
from redstone.design.evaluate import evaluate
from redstone.design.spec import load
from redstone.model import BlockState, Grid, Pos

ROOT = Path(__file__).parents[1]
OUT = ROOT / ".cache" / "mined"
DIRS = ("north", "east", "south", "west")
ALPHABET = (
    ["stone", "redstone_wire[east=none,north=none,power=0,south=none,west=none]", "redstone_torch[lit=true]"]
    + [f"redstone_wall_torch[facing={d},lit=true]" for d in DIRS]
    + [f"repeater[delay=1,facing={d},locked=false,powered=false]" for d in DIRS]
    + [f"comparator[facing={d},mode={m},powered=false]" for d in DIRS for m in ("compare", "subtract")]
)
AROUND = [Pos(1, 0, 0), Pos(-1, 0, 0), Pos(0, 1, 0), Pos(0, -1, 0), Pos(0, 0, 1), Pos(0, 0, -1)]


def _layout(c: Candidate) -> tuple[dict, list, list]:
    return {p: s for p, s in c.grid.items()}, list(c.inputs), list(c.outputs)


def _build(blocks: dict, ins: list, outs: list, name: str) -> Candidate | None:
    if not blocks:
        return None
    lo = Pos(*(min(p[i] for p in blocks) for i in range(3)))
    hi = Pos(*(max(p[i] for p in blocks) for i in range(3)))
    g = Grid(tuple(h - l + 1 for h, l in zip(hi, lo)))
    for p, s in blocks.items():
        g[p - lo] = s if isinstance(s, BlockState) else BlockState.parse(s)
    c = Candidate(name=name, grid=g, inputs=[p - lo for p in ins], outputs=[p - lo for p in outs],
                  origin="mined")
    try:
        c = normalize(c)
    except Exception:
        return None
    for p in c.inputs:
        if c.grid.get(p).id != "lever":
            return None
    for p in c.outputs:
        if c.grid.get(p).id != "redstone_lamp":
            return None
    return c


def mutate(c: Candidate, rng: random.Random) -> Candidate | None:
    blocks, ins, outs = _layout(c)
    ports = set(ins) | set(outs)
    free = [p for p in blocks if p not in ports]
    kind = rng.choices(["remove", "replace", "add", "move", "port", "cut"], [4, 3, 2, 2, 1, 1])[0]
    if kind == "remove" and free:
        del blocks[rng.choice(free)]
    elif kind == "replace" and free:
        blocks[rng.choice(free)] = rng.choice(ALPHABET)
    elif kind == "add":
        p = rng.choice(list(blocks)) + rng.choice(AROUND)
        if p in blocks:
            return None
        blocks[p] = rng.choice(ALPHABET)
    elif kind in ("move", "port"):
        pool = free if kind == "move" else list(ports)
        if not pool:
            return None
        p = rng.choice(pool)
        q = p + rng.choice(AROUND)
        if q in blocks:
            return None
        blocks[q] = blocks.pop(p)
        ins = [q if x == p else x for x in ins]
        outs = [q if x == p else x for x in outs]
    elif kind == "cut":
        axis = rng.randrange(3)
        ks = sorted({p[axis] for p in blocks})
        k = rng.choice(ks)
        if any(p[axis] == k for p in ports):
            return None

        def mv(p):
            if p[axis] < k:
                return p
            q = list(p)
            q[axis] -= 1
            return Pos(*q)
        blocks = {mv(p): s for p, s in blocks.items() if p[axis] != k}
        ins, outs = [mv(p) for p in ins], [mv(p) for p in outs]
    else:
        return None
    return _build(blocks, ins, outs, c.name)


def wrong(c: Candidate, spec) -> int | None:
    """Wrong combinations of the fresh-world truth table; None if it does not even rest."""
    ev = evaluate(c, spec, full=False)
    if any("Ruhe" in e for e in ev.errors) or any("Anzahl" in e for e in ev.errors):
        return None
    return len(ev.errors)


def score(c: Candidate, w: int) -> float:
    return c.block_count + c.volume / 20 + 3 * w


def key(c: Candidate) -> tuple:
    return (tuple(c.grid.size), tuple(sorted((tuple(p), str(s)) for p, s in c.grid.items())),
            tuple(map(tuple, c.inputs)), tuple(map(tuple, c.outputs)))


def accept_full(c: Candidate, spec) -> tuple[bool, str, Candidate]:
    from redstone.design.decompose import drivable_first
    from redstone.design.robust import check

    ev = evaluate(c, spec)
    if not ev.correct:
        return False, f"volle Prüfung: {ev.errors[0]}", c
    r = check(c, spec, sample=12)
    if not r.ok:
        return False, f"ortsabhängig: {r.findings[0]}", c
    for c2 in _orders(c, spec):  # symmetric functions: any input may be the drivable first one
        if drivable_first(c2, spec):
            return True, f"Verzögerung {ev.max_delay} gt" + ("" if c2 is c else ", Eingänge umsortiert"), c2
    return False, "kein Eingang über eine Leitung ansteuerbar", c


def _orders(c: Candidate, spec):
    """c, then c with another input first wherever swapping that input with the first leaves the table alone."""
    yield c
    n = len(spec.inputs)
    for i in range(1, n):
        def sw(t):
            t = list(t)
            t[0], t[i] = t[i], t[0]
            return tuple(t)
        if all(spec.table.get(sw(k)) == v for k, v in spec.table.items()):
            ins = list(c.inputs)
            ins[0], ins[i] = ins[i], ins[0]
            yield replace(c, inputs=ins)


def starts(spec) -> list[Candidate]:
    """Working designs of `rsx redesign` plus earlier finds for the same spec (.cache/mined/<spec>-*.pickle)."""
    from redstone.design.search import redesign

    out = [r.candidate for r in redesign(spec, compact_budget=100) if r.ok][:6]
    stem = spec.source.removesuffix(".yaml")
    earlier = sorted(OUT.glob(f"{stem}-*.pickle"), key=lambda p: int(p.stem.split("-")[-2]))
    return out + [pickle.loads(p.read_bytes()) for p in earlier[:3]]


def mine(spec, minutes: float, seed: int, max_volume: int, log=print) -> list[tuple[Candidate, str]]:
    from redstone.io import save

    rng = random.Random(seed)
    pool = starts(spec)
    log(f"Start: {[(c.name, c.block_count) for c in pool]}")
    best = min(c.block_count for c in pool)
    found: list[tuple[Candidate, str]] = []
    seen: set = set()
    cur = rng.choice(pool)
    cur_w = 0
    t_end = time.time() + 60 * minutes
    steps = evals = 0
    T0, T1 = 3.0, 0.3
    OUT.mkdir(parents=True, exist_ok=True)
    while time.time() < t_end:
        frac = 1 - (t_end - time.time()) / (60 * minutes)
        T = T0 * (T1 / T0) ** frac
        steps += 1
        if steps % 400 == 0 and rng.random() < 0.3:  # restart from a start design now and then
            cur, cur_w = rng.choice(pool + [c for c, _ in found]), 0
        nxt = mutate(cur, rng)
        if nxt is None or nxt.volume > max_volume:
            continue
        k = key(nxt)
        if k in seen:
            continue
        seen.add(k)
        w = wrong(nxt, spec)
        evals += 1
        if w is None or w > 1:
            continue
        d = score(nxt, w) - score(cur, cur_w)
        if d <= 0 or rng.random() < math.exp(-d / T):
            cur, cur_w = nxt, w
        if w == 0 and nxt.block_count < best:
            ok, why, nxt = accept_full(nxt, spec)
            log(f"  {nxt.block_count} Blöcke {tuple(nxt.grid.size)}: {'Fund' if ok else 'verworfen'} ({why})")
            if ok:
                best = nxt.block_count
                found.append((nxt, why))
                stem = OUT / f"{spec.source.removesuffix('.yaml')}-{nxt.block_count}-{seed}"
                save(nxt.grid, stem.with_suffix(".litematic"))
                stem.with_suffix(".pickle").write_bytes(pickle.dumps(nxt))
    log(f"{steps} Züge, {evals} Bewertungen, bester Fund: {best} Blöcke")
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-volume", type=int, default=80)
    args = ap.parse_args()
    spec = load(args.spec)
    for c, why in mine(spec, args.minutes, args.seed, args.max_volume):
        print(f"{c.block_count} Blöcke, {tuple(c.grid.size)}, {why}, Eingänge {c.inputs}, Ausgänge {c.outputs}")


if __name__ == "__main__":
    main()
