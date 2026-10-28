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
    p.add_argument("scenarios", nargs="+", metavar="scenario.yaml")
    p.add_argument("--golden", action="store_true", help="copy the traces to tests/golden/")
    p.add_argument("--timeout", type=float, default=900, help="seconds until the server is killed (default 900)")
    p.add_argument("-v", "--verbose", action="store_true", help="print the full server log")
    p.set_defaults(func=_cmd_oracle)

    p = sub.add_parser("sim", help="run scenarios in the simulator, optionally diff against golden traces")
    p.add_argument("scenarios", nargs="+", metavar="scenario.yaml")
    p.add_argument("--diff", action="store_true", help="compare with tests/golden/<name>.trace.json")
    p.add_argument("--limit", type=int, default=20, help="max mismatches to print")
    p.add_argument("--out", help="directory to write simulator traces to")
    p.set_defaults(func=_cmd_sim)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
