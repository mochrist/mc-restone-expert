"""The repeater planning of the Rust core finds exactly the repeaters of the Python reference
(`synth._plan_line_py`)."""

import random

import pytest

from redstone.design import synth

needs_rust = pytest.mark.skipif(synth._plan_line_rust is None, reason="Rust core without plan_line")


@needs_rust
def test_rust_plan_line_matches_python():
    rng = random.Random(5)
    found = 0
    for _ in range(20000):
        length = rng.randint(0, 60)
        cells = list(range(length))
        sources = {c: rng.choice((15, 15, 16, rng.randint(1, 16))) for c in rng.sample(cells, min(length, rng.randint(1, 4)))}
        need = set(rng.sample(cells, min(length, rng.randint(0, 6))))
        allowed = {c for c in range(-1, length + 2) if rng.random() < rng.choice((0.2, 0.5, 0.9))}
        want = synth._plan_line_py(length, sources, need, allowed)
        got = synth._plan_line(length, sources, need, allowed)
        assert got == want, (length, sources, need, allowed)
        found += want is not None and len(want) > 0
    assert found > 1000  # many cases need repeaters
