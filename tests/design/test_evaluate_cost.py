"""Simulator work of a full evaluation (task 03): each directed transition is checked once, not twice."""

from __future__ import annotations

import pytest

from redstone.design import evaluate as evmod
from redstone.design.evaluate import evaluate
from redstone.design.spec import from_functions
from redstone.design.synth import pla


@pytest.fixture
def xor4():
    spec = from_functions(list("abcd"), {"y": "a != b != c != d"})
    return spec, pla(spec)


def test_full_evaluation_of_four_inputs_runs_and_ticks(xor4, monkeypatch):
    spec, cand = xor4
    ev = evaluate(cand, spec)
    assert ev.ok
    # 1 idle run, 15 combinations from a fresh world, 15 transition runs (all levers on: nothing to switch)
    assert ev.runs == 31
    fresh = evaluate(cand, spec, full=False)
    assert fresh.runs == 16
    monkeypatch.setattr(evmod, "TRANSITIONS", "all")
    both = evaluate(cand, spec)
    assert both.ok and both.runs == 32 and both.max_delay == ev.max_delay
    # n·2ⁿ lever changes instead of 2n·2ⁿ: the transition runs take about half the ticks
    half, all_ = ev.ticks - fresh.ticks, both.ticks - fresh.ticks
    assert 0.45 * all_ < half < 0.55 * all_


def test_half_and_all_transitions_agree_on_the_templates(monkeypatch):
    """Every logic template, checked against its own function and against a 2-input AND: the same verdict and
    the same delay with each transition checked once as with each checked twice."""
    from redstone.design.search import _template_table
    from redstone.design.templates import TEMPLATES

    spec_and = from_functions(["a", "b"], {"y": "a and b"})
    for t in TEMPLATES:
        c = t.build()
        for spec in (_template_table(t), spec_and):
            if len(spec.inputs) != len(c.inputs) or len(spec.outputs) != len(c.outputs):
                continue
            monkeypatch.setattr(evmod, "TRANSITIONS", "half")
            ev = evaluate(c, spec)
            monkeypatch.setattr(evmod, "TRANSITIONS", "all")
            other = evaluate(c, spec)
            assert (ev.correct, ev.max_delay) == (other.correct, other.max_delay), t.name
