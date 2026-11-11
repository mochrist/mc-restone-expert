"""Logic in front of a building block: `rsx explain` reports e.g. a T flip-flop clocked by in1 AND in2
instead of the AND gate its truth table alone suggests."""

from functools import cache
from pathlib import Path

import pytest

from redstone.analysis.analyze import analyze
from redstone.analysis.explain import explain
from redstone.analysis.patterns import (MEMORY, NO_REACTION, PULSE_BOTH, PULSE_RISING, TFF_FALLING, TFF_RISING,
                                        gate_from_edges, memory_gate_from_edges)
from redstone.verify import load_scenario

ROOT = Path(__file__).parents[2]
GATED = ROOT / "tests/fixtures/analysis/gated"


@cache
def _analysis(path: Path):
    return analyze(load_scenario(path).grid)


def _edges(n: int, gate, rising: str, falling: str) -> dict:
    """Reactions of an ideal block behind `gate` on every edge of the lever cube."""
    import itertools

    out = {}
    for low in itertools.product([False, True], repeat=n):
        for i in range(n):
            if low[i]:
                continue
            high = low[:i] + (True,) + low[i + 1:]
            a, b = gate(low), gate(high)
            out[(i, low)] = NO_REACTION if a == b else rising if b else falling
    return out


# ---------------------------------------------------------------------- gate from the edge reactions
@pytest.mark.parametrize("gate", [
    lambda c: c[0] and c[1], lambda c: c[0] or c[1], lambda c: c[0] != c[1], lambda c: c[0] and not c[1]])
def test_gate_from_edges_two_levers(gate):
    g, kind = gate_from_edges(2, _edges(2, gate, TFF_RISING, TFF_FALLING))
    assert kind == TFF_RISING
    assert g == {c: bool(gate(c)) for c in g}


def test_gate_from_edges_falling_edge_block_and_three_levers():
    def gate(c):
        return c[0] and (c[1] or c[2])

    g, kind = gate_from_edges(3, _edges(3, gate, TFF_FALLING, TFF_RISING))
    assert kind == TFF_FALLING and g == {c: bool(gate(c)) for c in g}
    g, kind = gate_from_edges(3, _edges(3, gate, PULSE_BOTH, PULSE_BOTH))
    assert kind == PULSE_BOTH and g == {c: bool(gate(c)) for c in g}


def test_gate_from_edges_rejects_what_no_block_explains():
    edges = _edges(2, lambda c: c[0] and c[1], TFF_RISING, TFF_FALLING)
    assert gate_from_edges(2, {**edges, (0, (False, False)): TFF_RISING}) is None  # reacts where g is constant
    assert gate_from_edges(2, {**edges, (0, (False, True)): PULSE_RISING}) is None  # two different blocks
    assert gate_from_edges(2, {**edges, (0, (False, True)): "folgt dem Eingang"}) is None  # combinational
    assert gate_from_edges(2, dict.fromkeys(edges, NO_REACTION)) is None  # nothing reacts
    # memory that is only set (an RS latch, "Speicher") is no edge-triggered block
    assert gate_from_edges(2, {**edges, (0, (False, True)): "Speicher (wird gesetzt und bleibt)"}) is None


# ---------------------------------------------------------------------- circuits
@pytest.mark.parametrize("path, gate", [
    (ROOT / "scenarios/cmp-t-flip-flop-and.yaml", "in1 AND in2"),
    (GATED / "t-flip-flop-or.yaml", "in1 OR in2"),
    (GATED / "t-flip-flop-xor.yaml", "in1 XOR in2"),
    (GATED / "t-flip-flop-a-and-not-b.yaml", "in1 AND NOT in2"),
    (GATED / "t-flip-flop-and3.yaml", "in1 AND in2 AND in3"),
], ids=lambda x: x.stem if isinstance(x, Path) else None)
def test_t_flip_flop_behind_gate(path, gate):
    a = _analysis(path)
    blocks = {b.output.name: b for b in a.gated}
    # copper bulb (the flip-flop itself) and the lamp it drives
    assert set(blocks) == {"out1", "out2"}
    for b in blocks.values():
        assert b.kind == TFF_RISING and b.gate == gate
        assert b.summary == f"{TFF_RISING}, getaktet durch {gate}"
        assert a.gates[b.output.name] == b.summary  # not the gate the truth table suggests
        assert f"{b.summary} ({', '.join(p.name for p in b.levers)} → {b.output.name})" in a.patterns


def test_explain_t_flip_flop_and():
    a = _analysis(ROOT / "scenarios/cmp-t-flip-flop-and.yaml")
    text = explain(a, "cmp-t-flip-flop-and")
    summary = text.split("## Zusammenfassung", 1)[1].split("##", 1)[0]
    assert f"- out1: **{TFF_RISING}, getaktet durch in1 AND in2**" in summary
    assert "out1 hängt von mehreren Eingängen ab" not in summary
    # out3 is the AND gate's own torch: that one really is combinational
    assert "- out3 hängt von mehreren Eingängen ab: **AND**" in summary
    assert "## Logik vor Speicher / Pulsgeber" in text
    table = text.split("## Wahrheitstabelle", 1)[1].split("## Verhalten", 1)[0]
    assert "| in1 | in2 | out3 |" in table and "out1 |" not in table.replace("Ohne out1", "")


