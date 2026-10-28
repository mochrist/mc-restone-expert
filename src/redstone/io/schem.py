"""Sponge schematic ``.schem`` files (versions 1-3), as written by WorldEdit.

v1/v2: root compound "Schematic" with Width/Height/Length, Palette{state: id},
       BlockData (varint byte array), BlockEntities (v2) / TileEntities (v1) [{Pos[3], Id, ...}].
v3:    root {Schematic: {..., Blocks: {Palette, Data, BlockEntities[{Pos, Id, Data{...}}]}}}.
Block index is ``x + z * Width + y * Width * Length``.
"""

from __future__ import annotations

from pathlib import Path

from nbtlib import File, tag

from ..model import Grid, Pos, SchematicMeta
from ..model.blockstate import BlockState
from ..versions import TARGET_DATA_VERSION
from . import nbtutil


def read(path: str | Path) -> Grid:
    return from_nbt(nbtutil.load(str(path)))


def from_nbt(root: tag.Compound) -> Grid:
    schem = root["Schematic"] if "Schematic" in root else root
    version = int(schem.get("Version", 1))
    if version >= 3:
        blocks = schem["Blocks"]
        palette_tag, data, be_list = blocks["Palette"], blocks["Data"], blocks.get("BlockEntities", [])
    else:
        palette_tag, data = schem["Palette"], schem["BlockData"]
        be_list = schem.get("BlockEntities", schem.get("TileEntities", []))

    size = Pos(int(schem["Width"]), int(schem["Height"]), int(schem["Length"]))
    metadata = schem.get("Metadata", tag.Compound())
    meta = SchematicMeta(
        name=str(metadata.get("Name", "")),
        author=str(metadata.get("Author", "")),
        data_version=int(schem["DataVersion"]) if "DataVersion" in schem else None,
        source_format="schem",
        extra={"sponge_version": version, "offset": tuple(int(v) for v in schem.get("Offset", [0, 0, 0]))},
    )
    grid = Grid(tuple(size), meta)

    palette: dict[int, BlockState] = {int(i): BlockState.parse(str(s)) for s, i in palette_tag.items()}
    indices = nbtutil.decode_varints(list(data), size.x * size.y * size.z)
    for i, pid in enumerate(indices):
        state = palette[pid]
        if state.is_air:
            continue
        y, rest = divmod(i, size.x * size.z)
        z, x = divmod(rest, size.x)
        grid.set((x, y, z), state)

    for be in be_list:
        x, y, z = (int(v) for v in be["Pos"])
        py = nbtutil.to_py(be)
        if version >= 3:
            entry = dict(py.get("Data", {}))
            entry["id"] = py.get("Id", entry.get("id"))
        else:
            entry = {k: v for k, v in py.items() if k not in ("Pos", "Id")}
            entry["id"] = py.get("Id")
        grid.block_entities[Pos(x, y, z)] = entry
    return grid


def to_nbt(grid: Grid) -> File:
    palette = grid.palette()
    index = {state: i for i, state in enumerate(palette)}
    sx, sy, sz = grid.size
    values = [0] * grid.volume
    for pos, state in grid.items():
        values[pos.x + pos.z * sx + pos.y * sx * sz] = index[state]

    block_entities = []
    for pos, data in sorted(grid.block_entities.items()):
        payload = {k: v for k, v in data.items() if k != "id"}
        entry = tag.Compound({"Pos": tag.IntArray(list(pos)), "Id": tag.String(data.get("id", ""))})
        if payload:
            entry["Data"] = nbtutil.to_nbt(payload)
        block_entities.append(entry)

    schem = tag.Compound(
        {
            "Version": tag.Int(3),
            "DataVersion": tag.Int(grid.meta.data_version or TARGET_DATA_VERSION),
            "Width": tag.Short(sx),
            "Height": tag.Short(sy),
            "Length": tag.Short(sz),
            "Offset": tag.IntArray([0, 0, 0]),
            "Blocks": tag.Compound(
                {
                    "Palette": tag.Compound({str(s): tag.Int(i) for s, i in index.items()}),
                    "Data": tag.ByteArray(list(_signed(nbtutil.encode_varints(values)))),
                    "BlockEntities": tag.List[tag.Compound](block_entities),
                }
            ),
        }
    )
    if grid.meta.name or grid.meta.author:
        schem["Metadata"] = tag.Compound(
            {"Name": tag.String(grid.meta.name), "Author": tag.String(grid.meta.author)}
        )
    return File({"Schematic": schem}, gzipped=True)


def _signed(data: bytes):
    return (b - 256 if b > 127 else b for b in data)


def write(grid: Grid, path: str | Path) -> None:
    to_nbt(grid).save(str(path), gzipped=True)
