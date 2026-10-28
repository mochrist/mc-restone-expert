"""Helpers around nbtlib: NBT <-> plain Python values, and packed block-index arrays."""

from __future__ import annotations

from typing import Any

import nbtlib
from nbtlib import tag

from ..model import BlockState


def to_py(value: Any) -> Any:
    """Convert nbtlib tags into plain Python values (dict, list, int, float, str).

    Typed arrays become lists. The NBT type information is lost, which is fine for
    the block-entity data we only need to read (comparator output, container items).
    Writers use :func:`to_nbt` with heuristics, or keep the original tag if available.
    """
    if isinstance(value, tag.Compound):
        return {str(k): to_py(v) for k, v in value.items()}
    if isinstance(value, (tag.List, tag.ByteArray, tag.IntArray, tag.LongArray)):
        return [to_py(v) for v in value]
    if isinstance(value, tag.String):
        return str(value)
    if isinstance(value, (tag.Float, tag.Double)):
        return float(value)
    if isinstance(value, (tag.Byte, tag.Short, tag.Int, tag.Long)):
        return int(value)
    return value


def to_nbt(value: Any) -> Any:
    """Best-effort conversion of plain Python values into NBT tags."""
    if isinstance(value, tag.Base):
        return value
    if isinstance(value, dict):
        return tag.Compound({k: to_nbt(v) for k, v in value.items()})
    if isinstance(value, list):
        if not value:
            return tag.List[tag.Compound]()
        items = [to_nbt(v) for v in value]
        return tag.List[type(items[0])](items)
    if isinstance(value, bool):
        return tag.Byte(int(value))
    if isinstance(value, int):
        return tag.Int(value)
    if isinstance(value, float):
        return tag.Double(value)
    if isinstance(value, str):
        return tag.String(value)
    raise TypeError(f"cannot convert {type(value).__name__} to NBT")


def state_from_compound(entry: tag.Compound) -> BlockState:
    """Palette entry of the form ``{Name: "...", Properties: {...}}``."""
    props = entry.get("Properties") or {}
    return BlockState.of(str(entry["Name"]), {str(k): str(v) for k, v in props.items()})


def state_to_compound(state: BlockState) -> tag.Compound:
    entry = tag.Compound({"Name": tag.String(state.name)})
    if state.props:
        entry["Properties"] = tag.Compound({k: tag.String(v) for k, v in state.props})
    return entry


def load(path: str) -> nbtlib.File:
    return nbtlib.load(str(path))


def bits_for_palette(size: int, minimum: int) -> int:
    return max(minimum, (size - 1).bit_length())


def unpack_tight(longs: list[int], bits: int, count: int) -> list[int]:
    """Values packed back to back across 64-bit longs (Litematica's LitematicaBitArray)."""
    mask = (1 << bits) - 1
    data = [v & 0xFFFFFFFFFFFFFFFF for v in longs]
    out = []
    for i in range(count):
        start_bit = i * bits
        idx, offset = divmod(start_bit, 64)
        value = data[idx] >> offset
        if offset + bits > 64:
            value |= data[idx + 1] << (64 - offset)
        out.append(value & mask)
    return out


def pack_tight(values: list[int], bits: int) -> list[int]:
    n_longs = (len(values) * bits + 63) // 64
    data = [0] * n_longs
    for i, value in enumerate(values):
        start_bit = i * bits
        idx, offset = divmod(start_bit, 64)
        data[idx] |= (value << offset) & 0xFFFFFFFFFFFFFFFF
        if offset + bits > 64:
            data[idx + 1] |= value >> (64 - offset)
    return [v - (1 << 64) if v >= (1 << 63) else v for v in data]


def decode_varints(data: bytes | list[int], count: int) -> list[int]:
    raw = bytes(b & 0xFF for b in data)
    out = []
    i = 0
    while len(out) < count:
        value = 0
        shift = 0
        while True:
            if i >= len(raw):
                raise ValueError("truncated varint data")
            b = raw[i]
            i += 1
            value |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
        out.append(value)
    return out


def encode_varints(values: list[int]) -> bytes:
    out = bytearray()
    for value in values:
        while value >= 0x80:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value)
    return bytes(out)
