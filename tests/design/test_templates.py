"""Every gate template: truth table, every single-lever transition, idle without input, tight grid."""

import itertools
import re

import pytest

from redstone.analysis.experiment import Circuit
from redstone.design.templates import TEMPLATES, Template, templates_for

MAX_TICKS = 400
QUIET = 12


def _outputs(rec, cand, template):
    return {name: rec.on_at(pos, rec.ticks) for name, pos in zip(template.outputs, cand.outputs)}


def test_names_unique_and_kebab_case():
    names = [t.name for t in TEMPLATES]
    assert len(names) == len(set(names))
    for name in names:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), name


def test_templates_for():
    assert {t.name for t in templates_for(2, 1)} >= {"and2-torch", "xor2-comparator", "or2-direct"}
    assert all(len(t.inputs) == 3 and len(t.outputs) == 1 for t in templates_for(3, 1))
    assert [t.name for t in templates_for(2, 2)] == [t.name for t in TEMPLATES if len(t.inputs) == len(t.outputs) == 2]
    assert [t.name for t in templates_for(3, 2)] == ["fulladder-comparator"]
    assert templates_for(9, 9) == []


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.name)
def test_structure(template: Template):
    cand = template.build()
    assert cand.name == template.name
    assert cand.origin == f"template:{template.name}"
    assert cand.description == template.description
    assert set(template.function) == set(template.outputs)
    assert len(cand.inputs) == len(template.inputs) and len(cand.outputs) == len(template.outputs)
    for pos in cand.inputs:
        state = cand.grid[pos]
        assert state.id == "lever" and state.get("face") == "floor" and state.get("powered") == "false"
    for pos in cand.outputs:
        assert cand.grid[pos].id == "redstone_lamp"
    # tight bounding box: blocks touch every face of the grid
    positions = [p for p, _ in cand.grid.items()]
    for axis in range(3):
        assert min(p[axis] for p in positions) == 0
        assert max(p[axis] for p in positions) == cand.grid.size[axis] - 1
    # a fresh build is independent of earlier ones
    cand.grid.set(cand.inputs[0], "stone")
    assert template.build().grid[cand.inputs[0]].id == "lever"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.name)
def test_stored_state_is_settled(template: Template):
    """Loaded as stored, nothing changes, also not after every block got a neighbour update."""
    circuit = Circuit(template.build().grid)
    for kick in (False, True):
        rec = circuit.run([], max_ticks=60, kick=kick, quiet=QUIET)
        assert rec.settled_at == 0, f"kick={kick}"
        assert rec.changes == [], f"kick={kick}: {rec.changes[:3]}"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.name)
def test_truth_table_and_transitions(template: Template):
    cand = template.build()
    circuit = Circuit(cand.grid)
    n = len(template.inputs)
    for combo in itertools.product((False, True), repeat=n):
        world = circuit.new_world()
        actions = [(1, cand.inputs[i], "use") for i in range(n) if combo[i]]
        rec = circuit.run(actions, max_ticks=MAX_TICKS, quiet=QUIET, world=world)
        assert rec.settled_at is not None, f"{combo} does not settle"
        expected = template.evaluate(dict(zip(template.inputs, combo)))
        assert _outputs(rec, cand, template) == expected, f"inputs {combo}"
        # from this settled state flip each lever and flip it back
        for i in range(n):
            for state in ([*combo[:i], not combo[i], *combo[i + 1:]], list(combo)):
                rec = circuit.run([(0, cand.inputs[i], "use")], max_ticks=MAX_TICKS, quiet=QUIET, world=world)
                assert rec.settled_at is not None, f"{combo}, lever {i} -> {state} does not settle"
                expected = template.evaluate(dict(zip(template.inputs, state)))
                assert _outputs(rec, cand, template) == expected, f"{combo}, lever {i} -> {state}"
