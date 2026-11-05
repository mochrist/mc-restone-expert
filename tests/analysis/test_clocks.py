"""Clock detection on typical clock designs that a schematic stores in a stopped state."""

from pathlib import Path

import pytest

from redstone.analysis.analyze import analyze
from redstone.analysis.explain import explain
from redstone.verify import load_scenario

CLOCKS = Path(__file__).parents[1] / "fixtures" / "analysis" / "clocks"


@pytest.mark.parametrize(("name", "period", "on_ticks", "stops_at"), [
    ("observer-pair-stopped", 6, 2, None),      # matches golden trace observer-clock
    ("repeater-ring-running", 8, 2, None),      # lamp off delay (4 gt) is subtracted
    ("torch-repeater-4", 20, 10, None),
    ("torch-repeater-1", 8, 4, 60),             # torch burns out (golden trace torch-repeater-clock)
])
def test_clock_detected(name, period, on_ticks, stops_at):
    a = analyze(load_scenario(CLOCKS / f"{name}.yaml").grid)
    assert a.oscillates
    assert a.clock is not None
    assert (a.clock.period, a.clock.on_ticks, a.clock.stops_at) == (period, on_ticks, stops_at)
    assert a.clock.needs_start  # stored stopped: only the kick (neighbour + shape updates) starts it


def test_burnout_is_explained():
    a = analyze(load_scenario(CLOCKS / "torch-repeater-1.yaml").grid)
    text = explain(a, "torch-repeater-1")
    assert "endet bei Tick 60 (Fackel-Burnout)" in text
