"""Simulator vs. golden traces recorded on the real 26.3 server (tests/golden, made with `rsx oracle --golden`)."""

from pathlib import Path

import pytest

from redstone.sim import run
from redstone.verify import Trace, diff, load_scenario

ROOT = Path(__file__).parents[2]
GOLDEN = sorted((ROOT / "tests" / "golden").glob("*.trace.json"))

# Scenarios whose components are not modeled yet. strict=True: a fixed one must be removed from this list.
NOT_YET_MODELED: set[str] = set()


@pytest.mark.parametrize("golden", GOLDEN, ids=lambda p: p.name.removesuffix(".trace.json"))
def test_simulator_matches_game(golden: Path):
    expected = Trace.load(golden)
    if expected.scenario in NOT_YET_MODELED:
        pytest.xfail("components not modeled yet")
    scenario = load_scenario(ROOT / "scenarios" / f"{expected.scenario}.yaml")
    actual, world = run(scenario)
    mismatches = diff(expected, actual)
    assert not mismatches, "\n".join(str(m) for m in mismatches[:15]) + (
        "\nwarnings: " + "; ".join(world.warnings) if world.warnings else "")
