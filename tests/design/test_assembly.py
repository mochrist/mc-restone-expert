"""Part labels of compositions (`candidate.Assembly`): filled by compose/decompose, kept by compaction, used
by `compact.parts` to separate parts that touch (M4)."""

from dataclasses import replace
from functools import cache
from pathlib import Path

from redstone.design.candidate import Assembly, is_line
from redstone.design.compact import (_cut, _parts, _without, compact, crop, normalize, parts, relocations,
                                     shifted, shifts)
from redstone.design.compose import chains, place_beside, rotate, wire
from redstone.design.decompose import decomposed
from redstone.design.evaluate import evaluate_any
from redstone.design.search import template_candidates
from redstone.design.spec import from_functions, load
from redstone.model import Direction, Pos

ROOT = Path(__file__).parents[2]


def _gate(fn: str, name: str):
    return next(c for c in template_candidates(from_functions(["a", "b"], {"y": fn})) if c.name == name)


def _consistent(c) -> None:
    """Every block has a label, labels sit on blocks only, line ends are blocks of parts."""
    a = c.assembly
    blocks = {p for p, _ in c.grid.items()}
    assert set(a.labels) == blocks
    for name, (x, y) in a.ends.items():
        assert is_line(name)
        assert not is_line(a.labels[x]) and not is_line(a.labels[y]), (name, a.labels[x], a.labels[y])


AND3 = from_functions(["a", "b", "c"], {"y": "a and b and c"})


@cache
def _chain():
    """and2 -> and2 (a and b, then and c), the first composition that works."""
    g = _gate("a and b", "and2-torch")
    for _, c in chains(g, 0, g, 0):
        if evaluate_any(c, AND3, quick=True).correct:
            return c
    raise AssertionError("no working chain")


def test_connect_labels_both_parts_and_the_line():
    c = _chain()
    _consistent(c)
    labels = set(c.assembly.labels.values())
    assert {"0", "1"} <= labels and set(c.assembly.ends) == {"~0"}
    src, dst = c.assembly.ends["~0"]
    assert c.assembly.labels[src] == "0" and c.assembly.labels[dst] == "1"
    g = _gate("a and b", "and2-torch")
    assert sum(lab == "0" for lab in c.assembly.labels.values()) >= len(g.grid) - 1


def test_parts_separates_touching_parts():
    """The two gates are joined directly (repeater into the input dust, no line cell between them): the
    geometric split sees one group, the labels two."""
    c = _chain()
    groups, found, _, names = _parts(c)
    assert len(groups) == 2 and names == ["~0"]
    assert len(parts(replace(c, assembly=None))[0]) == 1


def test_relocated_part_still_works_and_keeps_labels():
    c = _chain()
    found = list(relocations(c))
    assert found and all(cand.volume < c.volume for _, cand in found)
    assert [m for m, _ in found] == [m for m, _ in relocations(c)]  # deterministic
    ok = [cand for _, cand in found if evaluate_any(normalize(cand), AND3).ok]
    assert ok
    _consistent(normalize(ok[0]))
    assert len(_parts(normalize(ok[0]))[0]) == 2


def test_rotate_and_place_beside_keep_labels():
    c = _chain()
    r = rotate(c, 1)
    _consistent(r)
    both, _ = place_beside(c, _gate("a or b", "or2-direct"), Direction.EAST)
    _consistent(both)
    assert {"0/0", "0/1", "1"} <= set(both.assembly.labels.values()) and set(both.assembly.ends) == {"0/~0"}


def test_wire_adds_a_line():
    """parallel: a lever of the first part taps into the second (`wire`): the tap is a new top-level line."""
    a, b = _gate("a and b", "and2-torch"), _gate("a or b", "or2-direct")
    both, _ = place_beside(a, b, Direction.EAST, 2)
    w = wire(both, both.inputs[0], both.inputs[2])
    assert w is not None
    _consistent(w)
    assert "~0" in w.assembly.ends
    start, end = w.assembly.ends["~0"]
    assert w.assembly.labels[start] == "0" and w.assembly.labels[end] == "1"


def test_labels_survive_compaction_steps():
    c = normalize(_chain())
    _consistent(crop(c))
    for axis in range(3):
        for k in range(c.grid.size[axis]):
            cut = _cut(c, axis, k)
            if cut is not None:
                assert set(cut.assembly.labels) <= {p for p, _ in cut.grid.items()}
    for _, part, v in shifts(c)[:10]:
        s = shifted(c, part, v)
        assert set(s.assembly.labels) == {p for p, _ in s.grid.items()}
    p = next(p for p, lab in c.assembly.labels.items() if lab == "1" and p not in c.inputs + c.outputs)
    w = _without(c, p)
    assert p not in w.assembly.labels and len(w.assembly.labels) == len(c.assembly.labels) - 1


def test_merged_blocks_keep_the_part_label():
    a = Assembly({Pos(0, 0, 0): "~0", Pos(1, 0, 0): "0"}, {})
    m = a.mapped(lambda p: Pos(0, 0, 0))
    assert m.labels == {Pos(0, 0, 0): "0"}


def test_compacted_composition_keeps_labels():
    small, log = compact(_chain(), AND3, max_evaluations=60)
    assert evaluate_any(small, AND3).ok
    assert small.assembly is not None
    assert set(small.assembly.labels) <= {p for p, _ in small.grid.items()}
    assert {"0", "1"} <= set(small.assembly.labels.values())


def test_nested_composition_keeps_stable_labels():
    """xor4 = xor2 -> (xor2 -> xor2): the inner composition keeps its labels below "1", through compaction."""
    spec = load(ROOT / "examples" / "specs" / "composed" / "xor4.yaml")
    found = decomposed(spec)
    nested = [c for c in found if any("/" in lab for lab in c.assembly.labels.values())]
    assert nested
    c = nested[0]
    _consistent(c)
    labels = set(c.assembly.labels.values())
    assert {"0", "1/0", "1/1"} <= labels and set(c.assembly.ends) == {"~0", "1/~0"}
    groups = _parts(c)[0]
    by_label = {}
    for p, lab in c.assembly.labels.items():
        by_label.setdefault(lab.split("/~")[0] if "/~" in lab else lab, set()).add(p)
    # each gate on its own, and the inner composition as a whole (its line included later by `relocations`)
    assert {frozenset(by_label["0"]), frozenset(by_label["1/0"]), frozenset(by_label["1/1"])} <= set(groups)
    assert any(by_label["1/0"] | by_label["1/1"] <= g for g in groups if len(g) > len(by_label["1/0"]) + 1)
    small, _ = compact(c, spec, max_evaluations=30)
    assert evaluate_any(small, spec).ok
    kept = set(small.assembly.labels.values())
    assert {"0", "1/0", "1/1"} <= kept
