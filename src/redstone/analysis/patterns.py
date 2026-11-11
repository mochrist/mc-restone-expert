"""Pattern experiments on top of the basic analysis (all derived from simulation, never from the layout).

- Pulse response: a lever is switched on for L ticks (L = 1, 2, 3, ...) in a fresh world each time. The
  output pulse lengths as a function of L reveal pulse filters, pulse shorteners/monoflops and extenders.
- Sequences for two inputs: each input is operated once ("pulse": lever on and off again, or a button
  press), in different orders. An output that remembers which input was operated last is an RS latch.
- Decoder: in the truth table every output is on for exactly one input combination, all different.
- Logic in front of a block (`gate_from_edges`): a lever is toggled while the other levers hold every
  combination. Where an edge-triggered block (T flip-flop, pulse generator) reacts, the logic function in
  front of it changes; the reactions on all edges of the lever cube give that function and the block.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from ..model import Pos
from ..sim.notes import Note, notes_of
from .experiment import Circuit, Recording
from .ports import Port

PULSE_LENGTHS = (1, 2, 3, 4, 5, 6, 8, 10, 15, 20)
MAX_TICKS = 400
# Output blocks that turn off later than their input (gt); counted separately from the circuit.
OFF_DELAY = {"redstone_lamp": 4}
QUIET = 12


@dataclass
class PulseResponse:
    input: Port
    output: Port
    # input pulse length -> output on-intervals (start relative to the input pulse start, length);
    # length None = the output stays on after the circuit has come to rest
    table: dict[int, list[tuple[int, int | None]]] = field(default_factory=dict)
    kind: str = ""  # classification, German
    detail: str = ""
    held: list[Port] = field(default_factory=list)  # levers switched on before the pulses (logic in front)

    @property
    def label(self) -> str:
        held = f", während {', '.join(p.name for p in self.held)} an" if self.held else ""
        return f"{self.input.name} → {self.output.name}{held}"

    @property
    def changes_length(self) -> bool:
        """The circuit changes pulse lengths (extender, shortener, monoflop), not just passes or filters them."""
        return self.kind.removeprefix("Pulsfilter; ").startswith(TIMING_KINDS)


TIMING_KINDS = ("Pulsverkürzer", "Pulsverlängerer", "fester", "Puls wird um", "kurze Pulse")


@dataclass
class Latch:
    output: Port
    set_input: Port
    reset_input: Port
    # steady output state after the sequences: (), (set,), (reset,), (set, reset), (reset, set)
    states: dict[tuple[str, ...], bool] = field(default_factory=dict)


# ---------------------------------------------------------------------- pulse response
def _intervals(rec: Recording, pos: Pos, start: int) -> list[tuple[int, int | None]]:
    out: list[tuple[int, int | None]] = []
    for a, b in rec.on_intervals(pos):
        if b is None:
            out.append((a - start, None))
        elif b > start:  # ignore an output that was on before the pulse and went off right at the start
            out.append((a - start, b - a))
    return out


def pulse_response(circuit: Circuit, lever: Port, outputs: list[Port],
                   lengths: tuple[int, ...] = PULSE_LENGTHS, notes: list[Note] | None = None,
                   held: list[Port] = ()) -> list[PulseResponse]:
    """Switch the lever on for L ticks (fresh world per L) and record what each output does.

    The levers in `held` are switched on first (tick 1); the pulse starts once the circuit is idle again. With
    logic in front of a timing block this makes the logic follow the lever.
    Mechanics notes of the runs (e.g. block dropping at short pulses) are appended to `notes`."""
    responses = [PulseResponse(lever, out, held=list(held)) for out in outputs]
    setup = [(1, p.pos, "use") for p in held]
    start = 1
    if setup:
        rec = circuit.run(list(setup), max_ticks=1 + MAX_TICKS, quiet=QUIET)
        if rec.settled_at is None:
            return []
        start = rec.ticks + 1
    for length in lengths:
        actions = setup + [(start, lever.pos, "use"), (start + length, lever.pos, "use")]
        world = circuit.new_world()
        rec = circuit.run(actions, max_ticks=start + length + MAX_TICKS, quiet=QUIET, world=world)
        if notes is not None:
            notes.extend(notes_of(world))
        if rec.settled_at is None:
            return []  # the circuit does not come to rest: no meaningful pulse response
        for r in responses:
            if r.output.pos not in rec.series:
                continue
            initially_on = rec.on_at(r.output.pos, start - 1)
            r.table[length] = [] if initially_on else _intervals(rec, r.output.pos, start)
            if initially_on:
                r.kind = "Ausgang ist im Ruhezustand an"
    for r in responses:
        if not r.kind:
            _classify_pulse(r)
    return responses


def _classify_pulse(r: PulseResponse) -> None:
    table = r.table
    if not table or not any(table.values()):
        r.kind = "keine Reaktion auf Pulse"
        return
    lengths = sorted(table)
    passed = [L for L in lengths if table[L]]
    if any(len(table[L]) > 1 for L in passed):
        many = {L: len(table[L]) for L in passed if len(table[L]) > 1}
        r.kind = "mehrere Ausgangspulse pro Eingangspuls"
        r.detail = "Anzahl Pulse je Eingangslänge: " + ", ".join(f"{L} gt: {n}" for L, n in many.items())
        return
    stuck = [L for L in passed if table[L][0][1] is None]
    if stuck:
        r.kind = "Ausgang bleibt nach dem Puls an (Speicher)"
        r.detail = f"ab {stuck[0]} gt Pulslänge" if stuck[0] > lengths[0] else ""
        return
    outs = {L: table[L][0][1] for L in passed}
    delays = {L: table[L][0][0] for L in passed}
    parts = []
    first = passed[0]
    if first > lengths[0]:
        blocked = [L for L in lengths if L < first]
        if all(L not in passed for L in blocked) and all(L in passed for L in lengths if L >= first):
            parts.append(f"Pulse unter {first} gt werden unterdrückt")
    own = OFF_DELAY.get(r.output.kind, 0)  # the output block itself stays on this long after its input
    own_note = f" (davon {own} gt Ausschaltverzögerung von {r.output.kind})" if own else ""
    values = set(outs.values())
    longest = passed[-1]
    k = outs[longest] - longest
    m = min(outs.values()) - k
    if len(values) == 1 and len(passed) > 1:
        c = values.pop()
        r.kind = f"fester Ausgangspuls von {c} gt (Monoflop)"
        if all(L >= c for L in passed) and any(L > c for L in passed):
            r.kind = f"Pulsverkürzer (Ausgangspuls immer {c} gt)"
        elif all(L <= c for L in passed) and any(L < c for L in passed):
            r.kind = f"Pulsverlängerer (Ausgangspuls immer {c} gt)"
    elif all(outs[L] - L == k for L in passed):
        k_circuit = k - own
        if k_circuit == 0:
            r.kind = "Puls wird unverändert durchgereicht"
        elif k_circuit > 0:
            r.kind = f"Puls wird um {k_circuit} gt verlängert"
        else:
            r.kind = f"Puls wird um {-k_circuit} gt verkürzt"
        if own:
            parts.append(f"Ausgangspuls = Eingangspuls + {k} gt{own_note}")
    elif all(outs[L] == max(L, m) + k for L in passed):
        r.kind = f"kurze Pulse werden auf mindestens {m + k - own} gt verlängert"
        parts.append(f"Ausgangspuls = max(Eingangspuls, {m} gt) + {k} gt{own_note}")
    else:
        r.kind = "Pulslänge hängt nichtlinear von der Eingangslänge ab"
        parts.append("Ausgang je Eingangslänge: " + ", ".join(f"{L}→{outs[L]}" for L in passed))
    if len(set(delays.values())) == 1:
        parts.append(f"Verzögerung {delays[first]} gt")
    else:
        parts.append("Verzögerung je Eingangslänge: " + ", ".join(f"{L}→{delays[L]}" for L in passed))
    if parts and parts[0].startswith("Pulse unter"):
        r.kind = f"Pulsfilter; {r.kind}"
    r.detail = "; ".join(parts)


# ---------------------------------------------------------------------- latches
def _operate(kind: str) -> int:
    return 2 if kind == "lever" else 1  # lever: on and off again; button/plate: one press


def run_sequence(circuit: Circuit, ports: list[Port]) -> tuple[Recording | None, bool]:
    """Operate each port once (lever: on, then off; button: press), each step once the world is idle."""
    actions: list = []
    next_tick = 1
    rec = circuit.run([], max_ticks=MAX_TICKS, quiet=QUIET)
    if rec.settled_at is None:
        return None, False
    for port in ports:
        for _ in range(_operate(port.kind)):
            actions.append((next_tick, port.pos, "use"))
            rec = circuit.run(list(actions), max_ticks=next_tick + MAX_TICKS, quiet=QUIET)
            if rec.settled_at is None:
                return None, False
            next_tick = rec.ticks + 1
    return rec, True


def find_latches(circuit: Circuit, inputs: list[Port], outputs: list[Port]) -> list[Latch]:
    """RS latch: after operating A the output is x, after B it is y != x, and the last operation wins."""
    ops = [p for p in inputs if p.kind in ("lever", "button", "plate")]
    if len(ops) != 2 or not outputs:
        return []
    if any(p.kind == "lever" and p.state.get_bool("powered") for p in ops):
        return []  # a lever stored as on would be operated off/on; keep the experiment simple
    a, b = ops
    seqs = {(): [], ("a",): [a], ("b",): [b], ("a", "b"): [a, b], ("b", "a"): [b, a]}
    results: dict[tuple[str, ...], Recording] = {}
    for key, seq in seqs.items():
        rec, ok = run_sequence(circuit, seq)
        if not ok:
            return []
        results[key] = rec
    latches = []
    for out in outputs:
        if any(out.pos not in rec.series for rec in results.values()):
            continue
        st = {k: rec.on_at(out.pos, rec.ticks) for k, rec in results.items()}
        x, y, init = st[("a",)], st[("b",)], st[()]
        if x != y and st[("a", "b")] == y and st[("b", "a")] == x:
            set_in, reset_in = (a, b) if x else (b, a)
            latches.append(Latch(out, set_in, reset_in, {
                (): init,
                (set_in.name,): True, (reset_in.name,): False,
                (set_in.name, reset_in.name): False, (reset_in.name, set_in.name): True,
            }))
    return latches


# ---------------------------------------------------------------------- decoder
def is_decoder(truth_table: list[tuple[tuple[bool, ...], tuple[bool, ...]]] | None) -> bool:
    """Every output is on for exactly one input combination, and no two outputs share one."""
    if not truth_table or len(truth_table[0][1]) < 2:
        return False
    n_out = len(truth_table[0][1])
    hits = []
    for i in range(n_out):
        on = [combo for combo, outs in truth_table if outs[i]]
        if len(on) != 1:
            return False
        hits.append(on[0])
    return len(set(hits)) == n_out


# ---------------------------------------------------------------------- logic in front of a block
TFF_RISING = "T-Flip-Flop (schaltet bei steigender Flanke um)"
TFF_FALLING = "T-Flip-Flop (schaltet bei fallender Flanke um)"
PULSE_RISING = "Pulsgenerator / Flankendetektor (steigende Flanke)"
PULSE_FALLING = "Pulsgenerator / Flankendetektor (fallende Flanke)"
PULSE_BOTH = "Pulsgenerator / Flankendetektor (steigende und fallende Flanke)"
# reaction to a lever under a gate that follows it -> reaction under a gate that inverts it
MIRROR = {TFF_RISING: TFF_FALLING, TFF_FALLING: TFF_RISING, PULSE_RISING: PULSE_FALLING,
          PULSE_FALLING: PULSE_RISING, PULSE_BOTH: PULSE_BOTH}
NO_REACTION = "keine Reaktion"

Combo = tuple[bool, ...]


@dataclass
class GatedBlock:
    output: Port
    levers: list[Port]  # the levers the gate depends on
    gate: str  # readable, e.g. "in1 AND in2"
    expression: str  # Python bool expression over the lever names
    table: dict[Combo, bool]  # gate value per combination of `levers`
    kind: str  # the block behind the gate (classification of a lever toggle when the gate follows it)
    detail: str = ""

    @property
    def summary(self) -> str:
        verb = ("getaktet durch" if self.kind.startswith("T-Flip-Flop") else
                "gesetzt durch" if self.kind == MEMORY else "ausgelöst durch")
        return f"{self.kind}, {verb} {self.gate}"


def gate_from_edges(n: int, edges: dict[tuple[int, Combo], str]) -> tuple[dict[Combo, bool], str] | None:
    """Logic function g in front of an edge-triggered block, from the block's reactions on the lever cube.

    `edges[(i, c)]` is the classification of toggling lever i (on/off/on/off) while the levers hold c
    (c[i] off). The block reacts on an edge iff g changes there; g is off with all levers off. Returns g and
    the block's own reaction (on edges where g rises) if all edges fit one block, else None."""
    combos = list(itertools.product([False, True], repeat=n))
    if len(edges) != n * 2 ** (n - 1) or any(k != NO_REACTION and k not in MIRROR for k in edges.values()):
        return None
    g: dict[Combo, bool] = {combos[0]: False}
    for c in sorted(combos[1:], key=sum):
        i = c.index(True)
        low = c[:i] + (False,) + c[i + 1:]
        g[c] = g[low] != (edges[(i, low)] != NO_REACTION)
    rising: set[str] = set()
    falling: set[str] = set()
    for (i, low), kind in edges.items():
        high = low[:i] + (True,) + low[i + 1:]
        if (g[low] != g[high]) != (kind != NO_REACTION):
            return None  # the reactions do not fit any function
        if g[low] != g[high]:
            (rising if g[high] else falling).add(kind)
    if len(rising) != 1:
        return None
    kind = rising.pop()
    if falling - {MIRROR[kind]}:
        return None
    return g, kind


