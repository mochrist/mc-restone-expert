"""Everyday-German explanations (render/plain.py)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from redstone.design import spec as specmod
from redstone.design.behaviour import from_dict as behaviour_from_dict
from redstone.design.evaluate import evaluate_any
from redstone.design.search import redesign
from redstone.render.plain import plain_analysis, plain_design, seconds

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("Komparator", "Comparator", "PLA", "Zerlegung", "Tick", "Quasi", "Burnout", "Observer", "Shannon")


def _design(path: str):
    raw = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    spec = behaviour_from_dict(raw) if "behaviour" in raw else specmod.from_dict(raw)
    results = [r for r in redesign(spec, time_limit=20) if r.ok]
    assert results
    return spec, results[0]


def _prose(text: str) -> str:
    """Everything except the material section (block names are the game's own)."""
    return re.sub(r"## Größe und Material.*?(?=\n## )", "", text, flags=re.S)


def _check(text: str) -> None:
    for sec in ("Was es tut", "So bedienst du es", "Größe und Material", "Gut zu wissen"):
        assert f"## {sec}" in text
    prose = _prose(text)
    for w in FORBIDDEN:
        assert w not in prose, w
    assert not re.search(r"\bgt\b", prose)


def test_seconds():
    assert seconds(10) == "0,5 Sekunden"
    assert seconds(20) == "1 Sekunde"


def test_xor():
    spec, ev = _design("examples/specs/xor.yaml")
    text = plain_design(spec, ev)
    _check(text)
    assert "genau einer" in text
    assert "Hebel" in text


def test_monoflop():
    spec, ev = _design("examples/behaviour/monoflop.yaml")
    text = plain_design(spec, ev)
    _check(text)
    assert "Sekunden" in text


def test_blinker():
    spec, ev = _design("examples/behaviour/clock-8.yaml")
    text = plain_design(spec, ev)
    _check(text)
    assert "blinkt" in text


def test_analysis():
    from redstone.analysis.analyze import analyze

    spec, ev = _design("examples/specs/xor.yaml")
    text = plain_analysis(analyze(ev.candidate.grid))
    _check(text)


def test_job_plain():
    from redstone.gui.server import Job

    spec, ev = _design("examples/specs/xor.yaml")
    text = Job._plain(ev.candidate, spec)
    assert "## Was es tut" in text


# ---------------------------------------------------------------- printable guide
def test_guide_html():
    from redstone.gui.guide_html import guide_html

    _, ev = _design("examples/specs/xor.yaml")
    grid = ev.candidate.grid
    page = guide_html(grid, "xor")
    layers = {p.y for p, s in grid.items() if s.id != "air"}
    assert page.count("<svg") == len(layers)
    assert "<!doctype html>" in page


@pytest.mark.parametrize("facing,out", [("north", (0, 1)), ("south", (0, -1)), ("east", (-1, 0)), ("west", (1, 0))])
def test_guide_arrow_direction(facing, out):
    """A repeater's arrow points to its output, the side opposite `facing`."""
    from redstone.gui.guide_html import T, tile
    from redstone.model import BlockState

    svg = tile(BlockState.parse(f"repeater[delay=1,facing={facing}]"), 0, 0)
    m = re.search(r'class="arrow" points="([\d.]+),([\d.]+) ', svg)
    tx, ty = float(m.group(1)) - T / 2, float(m.group(2)) - T / 2
    assert tx * out[0] > 0 or ty * out[1] > 0
    assert (tx == 0 or out[0] != 0) and (ty == 0 or out[1] != 0)
