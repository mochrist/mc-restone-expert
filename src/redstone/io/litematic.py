"""Litematica ``.litematic`` files (schematic version 1-7).

Layout (gzipped NBT, see fi.dy.masa.litematica.schematic.LitematicaSchematic):
  Version, SubVersion, MinecraftDataVersion, Metadata{...},
  Regions{<name>: {Position{x,y,z}, Size{x,y,z}, BlockStatePalette[], BlockStates(long[]),
                   TileEntities[{x,y,z,...}], Entities[], PendingBlockTicks[], PendingFluidTicks[]}}

Size components may be negative: the region then extends from Position towards
negative coordinates. Block indices are ``(y * sizeZ + z) * sizeX + x`` relative to the
region's min corner, packed tightly across longs with max(2, ceil(log2(palette))) bits.
"""

from __future__ import annotations

import time
from pathlib import Path

from nbtlib import File, tag

from ..model import Grid, Pos, SchematicMeta
from ..versions import TARGET_DATA_VERSION
from . import nbtutil

SCHEMATIC_VERSION = 7
SCHEMATIC_SUBVERSION = 1


def _xyz(compound: tag.Compound) -> tuple[int, int, int]:
    return int(compound["x"]), int(compound["y"]), int(compound["z"])


def _region_min_and_size(pos: tuple[int, int, int], size: tuple[int, int, int]):
    lo = tuple(p + s + 1 if s < 0 else p for p, s in zip(pos, size))
    return Pos(*lo), Pos(*(abs(s) for s in size))


def read(path: str | Path) -> Grid:
    root = nbtutil.load(str(path))
    return from_nbt(root)


def from_nbt(root: tag.Compound) -> Grid:
    version = int(root.get("Version", 0))
    if not 1 <= version <= SCHEMATIC_VERSION:
        raise ValueError(f"unsupported litematic version {version}")
    meta_tag = root.get("Metadata", tag.Compound())
    regions = root["Regions"]

    placed = []
    for name, region in regions.items():
        lo, size = _region_min_and_size(_xyz(region["Position"]), _xyz(region["Size"]))
        placed.append((str(name), region, lo, size))
    if not placed:
        raise ValueError("litematic has no regions")

    origin = Pos(*(min(lo[i] for _, _, lo, _ in placed) for i in range(3)))
    extent = Pos(*(max(lo[i] + size[i] for _, _, lo, size in placed) - origin[i] for i in range(3)))

    meta = SchematicMeta(
        name=str(meta_tag.get("Name", "")),
        author=str(meta_tag.get("Author", "")),
        description=str(meta_tag.get("Description", "")),
        data_version=int(root["MinecraftDataVersion"]) if "MinecraftDataVersion" in root else None,
        source_format="litematic",
        extra={"litematic_version": version, "regions": [p[0] for p in placed], "origin": tuple(origin)},
    )
    grid = Grid(tuple(extent), meta)

    for _name, region, lo, size in placed:
        palette = [nbtutil.state_from_compound(e) for e in region["BlockStatePalette"]]
        volume = size.x * size.y * size.z
        bits = nbtutil.bits_for_palette(len(palette), 2)
        indices = nbtutil.unpack_tight(list(region["BlockStates"]), bits, volume)
        shift = lo - origin
        i = 0
        for y in range(size.y):
            for z in range(size.z):
                for x in range(size.x):
                    state = palette[indices[i]]
                    i += 1
                    if not state.is_air:
                        grid.set((x + shift.x, y + shift.y, z + shift.z), state)
        for te in region.get("TileEntities", []):
            rel = Pos(int(te["x"]), int(te["y"]), int(te["z"]))
            data = {k: v for k, v in nbtutil.to_py(te).items() if k not in ("x", "y", "z")}
            grid.block_entities[rel + shift] = data
    return grid


def to_nbt(grid: Grid, region_name: str = "Main") -> File:
    palette = grid.palette()
    index = {state: i for i, state in enumerate(palette)}
    sx, sy, sz = grid.size
    values = [0] * grid.volume
    for pos, state in grid.items():
        values[(pos.y * sz + pos.z) * sx + pos.x] = index[state]
    bits = nbtutil.bits_for_palette(len(palette), 2)

    def xyz(x: int, y: int, z: int) -> tag.Compound:
        return tag.Compound({"x": tag.Int(x), "y": tag.Int(y), "z": tag.Int(z)})

    tile_entities = []
    for pos, data in sorted(grid.block_entities.items()):
        te = nbtutil.to_nbt(data)
        te.update(xyz(*pos))
        tile_entities.append(te)

    region = tag.Compound(
        {
            "Position": xyz(0, 0, 0),
            "Size": xyz(sx, sy, sz),
            "BlockStatePalette": tag.List[tag.Compound]([nbtutil.state_to_compound(s) for s in palette]),
            "BlockStates": tag.LongArray(nbtutil.pack_tight(values, bits)),
            "TileEntities": tag.List[tag.Compound](tile_entities),
            "Entities": tag.List[tag.Compound](),
            "PendingBlockTicks": tag.List[tag.Compound](),
            "PendingFluidTicks": tag.List[tag.Compound](),
        }
    )
    now = int(time.time() * 1000)
    meta = tag.Compound(
        {
            "Name": tag.String(grid.meta.name or region_name),
            "Author": tag.String(grid.meta.author),
            "Description": tag.String(grid.meta.description),
            "EnclosingSize": xyz(sx, sy, sz),
            "RegionCount": tag.Int(1),
            "TimeCreated": tag.Long(now),
            "TimeModified": tag.Long(now),
            "TotalBlocks": tag.Int(len(grid)),
            "TotalVolume": tag.Int(grid.volume),
        }
    )
    root = File(
        {
            "Version": tag.Int(SCHEMATIC_VERSION),
            "SubVersion": tag.Int(SCHEMATIC_SUBVERSION),
            "MinecraftDataVersion": tag.Int(grid.meta.data_version or TARGET_DATA_VERSION),
            "Metadata": meta,
            "Regions": tag.Compound({region_name: region}),
        },
        gzipped=True,
    )
    return root


def write(grid: Grid, path: str | Path) -> None:
    to_nbt(grid).save(str(path), gzipped=True)
