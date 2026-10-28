"""Smoke tests for the M3 analysis (work in progress, see STATUS.md)."""

from pathlib import Path

from redstone.analysis.analyze import analyze
from redstone.analysis.explain import explain
from redstone.verify import load_scenario

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _reactions(name):
    a = analyze(load_scenario(SCENARIOS / f"{name}.yaml").grid)
    return a, {(r.input.name, x.output.name): x for r in a.responses for x in r.reactions}


def test_repeater_lock_is_and_not():
    a, reactions = _reactions("repeater-lock")
    assert reactions[("in1", "out1")].kind == "folgt dem Eingang"
    assert reactions[("in1", "out1")].delays[:2] == [2, 6]  # repeater 2 gt; off: repeater 2 + lamp 4
    assert a.gates["out1"] == "Eingang 1 AND NOT Eingang 2"
    assert "Wahrheitstabelle" in explain(a, "repeater-lock")


def test_torch_inverts_and_button_pulses():
    _, r = _reactions("torch-inverter")
    assert r[("in1", "out1")].kind == "invertiert den Eingang"
    _, r = _reactions("repeater-pulse-extend")
    assert r[("in3", "out3")].kind == "Puls"
    assert r[("in3", "out3")].pulses == [24, 24, 24]  # stone button 20 gt + lamp off delay 4 gt
    assert r[("in1", "out1")].kind.startswith("Pulsgenerator")
