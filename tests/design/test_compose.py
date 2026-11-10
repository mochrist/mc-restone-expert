"""Composition of building blocks (design/compose.py) and gated behaviour specs (behaviour.gated)."""

import sys
from pathlib import Path

import pytest
import yaml

from redstone.design import behaviour as bh
from redstone.design.compose import chains, rotate
from redstone.design.evaluate import evaluate_any
from redstone.design.search import template_candidates
from redstone.design.spec import from_functions
from redstone.verify.trace import Trace

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import compose_scenarios as gen  # noqa: E402


def _and_gate():
    return next(c for c in template_candidates(from_functions(["a", "b"], {"y": "a and b"})) if c.name == "and2-torch")


def test_rotate_four_times_is_identity():
    c = _and_gate()
    r = c
    for _ in range(4):
        r = rotate(r, 1)
    assert dict(r.grid.items()) == dict(c.grid.items())
    assert r.inputs == c.inputs and r.outputs == c.outputs


def test_rotated_gate_still_works():
    spec = from_functions(["a", "b"], {"y": "a and b"})
    for k in range(4):
        assert evaluate_any(rotate(_and_gate(), k), spec).ok


def test_rotate_turns_directional_states():
    c = rotate(_and_gate(), 1)
    torches = [s for _, s in c.grid.items() if s.id == "redstone_wall_torch"]
    assert torches and all(s.get("facing") == "west" for s in torches)  # south turned clockwise


def test_gated_spec_trials():
    spec = bh.gated(["a", "b"], "a and b", bh.t_flip_flop())
    names = [t.name for t in spec.trials]
    assert "a gesperrt (alle anderen aus)" in names and "b: vier Flanken (a=1)" in names
    t = next(t for t in spec.trials if t.name == "a: vier Flanken (b=1)")
    assert t.actions[0] == (bh.START, 1)  # b switched on first
    assert t.expected[0][0][0] == bh.t_flip_flop().trials[0].expected[0][0][0] + bh.SETUP + bh.GATE_SLACK


def test_gated_rejects_gate_on_at_rest():
    with pytest.raises(ValueError):
        bh.gated(["a", "b"], "not a", bh.monostable(8))


def test_buffer_composed_with_itself_is_a_delay():
    buf = next(c for c in template_candidates(from_functions(["a"], {"y": "a"})) if c.name == "buffer-repeater")
    spec = from_functions(["a"], {"y": "a"})
    assert any(evaluate_any(c, spec).ok for _, (_, c) in zip(range(20), chains(buf, 0, buf, 0)))


@pytest.mark.parametrize("path", gen.examples(), ids=lambda p: p.stem)
def test_composed_example(path):
    c = gen.design(path)
    assert c.origin.startswith("komponiert")
    assert evaluate_any(c, gen.spec_of(path)).ok


@pytest.mark.parametrize("path", gen.examples(), ids=lambda p: p.stem)
def test_composed_scenario_and_golden_up_to_date(path):
    scen = ROOT / "scenarios" / f"cmp-{path.stem}.yaml"
    stored = yaml.safe_load(scen.read_text(encoding="utf-8"))
    assert stored == yaml.safe_load(yaml.safe_dump(gen.scenario_for(path), allow_unicode=True))
    golden = ROOT / "tests" / "golden" / f"cmp-{path.stem}.trace.json"
    assert gen.check_trace(path, Trace.load(golden)) == []  # the real game shows the behaviour
