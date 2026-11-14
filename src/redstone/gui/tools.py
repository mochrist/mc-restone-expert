"""What the GUI server offers besides models, simulations and design searches: the other `rsx` commands
(explain, dump, sim, convert, compile, materials) as functions that return JSON-ready data or file contents."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from ..model import Grid

SCHEMATIC_FORMATS = ("litematic", "schem", "nbt")
TEXT_FORMATS = ("materials", "dump", "guide")
GOLDEN_DIR = Path(__file__).resolve().parents[3] / "tests" / "golden"


def safe_name(name: str, default: str = "datei") -> str:
    """A file name without directories or odd characters (uploads, downloads)."""
    name = re.sub(r"[^\w.\-]+", "_", Path(str(name).replace("\\", "/")).name, flags=re.ASCII).strip("._")
    return name or default


def explain(grid: Grid, title: str) -> dict:
    """`rsx explain`: the Markdown report plus the SVG timing diagrams it links (by file name)."""
    from ..analysis.analyze import analyze
    from ..analysis.explain import explain as explain_text

    svgs: dict[str, str] = {}
    return {"markdown": explain_text(analyze(grid), title, ("svg", svgs)), "svgs": svgs}


def dump(grid: Grid, layers: list[int] | None = None, components: bool = True, states: bool = False) -> str:
    """`rsx dump`: the circuit layer by layer as text."""
    from collections import Counter

    from ..render import render

    text = render(grid, layers, components=components)
    if states:
        text += "\n\nBlockzustände:\n" + "\n".join(
            f"  {n:>5}  {s}" for s, n in Counter(s for _, s in grid.items()).most_common())
    return text


def guide(grid: Grid, title: str) -> str:
    """Build instructions as plain text: material list, then every layer from the bottom up."""
    from .materials import format_materials

    return (f"Bauanleitung: {title}\nGröße {'×'.join(map(str, grid.size))} (x×y×z)\n\nMaterial\n--------\n"
            f"{format_materials(grid)}\n\nEbenen (von unten nach oben)\n----------------------------\n"
            f"{dump(grid, components=True)}\n")


def run_scenario(path: Path) -> dict:
    """`rsx sim --diff`: run a scenario in the simulator; timing diagram and comparison with its golden trace."""
    from .. import sim
    from ..verify import Trace, load_scenario, timing_diagram
    from ..verify.trace import trace_svg

    scenario = load_scenario(path)
    trace, world = sim.run(scenario)
    out = {"name": scenario.name, "description": scenario.description or "", "ticks": trace.ticks,
           "diagram": timing_diagram(trace), "svg": trace_svg(trace, scenario.name),
           "warnings": [str(w) for w in world.warnings], "golden": None}
    golden = GOLDEN_DIR / f"{scenario.name}.trace.json"
    if golden.exists():
        out["golden"] = compare(Trace.load(golden), trace)
    return out


def compare(expected, actual, limit: int = 50) -> dict:
    from ..verify import diff

    mismatches = diff(expected, actual)
    return {"matches": not mismatches, "count": len(mismatches), "mismatches": [str(m) for m in mismatches[:limit]]}


def export(grid: Grid, fmt: str, title: str) -> tuple[bytes, str, str]:
    """File contents, file name and content type of a download."""
    name = safe_name(title, "schaltung")
    if fmt in SCHEMATIC_FORMATS:
        from .. import io

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / f"{name}.{fmt}"
            io.save(grid, target)
            return target.read_bytes(), target.name, "application/octet-stream"
    if fmt == "materials":
        from .materials import format_materials

        return format_materials(grid).encode("utf-8"), f"{name}-material.txt", "text/plain; charset=utf-8"
    if fmt == "dump":
        return dump(grid, states=True).encode("utf-8"), f"{name}-ebenen.txt", "text/plain; charset=utf-8"
    if fmt == "guide":
        return guide(grid, title).encode("utf-8"), f"{name}-bauanleitung.txt", "text/plain; charset=utf-8"
    raise ValueError(f"unbekanntes Format {fmt!r}")


def compiled_scenario(path: Path) -> tuple[bytes, str, str]:
    """`rsx compile`: the JSON the oracle consumes."""
    from ..verify import load_scenario

    sc = load_scenario(path)
    return (json.dumps(sc.compile(), indent=1).encode("utf-8"), f"{safe_name(sc.name)}.scenario.json",
            "application/json")


def yaml_kind(text: str) -> str:
    """"scenarios" or "specs" for the text of a .yaml file; raises ValueError (German) if it is neither."""
    import yaml

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"kein gültiges YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError("die YAML-Datei muss aus Schlüsseln und Werten bestehen (z. B. inputs, function)")
    return "scenarios" if "build" in raw else "specs"
