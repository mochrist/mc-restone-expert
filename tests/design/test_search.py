"""Template matching up to input/output permutation, ranking (M4). Uses hand-made templates so it does not
depend on the template library."""

from dataclasses import dataclass, field

from redstone.design.candidate import Candidate
from redstone.design.evaluate import Constraints
from redstone.design.search import _matches, _template_table, redesign
from redstone.design.spec import from_functions
from redstone.model import Grid, Pos

from .test_spec_evaluate import dust_buffer, torch_inverter


@dataclass(frozen=True)
class FakeTemplate:
    name: str
    inputs: tuple
    outputs: tuple
    function: dict
    description: str
    build: object
    tags: frozenset = field(default_factory=frozenset)


INV = FakeTemplate("not-torch", ("a",), ("y",), {"y": "not a"}, "Fackel", torch_inverter)
BUF = FakeTemplate("buffer-dust", ("a",), ("y",), {"y": "a"}, "Staub", dust_buffer)


def test_matches_permutations():
    spec = from_functions(["p", "q"], {"y": "q and not p"})
    t = FakeTemplate("inhibit", ("a", "b"), ("y",), {"y": "a and not b"}, "", None)
    assert _matches(spec, _template_table(t)) == [((1, 0), (0,))]  # p -> b, q -> a
    t2 = FakeTemplate("ha", ("a", "b"), ("s", "c"), {"s": "a != b", "c": "a and b"}, "", None)
    spec2 = from_functions(["a", "b"], {"carry": "a and b", "sum": "a ^ b"})
    assert ((0, 1), (1, 0)) in _matches(spec2, _template_table(t2))


def test_redesign_picks_matching_template_and_ranks_original():
    spec = from_functions(["a"], {"y": "not a"})
    big = torch_inverter()
    g = Grid((6, 1, 1))  # same inverter with a longer dust-free spacing: wider box
    for p, s in big.grid.items():
        g[p] = s
    original = Candidate("Original", g, big.inputs, big.outputs, origin="original")
    results = redesign(spec, Constraints(), extra=[original], templates=[INV, BUF], synthesize=False)
    assert [r.candidate.name for r in results] == ["not-torch", "Original"]
    assert results[0].ok and results[1].ok
    assert results[0].candidate.origin == "template:not-torch"


def test_constraints_exclude_template():
    spec = from_functions(["a"], {"y": "a"})
    results = redesign(spec, Constraints(forbidden_blocks={"redstone_wire"}), templates=[INV, BUF],
                       synthesize=False)
    assert len(results) == 1 and not results[0].ok
