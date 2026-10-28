"""Live oracle tests: rerun scenarios on the Fabric server and compare with the golden traces.

Slow (starts a dedicated server), so they only run with RSX_ORACLE=1: ``RSX_ORACLE=1 uv run pytest -m oracle``.
"""

import os
from pathlib import Path

import pytest

from redstone import oracle
from redstone.verify.trace import Trace, diff

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"

pytestmark = [
    pytest.mark.oracle,
    pytest.mark.skipif(not os.environ.get("RSX_ORACLE"), reason="set RSX_ORACLE=1 to run live oracle tests"),
]


def test_golden_traces_are_reproducible():
    scenarios = [ROOT / "scenarios" / f"{p.name.removesuffix('.trace.json')}.yaml" for p in sorted(GOLDEN.glob("*.trace.json"))]
    scenarios = [s for s in scenarios if s.exists()]
    if not scenarios:
        pytest.skip("no golden traces with a scenario")
    for path in oracle.run(scenarios):
        golden = Trace.load(GOLDEN / path.name)
        assert diff(golden, Trace.load(path)) == []
