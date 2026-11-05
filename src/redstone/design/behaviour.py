"""Behavioural specs: circuits with timing or memory (pulse extender, monostable, T flip-flop, latch, clock).

A spec is a set of trials. A trial applies input actions at given ticks (lever toggle or button press) in a
fresh world and lists the expected on-intervals of every output. A candidate meets the spec when every
output shows the same number of on-intervals in every trial, each starting and ending within the
tolerances. For clocks (`periodic`), only period and on-time are compared, not the phase.

Specs come from constructors for the usual building blocks (`monostable`, `pulse_extender`, `t_flip_flop`,
`rs_latch`, `clock`, `delay_line`), from YAML (`from_dict`) or from the recorded behaviour of an existing
circuit (`from_recordings`).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from ..analysis.experiment import Circuit, Recording
from ..sim.notes import notes_of
from .candidate import Candidate
from .evaluate import Constraints, Evaluation, check_constraints

Interval = tuple[int, int | None]  # [start, end) in ticks; end None = still on when the trial ends
QUIET = 12
MAX_TICKS = 600


@dataclass
class Trial:
    name: str  # German, e.g. "Puls 3 gt"
    actions: list[tuple[int, int]]  # (tick, input index): lever toggle or button press
    expected: list[list[Interval]]  # per output
    length: int | None = None  # fixed number of ticks (clocks); None = until idle after the last action
    periodic: bool = False


@dataclass
class BehaviourSpec:
    inputs: list[str]
    input_kinds: list[str]  # "lever" or "button" per input
    outputs: list[str]
    trials: list[Trial]
    kind: str = ""  # German summary, e.g. "Monoflop: 10-gt-Puls bei steigender Flanke"
    delay_tolerance: int = 4  # an edge may come this many gt early or late
    length_tolerance: int = 0  # a pulse may be this many gt longer or shorter
    source: str = ""
    notes: list[str] = field(default_factory=list)

    def describe(self) -> str:
        return self.kind or f"{len(self.trials)} Testabläufe"


# ---------------------------------------------------------------------- matching
def intervals(rec: Recording, pos, until: int, off_delay: int = 0) -> list[Interval]:
    """On-intervals of a block up to `until`; `off_delay` (lamp: 4 gt) is taken off every end so that the
    intervals describe the signal, not the lamp."""
    if pos not in rec.series:
        return []
    out = []
    for a, b in rec.on_intervals(pos):
        if a > until:
            break
        out.append((a, b - off_delay if b is not None and b <= until else None))
    return out


def _off_delay(grid, pos) -> int:
    from ..analysis.patterns import OFF_DELAY

    return OFF_DELAY.get(grid.get(pos).id, 0)


def _match_intervals(got: list[Interval], want: list[Interval], spec: BehaviourSpec) -> str | None:
    """None if equal within tolerance, else a German reason."""
    if len(got) != len(want):
        return f"{len(got)} statt {len(want)} An-Phasen"
    for (ga, gb), (wa, wb) in zip(got, want):
        if abs(ga - wa) > spec.delay_tolerance:
            return f"An-Phase beginnt bei {ga} statt {wa}"
        if (gb is None) != (wb is None):
            return "bleibt an" if gb is None else f"geht bei {gb} aus, sollte an bleiben"
        if gb is not None:
            if abs(gb - wb) > spec.delay_tolerance + spec.length_tolerance:
                return f"An-Phase endet bei {gb} statt {wb}"
            if abs((gb - ga) - (wb - wa)) > spec.length_tolerance:
                return f"Pulslänge {gb - ga} statt {wb - wa} gt"
    return None


def _periodic(iv: list[Interval]) -> tuple[int, int] | None:
    closed = [(a, b) for a, b in iv if b is not None]
    if len(closed) < 4:
        return None
    starts = [a for a, _ in closed[1:]]
    periods = {b - a for a, b in zip(starts, starts[1:])}
    ons = {b - a for a, b in closed[1:]}
    if len(periods) != 1 or len(ons) != 1:
        return None
    return periods.pop(), ons.pop()


def evaluate_behaviour(candidate: Candidate, spec: BehaviourSpec, constraints: Constraints | None = None,
                       stop_early: bool = True) -> Evaluation:
    constraints = constraints or Constraints()
    ev = Evaluation(candidate, violations=check_constraints(candidate, constraints))
    if len(candidate.inputs) != len(spec.inputs) or len(candidate.outputs) != len(spec.outputs):
        ev.errors.append("Anzahl der Ein- oder Ausgänge passt nicht zur Spezifikation")
        return ev
    for p, kind in zip(candidate.inputs, spec.input_kinds):
        sid = candidate.grid.get(p).id
        if (kind == "button") != sid.endswith("_button"):
            ev.errors.append(f"Eingang bei {p} ist {sid}, erwartet {kind}")
            return ev
    circuit = Circuit(candidate.grid)
    worst = 0
    for trial in spec.trials:
        actions = [(t, candidate.inputs[i], "use") for t, i in trial.actions]
        world = circuit.new_world(kick=trial.periodic)
        if trial.length is not None:
            rec = circuit.run(actions, max_ticks=trial.length, quiet=10 ** 6, world=world)
            until = trial.length
        else:
            last = max((t for t, _ in trial.actions), default=0)
            rec = circuit.run(actions, max_ticks=last + MAX_TICKS, quiet=QUIET, world=world)
            until = rec.ticks
            if rec.settled_at is None:
                ev.errors.append(f"{trial.name}: kommt nicht zur Ruhe")
                if stop_early:
                    break
                continue
        ev.runs += 1
        ev.mechanics |= {n.kind for n in notes_of(world)}
        for j, pos in enumerate(candidate.outputs):
            got = intervals(rec, pos, until, _off_delay(candidate.grid, pos))
            want = trial.expected[j]
            if trial.periodic:
                g, w = _periodic(got), _periodic(want)
                reason = None if g == w else f"Takt {g} statt {w} (Periode, An-Zeit)"
            else:
                reason = _match_intervals(got, want, spec)
                for (ga, _), (wa, _) in zip(got, want):
                    worst = max(worst, ga - wa)
            if reason:
                ev.errors.append(f"{trial.name}, {spec.outputs[j]}: {reason}")
                if stop_early:
                    break
        if ev.errors and stop_early:
            break
    ev.correct = not ev.errors
    ev.max_delay = worst  # extra delay compared with the spec (negative = faster)
    if not constraints.allow_qc and "quasi_connectivity" in ev.mechanics:
        ev.violations.append("nutzt Quasi-Connectivity")
    return ev


# ---------------------------------------------------------------------- constructors
LEVER_PULSES = (1, 2, 3, 5, 10, 20, 40)
START = 2  # first action; tick 0/1 show the stored state


def _lever_pulse(i: int, length: int, at: int = START) -> list[tuple[int, int]]:
    return [(at, i), (at + length, i)]


def monostable(length: int, delay: int = 0, tolerance: int = 4, kind: str = "lever") -> BehaviourSpec:
    """Rising edge -> one pulse of exactly `length` gt, whatever the input pulse length."""
    trials = []
    if kind == "button":
        trials.append(Trial("Knopfdruck", [(START, 0)], [[(START + delay, START + delay + length)]]))
    else:
        for p in LEVER_PULSES:
            trials.append(Trial(f"Hebel {p} gt an", _lever_pulse(0, p),
                                [[(START + delay, START + delay + length)]]))
    return BehaviourSpec(["in"], [kind], ["out"], trials,
                         f"Monoflop: {length}-gt-Puls bei steigender Flanke", tolerance)


def pulse_extender(length: int, delay: int = 0, tolerance: int = 4) -> BehaviourSpec:
    """Output on from the rising edge until max(input length, `length`) gt later (lever input)."""
    trials = [Trial(f"Hebel {p} gt an", _lever_pulse(0, p),
                    [[(START + delay, START + delay + max(p, length))]]) for p in LEVER_PULSES]
    return BehaviourSpec(["in"], ["lever"], ["out"], trials,
                         f"Pulsverlängerer: Ausgang mindestens {length} gt an", tolerance)


def delay_line(delay: int, tolerance: int = 0) -> BehaviourSpec:
    trials = [Trial(f"Hebel {p} gt an", _lever_pulse(0, p), [[(START + delay, START + delay + p)]])
              for p in (2, 3, 5, 10, 20, 40)]
    return BehaviourSpec(["in"], ["lever"], ["out"], trials, f"Verzögerung um {delay} gt", tolerance,
                         length_tolerance=0)


def t_flip_flop(delay: int = 2, tolerance: int = 4, kind: str = "lever", gap: int = 30) -> BehaviourSpec:
    """Output toggles on every rising edge. Lever: on/off pairs; button: presses."""
    if kind == "button":
        presses = [START + k * gap for k in range(4)]
        actions = [(t, 0) for t in presses]
        rises = presses
    else:
        rises = [START + k * gap for k in range(4)]
        actions = [a for t in rises for a in ((t, 0), (t + 10, 0))]
    expected = [(rises[0] + delay, rises[1] + delay), (rises[2] + delay, rises[3] + delay)]
    return BehaviourSpec(["in"], [kind], ["out"], [Trial("vier Flanken", actions, [expected])],
                         "T-Flip-Flop: schaltet bei jeder steigenden Flanke um", tolerance)


def rs_latch(delay: int = 2, tolerance: int = 4, kind: str = "button", gap: int = 30) -> BehaviourSpec:
    """Inputs set, reset (short pulses). Output on after set until reset; repeated set/reset is idempotent."""
    def press(i, t):
        return [(t, i)] if kind == "button" else [(t, i), (t + 2, i)]

    s1, s2, r1, r2 = START, START + gap, START + 2 * gap, START + 3 * gap
    trials = [
        Trial("setzen, setzen, rücksetzen, rücksetzen", press(0, s1) + press(0, s2) + press(1, r1) + press(1, r2),
              [[(s1 + delay, r1 + delay)]]),
        Trial("rücksetzen im Ruhezustand", press(1, s1), [[]]),
    ]
    return BehaviourSpec(["set", "reset"], [kind, kind], ["out"], trials,
                         "RS-Latch: set schaltet ein, reset schaltet aus", tolerance)


def clock(period: int, on_ticks: int, length: int = 200) -> BehaviourSpec:
    """Runs by itself (started by one block update); compares period and on-time only."""
    iv, t = [], 0
    while t < length:
        iv.append((t, t + on_ticks))
        t += period
    return BehaviourSpec([], [], ["out"], [Trial("Takt", [], [iv], length=length, periodic=True)],
                         f"Clock: Periode {period} gt, {on_ticks} gt an")


CONSTRUCTORS = {
    "monostable": monostable, "pulse-extender": pulse_extender, "delay": delay_line,
    "t-flip-flop": t_flip_flop, "rs-latch": rs_latch, "clock": clock,
}


def from_dict(d: dict, source: str = "") -> BehaviourSpec:
    """YAML form: `behaviour: monostable` plus the constructor's parameters, e.g. `length: 10`."""
    params = {k: v for k, v in d.items() if k not in ("behaviour", "delay_tolerance")}
    spec = CONSTRUCTORS[d["behaviour"]](**params)
    if "delay_tolerance" in d:
        spec.delay_tolerance = int(d["delay_tolerance"])
    spec.source = source
    return spec