MEMORY = "Speicher (wird gesetzt und bleibt)"


def memory_gate_from_edges(n: int, edges: dict[tuple[int, Combo], str]) -> tuple[dict[Combo, bool], int] | None:
    """Logic function g in front of a set-only memory, from the reactions on the lever cube (as
    `gate_from_edges`). Each experiment starts in a fresh world, so the memory is set while the other levers
    take their places iff g is on there; afterwards nothing changes it. A toggle of lever i from c (c[i] off)
    therefore sets the memory iff g(c) is off and g(c + i) on, and shows no reaction otherwise.

    g is determined where some lower neighbour is off; a combination whose lower neighbours are all on is not
    observable and taken as on (the memory cannot tell OR from XOR). Returns g and the number of such
    assumed combinations, or None if the reactions do not fit."""
    combos = list(itertools.product([False, True], repeat=n))
    if len(edges) != n * 2 ** (n - 1) or any(k not in (NO_REACTION, MEMORY) for k in edges.values()):
        return None
    if MEMORY not in edges.values():
        return None
    g: dict[Combo, bool] = {combos[0]: False}
    assumed = 0
    for c in sorted(combos[1:], key=sum):
        seen = set()
        for i in range(n):
            if c[i]:
                low = c[:i] + (False,) + c[i + 1:]
                if not g[low]:
                    seen.add(edges[(i, low)] == MEMORY)
        if len(seen) > 1:
            return None
        if seen:
            g[c] = seen.pop()
        else:
            g[c] = True
            assumed += 1
    for (i, low), kind in edges.items():
        high = low[:i] + (True,) + low[i + 1:]
        if (kind == MEMORY) != (not g[low] and g[high]):
            return None
    return g, assumed


