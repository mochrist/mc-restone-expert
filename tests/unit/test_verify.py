from pathlib import Path

import pytest

from redstone.model import Pos
from redstone.verify import Trace, diff, load_scenario, timing_diagram
from redstone.verify.scenario import from_dict

SCENARIOS = sorted((Path(__file__).parents[2] / "scenarios").glob("*.yaml"))


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_all_scenarios_load_and_compile(path):
    s = load_scenario(path)
    assert s.name == path.stem
    compiled = s.compile()
    assert compiled["format"] == 1
    assert compiled["ticks"] == s.ticks
    assert all(":" in b["state"] for b in compiled["blocks"])


def _base(**over):
    data = {"name": "t", "build": {"size": [2, 1, 1], "blocks": [[0, 0, 0, "stone"]]}, "ticks": 5,
            "probes": {"p": [0, 0, 0]}}
    data.update(over)
    return data


def test_fill_and_blocks_order():
    s = from_dict(_base(build={"size": [3, 1, 1], "fill": [[0, 0, 0, 2, 0, 0, "stone"]],
                               "blocks": [[1, 0, 0, "glass"]]}))
    assert [str(st) for _, st in s.grid.items()] == ["minecraft:stone", "minecraft:glass", "minecraft:stone"]


@pytest.mark.parametrize("over", [
    {"inputs": [{"tick": 9, "pos": [0, 0, 0], "action": "use"}]},
    {"inputs": [{"tick": 1, "pos": [5, 0, 0], "action": "use"}]},
    {"inputs": [{"tick": 1, "pos": [0, 0, 0], "action": "setblock"}]},
    {"inputs": [{"tick": 1, "pos": [0, 0, 0], "action": "explode"}]},
    {"probes": {"p": [0, 3, 0]}},
    {"name": "Bad Name"},
])
def test_invalid_scenarios(over):
    with pytest.raises(ValueError):
        from_dict(_base(**over))


def _trace(samples, source="oracle"):
    t = Trace("x", source, 10, {k: Pos(0, 0, 0) for k in samples})
    for probe, values in samples.items():
        for tick, value in enumerate(values):
            t.record(probe, tick, value)
    return t


def test_trace_records_change_points_and_round_trips(tmp_path):
    t = _trace({"lamp": ["off"] * 3 + ["on"] * 8})
    assert t.samples["lamp"] == [(0, "off"), (3, "on")]
    assert t.value_at("lamp", 2) == "off" and t.value_at("lamp", 10) == "on"
    t.save(tmp_path / "t.json")
    assert Trace.load(tmp_path / "t.json") == t


def test_diff_reports_first_tick_of_each_mismatch_run():
    expected = _trace({"lamp": ["off"] * 3 + ["on"] * 8})
    actual = _trace({"lamp": ["off"] * 5 + ["on"] * 6}, "sim")
    mismatches = diff(expected, actual)
    assert [(m.tick, m.expected, m.actual) for m in mismatches] == [(3, "on", "off")]
    assert diff(expected, expected) == []


def test_timing_diagram():
    t = _trace({"lamp": ["minecraft:redstone_lamp[lit=false]"] * 3 + ["minecraft:redstone_lamp[lit=true]"] * 8,
                "cmp": ["minecraft:comparator[facing=north,mode=compare,powered=false]|output=0"] * 5
                + ["minecraft:comparator[facing=north,mode=compare,powered=true]|output=3"] * 6})
    rows = timing_diagram(t).splitlines()
    assert rows[2] == "lamp ___########"
    assert rows[3] == " cmp _____######"
