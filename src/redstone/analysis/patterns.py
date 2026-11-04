"""Pattern experiments on top of the basic analysis (all derived from simulation, never from the layout).

- Pulse response: a lever is switched on for L ticks (L = 1, 2, 3, ...) in a fresh world each time. The
  output pulse lengths as a function of L reveal pulse filters, pulse shorteners/monoflops and extenders.
- Sequences for two inputs: each input is operated once ("pulse": lever on and off again, or a button
  press), in different orders. An output that remembers which input was operated last is an RS latch.
- Decoder: in the truth table every output is on for exactly one input combination, all different.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Pos
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
                   lengths: tuple[int, ...] = PULSE_LENGTHS) -> list[PulseResponse]:
    """Switch the lever on for L ticks (fresh world per L) and record what each output does."""
    responses = [PulseResponse(lever, out) for out in outputs]
    for length in lengths:
        actions = [(1, lever.pos, "use"), (1 + length, lever.pos, "use")]
        rec = circuit.run(actions, max_ticks=1 + length + MAX_TICKS, quiet=QUIET)
        if rec.settled_at is None:
            return []  # the circuit does not come to rest: no meaningful pulse response
        for r in responses:
            if r.output.pos not in rec.series:
                continue
            initially_on = rec.on_at(r.output.pos, 0)
            r.table[length] = [] if initially_on else _intervals(rec, r.output.pos, 1)
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
    return 2 if kind == "lever" else 1  # lever: on and off again; button: one press


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
    ops = [p for p in inputs if p.kind in ("lever", "button")]
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
