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


def test_gated_spec_leaves_out_pulses_a_held_gate_swallows():
    # AND: the other lever is held on, so 1-gt pulses are left out; OR: nothing held, all pulses stay
    and_names = [t.name for t in bh.gated(["a", "b"], "a and b", bh.pulse_extender(12)).trials]
    or_names = [t.name for t in bh.gated(["a", "b"], "a or b", bh.pulse_extender(12)).trials]
    assert "a: Hebel 1 gt an (b=1)" not in and_names and "a: Hebel 2 gt an (b=1)" in and_names
    assert "a: Hebel 1 gt an" in or_names


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
    assert c.origin.removeprefix(gen.COMPACTED).startswith("komponiert")
    assert evaluate_any(c, gen.spec_of(path)).ok


@pytest.mark.parametrize("path", gen.examples(), ids=lambda p: p.stem)
def test_composed_scenario_and_golden_up_to_date(path):
    scen = ROOT / "scenarios" / f"cmp-{path.stem}.yaml"
    stored = yaml.safe_load(scen.read_text(encoding="utf-8"))
    assert stored == yaml.safe_load(yaml.safe_dump(gen.scenario_for(path), allow_unicode=True))
    golden = ROOT / "tests" / "golden" / f"cmp-{path.stem}.trace.json"
    assert gen.check_trace(path, Trace.load(golden)) == []  # the real game shows the behaviour


def test_gate_is_guessed_from_recorded_behaviour():
    from redstone.analysis.analyze import analyze
    from redstone.cli import _spec_of_existing
    from redstone.design.search import gate_guesses
    from redstone.verify import load_scenario

    grid = load_scenario(ROOT / "scenarios" / "cmp-t-flip-flop-and.yaml").grid
    spec, original = _spec_of_existing(analyze(grid), "cmp")
    assert len(spec.outputs) == 1  # only the lamp; bulb and torch are internal
    guesses = gate_guesses(spec)
    assert [g.gate for g, _ in guesses] == ["in1 and in2"]
    assert guesses[0][1][0].candidate.name.startswith("t-flip-flop")


# ---------------------------------------------------------------------- decomposition of truth tables
def test_splits_of_and5_are_deduplicated():
    from redstone.design.decompose import splits

    spec = from_functions(list("abcde"), {"y": "a and b and c and d and e"})
    sp = splits(spec)
    assert [len(s.bound) for s in sp] == [2, 3, 4]  # one split per size: the function is symmetric
    assert all(s.h.table[(True,) * len(s.h.inputs)] == (True,) for s in sp)


def test_no_split_for_majority():
    from redstone.design.decompose import splits

    assert splits(from_functions(list("abc"), {"y": "(a and b) or (a and c) or (b and c)"})) == []


SLOW_TABLES = {"adder3", "cmp3"}  # design search of about a minute


def _slow(paths):
    return [pytest.param(p, marks=pytest.mark.slow) if p.stem in SLOW_TABLES else p for p in paths]


@pytest.mark.parametrize("path", gen.table_examples(), ids=lambda p: p.stem)
def test_decomposed_golden_shows_the_truth_table(path):
    stored = yaml.safe_load((ROOT / "scenarios" / f"cmp-{path.stem}.yaml").read_text(encoding="utf-8"))
    ticks = [i["tick"] for i in stored["inputs"]]
    golden = ROOT / "tests" / "golden" / f"cmp-{path.stem}.trace.json"
    # the real game shows the truth table
    assert gen.check_table_trace(path, Trace.load(golden), step=ticks[1] - ticks[0]) == []


@pytest.mark.parametrize("path", _slow(gen.table_examples()), ids=lambda p: p.stem)
def test_decomposed_scenario_up_to_date(path):
    scen = ROOT / "scenarios" / f"cmp-{path.stem}.yaml"
    stored = yaml.safe_load(scen.read_text(encoding="utf-8"))
    assert stored == yaml.safe_load(yaml.safe_dump(gen.table_scenario_for(path), allow_unicode=True))


