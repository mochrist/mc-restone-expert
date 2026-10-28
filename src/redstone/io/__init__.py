"""Reading and writing schematic files. Format is chosen by file extension."""

from __future__ import annotations

import warnings
from pathlib import Path

from ..model import Grid
from ..versions import TARGET_DATA_VERSION, TARGET_VERSION
from . import litematic, schem, structure_nbt

_FORMATS = {".litematic": litematic, ".schem": schem, ".nbt": structure_nbt}


class DataVersionWarning(UserWarning):
    pass


def _module(path: Path):
    try:
        return _FORMATS[path.suffix.lower()]
    except KeyError:
        raise ValueError(f"unsupported schematic format {path.suffix!r} (expected one of {sorted(_FORMATS)})")


def load(path: str | Path) -> Grid:
    path = Path(path)
    grid = _module(path).read(path)
    if not grid.meta.name:
        grid.meta.name = path.stem
    dv = grid.meta.data_version
    if dv is not None and dv != TARGET_DATA_VERSION:
        warnings.warn(
            f"{path.name}: DataVersion {dv} differs from target {TARGET_DATA_VERSION} (Java {TARGET_VERSION}); "
            "block states may differ slightly",
            DataVersionWarning,
            stacklevel=2,
        )
    return grid


def save(grid: Grid, path: str | Path) -> None:
    path = Path(path)
    _module(path).write(grid, path)


__all__ = ["DataVersionWarning", "load", "save"]
