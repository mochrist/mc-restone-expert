"""Command line entry point: ``rsx <command> ...``."""

from __future__ import annotations

import argparse
import sys
import warnings
from collections import Counter

from . import io
from .render import render


def _cmd_dump(args: argparse.Namespace) -> int:
    grid = io.load(args.file)
    layers = [int(v) for v in args.layers.split(",")] if args.layers else None
    print(render(grid, layers, components=args.components))
    if args.blocks:
        print("\nBlock states:")
        for state, n in Counter(s for _, s in grid.items()).most_common():
            print(f"  {n:>5}  {state}")
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    io.save(io.load(args.src), args.dst)
    print(f"wrote {args.dst}")
    return 0


def _cmd_compile(args: argparse.Namespace) -> int:
    from .verify.scenario import load, write_compiled

    scenario = load(args.scenario)
    out = args.out or f"{scenario.name}.scenario.json"
    write_compiled(scenario, out)
    print(f"wrote {out}")
    return 0


def _cmd_oracle(args: argparse.Namespace) -> int:
    from pathlib import Path

    from . import oracle
    from .verify.trace import Trace, timing_diagram

    if args.dump_blocks:
        try:
            path = oracle.dump_blocks(timeout=args.timeout, verbose=args.verbose)
        except oracle.OracleError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KiB)")
        if not args.scenarios:
            return 0
    elif not args.scenarios:
        print("error: no scenarios given", file=sys.stderr)
        return 2
    try:
        traces = oracle.run([Path(s) for s in args.scenarios], timeout=args.timeout, verbose=args.verbose)
    except oracle.OracleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    golden = Path(__file__).resolve().parents[2] / "tests" / "golden"
    for path in traces:
        trace = Trace.load(path)
        print(f"\n{trace.scenario}: {path}")
        print(timing_diagram(trace))
        if args.golden:
            golden.mkdir(parents=True, exist_ok=True)
            dst = golden / path.name
            trace.save(dst)  # same formatting as simulator traces
            print(f"wrote {dst}")
    return 0


def _cmd_sim(args: argparse.Namespace) -> int:
    from pathlib import Path

    from . import sim
    from .verify import Trace, diff, load_scenario, timing_diagram

    golden_dir = Path(__file__).resolve().parents[2] / "tests" / "golden"
    status = 0
    for path in args.scenarios:
        scenario = load_scenario(path)
        trace, world = sim.run(scenario)
        print(f"\n{scenario.name} (simulated)")
        print(timing_diagram(trace))
        if args.svg:
            from .verify.trace import trace_svg

            dst = Path(args.svg)
            if len(args.scenarios) > 1:
                dst = dst / f"{scenario.name}.svg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(trace_svg(trace, scenario.name), encoding="utf-8")
        for w in world.warnings:
            print(f"warning: {w}")
        if args.out:
            trace.save(Path(args.out) / f"{scenario.name}.trace.json")
        golden = golden_dir / f"{scenario.name}.trace.json"
        if args.diff and golden.exists():
            expected = Trace.load(golden)
            mismatches = diff(expected, trace)
            if mismatches:
                status = 1
                print(f"{len(mismatches)} mismatches against {golden.name}:")
                for m in mismatches[: args.limit]:
                    print(f"  {m}")
            else:
                print(f"matches {golden.name}")
    return status


