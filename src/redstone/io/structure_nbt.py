"""Vanilla structure-block files (``.nbt``).

Layout: DataVersion, size[3], palette[{Name, Properties}] (or palettes[[...]]),
blocks[{pos[3], state, nbt?}], entities[]. Positions not listed in ``blocks`` are
"structure void" and are treated as air here.
"""

from __future__ import annotations

from pathlib import Path

from nbtlib import File, tag

from ..model import Grid, Pos, SchematicMeta
from ..versions import TARGET_DATA_VERSION
from . import nbtutil


def read(path: str | Path) -> Grid:
    return from_nbt(nbtutil.load(str(path)))


def from_nbt(root: tag.Compound) -> Grid:
    size = tuple(int(v) for v in root["size"])
    palette_tag = root["palette"] if "palette" in root else root["palettes"][0]
    palette = [nbtutil.state_from_compound(e) for e in palette_tag]
    meta = SchematicMeta(
        data_version=int(root["DataVersion"]) if "DataVersion" in root else None,
        source_format="nbt",
    )
    grid = Grid(size, meta)
    for block in root["blocks"]:
        pos = Pos(*(int(v) for v in block["pos"]))
        state = palette[int(block["state"])]
        if state.is_air:
            continue
        grid.set(pos, state)
        if "nbt" in block:
            grid.block_entities[pos] = nbtutil.to_py(block["nbt"])
    return grid


def to_nbt(grid: Grid, include_air: bool = True) -> File:
    palette = grid.palette()
    index = {state: i for i, state in enumerate(palette)}
    blocks = []
    if include_air:
        positions = (
            Pos(x, y, z) for y in range(grid.size.y) for z in range(grid.size.z) for x in range(grid.size.x)
        )
    else:
        positions = (pos for pos, _ in grid.items())
    for pos in positions:
        entry = tag.Compound(
            {"pos": tag.List[tag.Int]([tag.Int(v) for v in pos]), "state": tag.Int(index[grid.get(pos)])}
        )
        if pos in grid.block_entities:
            entry["nbt"] = nbtutil.to_nbt(grid.block_entities[pos])
        blocks.append(entry)
    return File(
        {
            "DataVersion": tag.Int(grid.meta.data_version or TARGET_DATA_VERSION),
            "size": tag.List[tag.Int]([tag.Int(v) for v in grid.size]),
            "palette": tag.List[tag.Compound]([nbtutil.state_to_compound(s) for s in palette]),
            "blocks": tag.List[tag.Compound](blocks),
            "entities": tag.List[tag.Compound](),
        },
        gzipped=True,
    )


def write(grid: Grid, path: str | Path) -> None:
    to_nbt(grid).save(str(path), gzipped=True)
