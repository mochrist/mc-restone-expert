"""Evaluate a candidate against a spec and constraints, by simulation only.

A candidate is correct when, for every input combination,
1. starting from the stored state (all levers off) and switching the levers on at tick 1, the outputs settle
   at the values of the truth table, and
2. starting from that settled state, toggling any single lever settles at the row of the new combination.
(2) catches designs that only work from a fresh world (stuck latches, races).
Delays are measured from the lever change to the last output change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..analysis.experiment import Circuit, Recording
from ..model import Pos
from ..sim.runner import ORACLE_ORIGIN
from ..sim.notes import notes_of
from . import parallel
from .candidate import Candidate
from .spec import Spec

MAX_TICKS = 200
QUIET = 12
TRANSITIONS = "half"  # "all": every lever from every combination; "half": only levers that are off (see _check_transitions)
GAP = 40  # minimum ticks between successive lever changes in a transition run (see _check_transitions)

# Blocks that form the interface of a candidate; not subject to the allowed/forbidden block lists.
INTERFACE = {"lever", "redstone_lamp"}


@dataclass
class Constraints:
    max_size: tuple[int, int, int] | None = None  # (x, y, z); x and z may be swapped (rotation)
    allowed_blocks: set[str] | None = None  # block ids without "minecraft:", None = everything
    forbidden_blocks: set[str] = field(default_factory=set)
    allow_qc: bool = True
    max_delay: int | None = None  # overrides spec.max_delay

    def describe(self) -> str:
        parts = []
        if self.max_size:
            parts.append("max. {}×{}×{}".format(*self.max_size))
        if self.allowed_blocks is not None:
            parts.append("nur " + ", ".join(sorted(self.allowed_blocks)))
        if self.forbidden_blocks:
            parts.append("ohne " + ", ".join(sorted(self.forbidden_blocks)))
        if not self.allow_qc:
            parts.append("ohne Quasi-Connectivity")
        if self.max_delay is not None:
            parts.append(f"Verzögerung ≤ {self.max_delay} gt")
        return ", ".join(parts) or "keine"


@dataclass
class Evaluation:
    candidate: Candidate
    correct: bool = False
    violations: list[str] = field(default_factory=list)  # constraint violations, German
    errors: list[str] = field(default_factory=list)  # wrong outputs, German
    max_delay: int | None = None
    mechanics: set[str] = field(default_factory=set)  # note kinds seen during the runs (qc, bud, ...)
    runs: int = 0
    ticks: int = 0  # simulated ticks over all runs

    @property
    def ok(self) -> bool:
        return self.correct and not self.violations

    def rank_key(self) -> tuple:
        c = self.candidate
        return (not self.ok, len(self.errors), c.volume, c.block_count,
                self.max_delay if self.max_delay is not None else 999)


def _block_ids(candidate: Candidate) -> set[str]:
    return {s.id for _, s in candidate.grid.items()}


def check_constraints(candidate: Candidate, constraints: Constraints) -> list[str]:
    out = []
    if constraints.max_size:
        mx, my, mz = constraints.max_size
        x, y, z = candidate.size
        if not (y <= my and ((x <= mx and z <= mz) or (z <= mx and x <= mz))):
            out.append(f"Größe {x}×{y}×{z} passt nicht in {mx}×{my}×{mz}")
    # a wall torch is the same item as a torch: allowing or forbidding one means both
    ids = {i.replace("_wall_torch", "_torch") for i in _block_ids(candidate) - INTERFACE}
    if constraints.allowed_blocks is not None:
        extra = ids - constraints.allowed_blocks
        if extra:
            out.append("nicht erlaubte Blöcke: " + ", ".join(sorted(extra)))
    bad = ids & constraints.forbidden_blocks
    if bad:
        out.append("verbotene Blöcke: " + ", ".join(sorted(bad)))
    if not constraints.allow_qc and "qc" in candidate.tags:
        out.append("nutzt Quasi-Connectivity")
    return out


def _outputs_at(rec: Recording, candidate: Candidate, tick: int) -> tuple[bool, ...]:
    return tuple(rec.on_at(p, tick) if p in rec.series else False for p in candidate.outputs)


def _last_change(rec: Recording, candidate: Candidate, start: int, end: int) -> int | None:
    last = None
    for p in candidate.outputs:
        for t, _ in rec.series.get(p, [])[1:]:
            if start <= t <= end:
                last = t if last is None else max(last, t)
    return None if last is None else last - start


def _stored(candidate: Candidate) -> tuple[bool, ...]:
    """Lever states as stored in the grid (templates store all levers off; originals may not)."""
    return tuple(candidate.grid.get(p).get_bool("powered") for p in candidate.inputs)


def _fmt(names: list[str], combo: tuple[bool, ...]) -> str:
    return ", ".join(f"{n}={'1' if b else '0'}" for n, b in zip(names, combo))


def _run(circuit: Circuit, actions: list, max_ticks: int) -> tuple[Recording, set[str]]:
    """One run from a fresh world: the recording and the kinds of mechanics notes."""
    world = circuit.new_world()
    rec = circuit.run(actions, max_ticks=max_ticks, quiet=QUIET, world=world)
    return rec, {n.kind for n in notes_of(world)}


def evaluate(candidate: Candidate, spec: Spec, constraints: Constraints | None = None,
             full: bool = True, stop_early: bool = False, origin: Pos = ORACLE_ORIGIN) -> Evaluation:
    """Simulate the candidate. With full=False only the fresh-world truth table is checked (cheap prefilter);
    with stop_early the checks end at the first wrong output (enough to reject a candidate)."""
    constraints = constraints or Constraints()
    ev = Evaluation(candidate, violations=check_constraints(candidate, constraints))
    if len(candidate.inputs) != len(spec.inputs) or len(candidate.outputs) != len(spec.outputs):
        ev.errors.append("Anzahl der Ein- oder Ausgänge passt nicht zur Spezifikation")
        return ev
    circuit = Circuit(candidate.grid, origin)
    delays: list[int] = []

    # Idle: the stored state must be at rest (no clock) and show the row for all levers off.
    world = circuit.new_world()
    rec = circuit.run([], max_ticks=MAX_TICKS, quiet=QUIET, world=world)
    ev.runs += 1
    ev.ticks += rec.ticks
    stored = _stored(candidate)
    zero = stored
    if rec.settled_at is None:
        ev.errors.append("kommt ohne Eingabe nicht zur Ruhe")
        return ev
    if zero in spec.table and _outputs_at(rec, candidate, rec.ticks) != spec.table[zero]:
        ev.errors.append(f"falscher Ruhezustand bei {_fmt(spec.inputs, zero)}")

    todo = []
    for combo in spec.combos():
        actions = [(1, p, "use") for p, on, st in zip(candidate.inputs, combo, stored) if on != st]
        if actions:
            todo.append((combo, actions, MAX_TICKS))
    # the runs are independent: side by side in threads (`parallel`), looked at in this order
    runs = parallel.ordered(lambda job: _run(circuit, job[1], job[2]), todo)
    for combo, _, _ in todo:
        if stop_early and ev.errors:
            runs.close()  # drops the runs started ahead
            break
        rec, kinds = next(runs)
        ev.runs += 1
        ev.ticks += rec.ticks
        ev.mechanics |= kinds
        if rec.settled_at is None:
            ev.errors.append(f"kommt bei {_fmt(spec.inputs, combo)} nicht zur Ruhe")
            continue
        got = _outputs_at(rec, candidate, rec.ticks)
        if got != spec.table[combo]:
            ev.errors.append(f"bei {_fmt(spec.inputs, combo)}: Ausgang {_fmt(spec.outputs, got)}, "
                             f"erwartet {_fmt(spec.outputs, spec.table[combo])}")
        d = _last_change(rec, candidate, 1, rec.ticks)
        if d is not None:
            delays.append(d)

    if full and not ev.errors:
        _check_transitions(candidate, spec, circuit, ev, delays)

    ev.correct = not ev.errors
    ev.max_delay = max(delays) if delays else 0
    limit = constraints.max_delay if constraints.max_delay is not None else spec.max_delay
    if limit is not None and ev.max_delay > limit:
        ev.violations.append(f"Verzögerung {ev.max_delay} gt > erlaubt {limit} gt")
    if not constraints.allow_qc and "quasi_connectivity" in ev.mechanics:
        ev.violations.append("nutzt Quasi-Connectivity")
    return ev


def _check_transitions(candidate: Candidate, spec: Spec, circuit: Circuit, ev: Evaluation,
                       delays: list[int]) -> None:
    """From every combination, toggle each lever that is off there and back, one after another in a single run,
    and check the settled outputs after every change.

    Every directed transition "combination c, lever i switched" is checked exactly once: the way there from the
    combination with lever i off, the way back from the one with lever i on (reached by that very switch). Toggling
    the levers that are on as well (TRANSITIONS = "all") checks each transition twice and costs twice the ticks."""
    n = len(spec.inputs)
    half = TRANSITIONS == "half"
    stored = _stored(candidate)
    # slow designs (long chains of parts) get more time per change: twice their delay from a fresh world
    gap = max(GAP, 2 * max(delays, default=0) + QUIET)
    todo = []  # (combination, actions, max ticks, phases)
    for combo in spec.combos():
        actions = [(1, p, "use") for p, on, st in zip(candidate.inputs, combo, stored) if on != st]
        phases = []  # (start tick, expected combination, label)
        t = 1
        for i in range(n):
            if half and combo[i]:
                continue  # checked from the combination with lever i off
            flipped = tuple(not b if j == i else b for j, b in enumerate(combo))
            if flipped not in spec.table:
                continue  # a combination that does not matter (partial spec)
            for want in (flipped, combo):
                t += gap
                actions.append((t, candidate.inputs[i], "use"))
                phases.append((t, want, spec.inputs[i]))
        if not phases and half:
            continue  # nothing to switch (all levers on); the fresh world was checked in evaluate
        todo.append((combo, actions, t + MAX_TICKS, phases))
    # independent runs side by side (`parallel`), looked at in this order; the first error ends the check
    runs = parallel.ordered(lambda job: _run(circuit, job[1], job[2]), todo)
    try:
        _transition_results(candidate, spec, ev, delays, gap, todo, runs)
    finally:
        runs.close()  # drops the runs started ahead


def _transition_results(candidate: Candidate, spec: Spec, ev: Evaluation, delays: list[int], gap: int,
                        todo: list, runs) -> None:
    for combo, _, _, phases in todo:
        rec, kinds = next(runs)
        ev.runs += 1
        ev.ticks += rec.ticks
        ev.mechanics |= kinds
        ends = [p[0] - 1 for p in phases[1:]] + [rec.ticks]
        for (start, want, name), end in zip(phases, ends):
            got = _outputs_at(rec, candidate, end)
            if got != spec.table[want]:
                ev.errors.append(f"Übergang ab {_fmt(spec.inputs, combo)}, {name} umgelegt: "
                                 f"Ausgang {_fmt(spec.outputs, got)}, erwartet {_fmt(spec.outputs, spec.table[want])}")
                return
            last = _last_change(rec, candidate, start, end)
            if last is not None:
                delays.append(last)
                if end != rec.ticks and last > gap - QUIET:
                    ev.errors.append(f"Übergang ab {_fmt(spec.inputs, combo)}, {name} umgelegt: "
                                     f"Ausgang kommt erst nach {last} gt zur Ruhe")
                    return
        if rec.settled_at is None:
            ev.errors.append(f"Übergang ab {_fmt(spec.inputs, combo)}: kommt nicht zur Ruhe")
            return


def observe(candidate: Candidate, combos: list[tuple[bool, ...]],
            origin: Pos = ORACLE_ORIGIN) -> dict[tuple[bool, ...], tuple[bool, ...]]:
    """Settled outputs of the candidate for each lever combination, each from a fresh world (like `evaluate`).
    Raises ValueError if a combination does not come to rest."""
    circuit = Circuit(candidate.grid, origin)
    stored = _stored(candidate)
    out = {}
    for combo in combos:
        actions = [(1, p, "use") for p, on, st in zip(candidate.inputs, combo, stored) if on != st]
        rec = circuit.run(actions, max_ticks=MAX_TICKS, quiet=QUIET, world=circuit.new_world())
        if rec.settled_at is None:
            raise ValueError(f"kommt bei {combo} nicht zur Ruhe")
        out[combo] = _outputs_at(rec, candidate, rec.ticks)
    return out


def evaluate_any(candidate: Candidate, spec, constraints: Constraints | None = None, quick: bool = False,
                 origin: Pos = ORACLE_ORIGIN) -> Evaluation:
    """Evaluate against a truth-table Spec or a BehaviourSpec. quick = cheap rejection run."""
    from .behaviour import BehaviourSpec, evaluate_behaviour

    if isinstance(spec, BehaviourSpec):
        return evaluate_behaviour(candidate, spec, constraints, stop_early=True, origin=origin)
    if quick:
        return evaluate(candidate, spec, constraints, full=False, stop_early=True, origin=origin)
    return evaluate(candidate, spec, constraints, origin=origin)
