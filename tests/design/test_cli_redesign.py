"""rsx redesign end to end with the template library."""

from pathlib import Path

from redstone import io
from redstone.cli import main
from redstone.design.evaluate import evaluate
from redstone.design.search import original_candidate
from redstone.design.spec import load

EXAMPLES = Path(__file__).parents[2] / "examples" / "specs"


def test_redesign_xor_exports_working_circuit(tmp_path, capsys):
    out = tmp_path / "xor.litematic"
    assert main(["redesign", str(EXAMPLES / "xor.yaml"), "-o", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Bester Kandidat: **xor2-" in text
    assert out.exists()
    grid = io.load(out)
    assert len(grid) > 0


def test_redesign_respects_box(capsys):
    assert main(["redesign", str(EXAMPLES / "halfadder.yaml"), "--max-size", "6,3,6"]) == 1
    assert "passt nicht in 6×3×6" in capsys.readouterr().out