def test_spec_of_existing_outputs_option():
    """--outputs overrides the lamps-only rule (all outputs) or picks outputs by name; unknown names fail."""
    import pytest

    from redstone.analysis.analyze import analyze
    from redstone.cli import _spec_of_existing
    from redstone.verify import load_scenario

    a = analyze(load_scenario(ROOT / "scenarios" / "cmp-t-flip-flop-and.yaml").grid)
    spec, original = _spec_of_existing(a, "cmp", "all")
    assert spec.outputs == [o.name for o in a.outputs] and len(original.outputs) == len(a.outputs)
    lamp = next(o for o in a.outputs if a.grid.get(o.pos).id == "redstone_lamp")
    spec, original = _spec_of_existing(a, "cmp", lamp.name)
    assert spec.outputs == [lamp.name] and original.outputs == [lamp.pos]
    with pytest.raises(ValueError, match="unbekannte Ausgänge"):
        _spec_of_existing(a, "cmp", "out99")


def test_spec_of_existing_outputs_subset_of_truth_table():
    from redstone.analysis.analyze import analyze
    from redstone.cli import _spec_of_existing
    from redstone.design.evaluate import evaluate
    from redstone.verify import load_scenario

    a = analyze(load_scenario(ROOT / "scenarios" / "tpl-fulladder-comparator.yaml").grid)
    full, _ = _spec_of_existing(a, "ha")
    name = full.outputs[1]
    spec, original = _spec_of_existing(a, "ha", name)
    assert spec.outputs == [name]
    assert all(v == (full.table[c][1],) for c, v in spec.table.items())
    assert evaluate(original, spec).ok


def test_shared_split_of_an_adder_is_the_carry():
    """2-bit adder: g = carry of bit 0 is computed with s0 from (a0, b0); s1 and c come from (g, a1, b1)."""
    from redstone.design.decompose import shared_splits
    from redstone.design.spec import load

    spec = load(ROOT / "examples/specs/composed/adder2.yaml")
    sp = shared_splits(spec)[0]
    names = spec.inputs
    assert [names[i] for i in sp.bound] == ["a0", "b0"] and [spec.outputs[j] for j in sp.local] == ["s0"]
    assert [spec.outputs[j] for j in sp.rest] == ["s1", "c"]
    assert all(sp.g.table[(a, b)] == (a and b, a != b) for a in (False, True) for b in (False, True))


def test_two_shared_signals_of_a_comparator():
    """2-bit comparator: the high bits give "greater" and "less" (three columns, so two signals and a partial
    H); splits that only pass two levers on are not offered."""
    from redstone.design.decompose import shared, shared_splits

    spec = from_functions(["a1", "b1", "a0", "b0"],
                          {"gt": "(a1 + a1 + a0) > (b1 + b1 + b0)", "lt": "(a1 + a1 + a0) < (b1 + b1 + b0)"})
    assert shared_splits(spec) == []
    sp = shared_splits(spec, width=2)
    assert all(s.width == 2 and len(s.bound) < len(spec.inputs) for s in sp)
    names = spec.inputs
    assert [names[i] for i in sp[0].bound] == ["a1", "b1"] and sp[0].h.partial
    assert {sp[0].g.table[(a, b)] for a in (False, True) for b in (False, True)} == {
        (False, False), (True, False), (False, True)}
    assert all(sp[0].g.table[(a, b)] in ((a and not b, b and not a), (b and not a, a and not b))
               for a in (False, True) for b in (False, True))
    found = shared(spec)
    assert found and found[0].origin.startswith("zerlegt: g0, g1 aus (a1, b1)")
    assert evaluate_any(found[0], spec).ok


