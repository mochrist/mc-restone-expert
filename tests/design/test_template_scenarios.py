"""Every template has an oracle scenario with a golden trace, and the scenario still matches the template.

If this fails after changing a template: uv run python scripts/template_scenarios.py, then record again with
uv run rsx oracle scenarios/tpl-<name>.yaml --golden."""

import importlib.util
from pathlib import Path

import pytest
import yaml

from redstone.design.templates import TEMPLATES

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("template_scenarios", ROOT / "scripts" / "template_scenarios.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.name)
def test_scenario_and_golden_up_to_date(template):
    path = ROOT / "scenarios" / f"tpl-{template.name}.yaml"
    assert path.exists()
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert stored == yaml.safe_load(yaml.safe_dump(gen.scenario_for(template), allow_unicode=True))
    assert (ROOT / "tests" / "golden" / f"tpl-{template.name}.trace.json").exists()


SPECS = sorted((ROOT / "examples" / "specs").glob("*.yaml"))


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.stem)
def test_pla_scenario_and_golden_up_to_date(spec_path):
    path = ROOT / "scenarios" / f"pla-{spec_path.stem}.yaml"
    assert path.exists()
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert stored == yaml.safe_load(yaml.safe_dump(gen.pla_scenario(spec_path), allow_unicode=True))
    assert (ROOT / "tests" / "golden" / f"pla-{spec_path.stem}.trace.json").exists()
