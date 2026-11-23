"""The line search of the Rust core finds exactly the path of the Python reference (`compact._dust_path_py`)."""

import random
from pathlib import Path

import pytest
import yaml

from redstone.design import compact
from redstone.design.spec import from_dict
from redstone.model import BlockState, Pos

needs_rust = pytest.mark.skipif(compact._dust_path_rust is None, reason="Rust core without dust_path")

STATES = [BlockState.parse(s) for s in (
    "stone", "stone", "stone", "redstone_wire[east=none,north=none,power=0,south=none,west=none]",
    "redstone_lamp[lit=false]", "repeater[delay=1,facing=north,locked=false,powered=false]",
    "redstone_torch[lit=true]", "glass")]


@needs_rust
def test_rust_dust_path_matches_python_on_random_cases():
    rng = random.Random(3)
    found = 0
    for _ in range(4000):
        size = (rng.randint(3, 10), rng.randint(2, 5), rng.randint(3, 10))
        cells = [Pos(x, y, z) for x in range(size[0]) for y in range(size[1]) for z in range(size[2])]
        density = rng.choice((0.03, 0.1, 0.25))
        states = {c: rng.choice(STATES) for c in cells if rng.random() < density}
        start, goal = rng.choice(cells), rng.choice(cells)
        a, b = rng.choice(cells), rng.choice(cells)
        box = (Pos(-1, -1, -1), Pos(size[0], size[1], size[2]))
        limit = rng.randint(1, 30)
        want = compact._dust_path_py(states, start, goal, a, b, limit, box)
        got = compact._dust_path(states, start, goal, a, b, limit, box)
        assert got == want, (states, start, goal, a, b, limit, box)
        found += want is not None and len(want) > 2
    assert found > 100  # the cases are not all blocked


@needs_rust
def test_rust_dust_path_matches_python_while_relocating(monkeypatch):
    """Every line search of the relocations of a real composed design gives the same path in both."""
    from redstone.design.decompose import decomposed

    calls = []

    def both(states, start, goal, a, b, limit, box):
        got = rust(states, start, goal, a, b, limit, box)
        assert got == compact._dust_path_py(states, start, goal, a, b, limit, box)
        calls.append(got is not None)
        return got

    rust = compact._dust_path
    monkeypatch.setattr(compact, "_dust_path", both)
    root = Path(__file__).resolve().parents[2]
    spec = from_dict(yaml.safe_load((root / "examples/specs/composed/and5.yaml").read_text(encoding="utf-8")))
    for cand in decomposed(spec)[:3]:
        for _ in compact.relocations(compact.normalize(cand)):
            pass
    assert len(calls) > 50 and any(calls)