def gate_label(names: list[str], ones: list[Combo]) -> str:
    """Readable gate: AND/OR/XOR chains for the symmetric functions, else a minimal sum of products."""
    from ..design.search import gate_expression

    n = len(names)
    combos = list(itertools.product([False, True], repeat=n))
    for op, want in (("AND", [c for c in combos if all(c)]), ("OR", [c for c in combos if any(c)]),
                     ("XOR", [c for c in combos if sum(c) % 2])):
        if sorted(ones) == sorted(want):
            return f" {op} ".join(names)
    expr = gate_expression(names, ones)
    return expr.replace(" and ", " AND ").replace(" or ", " OR ").replace("not ", "NOT ")


def gated_block(output: Port, levers: list[Port], edges: dict[tuple[int, Combo], tuple[str, str]]) -> GatedBlock | None:
    """`gate_from_edges` for one output; edges map to (kind, detail). The gate is reduced to the levers it
    depends on and must depend on at least two (a block behind one lever is reported per input)."""
    from ..design.search import depends_on_all, gate_expression

    kinds = {k: v[0] for k, v in edges.items()}
    found = gate_from_edges(len(levers), kinds)
    note = ""
    if found is None:
        memory = memory_gate_from_edges(len(levers), kinds)
        if memory is None:
            return None
        g, assumed = memory
        found = g, MEMORY
        if assumed:
            note = (f"; {assumed} Kombination(en) nicht beobachtbar, weil der Speicher dort schon beim Einstellen "
                    "der übrigen Hebel gesetzt wird; als „an“ angenommen (z. B. OR und XOR sind so nicht "
                    "unterscheidbar)")
    g, kind = found
    n = len(levers)
    used = [i for i in range(n) if any(g[c] != g[c[:i] + (not c[i],) + c[i + 1:]] for c in g)]
    if len(used) < 2:
        return None
    table = {tuple(c[i] for i in used): v for c, v in g.items() if all(not c[i] for i in range(n) if i not in used)}
    assert depends_on_all(table)
    names = [levers[i].name for i in used]
    ones = [c for c, v in sorted(table.items()) if v]
    detail = next(d for (i, low), (k, d) in sorted(edges.items())
                  if k == kind and not g[low] and g[low[:i] + (True,) + low[i + 1:]])
    return GatedBlock(output, [levers[i] for i in used], gate_label(names, ones), gate_expression(names, ones),
                      table, kind, (f"{detail} ab dem auslösenden Hebel" if detail else "") + note)
