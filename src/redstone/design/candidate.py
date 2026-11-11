"""A candidate circuit: a grid plus the positions of its inputs and outputs.

Inputs are levers (stored off). Outputs are blocks whose on/off state is read (usually redstone lamps).
The order of `inputs` and `outputs` matches the names in the specification (a, b, c, ... / y, z, ...).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..model import Grid, Pos

SEP = "/"  # between the levels of a label: "0/1" is part 1 of part 0
LINE = "~"  # the last level of a line label starts with this: "~0", "0/~1"


def is_line(label: str) -> bool:
    return label.rsplit(SEP, 1)[-1].startswith(LINE)


def nested(prefix: str, label: str) -> str:
    return f"{prefix}{SEP}{label}" if label else prefix


def under(label: str, prefix: str) -> bool:
    """label is prefix itself or lies inside it."""
    return label == prefix or label.startswith(prefix + SEP)


@dataclass
class Assembly:
    """Which building block of a composition every block belongs to (`compose`, `decompose`), so that
    compaction can move and turn the parts on their own (`compact.parts`), also where they touch.

    labels: block position -> label. Parts are labelled by their path in the composition ("0" drives "1";
    "0/1" is part 1 inside part 0, so nested compositions keep their labels). The dust and repeaters of a
    line between two parts, and the floors laid for them, carry the line's label ("~0", or "0/~0" inside
    part 0). Blocks without a label are taken to belong to whatever they touch.
    ends: line label -> (block the line starts at, in the driving part; block it ends at, in the driven
    part). The cells of a line lead from the first end to the second."""

    labels: dict[Pos, str] = field(default_factory=dict)
    ends: dict[str, tuple[Pos, Pos]] = field(default_factory=dict)

    @staticmethod
    def of(c: Candidate, prefix: str) -> Assembly:
        """The labels of c below `prefix` (all of c labelled `prefix` when it has no assembly)."""
        if c.assembly is None:
            return Assembly({p: prefix for p, _ in c.grid.items()}, {})
        a = c.assembly
        return Assembly({p: nested(prefix, lab) for p, lab in a.labels.items()},
                        {nested(prefix, k): v for k, v in a.ends.items()})

    def mapped(self, move: Callable[[Pos], Pos | None]) -> Assembly:
        """Labels at move(p); move returns None for removed blocks. Where two blocks land on one cell, a part
        label beats a line label (equal blocks merged by a shift). A line whose end is gone is forgotten (its
        cells then count as unlabelled)."""
        labels: dict[Pos, str] = {}
        for p in sorted(self.labels):
            q = move(p)
            if q is None:
                continue
            old = labels.get(q)
            new = self.labels[p]
            if old is None or (is_line(old) and not is_line(new)):
                labels[q] = new
        ends = {}
        for k, (a, b) in self.ends.items():
            qa, qb = move(a), move(b)
            if qa is not None and qb is not None:
                ends[k] = (qa, qb)
        return Assembly(labels, ends)

    def shifted(self, v: Pos) -> Assembly:
        return self.mapped(lambda p: p + v)

    def merged(self, other: Assembly) -> Assembly:
        labels = dict(self.labels)
        labels.update(other.labels)
        return Assembly(labels, self.ends | other.ends)

    def kept(self, grid: Grid) -> Assembly:
        """Only the labels of blocks still in the grid."""
        return Assembly({p: lab for p, lab in self.labels.items() if not grid.get(p).is_air}, dict(self.ends))

    def next_line(self) -> str:
        """An unused top-level line label."""
        k = 0
        while f"{LINE}{k}" in self.ends:
            k += 1
        return f"{LINE}{k}"


@dataclass
class Candidate:
    name: str
    grid: Grid
    inputs: list[Pos]
    outputs: list[Pos]
    description: str = ""  # German, shown to the user
    origin: str = ""  # e.g. "template:and-torch", "search"
    tags: set[str] = field(default_factory=set)  # e.g. {"qc"} when the design relies on quasi-connectivity
    assembly: Assembly | None = None  # parts of a composition (None: a single building block)

    @property
    def size(self) -> tuple[int, int, int]:
        return tuple(self.grid.size)

    @property
    def volume(self) -> int:
        x, y, z = self.grid.size
        return x * y * z

    @property
    def block_count(self) -> int:
        return len(self.grid)

    def moved_assembly(self, move: Callable[[Pos], Pos | None]) -> Assembly | None:
        return None if self.assembly is None else self.assembly.mapped(move)
