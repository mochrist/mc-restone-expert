"""The dust router of the Rust core finds exactly the path of the Python reference (`compose._route_py`)."""

import random

import pytest

from redstone.design import compose
from redstone.model import Pos

needs_rust = pytest.mark.skipif(compose._route_rust is None, reason="Rust core without the router")


def _case(rng: random.Random):
    size = Pos(rng.randint(3, 12), rng.randint(2, 5), rng.randint(3, 12))
    cells = [Pos(x, y, z) for x in range(-1, size.x + 1) for y in range(-1, size.y + 1) for z in range(-1, size.z + 1)]
    solid = {c for c in cells if rng.random() < rng.choice((0.05, 0.15, 0.3))}
    keep = {c for c in cells if rng.random() < 0.03}
    start = rng.choice(cells)  # also outside the box and on solid blocks
    goals = {rng.choice(cells) for _ in range(rng.randint(1, 4))}
    lo, hi = Pos(0, 0, 0), Pos(size.x - 1, size.y - 1, size.z - 1)
    return start, goals, solid, keep, lo, hi


@needs_rust
@pytest.mark.parametrize("tight", [False, True])
def test_rust_router_matches_python(tight):
    rng = random.Random(7)
    found = 0
    for _ in range(3000):
        start, goals, solid, keep, lo, hi = _case(rng)
        want = compose._route_py(start, goals, solid, keep, lo, hi, tight)
        got = compose._route_once(start, goals, solid, keep, lo, hi, tight, False)
        assert got == want, (start, goals, solid, keep, lo, hi, tight)
        found += want is not None
    assert found > 100  # the cases are not all unroutable


@pytest.mark.parametrize("core", ["python", "rust"])
def test_path_never_cuts_its_own_steps(core, monkeypatch):
    """A line winding up over itself would put a floor block on its own dust or above a step; such paths are
    searched again strictly. Paths without that stay exactly as the plain search finds them."""
    if core == "python":
        monkeypatch.setattr(compose, "_route_rust", None)
    elif compose._route_rust is None:
        pytest.skip("Rust core without the router")
    rng = random.Random(11)
    found = redone = 0
    for _ in range(3000):
        start, goals, solid, keep, lo, hi = _case(rng)
        plain = compose._route_once(start, goals, solid, keep, lo, hi, True, False)
        path = compose._route(start, goals, solid, keep, lo, hi, True)
        found += path is not None
        assert not compose.clashes(path or []), path
        if plain is not None and not compose.clashes(plain):
            assert path == plain
        redone += plain is not None and path != plain
    assert found > 50 and redone > 0


@needs_rust
def test_strict_rust_router_matches_python():
    rng = random.Random(5)
    for _ in range(2000):
        start, goals, solid, keep, lo, hi = _case(rng)
        want = compose._route_py(start, goals, solid, keep, lo, hi, True, True)
        got = compose._route_rust(tuple(start), goals, solid, keep, tuple(lo), tuple(hi), True, True)
        assert (None if got is None else [Pos(*c) for c in got]) == want
