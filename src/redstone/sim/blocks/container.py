"""Containers as comparator inputs (AbstractContainerMenu#getRedstoneSignalFromContainer).

Only the analog output is modeled; item transfer (hoppers, droppers) is not.
"""

from __future__ import annotations

import math

from ..block import REGISTRY, Block

# ASSUMPTION: max stack size 64 for every item (16-stackers and unstackables are not distinguished yet).
DEFAULT_MAX_STACK = 64


class ContainerBlockEntity:
    ticks = False

    def __init__(self, size: int) -> None:
        self.size = size
        self.items: dict[int, tuple[str, int]] = {}
        self.removed = False

    def load(self, data: dict) -> None:
        self.items = {}
        for item in data.get("Items", []):
            self.items[int(item.get("Slot", 0))] = (str(item.get("id", "")), int(item.get("count", 1)))

    def redstone_signal(self) -> int:
        if not self.size:
            return 0
        fullness = sum(min(count, DEFAULT_MAX_STACK) / DEFAULT_MAX_STACK for _, count in self.items.values())
        fullness /= self.size
        # Mth.lerpDiscrete(fullness, 0, 15) = floor(f * 14) + (f > 0 ? 1 : 0)
        return math.floor(fullness * 14) + (1 if fullness > 0 else 0)


class ContainerBlock(Block):
    def __init__(self, size: int) -> None:
        super().__init__()
        self.size = size

    def has_block_entity(self, state):
        return True

    def new_block_entity(self, pos, state):
        return ContainerBlockEntity(self.size)

    def has_analog_output_signal(self, state):
        return True

    def get_analog_output_signal(self, world, pos, state, direction):
        be = world.block_entities.get(pos)
        return be.redstone_signal() if isinstance(be, ContainerBlockEntity) else 0


REGISTRY.register(ContainerBlock(27), "barrel")
