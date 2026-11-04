"""Pattern experiments of the analysis: pulse response, RS latch, decoder."""

from pathlib import Path

from redstone.analysis.analyze import analyze
from redstone.analysis.patterns import PulseResponse, _classify_pulse, is_decoder
from redstone.analysis.ports import Port
from redstone.model import BlockState, Pos
from redstone.verify import load_scenario

ROOT = Path(__file__).parents[2]


def _port(name: str, kind: str) -> Port:
    return Port(name, Pos(0, 0, 0), kind, BlockState.parse("minecraft:stone"))


def _classify(table: dict, out_kind: str = "piston") -> PulseResponse:
    r = PulseResponse(_port("in1", "lever"), _port("out1", out_kind), table)
    _classify_pulse(r)
    return r


def test_pulse_shortener():
    r = _classify({L: [(1, 2)] for L in (2, 3, 4, 10, 20)})
    assert r.kind == "Pulsverkürzer (Ausgangspuls immer 2 gt)"
    assert "Verzögerung 1 gt" in r.detail


def test_pulse_filter_and_passthrough_with_lamp_delay():
    table = {1: [], 2: [], 3: [(8, 7)], 4: [(8, 8)], 10: [(8, 14)]}
    r = _classify(table, "redstone_lamp")
    assert r.kind == "Pulsfilter; Puls wird unverändert durchgereicht"
    assert r.detail.startswith("Pulse unter 3 gt werden unterdrückt")


def test_minimum_pulse_length_of_a_repeater():
    table = {L: [(4, max(L, 4) + 4)] for L in (1, 2, 4, 6, 10)}
    r = _classify(table, "redstone_lamp")
    assert r.kind == "kurze Pulse werden auf mindestens 4 gt verlängert"


def test_output_that_stays_on_is_memory():
    r = _classify({1: [], 2: [(3, None)], 4: [(3, None)]})
    assert r.kind == "Ausgang bleibt nach dem Puls an (Speicher)"


def test_decoder_truth_table():
    combos = [(False, False), (False, True), (True, False), (True, True)]
    decoder = [(c, tuple(i == j for j in range(4))) for i, c in enumerate(combos)]
    assert is_decoder(decoder)
    not_decoder = [(c, (c[0] and c[1], c[0] or c[1])) for c in combos]
    assert not is_decoder(not_decoder)


def test_rs_latch_end_to_end():
    a = analyze(load_scenario(ROOT / "tests/fixtures/analysis/rs-latch.yaml").grid)
    assert len(a.latches) == 1
    latch = a.latches[0]
    assert (latch.set_input.name, latch.reset_input.name, latch.output.name) == ("in2", "in1", "out1")
    assert "RS-Latch an out1: in2 setzt, in1 setzt zurück" in a.patterns
    # a 1 gt pulse is too short for the torch (it checks its input only in its scheduled tick)
    in2 = next(r for r in a.pulse_responses if r.input.name == "in2")
    assert in2.table[1] == [] and in2.kind == "Ausgang bleibt nach dem Puls an (Speicher)"


def test_repeater_minimum_pulse_from_scenario():
    a = analyze(load_scenario(ROOT / "scenarios/repeater-delays.yaml").grid)
    kinds = {(r.input.name, r.output.name): r.kind for r in a.pulse_responses}
    assert kinds[("in2", "out1")] == "kurze Pulse werden auf mindestens 4 gt verlängert"
    assert not any("kurze Pulse" in p for p in a.patterns)  # a plain repeater is no building block
