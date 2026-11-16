"""Position and rotation robustness (design/robust.py)."""

from __future__ import annotations

import pytest

from redstone.design.evaluate import observe
from redstone.design.robust import check, origins, piston_race, robust
from redstone.design.spec import from_functions
from redstone.design.templates import TEMPLATES
from redstone.model import Pos
from redstone.sim.blocks.wire import _spread, block_pos_hash
from redstone.sim.runner import ORACLE_ORIGIN

race = piston_race


def _template(name: str):
    return next(t for t in TEMPLATES if t.name == name).build()


def test_origins_cover_all_shifts_mod_16():
    places = origins()
    assert places[0] == ORACLE_ORIGIN
    low = {_spread(block_pos_hash((p.x, p.y, p.z))) & 15 for p in places
           if _spread(block_pos_hash((p.x, p.y, p.z))) >> 16 == 0}
    assert low == set(range(16))
    assert len({_spread(block_pos_hash((p.x, p.y, p.z))) >> 16 for p in places}) >= 6  # several k
    assert 40 <= len(places) <= 60
    sample = origins(12)
    assert len(sample) == 12 and sample[0] == ORACLE_ORIGIN


def test_same_shift_and_k_same_order():
    """The choice of origins rests on this: with the same (shift mod 16, k) the dust order is the same."""
    c = race()
    row = [observe(c, [(True,)], origin=Pos(dx, 200, 0))[(True,)] for dx in range(32)]
    assert row[:16] == row[16:]
    assert len(set(row)) == 2  # and the race really depends on the position


def test_position_dependent_candidate_is_found():
    spec = from_functions(["a"], {"y": "a"})
    r = check(race(), spec, quick=True)
    assert r.rotations == 4 and r.placements == 4 * len(origins())
    assert r.wrong > 0 and not r.ok
    assert robust(race(), spec, quick=True, stop_early=True)  # one finding is enough


@pytest.mark.parametrize("name", ["and2-torch", "xor2-comparator"])
def test_gates_are_position_proof(name):
    t = next(t for t in TEMPLATES if t.name == name)
    spec = from_functions(list(t.inputs), dict(t.function))
    r = check(_template(name), spec)
    assert r.ok, r.findings[:3]
    assert r.placements == 4 * len(origins())
