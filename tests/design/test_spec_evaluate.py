"""Spec parsing and candidate evaluation (M4)."""

import pytest

from redstone.design.candidate import Candidate
from redstone.design.evaluate import Constraints, evaluate
from redstone.design.spec import evaluate_expression, from_dict, from_functions
from redstone.model import Grid, Pos


def torch_inverter() -> Candidate:
    g = Grid((4, 1, 1))
    g[0, 0, 0] = "lever[face=wall,facing=west,powered=false]"
    g[1, 0, 0] = "stone"
    g[2, 0, 0] = "redstone_wall_torch[facing=east,lit=true]"
    g[3, 0, 0] = "redstone_lamp[lit=true]"
    return Candidate("not-torch", g, [Pos(0, 0, 0)], [Pos(3, 0, 0)])


def dust_buffer() -> Candidate:
    g = Grid((3, 2, 1))
    g[0, 0, 0] = "stone"
    g[1, 0, 0] = "stone"
    g[0, 1, 0] = "lever[face=floor,facing=east,powered=false]"
    g[1, 1, 0] = "redstone_wire[east=side,north=none,power=0,south=none,west=side]"
    g[2, 1, 0] = "redstone_lamp[lit=false]"
    return Candidate("buffer-dust", g, [Pos(0, 1, 0)], [Pos(2, 1, 0)])


def test_expression_parsing():
    assert evaluate_expression("a and not b", {"a": True, "b": False})
    assert evaluate_expression("a ^ b", {"a": True, "b": True}) is False
    with pytest.raises(ValueError):
        evaluate_expression("__import__('os')", {"a": True})
    with pytest.raises(ValueError):
        evaluate_expression("c", {"a": True})


def test_spec_from_table_and_function_agree():
    s1 = from_dict({"inputs": ["a", "b"], "function": {"y": "a != b"}})
    s2 = from_dict({"inputs": ["a", "b"], "outputs": ["y"], "table": {"00": "0", "01": "1", "10": "1", "11": "0"}})
    assert s1.table == s2.table
    assert s1.describe() == "y = (¬a ∧ b) ∨ (a ∧ ¬b)"
    with pytest.raises(ValueError):
        from_dict({"inputs": ["a"], "outputs": ["y"], "table": {"0": "1"}})


def test_inverter_is_correct():
    ev = evaluate(torch_inverter(), from_functions(["a"], {"y": "not a"}))
    assert ev.ok, ev.errors
    assert ev.max_delay == 6  # torch 2 gt; the lamp turns off 4 gt later


def test_wrong_function_is_reported():
    ev = evaluate(torch_inverter(), from_functions(["a"], {"y": "a"}))
    assert not ev.correct
    assert "falscher Ruhezustand" in ev.errors[0]


def test_buffer_and_constraints():
    spec = from_functions(["a"], {"y": "a"}, max_delay=2)
    ev = evaluate(dust_buffer(), spec)
    assert ev.correct, ev.errors
    assert ev.max_delay == 4  # dust is instant, lamp off delay 4 gt
    assert "Verzögerung 4 gt > erlaubt 2 gt" in ev.violations
    ev = evaluate(dust_buffer(), spec, Constraints(max_size=(1, 2, 3), forbidden_blocks={"redstone_wire"}, max_delay=10))
    assert ev.violations == ["verbotene Blöcke: redstone_wire"]  # 3x2x1 fits 1x2x3 rotated