def _cmd_materials(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .gui.materials import format_materials

    path = Path(args.file)
    if path.suffix in (".yaml", ".yml"):
        from .verify import load_scenario

        grid = load_scenario(path).grid
    else:
        grid = io.load(path)
    print(format_materials(grid))
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .analysis.analyze import analyze
    from .analysis.explain import explain

    path = Path(args.file)
    if path.suffix in (".yaml", ".yml"):
        from .verify import load_scenario

        grid, title = load_scenario(path).grid, path.stem
    else:
        grid, title = io.load(path), path.stem
    svg = None
    if args.svg:
        import os

        base = Path(args.out).resolve().parent if args.out else Path.cwd()
        link = Path(os.path.relpath(Path(args.svg).resolve(), base)).as_posix()
        svg = (link, {})
    text = explain(analyze(grid), title, svg)
    if svg:
        Path(args.svg).mkdir(parents=True, exist_ok=True)
        for fname, content in svg[1].items():
            (Path(args.svg) / fname).write_text(content, encoding="utf-8")
        print(f"wrote {len(svg[1])} SVG files to {args.svg}", file=sys.stderr)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def _parse_size(text: str) -> tuple[int, int, int]:
    parts = [int(x) for x in text.replace("x", ",").split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("size must be X,Y,Z")
    return tuple(parts)


def _spec_of_existing(analysis, title: str, wanted: str | None = None):
    """Truth-table spec if the circuit is combinational (it meets its own table, transitions included),
    else the recorded pulse behaviour; clocks become clock specs.

    wanted: comma separated output names (out1,out3) or "all"; by default all outputs count for a truth
    table and only the lamps (if there are any) for recorded behaviour."""
    from dataclasses import replace

    from .design import behaviour as bh
    from .design import spec as specmod
    from .design.candidate import Candidate
    from .design.evaluate import evaluate
    from .design.search import original_candidate

    if analysis.clock is not None:
        c = analysis.clock
        out = next((o for o in analysis.outputs if o.pos == c.observed_at), None)
        positions = [out.pos] if out else [c.observed_at]
        cand = Candidate("Original", analysis.grid, [], positions, "die analysierte Bestandsschaltung",
                         origin="original")
        spec = bh.clock(c.period, c.on_ticks)
        spec.source = f"Analyse von {title}"
        return spec, cand
    chosen = None
    if wanted and wanted != "all":
        names = [w.strip() for w in wanted.split(",") if w.strip()]
        by_name = {o.name: o for o in analysis.outputs}
        unknown = [n for n in names if n not in by_name]
        if unknown:
            raise ValueError(f"unbekannte Ausgänge {', '.join(unknown)}; vorhanden: "
                             + ", ".join(by_name))
        chosen = [by_name[n] for n in names]
    original = original_candidate(analysis, "Original")
    # an output with a timing block or memory behind its logic meets the truth table in steady states and
    # transitions, but the table would drop the timing: use the recorded behaviour for it
    timed = set(analysis.timing) | {b.output.name for b in analysis.gated}
    considered = chosen if chosen is not None else analysis.outputs
    try:
        if any(o.name in timed for o in considered):
            raise ValueError("timing behind logic")
        spec = specmod.from_analysis(analysis, title)
        if chosen is not None:
            idx = [spec.outputs.index(o.name) for o in chosen]
            spec = specmod.Spec(spec.inputs, [spec.outputs[i] for i in idx],
                                {c: tuple(v[i] for i in idx) for c, v in spec.table.items()},
                                spec.max_delay, spec.source, list(spec.notes), spec.care)
            original = replace(original, outputs=[o.pos for o in chosen])
        if evaluate(original, spec).ok:
            return spec, original
    except ValueError:
        pass
    partial = _partial_spec(analysis, title, original, chosen)
    if partial is not None:
        return partial
    ports = [p for p in analysis.inputs if p.kind in ("lever", "button")]
    if not ports or not analysis.outputs:
        raise ValueError("Die Schaltung hat keine Hebel/Knöpfe als Eingänge oder keine Ausgänge")
    if len(ports) > MAX_RECORDED_INPUTS:
        raise ValueError(f"Verhaltens-Spezifikationen werden bisher nur für bis zu {MAX_RECORDED_INPUTS} Eingänge "
                         "aufgezeichnet")
    from .analysis.experiment import Circuit

    # lamps are what the builder looks at; bulbs, torches etc. next to them are usually internal
    if chosen is not None:
        outputs = chosen
    elif wanted == "all":
        outputs = list(analysis.outputs)
    else:
        outputs = [o for o in analysis.outputs if analysis.grid.get(o.pos).id == "redstone_lamp"] or analysis.outputs
    spec = bh.from_recordings([p.name for p in ports], [p.kind for p in ports], [o.name for o in outputs],
                              Circuit(analysis.grid), [o.pos for o in outputs], [p.pos for p in ports], title)
    if len(outputs) == 1 and len(ports) == len(levers := [p for p in ports if p.kind == "lever"]):
        spec.gate_hints = _gate_hints(analysis, levers, outputs[0])
    skipped = [o for o in analysis.outputs if o not in outputs]
    if skipped and chosen is None:
        spec.notes.append("Nur die Lampen gelten als Ausgänge (andere mit --outputs wählen); nicht verlangt: "
                          + ", ".join(f"{o.name} ({analysis.grid.get(o.pos).id})" for o in skipped))
    cand = Candidate("Original", analysis.grid, [p.pos for p in ports], [o.pos for o in outputs],
                     "die analysierte Bestandsschaltung", origin="original")
    return spec, cand


MAX_RECORDED_INPUTS = 6  # stimuli: per input 8 pulses, plus every ordered pair (49 + 30 runs for 6 inputs)


def _gate_hints(analysis, levers, output) -> list[str]:
    """Gate expressions over all levers that the analysis found in front of the output: the logic in front of
    an edge-triggered block or memory (`analysis.gated`), or the truth table in front of a timing block
    (`analysis.timing`). Gates that leave a lever out are skipped (the composed logic has every lever)."""
    from .design.search import depends_on_all, gate_expression

    names = [p.name for p in levers]
    hints = []
    for b in analysis.gated:
        if b.output.name == output.name and [p.name for p in b.levers] == names:
            hints.append(b.expression)
    if output.name in analysis.timing and analysis.truth_table:
        j = analysis.outputs.index(output)
        table = {c: o[j] for c, o in analysis.truth_table}
        if depends_on_all(table):
            hints.append(gate_expression(names, [c for c, v in sorted(table.items()) if v]))
    return hints


def _partial_spec(analysis, title: str, original, chosen):
    """For many levers (no full truth table): a partial table with the stored lever states and each lever
    flipped on its own, measured on the original; every other combination does not matter. None if that does
    not apply."""
    from dataclasses import replace

    from .design import spec as specmod
    from .design.evaluate import evaluate, observe

    levers = [p for p in analysis.inputs if p.kind == "lever"]
    if analysis.truth_table or analysis.oscillates or len(levers) < 2 or len(levers) != len(analysis.inputs):
        return None
    outs = chosen if chosen is not None else list(analysis.outputs)
    if not outs:
        return None
    cand = replace(original, outputs=[o.pos for o in outs])
    n = len(levers)
    rest = tuple(analysis.grid.get(p.pos).get_bool("powered") for p in levers)
    combos = [rest] + [tuple(b != (j == i) for j, b in enumerate(rest)) for i in range(n)]
    try:
        table = observe(cand, combos)
    except ValueError:
        return None
    delays = [d for r in analysis.responses for x in r.reactions for d in x.delays if d is not None]
    spec = specmod.Spec([p.name for p in levers], [o.name for o in outs], table, max(delays) if delays else None,
                        source=f"Analyse von {title}", care=frozenset(combos))
    spec.notes.append(f"{n} Hebel: verlangt sind nur der gespeicherte Zustand der Hebel und jeder Hebel einzeln "
                      "umgelegt; alle anderen Kombinationen sind egal.")
    if not evaluate(cand, spec).ok:
        return None
    return spec, cand


class RedesignInputError(Exception):
    """No specification can be derived from the given circuit (German message)."""


def run_redesign(file, constraints=None, *, compact: int = 100, time_limit: float | None = 60,
                 outputs: str | None = None, out: str | None = None, top: int = 10,
                 steps: list[str] | None = None, output: str | None = None,
                 input: str | None = None):
    """`rsx redesign` without the command line: returns (best candidate or None, German report, spec).

    file: spec .yaml, scenario .yaml or schematic. Raises RedesignInputError (German message) if no spec can be
    derived from an existing circuit. steps: filled with the compaction log while the search runs.
    output: another block than a lamp at the outputs (key of design.actuators.ACTUATORS); the best design that
    works with it is returned. input: a pressure plate instead of the lever/button at the inputs (key of
    design.sensors.SENSORS), for designs that react to a single press; the spec returned is then the press version.
    A daylight detector replaces the one lever of a design (the spec stays the lever version)."""
    from pathlib import Path

    import yaml

    from .design import spec as specmod
    from .design.evaluate import Constraints, evaluate_any
    from .design.report import report
    from .design.search import redesign

    constraints = constraints or Constraints()
    path = Path(file)
    original = None
    title = path.stem
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix in (".yaml", ".yml") else None
    if raw is not None and "build" not in raw:
        if "behaviour" in raw:
            from .design.behaviour import from_dict as behaviour_from_dict

            spec = behaviour_from_dict(raw, source=path.name)
        else:
            spec = specmod.from_dict(raw, source=path.name)
    else:
        from .analysis.analyze import analyze

        if raw is not None:
            from .verify import load_scenario

            grid = load_scenario(path).grid
        else:
            grid = io.load(path)
        try:
            spec, original = _spec_of_existing(analyze(grid), title, outputs)
        except ValueError as e:
            raise RedesignInputError(str(e)) from e
    steps = [] if steps is None else steps
    results = redesign(spec, constraints, extra=[original] if original is not None else None,
                       compact_budget=compact, log=steps, time_limit=time_limit)
    results = [r for r in results if r.candidate is not original]
    orig_ev = evaluate_any(original, spec, constraints) if original is not None else None
    written = None
    ok = [r for r in results if r.ok]
    ok, robust_note = _position_proof_first(ok, spec, constraints)
    if ok:
        results = [ok[0]] + [r for r in results if r is not ok[0]]  # the report names the chosen design first
    best = ok[0].candidate if ok else None
    note = ""
    if output and ok:
        from .design.actuators import ACTUATORS, with_output

        best, why = None, ""
        for r in ok:
            best, why = with_output(r.candidate, output)
            if best is not None:
                note = f"\n\n## Ausgang\n\n- Entwurf „{r.candidate.name}“. {why}\n"
                break
        else:
            note = (f"\n\n## Ausgang\n\n- Kein funktionierender Entwurf ließ sich mit {ACTUATORS[output][0]} am "
                    f"Ausgang bauen ({why}). Mit Lampe gibt es Entwürfe.\n")
    if input and ok and best is not None:
        from .design.robust import check, plan, summary
        from .design.sensors import DAYLIGHT, SENSORS, button_spec, with_input

        plate, why = with_input(best, input, spec)
        if plate is None and input in DAYLIGHT:  # another working design may have its lever where it fits
            for r in ok[1:ROBUST_TRIES]:
                if output:
                    break  # (best carries the output block already)
                plate, why2 = with_input(r.candidate, input, spec)
                if plate is not None:
                    best, why = r.candidate, why2
                    break
        if plate is not None and input in DAYLIGHT:
            note += f"\n\n## Eingang\n\n- Entwurf „{best.name}“. {why}\n"
            best = plate
        elif plate is not None:
            note += f"\n\n## Eingang\n\n- Entwurf „{best.name}“. {why}\n"
            best = plate
            press_spec = button_spec(spec)
            if press_spec is not None:
                spec = press_spec
                if not output:  # (a door at the output cannot be judged by the spec)
                    import time

                    t0 = time.perf_counter()
                    quick, sample = plan(best, spec, constraints, ROBUST_BUDGET)
                    res = check(best, spec, constraints, quick=quick, sample=sample)
                    note += f"- Mit Druckplatte: {summary(res, time.perf_counter() - t0)}\n"
        else:
            note += (f"\n\n## Eingang\n\n- Mit {SENSORS[input][0]} ist dieser Entwurf nicht möglich ({why}). "
                     "Der Entwurf mit Hebel oder Knopf bleibt.\n")
    note = robust_note + note
    if out and best is not None:
        target = Path(out)
        if target.suffix == "":
            target.mkdir(parents=True, exist_ok=True)
            target = target / f"{title}-redesign.litematic"
        io.save(best.grid, target)
        written = str(target)
    text = report(spec, constraints, results, title, orig_ev, written, top=top, compact_log=steps) + note
    return best, text, spec


ROBUST_TRIES = 5  # working designs checked for position robustness, best first
ROBUST_BUDGET = 5.0  # seconds per design (more origins for small designs, fewer for large ones)


def _position_proof_first(ok: list, spec, constraints) -> tuple[list, str]:
    """Check the best working designs at many origins and in four rotations (design/robust.py, DUST-018) and
    move the first position-proof one to the front. Returns (reordered list, report section)."""
    import time

    from .design.robust import check, plan, summary

    if not ok:
        return ok, ""
    lines = []
    for i, r in enumerate(ok[:ROBUST_TRIES]):
        t0 = time.perf_counter()
        quick, sample = plan(r.candidate, spec, constraints, ROBUST_BUDGET)
        res = check(r.candidate, spec, constraints, quick=quick, sample=sample, stop_early=i > 0)
        took = time.perf_counter() - t0
        if res.ok:
            if i:
                lines.append(f"- Die {i} besser bewerteten Entwürfe hängen vom Bauort ab; gewählt ist "
                             f"„{r.candidate.name}“.")
            lines.append(f"- {summary(res, took)}")
            if quick or sample is not None:
                lines.append("- Großer Entwurf: nur Stichprobe" + (" der Positionen" if sample is not None else "")
                             + (", jede Hebelstellung aus frischer Welt (ohne Übergänge)" if quick else "") + ".")
            return [r] + ok[:i] + ok[i + 1:], "\n\n## Ortsfestigkeit\n\n" + "\n".join(lines) + "\n"
        if i == 0:
            lines.append(f"- „{r.candidate.name}“: {summary(res, took)}")
    lines.append(f"- **Warnung:** Keiner der {min(len(ok), ROBUST_TRIES)} besten Entwürfe verhält sich überall "
                 "gleich. Die Schaltung kann je nach Bauort oder Drehung anders reagieren.")
    return ok, "\n\n## Ortsfestigkeit\n\n" + "\n".join(lines) + "\n"


def _cmd_redesign(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .design.evaluate import Constraints

    constraints = Constraints(
        max_size=args.max_size,
        allowed_blocks=set(args.allow.split(",")) if args.allow else None,
        forbidden_blocks=set(args.forbid.split(",")) if args.forbid else set(),
        allow_qc=not args.no_qc,
        max_delay=args.max_delay,
    )
    try:
        best, text, _ = run_redesign(args.file, constraints, compact=args.compact, time_limit=args.time,
                                  outputs=args.outputs, out=args.out, top=args.top, output=args.output,
                                  input=args.input)
    except RedesignInputError as e:
        print(f"Fehler: {e}")
        return 2
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"wrote {args.report}")
    else:
        print(text)
    return 0 if best is not None else 1


def _cmd_catalog(args: argparse.Namespace) -> int:
    from .catalog import ENTRIES, get

    if not args.name:
        for e in ENTRIES:
            print(f"{e.key:<18} {e.title}")
        return 0
    try:
        e = get(args.name)
    except KeyError:
        print(f"unbekannter Eintrag {args.name!r}; vorhanden: {', '.join(x.key for x in ENTRIES)}", file=sys.stderr)
        return 2
    grid = e.build()
    size = " x ".join(map(str, grid.size))
    print(f"{e.title}\n\n{e.description}\n\nBedienung: {e.usage}\n\nGröße: {size}, {len(grid)} Blöcke. {e.notes}")
    if args.out:
        io.save(grid, args.out)
        print(f"wrote {args.out}")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from .gui.server import serve

    serve(args.port, args.file, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    warnings.formatwarning = lambda msg, category, *_: f"warning: {msg}\n"
    parser = argparse.ArgumentParser(prog="rsx", description="Redstone analysis and design toolkit")
    parser.add_argument("--sim-core", choices=("python", "rust", "auto"), default=None,
                        help="simulator core: the Python reference or the Rust port "
                             "(default: environment variable RSX_SIM_CORE, else auto = Rust if installed)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("dump", help="print a schematic layer by layer")
    p.add_argument("file")
    p.add_argument("--layers", help="comma separated y layers, e.g. 0,1")
    p.add_argument("--components", action="store_true", help="list position and state of every stateful block")
    p.add_argument("--blocks", action="store_true", help="also list all block states with counts")
    p.set_defaults(func=_cmd_dump)

    p = sub.add_parser("convert", help="convert between .litematic, .schem and .nbt")
    p.add_argument("src")
    p.add_argument("dst")
    p.set_defaults(func=_cmd_convert)

    p = sub.add_parser("compile", help="compile a scenario YAML into the JSON consumed by the oracle")
    p.add_argument("scenario")
    p.add_argument("-o", "--out")
    p.set_defaults(func=_cmd_compile)

    p = sub.add_parser("oracle", help="run scenarios on the Fabric oracle server and record traces")
    p.add_argument("scenarios", nargs="*", metavar="scenario.yaml")
    p.add_argument("--golden", action="store_true", help="copy the traces to tests/golden/")
    p.add_argument("--dump-blocks", action="store_true",
                   help="regenerate the block state table src/redstone/sim/data/blocks_26.3.json")
    p.add_argument("--timeout", type=float, default=900, help="seconds until the server is killed (default 900)")
    p.add_argument("-v", "--verbose", action="store_true", help="print the full server log")
    p.set_defaults(func=_cmd_oracle)

    p = sub.add_parser("sim", help="run scenarios in the simulator, optionally diff against golden traces")
    p.add_argument("scenarios", nargs="+", metavar="scenario.yaml")
    p.add_argument("--diff", action="store_true", help="compare with tests/golden/<name>.trace.json")
    p.add_argument("--limit", type=int, default=20, help="max mismatches to print")
    p.add_argument("--out", help="directory to write simulator traces to")
    p.add_argument("--svg", metavar="FILE", help="write an SVG timing diagram (several scenarios: DIR/<name>.svg)")
    p.set_defaults(func=_cmd_sim)

    p = sub.add_parser("explain", help="analyse a schematic or scenario by simulation and explain it (German)")
    p.add_argument("file", help=".litematic/.schem/.nbt or scenario .yaml")
    p.add_argument("-o", "--out", help="write the Markdown report to this file")
    p.add_argument("--svg", metavar="DIR", help="also write one SVG timing diagram per input into DIR and link it")
    p.set_defaults(func=_cmd_explain)

    p = sub.add_parser("materials", help="list the items needed to build a schematic or scenario (German)")
    p.add_argument("file", help=".litematic/.schem/.nbt or scenario .yaml")
    p.set_defaults(func=_cmd_materials)

    p = sub.add_parser("redesign", help="find compact circuits for a spec or an existing circuit (German report)")
    p.add_argument("file", help="spec .yaml (inputs/function|table), scenario .yaml or schematic")
    p.add_argument("--max-size", type=_parse_size, help="bounding box X,Y,Z (X and Z may be swapped)")
    p.add_argument("--allow", help="comma separated block ids that may be used (besides lever and lamp)")
    p.add_argument("--forbid", help="comma separated block ids that must not be used")
    p.add_argument("--no-qc", action="store_true", help="reject designs that use quasi-connectivity")
    p.add_argument("--max-delay", type=int, help="max delay in game ticks (default: from the spec)")
    p.add_argument("-o", "--out", help="write the best candidate as .litematic/.schem/.nbt (file or directory)")
    p.add_argument("--report", help="write the Markdown report to this file")
    p.add_argument("--top", type=int, default=10, help="candidates listed in the report")
    p.add_argument("--compact", type=int, default=100,
                   help="max evaluations for shrinking each synthesized/original design (0 = off, default 100)")
    p.add_argument("--time", type=float, default=60, help="time limit in seconds for shrinking (default 60)")
    p.add_argument("--input", default=None, metavar="BLOCK",
                   help="pressure plate instead of lever/button for designs that react to one press: "
                        "stone_pressure_plate, oak_pressure_plate; daylight detector instead of the one lever: "
                        "daylight_detector (on at day), daylight_detector_inverted (on at night)")
    p.add_argument("--outputs", default=None, metavar="NAMES",
                   help="outputs of an existing circuit that the redesign must keep: names from `rsx explain` "
                        "(out1,out3) or 'all' (default: all for a truth table, only the lamps for behaviour)")
    p.add_argument("--output", default=None, metavar="BLOCK",
                   help="put this block at the outputs instead of a lamp: note_block, dispenser, dropper, "
                        "iron_trapdoor, iron_door, piston, sticky_piston (checked in the simulator)")
    p.set_defaults(func=_cmd_redesign)

    p = sub.add_parser("catalog", help="list the finished builds (piston doors, item sorter) or write one")
    p.add_argument("name", nargs="?", help="entry key, e.g. piston-door-2x2")
    p.add_argument("-o", "--out", help="write the build as .litematic/.schem/.nbt")
    p.set_defaults(func=_cmd_catalog)

    p = sub.add_parser("gui", help="local web GUI: 3D/2D views, materials, build playback, search, simulation")
    p.add_argument("file", nargs="?", help="schematic or scenario to open first")
    p.add_argument("--port", type=int, default=8737)
    p.add_argument("--no-browser", action="store_true", help="do not open the browser")
    p.set_defaults(func=_cmd_gui)

    args = parser.parse_args(argv)
    if args.sim_core:
        from .sim import core

        core.use(args.sim_core)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
