"""Behavioural analysis of a circuit through simulation experiments.

Experiments (all in the simulator, which is validated against the real game):
1. Leerlauf: nothing is touched. Does anything move? (clock running as stored)
2. Anstoß: every block gets one neighbour update. Does a stored-but-stopped clock start?
3. Per input: lever toggled 4 times (on/off/on/off) or button pressed 3 times, each time waiting
   until the circuit is idle. Yields delays, pulse lengths, edge reactions, toggling.
4. Truth table for 2-6 levers: every combination in a fresh world.
5. Logic in front of a block, for 2-3 levers: experiment 3 for every lever while the other levers hold each
   combination (`patterns.gate_from_edges`). Finds e.g. a T flip-flop clocked by in1 AND in2, whose truth
   table alone would look like an AND gate.
6. Pulse response behind logic: where an output follows a lever only while other levers are on (e.g. an AND
   gate), the pulses of `patterns.pulse_response` are repeated with those levers held on. Finds e.g. a pulse
   extender behind in1 AND in2, whose toggle reactions alone look like a slow gate.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from ..model import Grid, Pos
from ..sim.notes import Note, notes_of
from .experiment import Circuit, Recording, is_on
from .patterns import (OFF_DELAY, GatedBlock, Latch, PulseResponse, find_latches, gated_block, is_decoder,
                       pulse_response)
from .ports import Port, find_ports

MAX_TICKS = 400
QUIET = 12
MAX_TRUTH_TABLE_LEVERS = 6  # 64 fresh runs
MAX_OUTPUTS = 64  # beyond that the schematic is rarely one circuit; analysing all would be slow
MAX_HELD_PULSE_GROUPS = 24  # pulse responses with other levers held on: 11 runs per (lever, held levers)
MAX_GATED_LEVERS = 3  # logic in front of a block: n * 2^(n-1) toggle experiments (as `search.GUESS_INPUTS`)


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
    stops_at: int | None = None  # tick from which the regular oscillation ends (e.g. torch burnout)


@dataclass
class Analysis:
    grid: Grid
    inputs: list[Port]
    outputs: list[Port]
    baseline: Recording
    clock: ClockInfo | None
    oscillates: bool = False  # the circuit never came to rest without input (clock or irregular)
    responses: list[InputResponse] = field(default_factory=list)
    truth_table: list[tuple[tuple[bool, ...], tuple[bool, ...]]] | None = None
    gates: dict[str, str] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)
    pulse_responses: list[PulseResponse] = field(default_factory=list)
    latches: list[Latch] = field(default_factory=list)
    gated: list[GatedBlock] = field(default_factory=list)  # logic in front of a T flip-flop / pulse generator
    # output name -> what happens to pulses behind its logic (e.g. a pulse extender behind an AND gate)
    timing: dict[str, str] = field(default_factory=dict)
    patterns: list[str] = field(default_factory=list)  # recognised building blocks, German
    # with too many levers for one table: (levers, outputs, table) per group of outputs with the same inputs
    partial_tables: list[tuple[list[Port], list[Port], list]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------- experiments
def _run_steps(circuit: Circuit, pos: Pos, kind: str, name: str,
               setup: list[Pos] = ()) -> tuple[Recording, list[Step], list[Note], bool]:
    """Apply input actions one after another, each once the circuit is idle.

    The levers in `setup` are switched on first (tick 1), the steps start once the circuit is idle again."""
    labels = (["an", "aus", "an", "aus"] if kind == "lever" else
              ["betreten"] * 3 if kind == "plate" else ["gedrückt"] * 3)
    steps: list[Step] = []
    actions: list = [(1, p, "use") for p in setup]
    next_tick = 1  # tick 0 shows the stored state before anything is touched
    rec, world = None, None
    if setup:
        world = circuit.new_world()
        rec = circuit.run(list(actions), max_ticks=1 + MAX_TICKS, quiet=QUIET, world=world)
        if rec.settled_at is None:
            return rec, [Step(1, "Vorbereitung")], notes_of(world), True
        next_tick = rec.ticks + 1
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


def _clock_from(rec: Recording, positions: list[Pos], grid: Grid) -> tuple[int, int, Pos, int | None] | None:
    """Period and on-time of the first block that switches on regularly at least three times.

    The first interval may be a start-up transient. If the period changes later (e.g. a torch burns
    out), the clock is reported up to that point."""
    for pos in positions + sorted(rec.series):
        iv = [i for i in rec.on_intervals(pos) if i[1] is not None]
        if len(iv) < 4:
            continue
        starts = [a for a, _ in iv]
        periods = [b - a for a, b in zip(starts[1:], starts[2:])]
        run = 1
        while run < len(periods) and periods[run] == periods[0]:
            run += 1
        if run < 2:
            continue
        on = [b - a for a, b in iv[1:run + 2]]
        state = grid.get(pos)
        own = OFF_DELAY.get(state.id, 0) if state is not None else 0
        on_ticks = max(set(on), key=on.count) - own
        stops = None if run == len(periods) else iv[run + 1][1]
        return periods[0], on_ticks, pos, stops
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
        if prev is not None and on != prev and t >= steps[0].tick:  # not while setup levers switch on
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


def _reactions(rec: Recording, steps: list[Step], kind: str, outputs: list[Port]) -> list[OutputReaction]:
    out = []
    for o in outputs:
        r = _reaction(rec, steps, o)
        # state before the first step (after the setup levers, if any)
        _classify(r, kind, rec.on_at(o.pos, steps[0].tick - 1) if o.pos in rec.series else False)
        out.append(r)
    return out


def _gated_blocks(analysis: Analysis, circuit: Circuit, levers: list[Port], outputs: list[Port]) -> None:
    """Toggle every lever while the other levers hold each combination, and look for outputs whose
    reactions fit an edge-triggered block behind a logic function of several levers."""
    n = len(levers)
    alone = {r.input.name: r for r in analysis.responses}
    edges: list[dict] = [{} for _ in outputs]
    for i, lever in enumerate(levers):
        for others in itertools.product([False, True], repeat=n - 1):
            low = others[:i] + (False,) + others[i:]
            if not any(low) and lever.name in alone:
                reactions = alone[lever.name].reactions  # experiment 3 already did this one
            else:
                rec, steps, _, oscillates = _run_steps(
                    circuit, lever.pos, "lever", lever.name, [levers[k].pos for k in range(n) if low[k]])
                if oscillates:
                    return
                reactions = _reactions(rec, steps, "lever", outputs)
            for j, x in enumerate(reactions):
                edges[j][(i, low)] = (x.kind, x.detail)
    for j, out in enumerate(outputs):
        block = gated_block(out, levers, edges[j])
        if block is not None:
            analysis.gated.append(block)


def _held_pulse_responses(analysis: Analysis, circuit: Circuit, levers: list[Port], outputs: list[Port]) -> None:
    """Pulse responses for outputs that follow a lever only while other levers are on (truth table), with the
    fewest such levers held on. Outputs behind an edge-triggered block or memory (`gated`) are left out."""
    table = dict(analysis.truth_table)
    n = len(levers)
    gated = {b.output.name for b in analysis.gated}
    seen = {(r.input.name, r.output.name) for r in analysis.pulse_responses if any(r.table.values())}
    groups: dict[tuple[int, tuple[bool, ...]], list[Port]] = {}
    for j, out in enumerate(outputs):
        if out.name in gated or table[(False,) * n][j]:
            continue
        for i, lever in enumerate(levers):
            if (lever.name, out.name) in seen:
                continue
            for low in sorted((c for c in table if not c[i]), key=lambda c: (sum(c), c)):
                if not table[low][j] and table[low[:i] + (True,) + low[i + 1:]][j]:
                    if any(low):
                        groups.setdefault((i, low), []).append(out)
                    break
    if len(groups) > MAX_HELD_PULSE_GROUPS:
        analysis.warnings.append(
            f"Pulsantwort hinter Logik nur für die ersten {MAX_HELD_PULSE_GROUPS} von {len(groups)} "
            "Kombinationen aus Hebel und gehaltenen Hebeln gemessen")
    for (i, low), outs in sorted(groups.items())[:MAX_HELD_PULSE_GROUPS]:
        analysis.pulse_responses.extend(pulse_response(
            circuit, levers[i], outs, notes=analysis.notes, held=[levers[k] for k in range(n) if low[k]]))


def _timing_behind_logic(analysis: Analysis) -> None:
    """Outputs that depend on several levers and change the pulse length the same way for each of them."""
    gated = {b.output.name for b in analysis.gated}
    by_output: dict[str, list[PulseResponse]] = {}
    for r in analysis.pulse_responses:
        if any(r.table.values()):
            by_output.setdefault(r.output.name, []).append(r)
    for name, rs in by_output.items():
        kinds = {r.kind.removeprefix("Pulsfilter; ") for r in rs}
        if (len({r.input.name for r in rs}) >= 2 and name not in gated and len(kinds) == 1
                and all(r.changes_length for r in rs)):
            analysis.timing[name] = kinds.pop()


def _truth_table(circuit: Circuit, levers: list[Port], outputs: list[Port]):
    """Steady output states for every lever combination, each in a fresh world; None if it never settles."""
    table = []
    for combo in itertools.product([False, True], repeat=len(levers)):
        actions = [(1, p.pos, "use") for p, want in zip(levers, combo) if p.state.get_bool("powered") != want]
        rec = circuit.run(actions, max_ticks=MAX_TICKS, quiet=QUIET)
        if rec.settled_at is None:
            return None
        table.append((combo, tuple(rec.on_at(o.pos, rec.ticks) for o in outputs)))
    return table


def _pair_dependencies(circuit: Circuit, levers: list[Port], outputs: list[Port]) -> dict[str, set[str]] | None:
    """Levers each output depends on, seen from the stored lever states: lever j counts if flipping it changes
    the steady output, either alone or together with one other lever (an AND of two levers that are both off
    at rest only shows up in the pair). Fresh world per run, as `_truth_table`; None if a run never settles."""
    def steady(flipped: tuple[int, ...]):
        rec = circuit.run([(1, levers[i].pos, "use") for i in flipped], max_ticks=MAX_TICKS, quiet=QUIET)
        if rec.settled_at is None:
            return None
        return tuple(rec.on_at(o.pos, rec.ticks) for o in outputs)

    n = len(levers)
    runs = {(): steady(())}
    for i in range(n):
        runs[(i,)] = steady((i,))
    for i, j in itertools.combinations(range(n), 2):
        runs[(i, j)] = steady((i, j))
    if any(v is None for v in runs.values()):
        return None
    deps: dict[str, set[str]] = {o.name: set() for o in outputs}
    for (i, j) in itertools.combinations(range(n), 2):
        for base, flip, both in ((runs[()], (i,), (i,)), (runs[()], (j,), (j,)),
                                 (runs[(i,)], (j,), (i, j)), (runs[(j,)], (i,), (i, j))):
            after = runs[both]
            for k, o in enumerate(outputs):
                if base[k] != after[k]:
                    deps[o.name].add(levers[flip[0]].name)
    return deps


MAX_PAIR_LEVERS = 20  # 1 + n + n(n-1)/2 runs: 211 for 20 levers


def _partial_tables(analysis: Analysis, circuit: Circuit, levers: list[Port], outputs: list[Port]) -> None:
    """Group outputs by the levers they depend on (single toggles and pairs from the stored states) and
    tabulate each group on its own."""
    deps: dict[str, set[str]] = {o.name: set() for o in outputs}
    for r in analysis.responses:
        if r.input.kind == "lever":
            for x in r.reactions:
                if x.kind != "keine Reaktion":
                    deps[x.output.name].add(r.input.name)
    pairs = _pair_dependencies(circuit, levers, outputs) if len(levers) <= MAX_PAIR_LEVERS else None
    if pairs is not None:
        for name, more in pairs.items():
            deps[name] |= more
    groups: dict[frozenset[str], list[Port]] = {}
    for o in outputs:
        groups.setdefault(frozenset(deps[o.name]), []).append(o)
    by_name = {p.name: p for p in levers}
    skipped = []
    for names, outs in sorted(groups.items(), key=lambda kv: sorted(kv[0])):
        if len(names) < 2:
            continue
        if len(names) > MAX_TRUTH_TABLE_LEVERS:
            skipped += [o.name for o in outs]
            continue
        group_levers = [by_name[n] for n in sorted(names, key=lambda n: [p.name for p in levers].index(n))]
        table = _truth_table(circuit, group_levers, outs)
        if table is None:
            analysis.warnings.append("Teil-Wahrheitstabelle abgebrochen: Schaltung kommt nicht zur Ruhe")
            continue
        analysis.partial_tables.append((group_levers, outs, table))
        for i, out in enumerate(outs):
            analysis.gates[out.name] = _gate_name([(c, o[i]) for c, o in table])
    analysis.warnings.append(
        f"{len(levers)} Hebel sind zu viele für eine volle Wahrheitstabelle (höchstens {MAX_TRUTH_TABLE_LEVERS}); "
        + ("Teiltabellen über die Hebel, auf die ein Ausgang einzeln oder paarweise umgelegt reagiert. "
           "Abhängigkeiten, die erst bei drei oder mehr gleichzeitig umgelegten Hebeln sichtbar werden, fehlen darin"
           if pairs is not None else
           "Teiltabellen über die Hebel, auf die ein Ausgang einzeln reagiert. Abhängigkeiten, die nur bei "
           "mehreren gleichzeitig betätigten Hebeln sichtbar werden, fehlen darin")
        + (f"; ohne Tabelle: {', '.join(skipped)}" if skipped else ""))


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
    if n > 2:
        on = [o for _, o in sorted(table)]
        for name, pattern in (("AND", [False] * (2 ** n - 1) + [True]), ("NOR", [True] + [False] * (2 ** n - 1)),
                              ("OR", [False] + [True] * (2 ** n - 1)), ("NAND", [True] * (2 ** n - 1) + [False])):
            if on == pattern:
                return f"{name} ({n} Eingänge)"
    ones = [i for (i, _), o in zip(sorted(table), outs) if o]
    return "an bei " + ", ".join("".join("1" if b else "0" for b in combo) for combo in ones)


# ---------------------------------------------------------------------- entry point
def analyze(grid: Grid, inputs: list[Port] | None = None, outputs: list[Port] | None = None) -> Analysis:
    found_in, found_out = find_ports(grid)
    inputs = found_in if inputs is None else inputs
    outputs = found_out if outputs is None else outputs
    circuit = Circuit(grid)
    too_many = len(outputs) > MAX_OUTPUTS
    if too_many:
        skipped = len(outputs) - MAX_OUTPUTS
        outputs = outputs[:MAX_OUTPUTS]

    baseline = circuit.run([], max_ticks=MAX_TICKS, quiet=QUIET)
    analysis = Analysis(grid, inputs, outputs, baseline, None, warnings=list(baseline.warnings))
    if too_many:
        analysis.warnings.append(f"Nur die ersten {MAX_OUTPUTS} Ausgänge werden ausgewertet ({skipped} weitere ignoriert)")
    out_positions = [o.pos for o in outputs]
    idle_rec, needs_start = baseline, False
    if baseline.settled_at is not None:
        kicked_world = circuit.new_world(kick=True)
        idle_rec = circuit.run([], max_ticks=MAX_TICKS, quiet=QUIET, world=kicked_world)
        needs_start = True
    else:
        kicked_world = circuit.new_world()
        circuit.run([], max_ticks=MAX_TICKS, quiet=QUIET, world=kicked_world)
    if idle_rec.settled_at is None:
        analysis.oscillates = True
        analysis.notes.extend(notes_of(kicked_world))
        c = _clock_from(idle_rec, out_positions, grid)
        if c:
            analysis.clock = ClockInfo(c[0], c[1], needs_start, c[2], c[3])
    elif needs_start and idle_rec.changes:
        analysis.warnings.append("Gespeicherter Zustand war nicht stabil: nach einem Anstoß ändern sich Blöcke "
                                 "einmalig, ohne dass etwas betätigt wurde")

    for port in inputs:
        if port.kind not in ("lever", "button", "plate"):
            analysis.warnings.append(f"{port}: Eingangstyp {port.kind} wird nicht automatisch betätigt")
            continue
        rec, steps, notes, oscillates = _run_steps(circuit, port.pos, port.kind, port.name)
        analysis.notes.extend(notes)
        reactions = _reactions(rec, steps, port.kind, outputs)
        end = steps[1].tick - 1 if len(steps) > 1 else rec.ticks
        analysis.responses.append(
            InputResponse(port, steps, rec, reactions, _chain(rec, steps[0].tick, end), oscillates))

    levers = [p for p in inputs if p.kind == "lever"]
    if len(levers) > MAX_TRUTH_TABLE_LEVERS and outputs:
        _partial_tables(analysis, circuit, levers, outputs)
    if 2 <= len(levers) <= MAX_TRUTH_TABLE_LEVERS and outputs:
        table = _truth_table(circuit, levers, outputs)
        if table is None:
            analysis.warnings.append("Wahrheitstabelle abgebrochen: Schaltung kommt nicht zur Ruhe")
        if table:
            analysis.truth_table = table
            for i, out in enumerate(outputs):
                analysis.gates[out.name] = _gate_name([(c, o[i]) for c, o in table])
            if is_decoder(table):
                analysis.patterns.append(f"Decoder: {len(levers)} Eingänge, jeder Ausgang gehört zu genau einer Kombination")

    if not analysis.oscillates:
        for port in levers:
            if port.state.get_bool("powered"):
                continue
            analysis.pulse_responses.extend(pulse_response(circuit, port, outputs, notes=analysis.notes))
        analysis.latches = find_latches(circuit, inputs, outputs)
        if (2 <= len(levers) <= MAX_GATED_LEVERS and outputs
                and not any(p.state.get_bool("powered") for p in levers)):
            _gated_blocks(analysis, circuit, levers, outputs)
        for block in analysis.gated:
            # the truth table of such an output only shows the block after one switch-on, not a gate
            analysis.gates[block.output.name] = block.summary
            analysis.patterns.append(f"{block.summary} ({', '.join(p.name for p in block.levers)} → "
                                     f"{block.output.name})")
        for latch in analysis.latches:
            analysis.patterns.append(
                f"RS-Latch an {latch.output.name}: {latch.set_input.name} setzt, {latch.reset_input.name} setzt zurück")
        if analysis.truth_table and not any(p.state.get_bool("powered") for p in levers):
            _held_pulse_responses(analysis, circuit, levers, outputs)
            _timing_behind_logic(analysis)
        for name, kind in analysis.timing.items():
            analysis.patterns.append(f"Logik vor Zeitglied an {name}: {analysis.gates[name]}, dahinter: {kind}")
        for pr in analysis.pulse_responses:
            if pr.held and (not pr.changes_length or pr.output.name in analysis.timing):
                continue  # a gate that only swallows short pulses is no building block; see the pulse table
            if pr.kind.startswith(("Pulsfilter", "Pulsverkürzer", "Pulsverlängerer", "fester", "Puls wird um")):
                analysis.patterns.append(f"{pr.kind} ({pr.label})")
    return analysis
