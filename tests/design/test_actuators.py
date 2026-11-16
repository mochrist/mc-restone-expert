"""design.actuators.with_output: door, piston, note block ... instead of the lamp, checked against the lamp version."""

from pathlib import Path

import pytest
import yaml

from redstone.design import behaviour as bh
from redstone.design.actuators import ACTUATORS, _steps, _traces, with_output
from redstone.design.search import redesign
from redstone.design.templates import TEMPLATES

EXAMPLES = Path(__file__).parents[2] / "examples" / "behaviour"
TEMPLATE = {t.name: t for t in TEMPLATES}
ALL = tuple(ACTUATORS)

# Which actuators work with which design (as of session 19). The torch AND does not work with door, piston and
# dispenser/dropper: the block does not follow the lamp. That is the expected value, not a bug.
WORKS = {
    "and2-torch": {"note_block", "iron_trapdoor"},
    "xor2-comparator": set(ALL),
    "t-flip-flop": set(ALL),
    "monostable-8": set(ALL),
}


def _best(name: str):
    spec = bh.from_dict(yaml.safe_load((EXAMPLES / f"{name}.yaml").read_text(encoding="utf-8")), source=name)
    return next(e.candidate for e in redesign(spec) if e.ok)


@pytest.fixture(scope="module")
def designs():
    return {
        "and2-torch": TEMPLATE["and2-torch"].build(),
        "xor2-comparator": TEMPLATE["xor2-comparator"].build(),
        "t-flip-flop": _best("t-flip-flop"),
        "monostable-8": _best("monoflop"),
    }


@pytest.mark.parametrize("name", list(WORKS))
@pytest.mark.parametrize("kind", ALL)
def test_actuator_matrix(designs, name, kind):
    cand = designs[name]
    new, why = with_output(cand, kind)
    if kind not in WORKS[name]:
        assert new is None
        assert why
        return
    assert new is not None, why
    block_id = ACTUATORS[kind][1].split("[")[0]
    assert len(new.outputs) == len(cand.outputs)
    for p in new.outputs:
        assert new.grid.get(p).id == block_id
    steps = _steps(len(cand.inputs))
    assert _traces(new, steps) == _traces(cand, steps)  # switches like the lamp version


def test_unknown_actuator(designs):
    new, why = with_output(designs["xor2-comparator"], "gibtsnicht")
    assert new is None
    assert "gibtsnicht" in why


@pytest.mark.parametrize("kind", ["iron_door", "piston", "note_block"])
def test_two_outputs_both_get_the_actuator(kind):
    cand = TEMPLATE["halfadder-comparator"].build()
    assert len(cand.outputs) == 2
    new, why = with_output(cand, kind)
    assert new is not None, why
    assert len(new.outputs) == 2
    block_id = ACTUATORS[kind][1].split("[")[0]
    assert all(new.grid.get(p).id == block_id for p in new.outputs)
    steps = _steps(len(cand.inputs))
    assert _traces(new, steps) == _traces(cand, steps)
