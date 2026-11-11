"""Partial truth tables: only some lever combinations matter, the others are "egal" (don't care)."""

from pathlib import Path

import pytest

from redstone.design.evaluate import evaluate
from redstone.design.spec import Spec, load
from redstone.design.synth import minimize_partial, pla

ROOT = Path(__file__).parents[2]


def test_partial_spec_from_yaml():
    spec = load(ROOT / "examples" / "specs" / "encoder7.yaml")
    assert spec.partial and len(spec.combos()) == 8
    assert spec.combos()[0] == (False,) * 7  # itertools.product order
    assert "8 von 128 Kombinationen" in spec.describe()
    assert spec.to_dict()["others"] == "dont_care"


def test_partial_spec_must_list_exactly_the_care_set():
    with pytest.raises(ValueError):
        Spec(["a", "b"], ["y"], {(False, False): (False,)}, care=frozenset({(False, False), (True, False)}))
    with pytest.raises(ValueError):  # a full spec still needs every row
        Spec(["a", "b"], ["y"], {(False, False): (False,)})


def test_minimize_partial_uses_dont_cares():
    one_hot = [tuple(j == i for j in range(5)) for i in range(5)]
    zero = (False,) * 5
    terms = minimize_partial(5, one_hot[:3], [zero] + one_hot[3:])
    # each on-combination grows to its single positive literal
    assert set(terms) == {tuple(True if j == i else None for j in range(5)) for i in range(3)}


def test_pla_of_partial_encoder_is_correct():
    spec = load(ROOT / "examples" / "specs" / "encoder7.yaml")
    cand = pla(spec)
    assert cand is not None
    assert evaluate(cand, spec).ok


def test_evaluate_ignores_dont_care_rows():
    spec = load(ROOT / "examples" / "specs" / "encoder7.yaml")
    cand = pla(spec)
    wrong = Spec(spec.inputs, spec.outputs, dict(spec.table) | {(True,) + (False,) * 6: (True, True, True)},
                 care=spec.care)
    assert not evaluate(cand, wrong).correct


def test_seg7_gets_a_partial_spec():
    path = ROOT / "tests" / "fixtures" / "external" / "seg7.litematic"
    if not path.exists():
        pytest.skip("seg7.litematic missing, run: uv run python scripts/fetch_external_fixtures.py")
    from redstone import io
    from redstone.analysis.analyze import analyze
    from redstone.cli import _spec_of_existing

    spec, original = _spec_of_existing(analyze(io.load(path)), "seg7")
    assert spec.partial and len(spec.combos()) == 11  # stored lever states plus each lever flipped
    assert evaluate(original, spec).ok
