"""Generic torch PLA synthesis: logic minimisation, layout variants and simulated correctness (M4).

4-input designs are checked with the fresh-world truth table only (full=False) to keep this file fast;
the full check with all single-lever transitions passes as well (run by hand, about 5-20 s per design)."""

import itertools
import random

import pytest

from redstone.design import synth
from redstone.design.compact import crop, normalize
from redstone.design.evaluate import evaluate
from redstone.design.spec import Spec, from_functions
from redstone.design.synth import _covers, minimize, minimize_multi, pla


def _random_spec(rng, n, m):
    table = {c: tuple(rng.random() < 0.5 for _ in range(m)) for c in itertools.product([False, True], repeat=n)}
    return Spec(list("abcd"[:n]), [f"y{j}" for j in range(m)], table)


def _ids(c, block):
    return [(p, s) for p, s in c.grid.items() if s.id == block]


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


def test_minimize_multi_covers_exactly():
    rng = random.Random(8)
    for _ in range(100):
        n, m = rng.choice([1, 2, 3, 4]), rng.choice([1, 2, 3])
        combos = list(itertools.product([False, True], repeat=n))
        ones = [[c for c in combos if rng.random() < 0.5] for _ in range(m)]
        for imps, o in zip(minimize_multi(n, ones), ones):
            for c in combos:
                assert any(_covers(i, c) for i in imps) == (c in o)


def test_minimize_multi_prefers_shared_terms():
    # y = a b, z = a b + c: a b serves both outputs
    combos = list(itertools.product([False, True], repeat=3))
    ones = [[c for c in combos if c[0] and c[1]], [c for c in combos if (c[0] and c[1]) or c[2]]]
    terms = minimize_multi(3, ones)
    assert terms == [[(True, True, None)], [(None, None, True), (True, True, None)]]
    # the full adder has nothing to share: still as few terms as with separate minimisation
    ones = [[c for c in combos if sum(c) % 2], [c for c in combos if sum(c) >= 2]]
    assert sum(len(t) for t in minimize_multi(3, ones)) == 7


@pytest.mark.parametrize(("inputs", "functions"), [
    (["a"], {"y": "not a"}),
    (["a", "b"], {"y": "a != b"}),
    (["s", "a", "b"], {"y": "(a and not s) or (b and s)"}),
    (["a", "b"], {"y": "False", "z": "True"}),
    (["a", "b"], {"y": "not a and not b"}),  # two inputs with only the inverted rail
    (["a", "b", "c"], {"y": "not a and c"}),  # unused input b
    (["a", "b", "c"], {"y": "(not a and not b) or not c"}),
    (["a", "b", "c"], {"y": "not a and not b and not c", "z": "b"}),
])
def test_pla_is_correct(inputs, functions):
    spec = from_functions(inputs, functions)
    c = pla(spec)
    ev = evaluate(c, spec)
    assert ev.ok, ev.errors


def test_shared_term_uses_one_column():
    spec = from_functions(["a", "b", "c"], {"y": "a and b", "z": "(a and b) or c"})
    shared, separate = pla(spec, share=True), pla(spec, share=False)
    assert "2 Termspalten" in shared.description and "gemeinsame Terme" in shared.description
    assert "3 Termspalten" in separate.description
    assert shared.volume <= separate.volume
    for c in (shared, separate):
        ev = evaluate(c, spec)
        assert ev.ok, ev.errors


def test_term_shared_by_three_outputs_climbs_to_a_second_row():
    spec = from_functions(["a", "b", "c"], {"x": "a and b", "y": "(a and b) or c",
                                            "z": "(a and b) or (not c and not a)"})
    c = pla(spec, share=True)
    assert any(p.y == 2 for p, _ in _ids(c, "redstone_wire"))  # a collector climbs into the OR plane
    ev = evaluate(c, spec)
    assert ev.ok, ev.errors


