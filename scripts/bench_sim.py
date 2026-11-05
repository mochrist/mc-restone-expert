"""Measure simulator speed for the M4 design note (docs/m4-search-and-performance.md).

uv run python scripts/bench_sim.py
"""

from __future__ import annotations

import time
from pathlib import Path

from redstone.analysis.analyze import analyze
from redstone.analysis.experiment import Circuit
from redstone.io import load
from redstone.verify import load_scenario

ROOT = Path(__file__).parents[1]
CASES = [
    ("repeater-ring (Clock, 13 Blöcke)", ROOT / "tests/fixtures/analysis/clocks/repeater-ring-running.yaml"),
    ("torch-repeater-4 (Clock)", ROOT / "tests/fixtures/analysis/clocks/torch-repeater-4.yaml"),
    ("rs-latch", ROOT / "tests/fixtures/analysis/rs-latch.yaml"),
    ("mux3-8", ROOT / "tests/fixtures/external/mux3-8.litematic"),
    ("seg7", ROOT / "tests/fixtures/external/seg7.litematic"),
]


def grid_of(path: Path):
    return load_scenario(path).grid if path.suffix == ".yaml" else load(path)


def bench_ticks(grid, ticks: int = 400) -> tuple[float, int]:
    circuit = Circuit(grid)
    world = circuit.new_world(kick=True)
    updates = 0
    orig = world._execute_update

    def counting(*a, **k):
        nonlocal updates
        updates += 1
        return orig(*a, **k)

    world._execute_update = counting
    t0 = time.perf_counter()
    for _ in range(ticks):
        world.tick()
    return time.perf_counter() - t0, updates


def bench_place(grid, n: int = 20) -> float:
    circuit = Circuit(grid)
    t0 = time.perf_counter()
    for _ in range(n):
        circuit.new_world()
    return (time.perf_counter() - t0) / n


def main() -> None:
    print("| Fall | Blöcke | Welt aufbauen | Ticks/s (400 gt, angestoßen) | Neighbor-Updates/s | rsx-Analyse |")
    print("|---|---|---|---|---|---|")
    for name, path in CASES:
        if not path.exists():
            continue
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            grid = grid_of(path)
        blocks = sum(1 for _ in grid.items())
        place = bench_place(grid)
        dt, updates = bench_ticks(grid)
        t0 = time.perf_counter()
        analyze(grid)
        full = time.perf_counter() - t0
        print(f"| {name} | {blocks} | {place * 1000:.1f} ms | {400 / dt:,.0f} | {updates / dt:,.0f} | {full:.2f} s |")


if __name__ == "__main__":
    main()
