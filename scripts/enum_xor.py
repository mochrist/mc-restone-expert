"""Enumerate compact two-comparator XOR layouts and check them in the simulator (task 07).

Lamp at the origin; each subtracting comparator powers the lamp or a block next to it. Each lever is the rear
input of one comparator (directly or through the block it hangs on) and feeds the side of the other one with
dust next to the lever or its block, or with a repeater behind a dust path of up to K cells. Working layouts
(full check, position robustness, drivable input) are the seeds that scripts/mine_templates.py shrank to the
17-block xor2-stacked.

uv run python scripts/enum_xor.py [max_blocks=21] [out.pkl] [K=2]
"""
import itertools, sys, pickle
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from redstone.design.templates import _Layout, _grid_from_layout, _settle, STONE, LAMP, WIRE, REPEATER, COMPARATOR
from redstone.design.candidate import Candidate
from redstone.design.evaluate import evaluate
from redstone.design.spec import load
import mine_templates as mt

MAXB = int(sys.argv[1]) if len(sys.argv) > 1 else 21
HD = {(1, 0, 0): "east", (-1, 0, 0): "west", (0, 0, 1): "south", (0, 0, -1): "north"}
ALL6 = list(HD) + [(0, 1, 0), (0, -1, 0)]
add = lambda a, b: (a[0] + b[0], a[1] + b[1], a[2] + b[2])
sub = lambda a, b: (a[0] - b[0], a[1] - b[1], a[2] - b[2])
neg = lambda a: (-a[0], -a[1], -a[2])
L = (0, 0, 0)


def lever_state(w):  # w: direction from lever to the block it hangs on
    if w == (0, -1, 0):
        return "lever[face=floor,facing=north,powered=false]"
    if w == (0, 1, 0):
        return "lever[face=ceiling,facing=north,powered=false]"
    return f"lever[face=wall,facing={HD[neg(w)]},powered=false]"


def placements():
    out = []
    for d in HD:  # straight into the lamp
        out.append((sub(L, d), d, None))
    for u in ALL6:  # into a stone next to the lamp
        T = add(L, u)
        for d in HD:
            p = sub(T, d)
            if p != L:
                out.append((p, d, T))
    return out


def rears(r):
    """(cells, lever cell, strong cells) for a lever feeding rear cell r."""
    for w in ALL6:
        yield {r: lever_state(w), add(r, w): STONE}, r, {r, add(r, w)}
        q = add(r, w)
        yield {r: STONE, q: lever_state(neg(w))}, q, {r, q}


def perp(d):
    return [e for e in HD if e != d and e != neg(d)]


K = int(sys.argv[3]) if len(sys.argv) > 3 else 2


def paths(srcs, k):
    """Dust paths (tuples of cells) of length 1..k, the first cell next to a source, horizontal steps."""
    frontier = [(add(x, w),) for x in srcs for w in ALL6 if add(x, w) not in srcs]
    out = list(frontier)
    for _ in range(k - 1):
        nxt = []
        for p in frontier:
            for e in HD:
                q = add(p[-1], e)
                if q not in p and q not in srcs and all(sub(q, x) not in ALL6 for x in srcs):
                    nxt.append(p + (q,))
        out += nxt
        frontier = nxt
    return out


def feeds(c, d, lever, strong):
    srcs = strong | {lever}
    ps = paths(srcs, K)
    for e in perp(d):
        s = add(c, e)
        if any(sub(s, x) in ALL6 for x in srcs):
            yield {s: WIRE}
        q = add(s, e)
        if q in srcs:
            yield {s: REPEATER(HD[e])}
        for p in ps:
            if p[-1] == q and s not in p and c not in p:
                f = {x: WIRE for x in p}
                f[s] = REPEATER(HD[e])
                yield f


def merge(a, b):
    for k, v in b.items():
        if k in a and a[k] != v:
            if a[k] == STONE and v == STONE:
                continue
            return None
    r = dict(a); r.update(b); return r


NEEDS = ("redstone_wire", "repeater", "comparator")


def supported(blocks):
    out = dict(blocks)
    for p, s in blocks.items():
        if s.startswith(NEEDS) or "face=floor" in s:
            below = add(p, (0, -1, 0))
            if below not in out:
                out[below] = STONE
            elif not (out[below] == STONE or out[below] == LAMP):
                return None
    return out


def main():
    spec = load("examples/specs/xor.yaml")
    P = placements()
    seen, cands = set(), []
    for (c1, d1, t1), (c2, d2, t2) in itertools.permutations(P, 2):
        if c1 == c2:
            continue
        base = {L: LAMP, c1: COMPARATOR(HD[neg(d1)]), c2: COMPARATOR(HD[neg(d2)])}
        for t in (t1, t2):
            if t is not None:
                if t in base:
                    base = None; break
                base[t] = STONE
        if base is None:
            continue
        for ra, la, sa in rears(sub(c1, d1)):
            b1 = merge(base, ra)
            if b1 is None:
                continue
            for rb, lb, sb in rears(sub(c2, d2)):
                if lb == la:
                    continue
                b2 = merge(b1, rb)
                if b2 is None:
                    continue
                for fa in feeds(c2, d2, la, sa):  # A into the side of C2
                    b3 = merge(b2, fa)
                    if b3 is None:
                        continue
                    for fb in feeds(c1, d1, lb, sb):
                        b4 = merge(b3, fb)
                        if b4 is None:
                            continue
                        full = supported(b4)
                        if full is None or len(full) > MAXB:
                            continue
                        key = frozenset(full.items()), la, lb
                        if key in seen:
                            continue
                        seen.add(key)
                        cands.append((len(full), full, la, lb))
    cands.sort(key=lambda t: t[0])
    print(len(cands), "layouts up to", MAXB, "blocks; sizes", sorted({c[0] for c in cands}))
    good = []
    for n, full, la, lb in cands:
        try:
            g, ins, outs = _grid_from_layout(_Layout(full, (la, lb), (L,)))
            g = _settle(g)
        except Exception:
            continue
        c = Candidate(name="xor", grid=g, inputs=ins, outputs=outs, origin="enum")
        if not evaluate(c, spec, full=False, stop_early=True).correct:
            continue
        ok, why, c2 = mt.accept_full(c, spec)
        print(n, tuple(c.grid.size), ok, why, flush=True)
        if ok:
            good.append((n, full, la, lb))
            if len(good) >= 15:
                break
    pickle.dump(good, open(sys.argv[2] if len(sys.argv) > 2 else ".cache/mined/enum-xor.pkl", "wb"))


main()
