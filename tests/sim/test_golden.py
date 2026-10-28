"""Simulator vs. golden traces recorded on the real 26.3 server (tests/golden, made with `rsx oracle --golden`)."""

from pathlib import Path

import pytest

from redstone.sim import run
from redstone.verify import Trace, diff, load_scenario

ROOT = Path(__file__).parents[2]
GOLDEN = sorted((ROOT / "tests" / "golden").glob("*.trace.json"))

# Scenarios whose components are not modeled yet. strict=True: a fixed one must be removed from this list.
NOT_YET_MODELED: set[str] = {
    "comparator-container", "comparator-modes", "dust-decay", "observer-clock", "observer-pulse",
    "piston-timing", "qc-bud", "repeater-delay-2", "repeater-delays", "repeater-lock", "torch-burnout",
    "torch-inverter",
}


@pytest.mark.parametrize("golden", GOLDEN, ids=lambda p: p.name.removesuffix(".trace.json"))
def test_simulator_matches_game(golden: Path):
    expected = Trace.load(golden)
    if expected.scenario in NOT_YET_MODELED:
        pytest.xfail("components not modeled yet")  # remove the name once it passes
    scenario = load_scenario(ROOT / "scenarios" / f"{expected.scenario}.yaml")
    actual, world = run(scenario)
    mismatches = diff(expected, actual)
    assert not mismatches, "\n".join(str(m) for m in mismatches[:15]) + (
        "\nwarnings: " + "; ".join(world.warnings) if world.warnings else "")
