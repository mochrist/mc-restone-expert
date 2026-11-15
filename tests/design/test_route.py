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
        got = compose._route(start, goals, solid, keep, lo, hi, tight)
        assert got == want, (start, goals, solid, keep, lo, hi, tight)
        found += want is not None
    assert found > 100  # the cases are not all unroutable


@pytest.mark.parametrize("router", ["_route_py", "_route"])
def test_path_never_runs_straight_over_itself(router):
    """A line winding up over itself would put a floor block on its own dust (it cuts the step up)."""
    rng = random.Random(11)
    found = 0
    for _ in range(1500):
        start, goals, solid, keep, lo, hi = _case(rng)
        path = getattr(compose, router)(start, goals, solid, keep, lo, hi, True)
        found += path is not None
        for k, a in enumerate(path or []):
            for b in path[k + 1:]:
                assert not (a.x == b.x and a.z == b.z and 1 <= abs(a.y - b.y) <= 2), path
    assert found > 50


@pytest.mark.parametrize("router", ["_route_py", "_route"])
def test_winding_line_is_refused(router):
    """In a 2x2 shaft the only way three blocks up is a spiral, whose floors would cut its own steps."""
    solid = {Pos(x, y, z) for x in range(-1, 3) for y in range(0, 6) for z in range(-1, 3)
             if not (0 <= x <= 1 and 0 <= z <= 1)} | {Pos(x, 0, z) for x in (0, 1) for z in (0, 1)}
    lo, hi = Pos(-1, 0, -1), Pos(2, 5, 2)
    assert getattr(compose, router)(Pos(0, 1, 0), {Pos(1, 4, 0)}, solid, set(), lo, hi, True) is None