def test_monoflop_behind_or():
    a = _analysis(ROOT / "scenarios/cmp-monoflop-or.yaml")
    (b,) = a.gated
    assert (b.output.name, b.kind, b.gate) == ("out1", PULSE_RISING, "in1 OR in2")
    assert b.summary == f"{PULSE_RISING}, ausgelöst durch in1 OR in2"


@pytest.mark.parametrize("path", [
    "tests/fixtures/analysis/rs-latch.yaml", "scenarios/tpl-and2-torch.yaml", "scenarios/tpl-xor2-comparator.yaml",
    "scenarios/seq-t-flip-flop-copper-bulb.yaml", "scenarios/pla-halfadder.yaml",
])
def test_no_gated_block_elsewhere(path):
    a = _analysis(ROOT / path)
    assert a.gated == []
    assert not any("getaktet durch" in p or "ausgelöst durch" in p for p in a.patterns)


# ---------------------------------------------------------------------- set-only memory behind a gate
def _memory_edges(n: int, gate) -> dict:
    """Reactions of an ideal set-only memory behind `gate`, each experiment in a fresh world."""
    import itertools

    out = {}
    for low in itertools.product([False, True], repeat=n):
        for i in range(n):
            if not low[i]:
                high = low[:i] + (True,) + low[i + 1:]
                out[(i, low)] = MEMORY if not gate(low) and gate(high) else NO_REACTION
    return out


@pytest.mark.parametrize("gate, n, assumed", [
    (lambda c: c[0] and c[1], 2, 0), (lambda c: c[0] and not c[1], 2, 0), (lambda c: c[0] or c[1], 2, 1),
    (lambda c: c[0] and (c[1] or c[2]), 3, 0), (lambda c: c[0] or c[1] or c[2], 3, 4)])
def test_memory_gate_from_edges(gate, n, assumed):
    g, k = memory_gate_from_edges(n, _memory_edges(n, gate))
    assert g == {c: bool(gate(c)) for c in g} and k == assumed


def test_memory_cannot_tell_or_from_xor():
    g, assumed = memory_gate_from_edges(2, _memory_edges(2, lambda c: c[0] != c[1]))
    assert g[(True, True)] and assumed == 1


@pytest.mark.parametrize("name, gate", [("memory-and", "in1 AND in2"), ("memory-or", "in1 OR in2")])
def test_memory_behind_gate(name, gate):
    a = _analysis(GATED / f"{name}.yaml")
    blocks = {b.output.name: b for b in a.gated}
    assert "out1" in blocks
    b = blocks["out1"]
    assert (b.kind, b.gate) == (MEMORY, gate)
    assert b.summary == f"{MEMORY}, gesetzt durch {gate}"
    assert ("nicht beobachtbar" in b.detail) == (gate == "in1 OR in2")


# ---------------------------------------------------------------------- timing block behind a gate
EXTENDED = "kurze Pulse werden auf mindestens 12 gt verlängert"


@pytest.mark.parametrize("name, gate", [("pulse-extender-and", "AND"), ("pulse-extender-or", "OR")])
def test_pulse_extender_behind_gate(name, gate):
    a = _analysis(GATED / f"{name}.yaml")
    assert a.gates["out2"] == gate  # the lamp; out1 is the copper bulb inside the extender
    assert a.timing == {"out2": EXTENDED}
    assert f"Logik vor Zeitglied an out2: {gate}, dahinter: {EXTENDED}" in a.patterns
    held = [r for r in a.pulse_responses if r.held and r.output.name == "out2"]
    if gate == "AND":  # the lamp follows a lever only while the other one is on
        assert sorted((r.input.name, [p.name for p in r.held]) for r in held) == [("in1", ["in2"]), ("in2", ["in1"])]
        assert all(r.table[1] == [] and r.table[5][0][1] == 16 and r.table[20][0][1] == 24 for r in held)
        assert held[0].label == "in1 → out2, während in2 an"
    else:  # an OR passes each lever on its own: nothing to hold
        assert held == []
    text = explain(a, name)
    assert f"- out2 hängt von mehreren Eingängen ab: **{gate}**, dahinter ein Zeitglied: **{EXTENDED}**" in text
    assert ("während in2 an |" in text) == (gate == "AND")


@pytest.mark.parametrize("path", [
    "scenarios/tpl-and2-torch.yaml", "scenarios/pla-fulladder.yaml", "scenarios/cmp-and5.yaml",
    "scenarios/tpl-or2-direct.yaml",
])
def test_plain_gates_have_no_timing_block(path):
    a = _analysis(ROOT / path)
    assert a.timing == {}
    assert not any(p.startswith("Logik vor Zeitglied") or "während" in p for p in a.patterns)


def test_t_flip_flop_behind_gate_of_four_levers():
    a = _analysis(GATED / "t-flip-flop-and-or4.yaml")
    blocks = {b.output.name: b for b in a.gated}
    assert set(blocks) == {"out1", "out2"}
    for b in blocks.values():
        assert (b.kind, b.gate) == (TFF_RISING, "(in3 AND in4) OR (in1 AND in2)")
        assert [p.name for p in b.levers] == ["in1", "in2", "in3", "in4"]
