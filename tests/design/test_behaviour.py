"""Behavioural specs (timing and memory) evaluated by simulation (M4)."""

from redstone.analysis.experiment import Circuit
from redstone.design import behaviour as bh
from redstone.design.candidate import Candidate
from redstone.model import Grid, Pos


def repeater_line(delays: list[int]) -> Candidate:
    """Lever, a chain of repeaters with the given delay settings, lamp."""
    n = len(delays)
    g = Grid((n + 2, 2, 1))
    for x in range(n + 2):
        g[x, 0, 0] = "stone"
    g[0, 1, 0] = "lever[face=floor,facing=east,powered=false]"
    for k, d in enumerate(delays):
        g[1 + k, 1, 0] = f"repeater[delay={d},facing=west,locked=false,powered=false]"
    g[n + 1, 1, 0] = "redstone_lamp[lit=false]"
    return Candidate("repeater-line", g, [Pos(0, 1, 0)], [Pos(n + 1, 1, 0)])


def observer_clock() -> Candidate:
    """Output is the observer itself: a lamp behind it would stay lit (off delay 4 gt > off time)."""
    g = Grid((2, 1, 1))
    g[0, 0, 0] = "observer[facing=east,powered=false]"
    g[1, 0, 0] = "observer[facing=west,powered=false]"
    return Candidate("observer-clock", g, [], [Pos(0, 0, 0)])


def test_delay_line_matches_exactly():
    c = repeater_line([1, 1, 1])  # 3 x 2 gt; pulses >= 2 gt pass unchanged
    assert bh.evaluate_behaviour(c, bh.delay_line(6)).ok
    ev = bh.evaluate_behaviour(c, bh.delay_line(4))
    assert not ev.ok and "beginnt bei 8 statt 6" in ev.errors[0]
    # a 4-gt repeater stretches a 2-gt pulse to 4 gt (REP-011), so it is no exact delay line
    ev = bh.evaluate_behaviour(repeater_line([2, 1]), bh.delay_line(6))
    assert not ev.ok and "endet bei 12 statt 10" in ev.errors[0]


def test_delay_line_is_not_a_monostable():
    ev = bh.evaluate_behaviour(repeater_line([1]), bh.monostable(4, delay=2))
    assert not ev.ok and "Pulslänge" in ev.errors[0]


def test_clock_period_and_on_time():
    assert bh.evaluate_behaviour(observer_clock(), bh.clock(6, 2)).ok  # see golden trace observer-clock
    assert not bh.evaluate_behaviour(observer_clock(), bh.clock(4, 2)).ok


def test_spec_from_recordings_reproduces_itself():
    c = repeater_line([3])
    spec = bh.from_recordings(["in"], ["lever"], ["out"], Circuit(c.grid), c.outputs, c.inputs)
    assert bh.evaluate_behaviour(c, spec).ok
    assert not bh.evaluate_behaviour(repeater_line([1]), spec).ok or spec.delay_tolerance >= 4


def test_yaml_form():
    spec = bh.from_dict({"behaviour": "monostable", "length": 10, "delay_tolerance": 2})
    assert spec.delay_tolerance == 2 and spec.trials[0].expected == [[(2, 12)]]


def test_recorded_spec_captures_latch_memory():
    """Pair trials (set, then reset) make a 'set only' circuit fail the recorded latch spec."""
    from pathlib import Path

    from redstone.verify import load_scenario

    grid = load_scenario(Path(__file__).parents[1] / "fixtures" / "analysis" / "rs-latch.yaml").grid
    levers = [p for p, s in sorted(grid.items()) if s.id == "lever"]
    lamp = next(p for p, s in grid.items() if s.id == "redstone_lamp")
    spec = bh.from_recordings(["s", "r"], ["lever", "lever"], ["out"], Circuit(grid), [lamp], levers)
    assert any(t.name == "s, dann r" for t in spec.trials)
    assert bh.evaluate_behaviour(Candidate("orig", grid, levers, [lamp]), spec).ok
    swapped = Candidate("swapped", grid, levers[::-1], [lamp])  # set and reset exchanged
    assert not bh.evaluate_behaviour(swapped, spec).ok