def test_parity_of_four_inputs_needs_eight_terms():
    spec = from_functions(list("abcd"), {"y": "a ^ b ^ c ^ d"})
    c = pla(spec)
    assert "8 Termspalten" in c.description
    ev = evaluate(c, spec, full=False)
    assert ev.correct, ev.errors


def test_more_than_fourteen_columns_get_repeaters():
    # 20 hand-picked columns: rails and the long output line need repeaters, the other output climbs
    combos = list(itertools.product([False, True], repeat=3))
    imps = combos + [p for p in itertools.product([False, True, None], repeat=3) if p.count(None) == 1]
    cols = [synth._Col(p, (0, 1) if k in (0, len(imps) - 1) else (1,)) for k, p in enumerate(imps)]
    terms = [[c.imp for c in cols if j in c.outs] for j in range(2)]
    table = {x: tuple(any(_covers(t, x) for t in terms[j]) for j in range(2)) for x in combos}
    spec = Spec(["a", "b", "c"], ["y", "z"], table)
    c = normalize(crop(synth._to_candidate("t", synth._build(3, 2, cols, [0, 1]), spec, terms, True)))
    reps = _ids(c, "repeater")
    assert any(p.y == 3 for p, _ in reps)  # rails
    assert any(p.y == 1 and s.get("facing") in ("east", "west") for p, s in reps)  # output line
    ev = evaluate(c, spec, full=False)
    assert ev.correct, ev.errors


def test_line_planning_places_repeaters_late():
    # one source at cell 0, needed cells far away: a repeater just before the dust runs out
    assert synth._plan_line(20, {0: 15}, {19}, set(range(1, 20, 2))) == {15}
    assert synth._plan_line(14, {0: 15}, {13}, set(range(1, 14))) == set()
    assert synth._plan_line(20, {0: 15}, {19}, set()) is None
    # every source alone must reach the end: the far one decides
    assert synth._plan_line(30, {0: 15, 20: 15}, {29}, {10, 15, 25}) == {15}


def test_pla_random_functions():
    rng = random.Random(3)
    for n, m in [(2, 2), (3, 1), (3, 2), (3, 3)]:
        spec = _random_spec(rng, n, m)
        ev = evaluate(pla(spec), spec)
        assert ev.ok, (spec.table, ev.errors)
    for n, m in [(4, 3)]:
        spec = _random_spec(rng, n, m)
        ev = evaluate(pla(spec), spec, full=False)
        assert ev.correct, (spec.table, ev.errors)


def test_pla_limits():
    spec = from_functions(list("abcdefg"), {"y": "a"})  # 7 inputs, over MAX_INPUTS
    assert pla(spec) is None


@pytest.mark.parametrize("seed", range(6))
def test_equal_outputs_share_a_line(seed):
    """Outputs with the same function get one line with a lamp each (seg7: 18 of 21 outputs are equal)."""
    rng = random.Random(100 + seed)
    n = rng.choice([2, 3])
    funcs = [tuple(rng.random() < 0.5 for _ in range(2 ** n)) for _ in range(2)]
    pick = [rng.randrange(2) for _ in range(rng.randint(3, 8))]
    combos = list(itertools.product([False, True], repeat=n))
    spec = Spec(list("abc"[:n]), [f"y{j}" for j in range(len(pick))],
                {c: tuple(funcs[f][i] for f in pick) for i, c in enumerate(combos)})
    c = pla(spec)
    assert c is not None and len(set(c.outputs)) == len(pick)
    ev = evaluate(c, spec)
    assert ev.correct, ev.errors


def test_many_equal_outputs_lamps_on_both_sides():
    spec = from_functions(["a", "b"], {f"y{j}": "not a" for j in range(18)} | {"z": "a and b"})
    c = pla(spec)
    assert c is not None and len(set(c.outputs)) == 19
    lamps = _ids(c, "redstone_lamp")
    assert len(lamps) == 19
    ev = evaluate(c, spec)
    assert ev.ok, (ev.errors, ev.violations)
    assert c.block_count < 150, c.block_count
