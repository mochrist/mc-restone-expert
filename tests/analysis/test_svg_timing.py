"""SVG timing diagrams: well-formed, named signals, waveform equals the recording, links in the Markdown."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from redstone import cli
from redstone.analysis.analyze import analyze
from redstone.analysis.experiment import is_on
from redstone.analysis.explain import explain
from redstone.render.svg_timing import TICK_W, render_timing
from redstone.verify import load_scenario

LATCH = Path(__file__).parents[1] / "fixtures" / "analysis" / "rs-latch.yaml"
POLY = "{http://www.w3.org/2000/svg}polyline"


def _levels(svg_text: str, name: str) -> list[int]:
    """Per-tick high/low of a signal read back from its polyline."""
    root = ET.fromstring(svg_text)
    line = next(e for e in root.iter(POLY) if e.get("data-signal") == name)
    pts = [tuple(map(int, p.split(","))) for p in line.get("points").split()]
    high = min(y for _, y in pts)
    x0 = pts[0][0]
    n = (pts[-1][0] - x0) // TICK_W
    out = []
    for t in range(n):
        x = x0 + t * TICK_W
        y = [py for px, py in pts if px <= x][-1]
        out.append(int(y == high))
    return out


def test_render_basic():
    svg = render_timing([("a", [False, True, True, False]), ("b", [True] * 4)], marks=[1], title="t")
    assert ET.fromstring(svg).tag.endswith("svg")
    assert render_timing([("a", [False, True])]) == render_timing([("a", [False, True])])
    assert 'fill="#ffffff"' in svg
    assert _levels(svg, "a") == [0, 1, 1, 0]


def test_explain_svg_matches_recording():
    a = analyze(load_scenario(LATCH).grid)
    files: dict[str, str] = {}
    text = explain(a, "rs-latch", ("svgs", files))
    assert files
    for r in a.responses:
        fname = f"{r.input.name}.svg"
        assert f"![{r.input.name}](svgs/{fname})" in text
        svg = files[fname]
        ET.fromstring(svg)
        assert r.input.name in svg
        for o in a.outputs:
            assert o.name in svg
        rec = r.recording
        for name, pos in [(r.input.name, r.input.pos)] + [(o.name, o.pos) for o in a.outputs]:
            if pos not in rec.series:
                continue
            expected = [int(is_on(rec.value_at(pos, t))) for t in range(rec.ticks + 1)]
            if len(set(expected)) > 1:  # a constant row cannot be told high from low
                assert _levels(svg, name) == expected
    assert "```" in text  # ASCII diagrams stay


def test_explain_without_svg_has_no_images():
    assert "![" not in explain(analyze(load_scenario(LATCH).grid), "rs-latch")


def test_cli_svg_option(tmp_path):
    out = tmp_path / "report.md"
    assert cli.main(["explain", str(LATCH), "-o", str(out), "--svg", str(tmp_path / "img")]) == 0
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", out.read_text(encoding="utf-8"))
    assert links
    for link in links:
        ET.parse(out.parent / link)


def test_sim_svg_option(tmp_path):
    f = tmp_path / "t.svg"
    scen = Path(__file__).parents[2] / "scenarios" / "repeater-delays.yaml"
    assert cli.main(["sim", str(scen), "--svg", str(f)]) == 0
    root = ET.parse(f).getroot()
    assert len(list(root.iter(POLY))) >= 2
