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
    assert main(["redesign", str(EXAMPLES / "xor.yaml"), "-o", str(out), "--compact", "0"]) == 0
    text = capsys.readouterr().out
    assert "Bester Kandidat: **xor2-" in text
    assert out.exists()
    grid = io.load(out)
    assert len(grid) > 0


def test_redesign_respects_box(capsys):
    assert main(["redesign", str(EXAMPLES / "halfadder.yaml"), "--max-size", "6,3,6", "--compact", "0"]) == 1
    assert "passt nicht in 6×3×6" in capsys.readouterr().out


def test_redesign_with_pressure_plate_and_door(tmp_path, capsys):
    out = tmp_path / "tuer.litematic"
    behaviour = Path(__file__).parents[2] / "examples" / "behaviour" / "monoflop.yaml"
    assert main(["redesign", str(behaviour), "--input", "stone_pressure_plate", "--output", "iron_door",
                 "-o", str(out), "--compact", "0"]) == 0
    text = capsys.readouterr().out
    assert "## Eingang" in text and "Steindruckplatte" in text
    assert any(s.id == "stone_pressure_plate" for _, s in io.load(out).items())


def test_redesign_plate_refused_for_lever_logic(capsys):
    assert main(["redesign", str(EXAMPLES / "xor.yaml"), "--input", "stone_pressure_plate", "--compact", "0"]) == 0
    assert "nicht möglich" in capsys.readouterr().out
