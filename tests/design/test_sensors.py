"""design.sensors.with_input: a pressure plate instead of lever/button, checked against the original."""

from pathlib import Path

import pytest
import yaml

from redstone.design import behaviour as bh
from redstone.design.candidate import Candidate
from redstone.design.evaluate import evaluate_any
from redstone.design.robust import check
from redstone.design.search import redesign
from redstone.design.sensors import SENSORS, button_spec, with_input
from redstone.design.templates import TEMPLATES
from redstone.model import Grid, Pos

EXAMPLES = Path(__file__).parents[2] / "examples" / "behaviour"


def _spec(name: str):
    return bh.from_dict(yaml.safe_load((EXAMPLES / f"{name}.yaml").read_text(encoding="utf-8")), source=name)


def _best(spec):
    return next(e.candidate for e in redesign(spec) if e.ok)


@pytest.mark.parametrize("kind", list(SENSORS))
@pytest.mark.parametrize("name", ["monoflop", "t-flip-flop"])
def test_pulse_designs_take_a_plate(name, kind):
    spec = _spec(name)
    cand = _best(spec)
    new, why = with_input(cand, kind, spec)
    assert new is not None, why
    assert all(new.grid.get(p).id.endswith("_pressure_plate") for p in new.inputs)
    # the press version of the spec holds, also at other places and turned (DUST-018)
    press = button_spec(spec)
    assert press.input_kinds == ["button"]
    assert not evaluate_any(new, press).errors
    assert check(new, press, sample=8).ok


def test_button_design_takes_a_plate():
    spec = bh.monostable(8, kind="button")
    cand = _best(spec)
    assert cand.grid.get(cand.inputs[0]).id.endswith("_button")
    new, why = with_input(cand, "stone_pressure_plate")  # buttons need no spec
    assert new is not None, why
    assert not evaluate_any(new, spec).errors


def test_lever_logic_is_refused():
    and2 = next(t for t in TEMPLATES if t.name == "and2-torch").build()
    new, why = with_input(and2, "stone_pressure_plate")
    assert new is None
    assert "Hebel" in why
    spec = _spec("pulse-extender-and")  # gate over two levers
    new, why = with_input(_best(spec), "stone_pressure_plate", spec)
    assert new is None and why


def test_pulse_extender_spec_in_press_form():
    spec = bh.pulse_extender(12)
    cand = _best(spec)
    new, why = with_input(cand, "oak_pressure_plate", spec)
    assert new is not None, why
    assert not evaluate_any(new, button_spec(spec)).errors


def test_wall_button_plate_goes_on_top_of_the_block():
    g = Grid((3, 4, 3))
    for x in range(3):
        for z in range(3):
            g.set(Pos(x, 0, z), "stone")
    g.set(Pos(1, 1, 1), "stone")
    g.set(Pos(1, 1, 2), "stone_button[face=wall,facing=south,powered=false]")
    g.set(Pos(0, 1, 1), "redstone_lamp[lit=false]")
    cand = Candidate("wall", g, [Pos(1, 1, 2)], [Pos(0, 1, 1)])
    new, why = with_input(cand, "stone_pressure_plate")
    assert new is not None, why
    assert new.grid.get(new.inputs[0]).id == "stone_pressure_plate"
    assert new.grid.get(new.inputs[0] + Pos(0, -1, 0)).id == "stone"
    # a hanging button with a block above has no room for a plate
    g.set(Pos(1, 2, 1), "stone")
    new, why = with_input(cand, "stone_pressure_plate")
    assert new is None and why
