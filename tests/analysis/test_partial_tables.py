"""Partial truth tables for circuits with more levers than a full table allows: dependencies that only show
when two levers are flipped together (an AND of two levers that are both off at rest) or three and more (found
at random lever positions)."""

from redstone.analysis.analyze import MAX_TRUTH_TABLE_LEVERS, analyze
from redstone.design.templates import TEMPLATES
from redstone.model import Grid


def _and_with_spare_levers(spare: int, template: str = "and2-torch") -> Grid:
    """The AND template with `spare` unconnected levers on stone two rows south of it."""
    c = next(t for t in TEMPLATES if t.name == template).build()
    sx, sy, sz = c.grid.size
    g = Grid((max(sx, 2 * spare), sy, sz + 3))
    for p, s in c.grid.items():
        g[p] = s
    for k in range(spare):
        g[2 * k, 0, sz + 2] = "stone"
        g[2 * k, 1, sz + 2] = "lever[face=floor,facing=north,powered=false]"
    return g


def test_and_of_two_levers_that_are_off_at_rest_gets_a_table():
    grid = _and_with_spare_levers(MAX_TRUTH_TABLE_LEVERS)  # 8 levers: no full table
    a = analyze(grid)
    assert not a.truth_table
    lamp = next(o for o in a.outputs if grid.get(o.pos).id == "redstone_lamp")
    tables = [(levers, outs, table) for levers, outs, table in a.partial_tables if lamp in outs]
    assert len(tables) == 1, a.partial_tables
    levers, outs, table = tables[0]
    assert len(levers) == 2
    k = outs.index(lamp)
    assert [o[k] for _, o in table] == [False, False, False, True]
    assert a.gates[lamp.name] == "AND"
    assert any("paarweise" in w for w in a.warnings)


def test_and_of_three_levers_that_are_off_at_rest_gets_a_table():
    grid = _and_with_spare_levers(MAX_TRUTH_TABLE_LEVERS, "and3-torch")  # 9 levers; no single or pair flip shows it
    a = analyze(grid)
    assert not a.truth_table
    lamp = next(o for o in a.outputs if grid.get(o.pos).id == "redstone_lamp")
    ((levers, outs, table),) = [t for t in a.partial_tables if lamp in t[1]]
    assert len(levers) == 3
    k = outs.index(lamp)
    assert [o[k] for _, o in table] == [False] * 7 + [True]
    assert a.gates[lamp.name] == "AND (3 Eingänge)"
    assert any("zufälligen Hebelstellungen" in w for w in a.warnings)
