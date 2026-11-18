"""Grid -> model JSON of the GUI (docs/gui-api.md, "Modell")."""

from __future__ import annotations

from pathlib import Path

from ..model import BlockState, Grid, Pos

PREFIX = "minecraft:"


def state_str(state: BlockState | str) -> str:
    """State string without the `minecraft:` prefix (also for probe values with `|output=N`)."""
    s = str(state)
    return s[len(PREFIX):] if s.startswith(PREFIX) else s


def blocks(grid: Grid) -> list[dict]:
    return [{"p": list(p), "s": state_str(s)} for p, s in sorted(grid.items(), key=lambda e: (e[0].y, e[0].x, e[0].z))
            if s.id != "air"]


def model(grid: Grid, name: str, inputs: list[tuple[str, Pos]] | None = None,
          outputs: list[tuple[str, Pos]] | None = None, notes: list[str] | None = None) -> dict:
    """Model JSON; inputs/outputs default to the ports `rsx explain` finds (levers/buttons, lamps ...)."""
    from .materials import build_order, materials

    if inputs is None or outputs is None:
        from ..analysis.ports import find_ports

        ins, outs = find_ports(grid)
        inputs = [(p.name, p.pos) for p in ins] if inputs is None else inputs
        outputs = [(p.name, p.pos) for p in outs] if outputs is None else outputs
    return {
        "name": name,
        "size": list(grid.size),
        "blocks": blocks(grid),
        "inputs": [{"name": n, "p": list(p)} for n, p in inputs],
        "outputs": [{"name": n, "p": list(p)} for n, p in outputs],
        "materials": materials(grid),
        "build_order": [list(p) for p in build_order(grid)],
        "notes": list(notes or []),
    }


def load(path: str | Path) -> tuple[Grid, dict]:
    """Grid and model of a schematic or a scenario (.yaml with `build`). Raises ValueError (German) otherwise."""
    from .. import io

    path = Path(path)
    if path.suffix in (".yaml", ".yml"):
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "build" not in raw:
            raise ValueError(f"{path.name} ist kein Szenario (kein Abschnitt `build`)")
        from ..analysis.ports import input_kind
        from ..verify import load_scenario

        sc = load_scenario(path)
        grid = sc.grid
        probes = [(n, Pos(*p)) for n, p in sc.probes.items()]
        named = {p: n for n, p in probes}
        ins = sorted({Pos(*i.pos) for i in sc.inputs if i.action in ("use", "step")})
        if not ins:  # no test run (e.g. a catalog entry): levers and buttons among the probes are the inputs
            ins = sorted(p for _, p in probes if input_kind(grid.get(p)) is not None)
        inputs = [(named.get(p, f"in{k + 1}"), p) for k, p in enumerate(ins)]
        outputs = [(n, p) for n, p in probes if p not in set(ins) and input_kind(grid.get(p)) is None]
        notes = [sc.description] if sc.description else []
        if not sc.inputs and not sc.probes:  # a plain build (e.g. a catalog entry): ports as for a schematic
            return grid, model(grid, sc.name, notes=notes)
        return grid, model(grid, sc.name, inputs, outputs, notes)
    grid = io.load(path)
    return grid, model(grid, path.stem)


def of_candidate(cand, spec=None) -> dict:
    """Model of a design candidate; port names from the spec when it is given."""
    in_names = list(getattr(spec, "inputs", None) or [f"in{k + 1}" for k in range(len(cand.inputs))])
    out_names = list(getattr(spec, "outputs", None) or [f"out{k + 1}" for k in range(len(cand.outputs))])
    notes = [cand.description] if cand.description else []
    return model(cand.grid, cand.name, list(zip(in_names, cand.inputs)), list(zip(out_names, cand.outputs)), notes)
