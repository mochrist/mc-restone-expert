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
    text = explain(analyze(grid), title)
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


def _cmd_redesign(args: argparse.Namespace) -> int:
    from pathlib import Path

    import yaml

    from .design import spec as specmod
    from .design.evaluate import Constraints, evaluate
    from .design.report import report
    from .design.search import original_candidate, redesign

    path = Path(args.file)
    original = None
    title = path.stem
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix in (".yaml", ".yml") else None
    if raw is not None and "build" not in raw:
        spec = specmod.from_dict(raw, source=path.name)
    else:
        from .analysis.analyze import analyze

        if raw is not None:
            from .verify import load_scenario

            grid = load_scenario(path).grid
        else:
            grid = io.load(path)
        analysis = analyze(grid)
        try:
            spec = specmod.from_analysis(analysis, title)
        except ValueError as e:
            print(f"Fehler: {e}")
            return 2
        original = original_candidate(analysis, "Original")
    constraints = Constraints(
        max_size=args.max_size,
        allowed_blocks=set(args.allow.split(",")) if args.allow else None,
        forbidden_blocks=set(args.forbid.split(",")) if args.forbid else set(),
        allow_qc=not args.no_qc,
        max_delay=args.max_delay,
    )
    steps: list[str] = []
    results = redesign(spec, constraints, extra=[original] if original is not None else None,
                       compact_budget=args.compact, log=steps, time_limit=args.time)
    results = [r for r in results if r.candidate is not original]
    orig_ev = evaluate(original, spec, constraints) if original is not None else None
    written = None
    ok = [r for r in results if r.ok]
    if args.out and ok:
        out = Path(args.out)
        if out.suffix == "":
            out.mkdir(parents=True, exist_ok=True)
            out = out / f"{title}-redesign.litematic"
        io.save(ok[0].candidate.grid, out)
        written = str(out)
    text = report(spec, constraints, results, title, orig_ev, written, top=args.top, compact_log=steps)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"wrote {args.report}")
    else:
        print(text)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    warnings.formatwarning = lambda msg, category, *_: f"warning: {msg}\n"
    parser = argparse.ArgumentParser(prog="rsx", description="Redstone analysis and design toolkit")
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
    p.set_defaults(func=_cmd_sim)

    p = sub.add_parser("explain", help="analyse a schematic or scenario by simulation and explain it (German)")
    p.add_argument("file", help=".litematic/.schem/.nbt or scenario .yaml")
    p.add_argument("-o", "--out", help="write the Markdown report to this file")
    p.set_defaults(func=_cmd_explain)

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
    p.set_defaults(func=_cmd_redesign)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
