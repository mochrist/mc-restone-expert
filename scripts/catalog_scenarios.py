"""Write one oracle scenario per catalog entry (scenarios/cat-<key>.yaml), so the real game can confirm the
builds of src/redstone/catalog.

uv run python scripts/catalog_scenarios.py && uv run rsx oracle scenarios/cat-*.yaml --golden
"""

from __future__ import annotations

from pathlib import Path

import yaml

from redstone.catalog import get
from redstone.catalog.entries import FILTER_ITEM, OTHER_ITEM, SORTER_ITEMS, items_nbt
from redstone.io.nbtutil import to_nbt
from redstone.model import Grid, Pos

ROOT = Path(__file__).parents[1]


def _grow(grid: Grid, below: int = 0, east: int = 0, south: int = 0) -> tuple[Grid, Pos]:
    """A copy of `grid` with extra room (`below` layers under it, `east`/`south` columns after it); returns the
    copy and the shift of the old coordinates."""
    shift = Pos(0, below, 0)
    out = Grid((grid.size[0] + east, grid.size[1] + below, grid.size[2] + south), grid.meta)
    for p, s in grid.items():
        out.set(p + shift, s)
    out.block_entities = {p + shift: be for p, be in grid.block_entities.items()}
    return out, shift


def _scenario(name: str, grid: Grid, text: str, ticks: int, inputs: list[tuple[int, Pos]],
              probes: dict[str, Pos]) -> dict:
    d = {
        "name": name,
        "description": text,
        "build": {"size": list(grid.size),
                  "blocks": [[*p, str(s).removeprefix("minecraft:")] for p, s in sorted(grid.items())]},
        "ticks": ticks,
        "inputs": [{"tick": t, "pos": list(p), "action": "use"} for t, p in inputs],
        "probes": {k: list(p) for k, p in probes.items()},
    }
    if grid.block_entities:
        d["build"]["block_entities"] = [[*p, to_nbt(be).snbt()] for p, be in sorted(grid.block_entities.items())]
    return d


def piston_door() -> dict:
    b = get("piston-door-2x2").built()
    lever = b.ports["lever"]
    ticks, t, inputs = 0, 2, []
    for _ in range(6):  # slow: open, close, ...
        inputs.append((t, lever))
        t += 20
    for gap in (4, 2):  # fast flicking from closed and from open
        inputs += [(t, lever), (t + gap, lever)]
        t += 24
        inputs.append((t, lever))
        t += 20
        inputs += [(t, lever), (t + gap, lever)]
        t += 24
        inputs.append((t, lever))
        t += 20
    ticks = t
    probes = {"lever": lever} | {f"door{i}": b.ports[f"door{i}"] for i in range(4)}
    probes |= {"pocket_left_low": b.ports["pocket_left_low"], "pocket_right_high": b.ports["pocket_right_high"]}
    return _scenario("cat-piston-door-2x2", b.grid,
                     "Katalog: Kolbentür 2x2 (src/redstone/catalog). Hebel sechsmal im Abstand von 20 gt, dann "
                     "schnelles Umlegen mit 4 und 2 gt Abstand, je aus geschlossener und offener Tür.",
                     ticks, inputs, probes)


def hidden_door() -> dict:
    b = get("hidden-door-1x2").built()
    button = b.ports["button"]
    inputs = [(2, button), (102, button), (140, button)]  # once, then again while open (after the button reset)
    probes = {"button": button, "door0": b.ports["door0"], "door1": b.ports["door1"]}
    return _scenario("cat-hidden-door-1x2", b.grid,
                     "Katalog: versteckte Tür 1x2 mit Holzknopf (src/redstone/catalog). Ein Druck; dann ein Druck "
                     "und ein zweiter, solange die Tür noch offen ist.",
                     240, inputs, probes)


def item_sorter() -> dict:
    b = get("item-sorter").built()
    grid, shift = _grow(b.grid, below=1, east=1, south=1)
    load = [(s, FILTER_ITEM if s % 2 == 0 else OTHER_ITEM, 16) for s in range(8)]
    grid.block_entities[b.ports["input"] + shift] = items_nbt("minecraft:chest", load)
    # comparators that read the target and the overflow chest (only for the recording)
    target, overflow = b.ports["target"] + shift, b.ports["overflow"] + shift
    t_cmp, o_cmp = target + Pos(0, 0, 1), overflow + Pos(1, 0, 0)
    grid.set(t_cmp, "comparator[facing=north,mode=compare,powered=false]")
    grid.set(t_cmp + Pos(0, -1, 0), "stone")
    grid.set(o_cmp, "comparator[facing=west,mode=compare,powered=false]")
    grid.set(o_cmp + Pos(0, -1, 0), "stone")
    for p in (t_cmp, o_cmp):
        grid.block_entities[p] = {"id": "minecraft:comparator", "OutputSignal": 0}
    probes = {"filter": b.ports["comparator"] + shift, "inverter": b.ports["inverter"] + shift,
              "lock": b.ports["lock"] + shift, "target": t_cmp, "overflow": o_cmp}
    return _scenario("cat-item-sorter", grid,
                     "Katalog: Itemsortierer (src/redstone/catalog). Eingangstruhe mit je 4 x 16 Bruchstein und "
                     "Erde abwechselnd; zwei Komparatoren nur für die Aufnahme lesen Ziel- und Überlauftruhe.",
                     1100, [], probes)


def item_sorter_4() -> dict:
    b = get("item-sorter-4").built()
    grid, shift = _grow(b.grid, below=1, east=1, south=1)
    load = [(s, (*SORTER_ITEMS, OTHER_ITEM)[s % 5], 8) for s in range(20)]
    grid.block_entities[b.ports["input"] + shift] = items_nbt("minecraft:chest", load)
    probes = {}
    # comparators that read every target chest and the overflow chest (only for the recording)
    reads = [(f"target{k}", b.ports[f"target{k}"] + shift + Pos(0, 0, 1), "north") for k in range(1, 5)]
    reads.append(("overflow", b.ports["overflow"] + shift + Pos(1, 0, 0), "west"))
    for name, p, facing in reads:
        grid.set(p, f"comparator[facing={facing},mode=compare,powered=false]")
        grid.set(p + Pos(0, -1, 0), "stone")
        grid.block_entities[p] = {"id": "minecraft:comparator", "OutputSignal": 0}
        probes[name] = p
    probes |= {f"filter{k}": b.ports[f"comparator{k}"] + shift for k in range(1, 5)}
    return _scenario("cat-item-sorter-4", grid,
                     "Katalog: Itemsortierer mit vier Fächern (src/redstone/catalog). Eingangstruhe mit je 4 x 8 "
                     "Bruchstein, Andesit, Granit, Diorit und Erde abwechselnd; Komparatoren nur für die Aufnahme "
                     "lesen die vier Zieltruhen und die Überlauftruhe.",
                     1400, [], probes)


def main() -> None:
    for d in (piston_door(), hidden_door(), item_sorter(), item_sorter_4()):
        path = ROOT / "scenarios" / f"{d['name']}.yaml"
        path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120, default_flow_style=None),
                        encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
