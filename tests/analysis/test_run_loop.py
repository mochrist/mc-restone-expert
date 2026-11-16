"""Circuit.run with the loop in the Rust core (`run_recording`) against the Python loop (`run_python`)."""

from __future__ import annotations

import random

import pytest

from redstone.analysis.experiment import Circuit, Recording
from redstone.sim.core import World

pytestmark = pytest.mark.skipif(not hasattr(World(), "run_recording"), reason="needs the Rust core")


def _same(a: Recording, b: Recording) -> None:
    assert (a.ticks, a.settled_at, a.warnings) == (b.ticks, b.settled_at, b.warnings)
    assert a.series == b.series
    key = lambda c: (c.tick, c.pos, c.old, c.new)  # noqa: E731  (the order within a tick may differ)
    assert sorted(a.changes, key=key) == sorted(b.changes, key=key)


def _schedules(inputs, rng: random.Random):
    yield [], 200, 12
    for p in inputs:
        yield [(1, p, "use")], 200, 12
    # several levers, some at the same tick, toggled back and forth (like the transition checks)
    actions = [(1, p, "use") for p in inputs if rng.random() < 0.5]
    t = 1
    for _ in range(2 * len(inputs) if inputs else 0):
        t += rng.choice((1, 2, 5, 40))
        actions.append((t, rng.choice(inputs), "use"))
    yield actions, t + 200, 12
    yield actions, t // 2, 12  # stops at max_ticks, before the last action
    yield [(1, p, "use") for p in inputs], 60, 10 ** 6  # never quiet long enough


def _candidates():
    from redstone.design.seq_templates import SEQ_TEMPLATES
    from redstone.design.templates import TEMPLATES

    for tpl in TEMPLATES:
        yield pytest.param(lambda tpl=tpl: [tpl.build()], id=f"tpl-{tpl.name}")
    for tpl in SEQ_TEMPLATES:
        yield pytest.param(lambda tpl=tpl: [c for _, c in tpl.variants()], id=f"seq-{tpl.name}")


@pytest.mark.parametrize("build", list(_candidates()))
def test_rust_loop_matches_python_loop(build):
    for i, cand in enumerate(build()):
        circuit = Circuit(cand.grid)
        rng = random.Random(i)
        for actions, max_ticks, quiet in _schedules(cand.inputs, rng):
            fast = circuit.run(actions, max_ticks=max_ticks, quiet=quiet)
            slow = circuit.run_python(actions, max_ticks=max_ticks, quiet=quiet)
            _same(fast, slow)
        # a kicked world and a world handed in that was already run once
        _same(circuit.run([], max_ticks=200, kick=True), circuit.run_python([], max_ticks=200, kick=True))
        w1, w2 = circuit.new_world(), circuit.new_world()
        circuit.run([(1, p, "use") for p in cand.inputs[:1]], max_ticks=100, world=w1)
        circuit.run_python([(1, p, "use") for p in cand.inputs[:1]], max_ticks=100, world=w2)
        _same(circuit.run([(3, p, "use") for p in cand.inputs], max_ticks=200, world=w1),
              circuit.run_python([(3, p, "use") for p in cand.inputs], max_ticks=200, world=w2))