def from_recordings(names_in: list[str], kinds: list[str], names_out: list[str], circuit: Circuit,
                    out_positions, in_positions, title: str = "", tolerance: int = 4) -> BehaviourSpec:
    """Record the standard stimuli on an existing circuit and use its outputs as the expected behaviour."""
    trials: list[Trial] = []

    def pulse(i: int, at: int, length: int) -> list[tuple[int, int]]:
        return [(at, i)] if kinds[i] == "button" else _lever_pulse(i, length, at)

    stimuli: list[tuple[str, list[tuple[int, int]]]] = []
    for i, kind in enumerate(kinds):
        if kind == "button":
            stimuli.append((f"{names_in[i]} gedrückt", pulse(i, START, 0)))
            stimuli.append((f"{names_in[i]} zweimal gedrückt", pulse(i, START, 0) + pulse(i, START + 40, 0)))
        else:
            stimuli += [(f"{names_in[i]} {p} gt an", pulse(i, START, p)) for p in LEVER_PULSES]
            stimuli.append((f"{names_in[i]} zweimal 5 gt an", pulse(i, START, 5) + pulse(i, START + 40, 5)))
    # memory between inputs: pulse i, later pulse j (e.g. set then reset)
    for i, j in itertools.permutations(range(len(kinds)), 2):
        stimuli.append((f"{names_in[i]}, dann {names_in[j]}", pulse(i, START, 5) + pulse(j, START + 40, 5)))
    # inputs held together (combinational overlap)
    if len(kinds) > 1 and all(k == "lever" for k in kinds):
        stimuli.append(("alle Hebel zusammen 20 gt an", [a for i in range(len(kinds)) for a in pulse(i, START, 20)]))
    skipped = []
    for label, actions in stimuli:
        acts = [(t, in_positions[k], "use") for t, k in actions]
        last = max(t for t, _ in actions)
        rec = circuit.run(acts, max_ticks=last + MAX_TICKS, quiet=QUIET)
        if rec.settled_at is None:
            skipped.append(label)
            continue
        trials.append(Trial(label, actions, [intervals(rec, p, rec.ticks, _off_delay(circuit.grid, p))
                                             for p in out_positions]))
    if not trials:
        raise ValueError("Die Schaltung kommt bei keinem Testablauf zur Ruhe; Verhalten nicht aufzeichenbar")
    spec = BehaviourSpec(names_in, kinds, names_out, trials,
                         "gemessenes Verhalten (Pulse je Eingang, Eingangspaare)", tolerance,
                         source=f"Analyse von {title}" if title else "Analyse")
    if skipped:
        spec.notes.append("Nicht aufgezeichnet, weil die Schaltung danach nicht zur Ruhe kommt: " + ", ".join(skipped))
    return spec
