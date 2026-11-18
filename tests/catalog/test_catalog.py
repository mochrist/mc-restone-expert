"""Acceptance of every catalog entry (src/redstone/catalog) on both simulator cores."""

from __future__ import annotations

import pytest

from redstone.catalog import ENTRIES, entries, find, get
from redstone.sim import core

CORES = ["python"] + (["rust"] if core.rust_available() else [])


@pytest.fixture(params=CORES)
def sim_core(request):
    before = core.active()
    core.use(request.param)
    entries._settled.cache_clear()
    yield request.param
    core.use(before)
    entries._settled.cache_clear()


@pytest.mark.parametrize("key", [e.key for e in ENTRIES])
def test_acceptance(key, sim_core):
    assert get(key).accept() == []


def test_entries_are_complete():
    keys = [e.key for e in ENTRIES]
    assert len(keys) == len(set(keys))
    for e in ENTRIES:
        built = e.built()
        for name in e.inputs:
            assert name in built.ports
        assert e.title and e.description and e.usage and e.keywords


def test_build_returns_a_fresh_copy():
    e = get("piston-door-2x2")
    g = e.build()
    g.set((0, 0, 0), "glass")
    assert e.build().get((0, 0, 0)).id != "glass"


@pytest.mark.parametrize("query, key", [
    ("Kolbentür", "piston-door-2x2"),
    ("ich will eine 2x2 piston door", "piston-door-2x2"),
    ("Itemsortierer für meine Truhen", "item-sorter"),
    ("geheimtür mit knopf", "hidden-door-1x2"),
])
def test_find(query, key):
    assert find(query)[0].key == key


def test_find_nothing():
    assert find("Taktgeber") == []


@pytest.mark.parametrize("key", [e.key for e in ENTRIES])
def test_position_and_rotation_proof(key):
    """Like design/robust.py: several origins (dust update order depends on coordinates) and all rotations."""
    from redstone.design.robust import origins

    e = get(key)
    for turns in range(4):
        for origin in origins(sample=6):
            assert e.accept(origin, turns) == [], (tuple(origin), turns)
