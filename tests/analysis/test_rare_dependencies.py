"""Partial tables for outputs that only react in rare lever combinations: an AND over many levers, an OR of
ANDs whose terms need three or more levers at once. Ground truth: an exhaustive sweep over all levers."""

import itertools

import pytest

from redstone.analysis.analyze import analyze
from redstone.analysis.experiment import Circuit
from redstone.design import spec as spec_mod
from redstone.design.synth import pla

LETTERS = "abcdefgh"


def _grid(function: str, n: int):
    s = spec_mod.from_dict({"inputs": list(LETTERS[:n]), "outputs": ["y"], "function": {"y": function}})
    return pla(s).grid


def _truth(grid, a, lamp):
    """Lamp state for every combination of all levers (fresh world each)."""
    circuit = Circuit(grid)
    result = {}
    for combo in itertools.product([False, True], repeat=len(a.inputs)):
        rec = circuit.run([(1, p.pos, "use") for p, want in zip(a.inputs, combo) if want], max_ticks=400, quiet=12)
        result[combo] = rec.on_at(lamp.pos, rec.ticks)
    return result


@pytest.mark.parametrize("function,n,used", [
    (" and ".join(LETTERS[:7]), 7, 7),
    (" and ".join(LETTERS[:8]), 8, 8),
    ("(a and b and c) or (d and e and f)", 7, 6),
    ("(a and b and c and d) or (e and f and g)", 7, 7),
    ("(a and b and c) or (d and e and f) or (g and h)", 8, 8),
])
def test_rare_combinations_are_found(function, n, used):
    grid = _grid(function, n)
    a = analyze(grid)
    assert not a.truth_table
    ((levers, outs, table),) = [t for t in a.partial_tables if any(o.kind == "redstone_lamp" for o in t[1])]
    lamp = next(o for o in outs if o.kind == "redstone_lamp")
    k = outs.index(lamp)
    assert len(levers) == used
    truth = _truth(grid, a, lamp)
    idx = [a.inputs.index(lv) for lv in levers]
    for combo, out in table:
        full = [False] * len(a.inputs)
        for i, v in zip(idx, combo):
            full[i] = v
        assert out[k] == truth[tuple(full)], (combo, function)
    # the table is the whole truth: the unused levers never matter
    assert all(truth[c] == truth[tuple(c[i] if i in idx else False for i in range(len(c)))] for c in truth)