@pytest.mark.slow
def test_comparator_cascade_of_templates():
    """3-bit comparator: the high bits as a 2-bit cascade (cmp1 → stage), then one more stage; the second
    signal leaves the enclosed lamp of the inner stage on top of it (`wire` mode "top", a bridge)."""
    from redstone.design.decompose import shared
    from redstone.design.spec import load

    spec = load(ROOT / "examples/specs/composed/cmp3.yaml")
    names = [c.name for c in shared(spec)]
    assert "cmp1-comparator → cmp-stage-comparator → cmp-stage-comparator" in names


def test_wire_from_a_lamp_lit_from_above():
    """A PLA lamp lit by the torch above it: a repeater on its cell reads nothing, stone is not powered by
    the torch; dust on the lamp's cell (the line starting beside it) works."""
    from redstone.design.compose import place_beside, wire
    from redstone.design.synth import pla
    from redstone.design.templates import TEMPLATES
    from redstone.model import Direction, Pos

    two = from_functions(["a", "b"], {"x": "a and not b", "y": "b and not a"})
    g = pla(two)
    lamp = g.outputs[1]
    assert g.grid.get(lamp + Pos(0, 1, 0)).id == "redstone_wall_torch"
    buffer = next(t for t in TEMPLATES if t.name == "buffer-dust").build()
    both, _ = place_beside(g, buffer, Direction.EAST)
    ok = {}
    for mode in ("stone", "repeater", "dust"):
        c = wire(both, both.outputs[1], both.inputs[2], mode, "dust")
        ok[mode] = c is not None and evaluate_any(c, two, quick=True).correct
    assert ok == {"stone": False, "repeater": False, "dust": True}


def test_enclosed_output_connects_with_tight_lines():
    """The full adder's lamps sit between its comparators: only the tight fallback of `chains` reaches them."""
    import itertools

    from redstone.design.compose import chains, connect, layouts
    from redstone.design.templates import TEMPLATES

    fa = next(t for t in TEMPLATES if t.name == "fulladder-comparator").build()
    assert all(connect(fa, 1, fa, 0, lay) is None for lay in layouts())  # output 1: the carry
    assert len(list(itertools.islice(chains(fa, 1, fa, 0), 3))) == 3


def test_redesign_of_recorded_behaviour_with_four_levers():
    """Beyond GUESS_INPUTS levers only the gate the analysis found is tried; the pulses under held levers
    keep compaction from dropping half of the logic (without them a 24-block design passed)."""
    from redstone.analysis.analyze import analyze
    from redstone.cli import _spec_of_existing
    from redstone.design.search import GUESS_INPUTS, gate_guesses, redesign
    from redstone.verify import load_scenario

    grid = load_scenario(ROOT / "tests/fixtures/analysis/gated/t-flip-flop-and-or4.yaml").grid
    spec, original = _spec_of_existing(analyze(grid), "and-or4")
    assert len(spec.inputs) == 4 > GUESS_INPUTS
    assert spec.gate_hints == ["(in3 and in4) or (in1 and in2)"]
    assert any(t.name == "in1 5 gt an, während in2 an" for t in spec.trials)
    assert [g.gate for g, _ in gate_guesses(spec)] == spec.gate_hints
    best = next(e for e in redesign(spec, compact_budget=100) if e.ok)
    assert best.candidate.origin.removeprefix("kompaktiert aus ").startswith("komponiert")
    assert len(best.candidate.grid) >= 40


def test_timing_behind_logic_is_not_redesigned_as_a_truth_table():
    from redstone.analysis.analyze import analyze
    from redstone.cli import _spec_of_existing
    from redstone.verify import load_scenario

    grid = load_scenario(ROOT / "scenarios/cmp-pulse-extender-and.yaml").grid
    spec, _ = _spec_of_existing(analyze(grid), "cmp")
    assert isinstance(spec, bh.BehaviourSpec)  # the AND table alone meets steady states and transitions
    assert spec.gate_hints == ["in1 and in2"]
