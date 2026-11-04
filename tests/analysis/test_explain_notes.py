"""`rsx explain` lists the piston mechanics notes (quasi-connectivity, BUD, block dropping, 0-tick) in German."""

from pathlib import Path

from redstone.analysis.analyze import analyze
from redstone.analysis.explain import explain
from redstone.cli import main
from redstone.sim import run
from redstone.sim.notes import MECHANICS, notes_of
from redstone.verify import load_scenario

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _section(text: str) -> str:
    return text.split("## Genutzte Sonderfälle", 1)[1].split("## Hinweise", 1)[0]


def test_explain_zero_tick_lists_qc_zero_tick_and_dropping(capsys):
    assert main(["explain", str(SCENARIOS / "zero-tick-piston.yaml")]) == 0
    section = _section(capsys.readouterr().out)
    assert f"- {MECHANICS['zero_tick']} (bei (2,2,0), (2,2,3))" in section
    assert f"- {MECHANICS['quasi_connectivity']} (bei (1,1,0), (1,1,3))" in section
    assert f"- {MECHANICS['piston_spit']} (bei (2,2,0))" in section
    assert "0-Tick" in section and "Quasi-Connectivity" in section and "Block-Dropping" in section


def test_explain_lists_dropping_from_sticky_pulse_run():
    """The analysis toggles levers only when the circuit is idle (no short pulses), so the notes of the
    scenario run itself are handed to explain here."""
    scenario = load_scenario(SCENARIOS / "sticky-pulse-lengths.yaml")
    _, world = run(scenario)
    analysis = analyze(scenario.grid)
    analysis.notes = notes_of(world)
    section = _section(explain(analysis, "sticky-pulse-lengths"))
    assert f"- {MECHANICS['piston_spit']} (bei (1,1,0), (1,1,2))" in section


def test_explain_qc_bud_notes():
    scenario = load_scenario(SCENARIOS / "qc-bud.yaml")
    _, world = run(scenario)
    analysis = analyze(scenario.grid)
    analysis.notes = notes_of(world)
    section = _section(explain(analysis, "qc-bud"))
    assert f"- {MECHANICS['bud']} (bei (1,1,0))" in section
    assert f"- {MECHANICS['quasi_connectivity']} (bei (1,1,0))" in section
