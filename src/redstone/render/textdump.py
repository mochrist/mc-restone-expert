"""Layer-by-layer text view of a grid.

Each Y layer is printed as seen from above: north is up, east is right.
Directional components use a glyph that points in the direction their output goes.
Every symbol that appears is listed in a legend below the layers.
"""

from __future__ import annotations

import string

from ..model import BlockState, Direction, Grid

# ASSUMPTION (knowledge/components/repeater.md): for repeaters and comparators `facing`
# points towards the input side; observers face the side they watch. In all three cases
# the output leaves on the opposite side.
_FACING_IS_INPUT = {"repeater", "comparator", "observer"}

_DIRECTIONAL = {
    #               north south west east up down
    "repeater":   ("^", "v", "<", ">", None, None),
    "comparator": ("A", "V", "{", "}", None, None),
    "observer":   ("↑", "↓", "←", "→", "⇑", "⇓"),
    "piston":        ("p", "p", "p", "p", "p", "p"),
    "sticky_piston": ("P", "P", "P", "P", "P", "P"),
}
_DIR_INDEX = {Direction.NORTH: 0, Direction.SOUTH: 1, Direction.WEST: 2, Direction.EAST: 3,
              Direction.UP: 4, Direction.DOWN: 5}

_FIXED = {
    "redstone_wire": "+",
    "redstone_torch": "*",
    "redstone_wall_torch": "*",
    "redstone_block": "R",
    "lever": "L",
    "redstone_lamp": "O",
    "target": "T",
    "piston_head": "=",
    "moving_piston": "~",
    "slime_block": "S",
    "honey_block": "Y",
    "hopper": "H",
    "dropper": "d",
    "dispenser": "D",
    "note_block": "n",
    "glass": "g",
}
_SOLID = "#"
_NON_SOLID_HINTS = ("slab", "stairs", "glass", "pane", "fence", "wall", "door", "button", "pressure_plate",
                    "rail", "carpet", "torch", "sign", "leaves", "ladder", "vine", "water", "lava", "bars",
                    "chain", "candle", "head", "skull", "flower", "sapling", "lantern", "chest", "barrel",
                    "sensor", "detector", "lectern", "rod", "bell", "button")
_RESERVED = set("".join(t for row in _DIRECTIONAL.values() for t in row if t)) | set(_FIXED.values()) | {_SOLID, "."}


def _output_direction(state: BlockState) -> Direction | None:
    facing = state.get("facing")
    if facing is None:
        return None
    d = Direction.from_name(facing)
    return d.opposite if state.id in _FACING_IS_INPUT else d


def _looks_full_solid(name: str) -> bool:
    # Display heuristic only; the simulator uses a proper block registry.
    return not any(h in name for h in _NON_SOLID_HINTS)


class _Symbols:
    def __init__(self) -> None:
        self.legend: dict[str, str] = {}  # symbol -> description
        self._by_name: dict[str, str] = {}
        self._free = (c for c in string.ascii_lowercase + string.ascii_uppercase + "0123456789&%$@!?"
                      if c not in _RESERVED)

    def __call__(self, state: BlockState) -> str:
        name = state.id
        if name in _DIRECTIONAL:
            d = _output_direction(state)
            sym = _DIRECTIONAL[name][_DIR_INDEX[d]] if d else "?"
            label = f"{name}, output {d}" if name in _FACING_IS_INPUT else f"{name}, facing {d}"
            self.legend.setdefault(sym, label if name in _FACING_IS_INPUT else name)
            return sym or "?"
        if name in _FIXED:
            sym = _FIXED[name]
            self.legend.setdefault(sym, name)
            return sym
        if _looks_full_solid(name):
            self.legend.setdefault(_SOLID, "full block (any solid)")
            return _SOLID
        if name not in self._by_name:
            self._by_name[name] = next(self._free, "?")
            self.legend.setdefault(self._by_name[name], name)
        return self._by_name[name]


def render(grid: Grid, layers: list[int] | None = None, components: bool = False) -> str:
    symbols = _Symbols()
    sx, sy, sz = grid.size
    out = [f"{grid.meta.name or 'schematic'}  size x={sx} y={sy} z={sz}  blocks={len(grid)}"]
    ruler = "     " + "".join(str(x % 10) for x in range(sx))
    for y in layers if layers is not None else range(sy):
        rows = []
        for z in range(sz):
            cells = (grid.get((x, y, z)) for x in range(sx))
            rows.append(f"{z:>4} " + "".join("." if s.is_air else symbols(s) for s in cells))
        if all(set(r[5:]) == {"."} for r in rows):
            out.append(f"\ny={y}: empty")
            continue
        out += [f"\ny={y}  (north up, east right; rows are z, columns are x)", ruler, *rows]
    out.append("\nLegend:")
    out += [f"  {sym}  {desc}" for sym, desc in sorted(symbols.legend.items())]
    if components:
        out.append("\nComponents (blocks with state properties):")
        out += [f"  {pos}  {state}" for pos, state in grid.items()
                if state.props and (layers is None or pos.y in layers)]
    return "\n".join(out)
