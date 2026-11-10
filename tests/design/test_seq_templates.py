"""Sequential templates (timing and memory): every variant meets its behaviour spec, and only that one.

If a scenario test fails after changing a template: uv run python scripts/seq_template_scenarios.py, then record
again with uv run rsx oracle scenarios/seq-<name>.yaml --golden."""

import dataclasses
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

from redstone.analysis.experiment import Circuit
from redstone.design import behaviour as bh
from redstone.design.compact import crop
from redstone.design.seq_templates import SEQ_TEMPLATES, seq_templates_for
from redstone.verify.trace import Trace

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("seq_template_scenarios", ROOT / "scripts" / "seq_template_scenarios.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

VARIANTS = [(t, params, c) for t in SEQ_TEMPLATES for params, c in t.variants()]


@pytest.mark.parametrize("template,params,cand", VARIANTS, ids=[c.name for _, _, c in VARIANTS])
def test_variant_meets_its_spec(template, params, cand):
    spec = bh.CONSTRUCTORS[template.behaviour](**params)
    assert list(template.inputs) == spec.inputs and list(template.input_kinds) == spec.input_kinds
    assert list(template.outputs) == spec.outputs
    ev = bh.evaluate_behaviour(cand, spec)
    assert ev.ok, ev.errors + ev.violations


@pytest.mark.parametrize("template,params,cand", VARIANTS, ids=[c.name for _, _, c in VARIANTS])
def test_grid_is_tight_and_ports_are_real(template, params, cand):
    assert crop(cand) is cand  # no empty border plane
    for p, kind in zip(cand.inputs, template.input_kinds):
        sid = cand.grid.get(p).id
        assert sid == ("stone_button" if kind == "button" else "lever")
        if sid == "lever":
            assert cand.grid.get(p).get("face") == "floor" and cand.grid.get(p).get("powered") == "false"
    assert not cand.grid.get(cand.outputs[0]).is_air


@pytest.mark.parametrize("template,params,cand", [v for v in VARIANTS if v[0].behaviour != "clock"],
                         ids=[c.name for t, _, c in VARIANTS if t.behaviour != "clock"])
def test_stored_state_is_settled(template, params, cand):
    # an observer fires once when every block gets an update (tag "observer"), so only check the plain load
    for kick in (False,) if "observer" in template.tags else (False, True):
        rec = Circuit(cand.grid).run([], max_ticks=20, kick=kick)
        assert rec.settled_at == 0 and not rec.changes, f"kick={kick}"


def test_names_and_parameters():
    names = [t.name for t in SEQ_TEMPLATES]
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", n) for n in names)
    assert {t.behaviour for t in SEQ_TEMPLATES} == set(bh.CONSTRUCTORS)
    for t in SEQ_TEMPLATES:
        params = [p for p, _ in t.variants()]
        assert len({tuple(sorted(p.items())) for p in params}) == len(params), t.name
        assert all(p.get("kind", k) == k for p in params for k in t.input_kinds[:1]), t.name
        assert t.description and t.outputs == ("out",)
    assert seq_templates_for("t-flip-flop") and all(t.behaviour == "clock" for t in seq_templates_for("clock"))


def _other(behaviour: str, params: dict) -> dict:
    """Parameters of a clearly different spec of the same kind."""
    p = dict(params)
    if behaviour in ("monostable", "pulse-extender"):
        p["length"] += 4
    elif behaviour == "delay":
        p["delay"] += 2
    elif behaviour == "clock":
        p["period"] += 4
    else:  # t-flip-flop, rs-latch: much later than the tolerance allows
        p["delay"] += 8
    return p


@pytest.mark.parametrize("template", SEQ_TEMPLATES, ids=lambda t: t.name)
def test_variant_does_not_meet_a_different_spec(template):
    for params, cand in template.variants()[:2]:
        other = bh.CONSTRUCTORS[template.behaviour](**_other(template.behaviour, params))
        assert not bh.evaluate_behaviour(cand, other).ok, (cand.name, params)


def _variant(name: str, **params):
    t = next(t for t in SEQ_TEMPLATES if t.name == name)
    return next(c for p, c in t.variants() if all(p[k] == v for k, v in params.items()))


def test_cross_checks_between_behaviours():
    # a monostable cuts long lever pulses, so it is no pulse extender, and vice versa
    assert not bh.evaluate_behaviour(_variant("monostable-copper-bulb", length=16),
                                     bh.pulse_extender(16, delay=8)).ok
    assert not bh.evaluate_behaviour(_variant("pulse-extender-copper-bulb", length=16),
                                     bh.monostable(16, delay=8)).ok
    # a pulse extender lengthens short pulses, so it is no delay line
    assert not bh.evaluate_behaviour(_variant("pulse-extender-repeater", length=8), bh.delay_line(8)).ok
    # an RS latch with set and reset exchanged
    rs = _variant("rs-latch-torch")
    swapped = dataclasses.replace(rs, inputs=rs.inputs[::-1])
    assert not bh.evaluate_behaviour(swapped, bh.rs_latch(delay=4)).ok
    # a T flip-flop is not a monostable
    assert not bh.evaluate_behaviour(_variant("t-flip-flop-copper-bulb"), bh.monostable(4, delay=2)).ok


@pytest.mark.parametrize("template", SEQ_TEMPLATES, ids=lambda t: t.name)
def test_scenario_and_golden_up_to_date(template):
    path = ROOT / "scenarios" / f"seq-{template.name}.yaml"
    assert path.exists()
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert stored == yaml.safe_load(yaml.safe_dump(gen.scenario_for(template), allow_unicode=True))
    golden = ROOT / "tests" / "golden" / f"seq-{template.name}.trace.json"
    assert golden.exists()
    assert gen.check_trace(template, Trace.load(golden)) == []  # the real game shows the behaviour
