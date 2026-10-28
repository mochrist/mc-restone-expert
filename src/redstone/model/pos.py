"""Block positions and directions (Minecraft Java coordinate conventions).

x grows to the east, y grows upwards, z grows to the south.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class Pos(NamedTuple):
    x: int
    y: int
    z: int

    def __add__(self, other: tuple[int, int, int]) -> Pos:  # type: ignore[override]
        return Pos(self.x + other[0], self.y + other[1], self.z + other[2])

    def __sub__(self, other: tuple[int, int, int]) -> Pos:
        return Pos(self.x - other[0], self.y - other[1], self.z - other[2])

    def offset(self, direction: Direction, n: int = 1) -> Pos:
        dx, dy, dz = direction.vec
        return Pos(self.x + dx * n, self.y + dy * n, self.z + dz * n)

    def __str__(self) -> str:
        return f"({self.x},{self.y},{self.z})"


class Direction(Enum):
    """The six directions in the declaration order of net.minecraft.core.Direction."""

    DOWN = ("down", (0, -1, 0))
    UP = ("up", (0, 1, 0))
    NORTH = ("north", (0, 0, -1))
    SOUTH = ("south", (0, 0, 1))
    WEST = ("west", (-1, 0, 0))
    EAST = ("east", (1, 0, 0))

    def __init__(self, label: str, vec: tuple[int, int, int]) -> None:
        self.label = label
        self.vec = vec

    @classmethod
    def from_name(cls, name: str) -> Direction:
        return _BY_NAME[name]

    @property
    def opposite(self) -> Direction:
        return _OPPOSITE[self]

    @property
    def is_horizontal(self) -> bool:
        return self.vec[1] == 0

    def clockwise(self) -> Direction:
        """Rotate around the y axis, seen from above (north -> east -> south -> west)."""
        return _CLOCKWISE[self]

    def counter_clockwise(self) -> Direction:
        return _CLOCKWISE_INV[self]

    def __str__(self) -> str:
        return self.label


_BY_NAME = {d.label: d for d in Direction}
_OPPOSITE = {
    Direction.DOWN: Direction.UP,
    Direction.UP: Direction.DOWN,
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.WEST: Direction.EAST,
    Direction.EAST: Direction.WEST,
}
_CLOCKWISE = {
    Direction.NORTH: Direction.EAST,
    Direction.EAST: Direction.SOUTH,
    Direction.SOUTH: Direction.WEST,
    Direction.WEST: Direction.NORTH,
}
_CLOCKWISE_INV = {v: k for k, v in _CLOCKWISE.items()}

HORIZONTALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
