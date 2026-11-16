"""Position and rotation robustness of a design.

Redstone dust updates its neighbours in the order of a Java ``HashSet<BlockPos>`` (DUST-018), which depends on
absolute coordinates. Everything else in the design pipeline simulates with the min corner at the oracle origin
(0, 200, 0). `robust` re-checks a candidate at many origins and in all four rotations about the vertical axis.

Choice of origins: ``hashCode = (y + 31 z) 31 + x``, spread ``h ^ (h >>> 16)``. Modulo 16, 31 = -1 and 961 = 1,
so a step in x, y or z moves the low bits by +1, -1, +1. While ``h >>> 16`` (k) is the same for all cells, the
bucket order in a 16-bucket table only depends on (shift mod 16, k mod 16). Larger sets resize to 32, 64 ...
buckets and see more bits, hence the random origins on top.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..model import Pos
from ..sim.runner import ORACLE_ORIGIN
from .candidate import Candidate
from .compose import rotate
from .evaluate import Constraints, evaluate_any

ANGLES = {0: "ungedreht", 1: "90° gedreht", 2: "180° gedreht", 3: "270° gedreht"}


def origins(sample: int | None = None) -> list[Pos]:
    """About 50 origins covering all 16 low-bit shifts at k = 0, several other k, negative coordinates, a low
    y and random far-away places (fixed seed). With `sample`, an evenly spread subset that keeps the oracle
    origin first."""
    ox, oy, oz = ORACLE_ORIGIN.x, ORACLE_ORIGIN.y, ORACLE_ORIGIN.z
    out = [Pos(ox + dx, oy, oz) for dx in range(16)]
    shifts = (0, 5, 10, 15)
    for j in (1, 2, 5, 11):
        out += [Pos(dx, oy, 68 * j) for dx in shifts]
    out += [Pos(-1000 + dx, oy, -1000) for dx in shifts]
    out += [Pos(dx, 64, 9) for dx in shifts]
    rng = random.Random(26_3)
    out += [Pos(rng.randint(-30_000, 30_000), rng.randint(-40, 250), rng.randint(-30_000, 30_000))
            for _ in range(8)]
    if sample is None or sample >= len(out):
        return out
    step = len(out) / sample
    return [out[int(i * step)] for i in range(sample)]


@dataclass
class Robustness:
    """Result of `check`: how many placements were simulated and what differed."""

    placements: int = 0
    rotations: int = 4  # 1 if the candidate cannot be turned (rails)
    origins: int = 0
    findings: list[str] = field(default_factory=list)
    wrong: int = 0  # placements with a wrong output or no rest
    timing: int = 0  # placements that are correct but settle at a different tick
    runs: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings


def _where(origin: Pos, turns: int) -> str:
    return f"bei Ursprung ({origin.x}, {origin.y}, {origin.z}), {ANGLES[turns]}"


def check(candidate: Candidate, spec, constraints: Constraints | None = None, quick: bool = False,
          sample: int | None = None, stop_early: bool = False, timing: bool = True) -> Robustness:
    """Evaluate the candidate at every origin in `origins(sample)` and in all four rotations. A placement that
    fails the spec is a finding; with `timing`, so is one whose worst delay differs from the oracle placement."""
    res = Robustness()
    turned = [(t, rotate(candidate, t)) for t in range(4)]
    turned = [(t, c) for t, c in turned if c is not None]
    res.rotations = len(turned)
    places = origins(sample)
    res.origins = len(places)
    base = None
    for turns, cand in turned:
        for origin in places:
            ev = evaluate_any(cand, spec, constraints, quick=quick, origin=origin)
            res.placements += 1
            res.runs += ev.runs
            if base is None:
                base = ev.max_delay
            if ev.errors:
                res.wrong += 1
                res.findings.append(f"{_where(origin, turns)}: {ev.errors[0]}")
            elif timing and ev.max_delay != base:
                res.timing += 1
                res.findings.append(f"{_where(origin, turns)}: Verzögerung {ev.max_delay} gt statt {base} gt")
            if stop_early and res.findings:
                return res
    return res


def robust(candidate: Candidate, spec, constraints: Constraints | None = None, quick: bool = False,
           sample: int | None = None, stop_early: bool = False) -> list[str]:
    """German findings for every placement where the candidate behaves differently; empty = position-proof."""
    return check(candidate, spec, constraints, quick, sample, stop_early).findings


def summary(r: Robustness, seconds: float | None = None) -> str:
    """One German line for reports."""
    turns = "in 4 Drehungen" if r.rotations == 4 else "nur ungedreht (Schienen lassen sich nicht drehen)"
    took = f" ({seconds:.1f} s)" if seconds is not None else ""
    if r.ok:
        return f"An {r.origins} Positionen und {turns} im Simulator geprüft: verhält sich überall gleich{took}."
    parts = []
    if r.wrong:
        parts.append(f"{r.wrong} falsch")
    if r.timing:
        parts.append(f"{r.timing} nur mit anderer Verzögerung")
    return (f"Achtung: an {r.origins} Positionen und {turns} geprüft, {r.placements} Lagen, davon "
            f"{', '.join(parts)}. Der Entwurf hängt vom Bauort ab{took}. Erste Abweichung: {r.findings[0]}")


def piston_race() -> Candidate:
    """A deliberately position-dependent design (tests, docs/robustness.md, scenarios/pos-race-*): two pistons
    powered by the same dust push the same lamp, east next to a redstone block (lamp lights) or down (lamp
    stays dark). Which piston fires first follows the dust's HashSet order, i.e. the absolute position."""
    from .templates import _grid_from_layout, _Layout, _settle

    wire = "redstone_wire[east=side,north=side,power=0,south=side,west=side]"
    blocks = {
        (-2, 0, 0): "stone", (-1, 0, 0): "stone", (-2, 1, 0): "lever[face=floor,facing=east,powered=false]",
        (-1, 1, 0): wire, (0, 1, 0): wire,
        (0, 0, 0): "piston[facing=east,extended=false]", (1, 1, 0): "piston[facing=down,extended=false]",
        (1, 0, 0): "redstone_lamp[lit=false]", (2, 0, 0): "air", (3, 0, 0): "redstone_block",
    }
    grid, ins, outs = _grid_from_layout(_Layout(blocks, ((-2, 1, 0),), ((2, 0, 0),)))
    return Candidate(name="piston-race", grid=_settle(grid), inputs=ins, outputs=outs,
                     description="Zwei Kolben am selben Staub schieben dieselbe Lampe (absichtlich ortsabhängig).",
                     origin="test")


def plan(candidate: Candidate, spec, constraints: Constraints | None = None, budget: float = 5.0,
         quick_inputs: int = 6) -> tuple[bool, int | None]:
    """(quick, sample) so that `check` takes about `budget` seconds: one timed evaluation at the oracle origin
    decides how many origins fit (at least 4, all four rotations always). Designs with more than
    `quick_inputs` inputs get the quick check (each combination from a fresh world)."""
    import time

    quick = len(candidate.inputs) > quick_inputs
    t0 = time.perf_counter()
    evaluate_any(candidate, spec, constraints, quick=quick)
    per = max(time.perf_counter() - t0, 1e-4)
    fit = int(budget / (4 * per))
    total = len(origins())
    return quick, None if fit >= total else max(4, fit)
