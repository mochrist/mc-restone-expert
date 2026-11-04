"""Behavioural analysis of a circuit through simulation experiments.

Experiments (all in the simulator, which is validated against the real game):
1. Leerlauf: nothing is touched. Does anything move? (clock running as stored)
2. Anstoß: every block gets one neighbour update. Does a stored-but-stopped clock start?
3. Per input: lever toggled 4 times (on/off/on/off) or button pressed 3 times, each time waiting
   until the circuit is idle. Yields delays, pulse lengths, edge reactions, toggling.
4. Truth table for 2-4 levers: every combination in a fresh world.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from ..model import Grid, Pos
from ..sim.notes import Note, notes_of
from .experiment import Circuit, Recording, is_on
from .patterns import Latch, PulseResponse, find_latches, is_decoder, pulse_response
from .ports import Port, find_ports

MAX_TICKS = 400
QUIET = 12


@dataclass
class Step:
    tick: int
    label: str  # e.g. "in1 an", "in1 aus", "in1 gedrückt"


@dataclass
class OutputReaction:
    output: Port
    events: list[tuple[int, bool]]  # (tick, on) for every change of the output
    steady_after: list[bool]  # output state when idle after each step
    delays: list[int | None]  # first output change after each step, relative to the step
    pulses: list[int]  # lengths of on-intervals that ended before the next step
    kind: str = ""  # classification, German
    detail: str = ""


@dataclass
class InputResponse:
    input: Port
    steps: list[Step]
    recording: Recording
    reactions: list[OutputReaction]
    chain: list[tuple[int, Pos, str, str, str]]  # (dt, pos, block id, old, new) after the first step
    oscillates: bool = False


@dataclass
class ClockInfo:
    period: int
    on_ticks: int
    needs_start: bool
    observed_at: Pos


@dataclass
class Analysis:
    grid: Grid
    inputs: list[Port]
    outputs: list[Port]
    baseline: Recording
    clock: ClockInfo | None
    responses: list[InputResponse] = field(default_factory=list)
    truth_table: list[tuple[tuple[bool, ...], tuple[bool, ...]]] | None = None
    gates: dict[str, str] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)
    pulse_responses: list[PulseResponse] = field(default_factory=list)
    latches: list[Latch] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)  # recognised building blocks, German
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------- experiments
def _run_steps(circuit: Circuit, pos: Pos, kind: str, name: str) -> tuple[Recording, list[Step], list[Note], bool]:
    """Apply input actions one after another, each once the circuit is idle."""
    labels = ["an", "aus", "an", "aus"] if kind == "lever" else ["gedrückt"] * 3
    steps: list[Step] = []
    actions: list = []
    next_tick = 1  # tick 0 shows the stored state before anything is touched
    rec, world = None, None
    for label in labels:
        steps.append(Step(next_tick, f"{name} {label}"))
        actions.append((next_tick, pos, "use"))
        # Replay from scratch with all actions so far (deterministic) until idle again.
        world = circuit.new_world()
        rec = circuit.run(list(actions), max_ticks=next_tick + MAX_TICKS, quiet=QUIET, world=world)
        if rec.settled_at is None:
            return rec, steps, notes_of(world), True
        next_tick = rec.ticks + 1
    return rec, steps, notes_of(world), False


def _clock_from(rec: Recording, positions: list[Pos]) -> tuple[int, int, Pos] | None:
    for pos in positions + sorted(rec.series):
        iv = [i for i in rec.on_intervals(pos) if i[1] is not None]
        if len(iv) >= 3:
            starts = [a for a, _ in iv]
            periods = {b - a for a, b in zip(starts[1:], starts[2:])}
            if len(periods) == 1:
                period = periods.pop()
                return period, iv[-1][1] - iv[-1][0], pos
    return None


def _classify(reaction: OutputReaction, kind: str, initial: bool) -> None:
    s = reaction.steady_after
    d = reaction.delays
    pulses = reaction.pulses
    if not reaction.events:
        reaction.kind = "keine Reaktion"
        return
    if kind == "lever":
        on_d, off_d = d[0], d[1]
        if s == [not initial, initial, not initial, initial]:
            follows = s[0] is True
            reaction.kind = "folgt dem Eingang" if follows else "invertiert den Eingang"
            reaction.detail = f"Verzögerung beim Einschalten {on_d} gt, beim Ausschalten {off_d} gt"
            if pulses:
                reaction.detail += f"; zusätzliche Pulse: {pulses} gt"
            return
        if s[0] != initial and s[2] == initial and s[1] == s[0]:
            reaction.kind = "T-Flip-Flop (schaltet bei steigender Flanke um)"
            reaction.detail = f"Umschaltverzögerung {on_d} gt"
            return
        if s[1] != initial and s[3] == initial and s[0] == initial:
            reaction.kind = "T-Flip-Flop (schaltet bei fallender Flanke um)"
            reaction.detail = f"Umschaltverzögerung {off_d} gt"
            return
        if s == [initial] * 4:
            rising = d[0] is not None
            falling = d[1] is not None
            edge = ("steigende und fallende Flanke" if rising and falling
                    else "steigende Flanke" if rising else "fallende Flanke")
            reaction.kind = f"Pulsgenerator / Flankendetektor ({edge})"
            reaction.detail = f"Pulslängen {pulses} gt, Verzögerung {on_d if rising else off_d} gt"
            return
        if s[0] != initial and all(x == s[0] for x in s):
            reaction.kind = "Speicher (wird gesetzt und bleibt)"
            reaction.detail = f"Verzögerung {on_d} gt"
            return
    else:  # button
        if len(set(s)) > 1 and s[0] != s[1] and s[1] != s[2]:
            reaction.kind = "T-Flip-Flop (schaltet bei jedem Knopfdruck um)"
            reaction.detail = f"Verzögerung {d[0]} gt"
            return
        if s == [initial] * len(s):
            reaction.kind = "Puls"
            reaction.detail = f"Pulslängen {pulses} gt, Verzögerung {d[0]} gt"
            return
        if all(x != initial for x in s):
            reaction.kind = "Speicher (wird gesetzt und bleibt)"
            reaction.detail = f"Verzögerung {d[0]} gt"
            return
    reaction.kind = "unregelmäßiges Verhalten"
    reaction.detail = f"Zustände nach den Schritten: {s}, Verzögerungen {d}"


def _reaction(rec: Recording, steps: list[Step], out: Port) -> OutputReaction:
    pos = out.pos
    events = []
    prev = None
    for t, v in rec.series.get(pos, []):
        on = is_on(v)
        if prev is not None and on != prev:
            events.append((t, on))
        prev = on
    bounds = [s.tick for s in steps] + [rec.ticks + 1]
    steady, delays, pulses = [], [], []
    for i, step in enumerate(steps):
        end = bounds[i + 1] - 1
        steady.append(rec.on_at(pos, end))
        changes = [t for t, _ in events if step.tick <= t <= end]
        delays.append(changes[0] - step.tick if changes else None)
        for a, b in rec.on_intervals(pos):
            # a pulse: off before the step, then on and off again before the next step
            if b is not None and step.tick <= a and b <= end and not rec.on_at(pos, step.tick - 1):
                pulses.append(b - a)
    return OutputReaction(out, events, steady, delays, pulses)


def _chain(rec: Recording, step_tick: int, end_tick: int) -> list[tuple[int, Pos, str, str, str]]:
    first: dict[Pos, tuple[int, str, str]] = {}
    for ch in rec.changes:
        if step_tick <= ch.tick <= end_tick and ch.pos not in first:
            first[ch.pos] = (ch.tick, ch.old, ch.new)
    out = []
    for pos, (t, old, new) in sorted(first.items(), key=lambda kv: (kv[1][0], kv[0])):
        block = new.split("[")[0].split("|")[0].removeprefix("minecraft:")
        if block == "air":
            block = old.split("[")[0].removeprefix("minecraft:")
        out.append((t - step_tick, pos, block, old, new))
    return out


def _gate_name(table: list[tuple[tuple[bool, ...], bool]]) -> str:
    n = len(table[0][0])
    outs = tuple(o for _, o in sorted(table))
    names1 = {(False, True): "Buffer (Eingang)", (True, False): "NOT"}
    names2 = {
        (False, False, False, True): "AND", (False, True, True, True): "OR", (False, True, True, False): "XOR",
        (True, True, True, False): "NAND", (True, False, False, False): "NOR", (True, False, False, True): "XNOR",
        (False, False, True, True): "folgt Eingang 1", (False, True, False, True): "folgt Eingang 2",
        (True, True, False, False): "NOT Eingang 1", (True, False, True, False): "NOT Eingang 2",
        (False, False, True, False): "Eingang 1 AND NOT Eingang 2",
        (False, True, False, False): "NOT Eingang 1 AND Eingang 2",
    }
    if all(o == outs[0] for o in outs):
        return "konstant " + ("an" if outs[0] else "aus")
    if n == 1:
        return names1.get(outs, "?")
    if n == 2:
        return names2.get(outs, "?")
    ones = [i for (i, _), o in zip(sorted(table), outs) if o]
    return "an bei " + ", ".join("".join("1" if b else "0" for b in combo) for combo in ones)


# ---------------------------------------------------------------------- entry point
def analyze(grid: Grid, inputs: list[Port] | None = None, outputs: list[Port] | None = None) -> Analysis:
    found_in, found_out = find_ports(grid)
    inputs = found_in if inputs is None else inputs
    outputs = found_out if outputs is None else outputs
    circuit = Circuit(grid)

    baseline = circuit.run([], max_ticks=MAX_TICKS, quiet=QUIET)
    analysis = Analysis(grid, inputs, outputs, baseline, None, warnings=list(baseline.warnings))
    out_positions = [o.pos for o in outputs]
    if baseline.settled_at is None:
        c = _clock_from(baseline, out_positions)
        if c:
            analysis.clock = ClockInfo(c[0], c[1], False, c[2])
    else:
        kicked_world = circuit.new_world(kick=True)
        kicked = circuit.run([], max_ticks=MAX_TICKS, quiet=QUIET, world=kicked_world)
        if kicked.settled_at is None:
            c = _clock_from(kicked, out_positions)
            if c:
                analysis.clock = ClockInfo(c[0], c[1], True, c[2])
                analysis.notes.extend(notes_of(kicked_world))

    for port in inputs:
        if port.kind not in ("lever", "button"):
            analysis.warnings.append(f"{port}: Eingangstyp {port.kind} wird nicht automatisch betätigt")
            continue
        rec, steps, notes, oscillates = _run_steps(circuit, port.pos, port.kind, port.name)
        analysis.notes.extend(notes)
        reactions = []
        for out in outputs:
            r = _reaction(rec, steps, out)
            _classify(r, port.kind, rec.on_at(out.pos, 0) if out.pos in rec.series else False)
            reactions.append(r)
        end = steps[1].tick - 1 if len(steps) > 1 else rec.ticks
        analysis.responses.append(
            InputResponse(port, steps, rec, reactions, _chain(rec, steps[0].tick, end), oscillates))

    levers = [p for p in inputs if p.kind == "lever"]
    if 2 <= len(levers) <= 4 and outputs:
        table = []
        for combo in itertools.product([False, True], repeat=len(levers)):
            actions = [(1, p.pos, "use") for p, want in zip(levers, combo) if p.state.get_bool("powered") != want]
            rec = circuit.run(actions, max_ticks=MAX_TICKS, quiet=QUIET)
            if rec.settled_at is None:
                table = None
                analysis.warnings.append("Wahrheitstabelle abgebrochen: Schaltung kommt nicht zur Ruhe")
                break
            table.append((combo, tuple(rec.on_at(o.pos, rec.ticks) for o in outputs)))
        if table:
            analysis.truth_table = table
            for i, out in enumerate(outputs):
                analysis.gates[out.name] = _gate_name([(c, o[i]) for c, o in table])
            if is_decoder(table):
                analysis.patterns.append(f"Decoder: {len(levers)} Eingänge, jeder Ausgang gehört zu genau einer Kombination")

    if analysis.clock is None:
        for port in levers:
            if port.state.get_bool("powered"):
                continue
            analysis.pulse_responses.extend(pulse_response(circuit, port, outputs, notes=analysis.notes))
        analysis.latches = find_latches(circuit, inputs, outputs)
        for latch in analysis.latches:
            analysis.patterns.append(
                f"RS-Latch an {latch.output.name}: {latch.set_input.name} setzt, {latch.reset_input.name} setzt zurück")
        for pr in analysis.pulse_responses:
            if pr.kind.startswith(("Pulsfilter", "Pulsverkürzer", "Pulsverlängerer", "fester", "Puls wird um")):
                analysis.patterns.append(f"{pr.kind} ({pr.input.name} → {pr.output.name})")
    return analysis
