"""Generic torch PLA synthesis: logic minimisation and simulated correctness (M4)."""

import itertools
import random

import pytest

from redstone.design.evaluate import evaluate
from redstone.design.spec import Spec, from_functions
from redstone.design.synth import _covers, minimize, pla


def test_minimize_covers_exactly():
    rng = random.Random(7)
    for _ in range(200):
        n = rng.choice([1, 2, 3, 4])
        combos = list(itertools.product([False, True], repeat=n))
        ones = [c for c in combos if rng.random() < 0.5]
        imps = minimize(n, ones)
        for c in combos:
            assert any(_covers(i, c) for i in imps) == (c in ones)


def test_minimize_finds_simple_forms():
    assert minimize(2, [(True, True)]) == [(True, True)]
    assert sorted(minimize(2, [(False, True), (True, True), (True, False)]), key=str) == [(None, True), (True, None)]
    assert minimize(2, list(itertools.product([False, True], repeat=2))) == [(None, None)]


@pytest.mark.parametrize(("inputs", "functions"), [
    (["a"], {"y": "not a"}),
    (["a", "b"], {"y": "a != b"}),
    (["s", "a", "b"], {"y": "(a and not s) or (b and s)"}),
    (["a", "b"], {"y": "False", "z": "True"}),
])
def test_pla_is_correct(inputs, functions):
    spec = from_functions(inputs, functions)
    c = pla(spec)
    ev = evaluate(c, spec)
    assert ev.ok, ev.errors


def test_pla_random_three_input_functions():
    rng = random.Random(3)
    for _ in range(4):
        table = {c: (rng.random() < 0.5,) for c in itertools.product([False, True], repeat=3)}
        spec = Spec(["a", "b", "c"], ["y"], table)
        ev = evaluate(pla(spec), spec)
        assert ev.ok, (table, ev.errors)


def test_pla_limits():
    spec = from_functions(["a", "b", "c", "d", "e"], {"y": "a"})
    assert pla(spec) is None
