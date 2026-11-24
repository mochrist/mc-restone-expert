"""Sparse 3D grid of block states: the internal representation of a schematic."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .blockstate import AIR, BlockState
from .pos import Pos


@dataclass
class SchematicMeta:
    name: str = ""
    author: str = ""
    description: str = ""
    data_version: int | None = None
    source_format: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Grid:
    """Blocks inside the box ``[0, size)`` on each axis. Air is not stored.

    Block entities are kept as plain dicts (converted from NBT) keyed by position,
    without the position fields themselves.
    """

    def __init__(self, size: tuple[int, int, int], meta: SchematicMeta | None = None) -> None:
        if any(s <= 0 for s in size):
            raise ValueError(f"grid size must be positive, got {size}")
        self.size = Pos(*size)
        self.meta = meta or SchematicMeta()
        self._blocks: dict[Pos, BlockState] = {}
        self._order: list[Pos] | None = None  # positions in items() order, until a block is added or removed
        self.block_entities: dict[Pos, dict[str, Any]] = {}

    def in_bounds(self, pos: tuple[int, int, int]) -> bool:
        return all(0 <= p < s for p, s in zip(pos, self.size))

    def get(self, pos: tuple[int, int, int]) -> BlockState:
        return self._blocks.get(Pos(*pos), AIR)

    def __getitem__(self, pos: tuple[int, int, int]) -> BlockState:
        return self.get(pos)

    def set(self, pos: tuple[int, int, int], state: BlockState | str) -> None:
        pos = Pos(*pos)
        if not self.in_bounds(pos):
            raise IndexError(f"{pos} outside grid of size {tuple(self.size)}")
        if isinstance(state, str):
            state = BlockState.parse(state)
        if state.is_air:
            if self._blocks.pop(pos, None) is not None:
                self._order = None
            self.block_entities.pop(pos, None)
        else:
            if pos not in self._blocks:
                self._order = None
            self._blocks[pos] = state

    def __setitem__(self, pos: tuple[int, int, int], state: BlockState | str) -> None:
        self.set(pos, state)

    def items(self) -> Iterator[tuple[Pos, BlockState]]:
        """Non-air blocks in y, z, x order (the iteration order of the file formats)."""
        order = self._order
        if order is None:  # sorting every call cost more than the searches using it (Task 13)
            order = self._order = sorted(self._blocks, key=lambda p: (p.y, p.z, p.x))
        blocks = self._blocks
        for pos in order:
            yield pos, blocks[pos]

    def positions(self):
        """Positions of the non-air blocks, in no particular order (a live view: do not change the grid while
        iterating)."""
        return self._blocks.keys()

    def __len__(self) -> int:
        return len(self._blocks)

    @property
    def volume(self) -> int:
        return self.size.x * self.size.y * self.size.z

    def palette(self) -> list[BlockState]:
        """Distinct states, air first, then in order of first appearance."""
        seen: dict[BlockState, None] = {AIR: None}
        for _, state in self.items():
            seen.setdefault(state, None)
        return list(seen)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Grid):
            return NotImplemented
        return (
            self.size == other.size
            and self._blocks == other._blocks
            and self.block_entities == other.block_entities
        )

    def __repr__(self) -> str:
        return f"Grid(size={tuple(self.size)}, blocks={len(self)})"
