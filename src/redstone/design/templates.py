"""Library of compact, simulator-verified logic gate templates (milestone M4).

Delays in the descriptions are from lever to lamp turning on; a lamp turns off 4 gt later than its input.

Every template builds a `Candidate`: levers (stored off) as inputs, redstone lamps as outputs. Layouts are written
down as block lists; `_settle` then runs the simulator once from that layout and stores the settled block states
(torch `lit`, dust `power`, lamp `lit`, comparator output), so a loaded schematic is already at rest with all
levers off. tests/design/test_templates.py checks truth table, every single-lever transition and the idle state.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache

from ..model import BlockState, Grid, Pos
from .candidate import Candidate


@dataclass(frozen=True)
class Template:
    name: str  # kebab-case, unique, e.g. "and2-torch"
    inputs: tuple[str, ...]  # ("a", "b")
    outputs: tuple[str, ...]  # ("y",)
    function: dict[str, str]  # output -> Python bool expression over the inputs, e.g. {"y": "a and not b"}
    description: str  # German, 1-2 sentences: construction, delay
    build: Callable[[], Candidate] = field(compare=False)  # builds a fresh Candidate
    tags: frozenset[str] = frozenset()  # e.g. {"qc"} if the design relies on quasi-connectivity

    def evaluate(self, values: dict[str, bool]) -> dict[str, bool]:
        """Expected output values for the given input values."""
        return {out: bool(eval(expr, {"__builtins__": {}}, dict(values))) for out, expr in self.function.items()}


# ---------------------------------------------------------------------------------------------- block shorthands
STONE = "stone"
GLASS = "glass"  # sturdy top for dust, but not a conductor: never powered
LAMP = "redstone_lamp[lit=false]"
WIRE = "redstone_wire[east=side,north=side,power=0,south=side,west=side]"  # shape is recomputed in _settle
TORCH = "redstone_torch[lit=true]"


def LEVER(facing: str = "north") -> str:
    return f"lever[face=floor,facing={facing},powered=false]"


def WALL_TORCH(facing: str) -> str:
    """Wall torch whose `facing` points away from the block it hangs on."""
    return f"redstone_wall_torch[facing={facing},lit=true]"


def REPEATER(facing: str, delay: int = 1) -> str:
    """Repeater reading from the `facing` side and powering the opposite side."""
    return f"repeater[delay={delay},facing={facing},locked=false,powered=false]"


def COMPARATOR(facing: str, mode: str = "subtract") -> str:
    """Comparator reading its rear from the `facing` side and powering the opposite side."""
    return f"comparator[facing={facing},mode={mode},powered=false]"


Xyz = tuple[int, int, int]


@dataclass(frozen=True)
class _Layout:
    blocks: dict[Xyz, str]
    inputs: tuple[Xyz, ...]
    outputs: tuple[Xyz, ...]


def _grid_from_layout(layout: _Layout) -> tuple[Grid, list[Pos], list[Pos]]:
    lo = [min(p[i] for p in layout.blocks) for i in range(3)]
    hi = [max(p[i] for p in layout.blocks) for i in range(3)]
    shift = Pos(*lo)
    grid = Grid(tuple(h - l + 1 for l, h in zip(lo, hi)))
    for p, state in layout.blocks.items():
        grid.set(Pos(*p) - shift, state)
    for p in layout.inputs + layout.outputs:
        if p not in layout.blocks:
            raise ValueError(f"port {p} has no block")
    return grid, [Pos(*p) - shift for p in layout.inputs], [Pos(*p) - shift for p in layout.outputs]


def _settle(grid: Grid) -> Grid:
    """Run the simulator from the written layout and return the grid with the settled block states.

    Dust shapes are first computed as if the dust had been placed by a player; then every block gets one
    neighbour update (like `Circuit.new_world(kick=True)`) and the world runs until it is idle."""
    import nbtlib

    from ..analysis.experiment import Circuit
    from ..sim.constants import UPDATE_ALL
    from ..sim.runner import ORACLE_ORIGIN
    from ..sim.core import World

    origin = ORACLE_ORIGIN
    world = World()
    world.place_grid(grid, origin)
    wires = [p + origin for p, s in grid.items() if s.id == "redstone_wire"]
    for _ in range(2):
        for p in wires:
            block = world.block(world.get(p))
            assert block.name == "minecraft:redstone_wire"
            world.blocks[p] = block.get_connection_state(world, block.cross_state(0), p)
    positions = [p + origin for p, _ in grid.items()]
    for p in positions:
        state = world.get(p)
        world.neighbor_changed_with_state(state, p, world.block(state), False)
    for p in positions:
        world.update_neighbour_shapes(p, world.get(p), UPDATE_ALL)
    rec = Circuit(grid, origin).run([], max_ticks=400, quiet=12, world=world)
    if rec.settled_at is None:
        raise RuntimeError("template does not come to rest without input")
    out = Grid(tuple(grid.size), copy.deepcopy(grid.meta))
    for p, old in grid.items():
        new = world.get(p + origin)
        if new.name != old.name:
            raise RuntimeError(f"{old} at {p} became {new} while settling")
        out.set(p, new)
        if new.id == "comparator":
            be = world.block_entities.get(p + origin)
            out.block_entities[p] = nbtlib.Compound({
                "id": nbtlib.String("minecraft:comparator"),
                "OutputSignal": nbtlib.Int(be.output_signal if be is not None else 0),
            })
    return out


def _copy_grid(grid: Grid) -> Grid:
    out = Grid(tuple(grid.size), copy.deepcopy(grid.meta))
    for p, s in grid.items():
        out.set(p, s)
    out.block_entities = copy.deepcopy(grid.block_entities)
    return out


TEMPLATES: list[Template] = []


def _register(name: str, inputs: str, outputs: str, function: dict[str, str], description: str,
              layout: Callable[[], _Layout], tags: frozenset[str] = frozenset()) -> None:
    @cache
    def settled() -> tuple[Grid, list[Pos], list[Pos]]:
        grid, ins, outs = _grid_from_layout(layout())
        grid.meta.name = name
        grid.meta.description = description
        return _settle(grid), ins, outs

    def build() -> Candidate:
        grid, ins, outs = settled()
        return Candidate(name=name, grid=_copy_grid(grid), inputs=list(ins), outputs=list(outs),
                         description=description, origin=f"template:{name}", tags=set(tags))

    TEMPLATES.append(Template(name, tuple(inputs.split()), tuple(outputs.split()), function, description, build,
                              frozenset(tags)))


def templates_for(n_inputs: int, n_outputs: int) -> list[Template]:
    return [t for t in TEMPLATES if len(t.inputs) == n_inputs and len(t.outputs) == n_outputs]


# =============================================================================================== templates
# Coordinates: x east, y up, z south. Layouts may use any offset; the grid is cropped to the blocks.

# --- buffer -------------------------------------------------------------------------------------------------
_register(
    "buffer-direct", "a", "y", {"y": "a"},
    "Hebel direkt auf der Lampe; der Hebel versorgt den Block, an dem er hängt. Verzögerung 0 gt.",
    lambda: _Layout({(0, 0, 0): LAMP, (0, 1, 0): LEVER()}, ((0, 1, 0),), ((0, 0, 0),)))

_register(
    "buffer-dust", "a", "y", {"y": "a"},
    "Hebel, ein Redstone-Staub, Lampe in einer Reihe. Verzögerung 0 gt.",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER("east"), (1, 0, 0): STONE, (1, 1, 0): WIRE,
                     (2, 1, 0): LAMP}, ((0, 1, 0),), ((2, 1, 0),)))

_register(
    "buffer-repeater", "a", "y", {"y": "a"},
    "Hebel, Verstärker (Stufe 1), Lampe in einer Reihe. Verzögerung 2 gt.",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER("east"), (1, 0, 0): STONE, (1, 1, 0): REPEATER("west"),
                     (2, 1, 0): LAMP}, ((0, 1, 0),), ((2, 1, 0),)))

# --- not ------------------------------------------------------------------------------------------------------
_register(
    "not-torch", "a", "y", {"y": "not a"},
    "Hebel auf einem Block, daran eine Wandfackel, daneben die Lampe. Verzögerung 2 gt (Fackel).",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER(), (1, 0, 0): WALL_TORCH("east"), (2, 0, 0): LAMP},
                    ((0, 1, 0),), ((2, 0, 0),)))

_register(
    "not-torch-below", "a", "y", {"y": "not a"},
    "Hebel auf einem Block, daran eine Wandfackel, die Lampe direkt unter der Fackel. Verzögerung 2 gt (Fackel).",
    lambda: _Layout({(0, 1, 0): STONE, (0, 2, 0): LEVER(), (1, 1, 0): WALL_TORCH("east"), (1, 0, 0): LAMP},
                    ((0, 2, 0),), ((1, 0, 0),)))

# --- or -------------------------------------------------------------------------------------------------------
_register(
    "or2-direct", "a b", "y", {"y": "a or b"},
    "Zwei Hebel direkt links und rechts neben der Lampe. Verzögerung 0 gt.",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER(), (1, 1, 0): LAMP, (2, 0, 0): STONE, (2, 1, 0): LEVER()},
                    ((0, 1, 0), (2, 1, 0)), ((1, 1, 0),)))

_register(
    "or2-stacked", "a b", "y", {"y": "a or b"},
    "Ein Hebel neben der Lampe, einer oben auf ihr. Verzögerung 0 gt.",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER(), (1, 1, 0): LAMP, (1, 2, 0): LEVER()},
                    ((0, 1, 0), (1, 2, 0)), ((1, 1, 0),)))

_register(
    "or3-direct", "a b c", "y", {"y": "a or b or c"},
    "Drei Hebel direkt an drei Seiten der Lampe. Verzögerung 0 gt.",
    lambda: _Layout({(0, 0, 1): STONE, (0, 1, 1): LEVER(), (2, 0, 1): STONE, (2, 1, 1): LEVER(),
                     (1, 0, 0): STONE, (1, 1, 0): LEVER(), (1, 1, 1): LAMP},
                    ((0, 1, 1), (1, 1, 0), (2, 1, 1)), ((1, 1, 1),)))

_register(
    "or3-stacked", "a b c", "y", {"y": "a or b or c"},
    "Zwei Hebel neben der Lampe, einer oben auf ihr. Verzögerung 0 gt.",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER(), (1, 1, 0): LAMP, (1, 2, 0): LEVER(),
                     (2, 0, 0): STONE, (2, 1, 0): LEVER()},
                    ((0, 1, 0), (1, 2, 0), (2, 1, 0)), ((1, 1, 0),)))

# --- nor ------------------------------------------------------------------------------------------------------
_register(
    "nor2-torch", "a b", "y", {"y": "not (a or b)"},
    "Zwei Hebel versorgen einen Staub auf einem Block, an dem eine Wandfackel hängt; die Lampe steht vor der "
    "Fackel. Verzögerung 2 gt (Fackel).",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER(), (1, 0, 0): STONE, (1, 1, 0): WIRE,
                     (2, 0, 0): STONE, (2, 1, 0): LEVER(), (1, 0, 1): WALL_TORCH("south"), (1, 0, 2): LAMP},
                    ((0, 1, 0), (2, 1, 0)), ((1, 0, 2),)))

_register(
    "nor2-torch-flat", "a b", "y", {"y": "not (a or b)"},
    "Ein Hebel auf dem Fackelblock, der andere speist ihn über einen Staub; Lampe unter der Wandfackel. "
    "Verzögerung 2 gt (Fackel).",
    lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER("east"), (1, 0, 0): STONE, (1, 1, 0): WIRE,
                     (2, 1, 0): STONE, (2, 2, 0): LEVER(), (3, 1, 0): WALL_TORCH("east"), (3, 0, 0): LAMP},
                    ((0, 1, 0), (2, 2, 0)), ((3, 0, 0),)))

# --- and ------------------------------------------------------------------------------------------------------
_register(
    "and2-torch", "a b", "y", {"y": "a and b"},
    "Klassisches Fackel-AND: Hebel auf zwei Blöcken, deren Wandfackeln einen Staub auf dem Ausgangsblock speisen; "
    "neben dessen Fackel steht die Lampe. Verzögerung 4 gt (zwei Fackeln).",
    lambda: _Layout({(0, 1, 0): STONE, (0, 2, 0): LEVER(), (2, 1, 0): STONE, (2, 2, 0): LEVER(),
                     (0, 1, 1): WALL_TORCH("south"), (2, 1, 1): WALL_TORCH("south"), (1, 1, 1): WIRE,
                     (1, 0, 1): STONE, (1, 0, 2): WALL_TORCH("south"), (0, 0, 2): LAMP},
                    ((0, 2, 0), (2, 2, 0)), ((0, 0, 2),)))

_register(
    "and2-torch-flat", "a b", "y", {"y": "a and b"},
    "Fackel-AND in einer Reihe: zwei Eingangsfackeln zeigen auf einen Staub zwischen ihnen, darunter der "
    "Ausgangsblock mit Fackel, daneben die Lampe. Verzögerung 4 gt (zwei Fackeln).",
    lambda: _Layout({(0, 1, 0): STONE, (0, 2, 0): LEVER(), (1, 1, 0): WALL_TORCH("east"), (2, 1, 0): WIRE,
                     (2, 0, 0): STONE, (3, 1, 0): WALL_TORCH("west"), (4, 1, 0): STONE, (4, 2, 0): LEVER(),
                     (2, 0, 1): WALL_TORCH("south"), (1, 0, 1): LAMP},
                    ((0, 2, 0), (4, 2, 0)), ((1, 0, 1),)))

_register(
    "and3-torch", "a b c", "y", {"y": "a and b and c"},
    "Fackel-AND mit drei Eingangsfackeln um einen Staub auf dem Ausgangsblock; dessen Fackel speist die Lampe. "
    "Verzögerung 4 gt (zwei Fackeln).",
    lambda: _Layout({(0, 1, 0): STONE, (0, 2, 0): LEVER(), (2, 1, 0): STONE, (2, 2, 0): LEVER(),
                     (1, 1, 3): STONE, (1, 2, 3): LEVER(),
                     (0, 1, 1): WALL_TORCH("south"), (2, 1, 1): WALL_TORCH("south"), (1, 1, 2): WALL_TORCH("north"),
                     (1, 1, 1): WIRE, (1, 0, 1): STONE, (1, 0, 2): WALL_TORCH("south"), (0, 0, 2): LAMP},
                    ((0, 2, 0), (2, 2, 0), (1, 2, 3)), ((0, 0, 2),)))

# --- nand -----------------------------------------------------------------------------------------------------
_register(
    "nand2-torch", "a b", "y", {"y": "not (a and b)"},
    "Zwei Fackel-Inverter links und rechts an der Lampe. Verzögerung 2 gt (Fackel).",
    lambda: _Layout({(0, 1, 0): STONE, (0, 2, 0): LEVER(), (1, 1, 0): WALL_TORCH("east"), (2, 1, 0): LAMP,
                     (3, 1, 0): WALL_TORCH("west"), (4, 1, 0): STONE, (4, 2, 0): LEVER()},
                    ((0, 2, 0), (4, 2, 0)), ((2, 1, 0),)))

_register(
    "nand2-torch-corner", "a b", "y", {"y": "not (a and b)"},
    "Zwei Fackel-Inverter über Eck an der Lampe. Verzögerung 2 gt (Fackel).",
    lambda: _Layout({(0, 1, 0): STONE, (0, 2, 0): LEVER(), (1, 1, 0): WALL_TORCH("east"), (2, 1, 0): LAMP,
                     (2, 1, 1): WALL_TORCH("north"), (2, 1, 2): STONE, (2, 2, 2): LEVER()},
                    ((0, 2, 0), (2, 2, 2)), ((2, 1, 0),)))

# --- inhibit (a and not b) ------------------------------------------------------------------------------------
_register(
    "a-and-not-b-torch", "a b", "y", {"y": "a and not b"},
    "Fackel unter dem Ausgangsblock invertiert a, Hebel b sitzt auf dem Ausgangsblock; dessen Wandfackel speist "
    "die Lampe. Verzögerung 4 gt (a), 2 gt (b).",
    lambda: _Layout({(0, 1, 0): STONE, (0, 2, 0): LEVER(), (1, 1, 0): WALL_TORCH("east"), (1, 2, 0): STONE,
                     (1, 3, 0): LEVER(), (2, 2, 0): WALL_TORCH("east"), (3, 2, 0): LAMP},
                    ((0, 2, 0), (1, 3, 0)), ((3, 2, 0),)))

_register(
    "a-and-not-b-comparator", "a b", "y", {"y": "a and not b"},
    "Komparator im Subtraktionsmodus: a direkt am Rückeingang, b über einen Staub am Seiteneingang. "
    "Verzögerung 2 gt (Komparator).",
    lambda: _Layout({(0, 0, 1): STONE, (0, 1, 1): LEVER(), (1, 0, 1): STONE, (1, 1, 1): COMPARATOR("west"),
                     (2, 1, 1): LAMP, (1, 0, 0): STONE, (1, 1, 0): WIRE, (1, 0, -1): STONE, (1, 1, -1): LEVER()},
                    ((0, 1, 1), (1, 1, -1)), ((2, 1, 1),)))


def _supported(blocks: dict[Xyz, str], support: str = STONE) -> dict[Xyz, str]:
    """Add a support block under every block of the layout that needs one and has air below."""
    out = dict(blocks)
    for (x, y, z), state in blocks.items():
        name = BlockState.parse(state).id
        if name in {"redstone_wire", "repeater", "comparator", "lever", "redstone_torch"} and (x, y - 1, z) not in out:
            out[(x, y - 1, z)] = support
    return out


# --- multiplexer ----------------------------------------------------------------------------------------------
def _mux2() -> _Layout:
    return _Layout(_supported({
        (0, 0, 1): LEVER(), (1, 0, 1): COMPARATOR("west"), (2, 0, 1): LAMP, (3, 0, 1): COMPARATOR("east"),
        (4, 0, 1): LEVER(),
        (1, 0, -1): LEVER(), (1, 0, 0): WIRE,  # s, straight into the side of the a comparator
        (2, -1, -1): WALL_TORCH("east"), (2, 0, -1): STONE,  # not s: torch on the lever block powers K
        (3, 0, -1): WIRE, (3, 0, 0): REPEATER("north"),  # K -> dust -> repeater (full strength) -> b comparator
    }), ((1, 0, -1), (0, 0, 1), (4, 0, 1)), ((2, 0, 1),))


_register(
    "mux2-comparator", "s a b", "y", {"y": "(a and not s) or (b and s)"},
    "Zwei Komparatoren im Subtraktionsmodus zeigen auf die Lampe: a minus s und b minus (nicht s); nicht s kommt "
    "von einer Fackel am Block unter Hebel s über einen Verstärker. Verzögerung 2 gt (a, b), bis 6 gt (s).",
    _mux2)


# --- magnitude comparison ---------------------------------------------------------------------------------------
def _cmp1() -> _Layout:
    return _Layout(_supported({
        (0, 0, 0): LEVER(), (1, 0, 0): COMPARATOR("west"), (2, 0, 0): LAMP,  # a minus b -> gt
        (1, 0, 2): LEVER(), (0, 0, 2): COMPARATOR("east"), (-1, 0, 2): LAMP,  # b minus a -> lt
        (0, 0, 1): REPEATER("north"), (1, 0, 1): REPEATER("south"),  # each lever into the other's side
    }), ((0, 0, 0), (1, 0, 2)), ((2, 0, 0), (-1, 0, 2)))


_register(
    "cmp1-comparator", "a b", "gt lt", {"gt": "a and not b", "lt": "b and not a"},
    "1-Bit-Größenvergleich: zwei Komparatoren im Subtraktionsmodus (a minus b, b minus a), jeder Hebel am "
    "eigenen Rückeingang und über einen Verstärker am Seiteneingang des anderen. Verzögerung bis 4 gt.",
    _cmp1)


def _cmp_stage() -> _Layout:
    blocks = {
        # go: (a minus b, joined with gi on the dust D1) minus li; lo: (b minus a, joined with li on D2) minus gi.
        # Only the last comparator of each row lights its lamp, so the lamp is powered strongly.
        (0, 0, 0): LEVER(), (1, 0, 0): COMPARATOR("west"), (2, 0, 0): WIRE, (3, 0, 0): COMPARATOR("west"),
        (4, 0, 0): LAMP,
        (1, 0, 2): LEVER(), (0, 0, 2): COMPARATOR("east"), (-1, 0, 2): WIRE, (-2, 0, 2): COMPARATOR("east"),
        (-3, 0, 2): LAMP,
        (0, 0, 1): REPEATER("north"), (1, 0, 1): REPEATER("south"),
        # li: row z=-2, over a repeater into the side of the go comparator, and down onto D2
        (-3, 0, -2): LEVER(), (3, 0, -1): REPEATER("north"), (-1, 0, -1): WIRE, (-1, 0, 0): REPEATER("north"),
        (-1, 0, 1): WIRE,
        # gi: row z=4, over a repeater into the side of the lo comparator, and up onto D1
        (4, 0, 4): LEVER(), (-2, 0, 3): REPEATER("south"), (2, 0, 3): WIRE, (2, 0, 2): REPEATER("south"),
        (2, 0, 1): WIRE,
    }
    for x in range(-2, 4):
        blocks[(x, 0, -2)] = WIRE
        blocks[(x, 0, 4)] = WIRE
    return _Layout(_supported(blocks), ((4, 0, 4), (-3, 0, -2), (0, 0, 0), (1, 0, 2)), ((4, 0, 0), (-3, 0, 2)))


_register(
    "cmp-stage-comparator", "gi li a b", "go lo",
    {"go": "(gi or (a and not b)) and not li", "lo": "(li or (b and not a)) and not gi"},
    "Stufe eines Größenvergleichs (Kaskade, höhere Stelle zuerst): gi/li sagen „schon größer/kleiner“ (nie beide). "
    "a minus b und gi laufen auf einem Staub zusammen in einen Komparator, der li abzieht; ebenso b minus a, li "
    "und gi. Nur diese Komparatoren speisen die Lampen. Verzögerung bis 6 gt.",
    _cmp_stage)


# --- xor / xnor -----------------------------------------------------------------------------------------------
def _xor2() -> _Layout:
    return _Layout(_supported({
        (1, 0, 1): COMPARATOR("west"), (2, 0, 1): LAMP, (3, 0, 1): COMPARATOR("east"),
        # a: lever next to the side dust of the b comparator (full strength), long dust to the rear of the a one
        (3, 0, -1): LEVER(), (3, 0, 0): WIRE,
        (2, 0, -1): WIRE, (1, 0, -1): WIRE, (0, 0, -1): WIRE, (0, 0, 0): WIRE, (0, 0, 1): WIRE,
        # b: mirrored
        (1, 0, 3): LEVER(), (1, 0, 2): WIRE,
        (2, 0, 3): WIRE, (3, 0, 3): WIRE, (4, 0, 3): WIRE, (4, 0, 2): WIRE, (4, 0, 1): WIRE,
    }), ((3, 0, -1), (1, 0, 3)), ((2, 0, 1),))


_register(
    "xor2-comparator", "a b", "y", {"y": "a != b"},
    "Zwei Komparatoren im Subtraktionsmodus (a minus b, b minus a) zeigen auf die Lampe. Jeder Hebel liegt am "
    "Seiteneingang des fremden Komparators (volle Stärke) und erreicht den eigenen Rückeingang über eine "
    "längere Leitung. Verzögerung 2 gt.",
    _xor2)


def _xor2_repeater() -> _Layout:
    blocks = _supported({
        (0, 0, 0): LEVER(), (1, 0, 0): COMPARATOR("west"), (2, 0, 0): LAMP,  # a minus b -> lamp
        (1, 0, 2): LEVER(), (0, 0, 2): COMPARATOR("east"), (-1, 0, 2): STONE,  # b minus a -> block M
        (0, 0, 1): REPEATER("north"), (1, 0, 1): REPEATER("south"),  # each lever into the other's side
    })
    # M carries b minus a over the top to a dust on the lamp
    path = [(-1, 1, 2), (-1, 1, 1), (-1, 1, 0), (-1, 1, -1), (0, 1, -1), (1, 1, -1), (2, 1, -1), (2, 1, 0)]
    for x, y, z in path:
        blocks[(x, y, z)] = WIRE
        blocks.setdefault((x, y - 1, z), STONE)
    return _Layout(blocks, ((0, 0, 0), (1, 0, 2)), ((2, 0, 0),))


_register(
    "xor2-comparator-repeater", "a b", "y", {"y": "a != b"},
    "Zwei Komparatoren im Subtraktionsmodus, jeder Hebel direkt am eigenen Rückeingang und über einen Verstärker "
    "am Seiteneingang des anderen; b minus a läuft über eine Leitung oben herum auf die Lampe. Verzögerung bis 4 gt.",
    _xor2_repeater)


def _xnor2() -> _Layout:
    layout = _xor2()
    blocks = dict(layout.blocks)
    blocks[(2, 0, 1)] = STONE  # the comparators power this block instead of a lamp
    blocks[(2, 1, 1)] = TORCH
    blocks[(2, 1, 0)] = LAMP
    return _Layout(blocks, layout.inputs, ((2, 1, 0),))


_register(
    "xnor2-comparator", "a b", "y", {"y": "a == b"},
    "Wie xor2-comparator, die Komparatoren versorgen aber einen Block mit Fackel obendrauf; die Lampe steht "
    "neben der Fackel. Verzögerung 4 gt (Komparator + Fackel).",
    _xnor2)


def _xnor2_repeater() -> _Layout:
    layout = _xor2_repeater()
    blocks = dict(layout.blocks)
    blocks[(2, 0, 0)] = STONE  # comparator a minus b and the dust from b minus a power this block
    blocks[(3, 0, 0)] = WALL_TORCH("east")
    blocks[(3, -1, 0)] = LAMP
    return _Layout(blocks, layout.inputs, ((3, -1, 0),))


_register(
    "xnor2-comparator-repeater", "a b", "y", {"y": "a == b"},
    "Wie xor2-comparator-repeater, statt der Lampe ein Block mit Wandfackel; die Lampe hängt unter der Fackel. "
    "Verzögerung bis 6 gt.",
    _xnor2_repeater)


# --- half adder -----------------------------------------------------------------------------------------------
def _halfadder() -> _Layout:
    layout = _xor2()
    blocks = dict(layout.blocks)
    blocks.update(_supported({
        # carry = a minus (not b): a third comparator reads the end of the a line (strength 11) ...
        (-1, 0, 1): COMPARATOR("east"), (-2, 0, 1): LAMP,
        # ... and not b at strength 14 from a torch on the block under lever b
        (0, -1, 3): WALL_TORCH("west"), (0, 0, 3): STONE, (-1, 0, 3): WIRE, (-1, 0, 2): WIRE,
    }))
    return _Layout(blocks, layout.inputs, ((2, 0, 1), (-2, 0, 1)))


_register(
    "halfadder-comparator", "a b", "sum carry", {"sum": "a != b", "carry": "a and b"},
    "xor2-comparator für die Summe; der Übertrag ist ein dritter Komparator: Ende der a-Leitung minus (nicht b) "
    "von einer Fackel am Block unter Hebel b. Verzögerung 2 gt (Summe), bis 4 gt (Übertrag).",
    _halfadder)


# --- full adder -----------------------------------------------------------------------------------------------
def _mirror_x(state: str) -> str:
    """Block state mirrored at a plane x = const (east and west exchanged)."""
    swap = {"east": "west", "west": "east"}
    bs = BlockState.parse(state)
    props = dict(bs.props)
    if props.get("facing") in swap:
        props["facing"] = swap[props["facing"]]
    if "east" in props and "west" in props:
        props["east"], props["west"] = props["west"], props["east"]
    return str(BlockState.of(bs.name, props)).removeprefix("minecraft:")


# s1 line from the top of the first sum block to the a input of the second half adder (found by a small router,
# kept as data): dust on blocks one level up, a repeater restores full strength near the end
_FA_LINE = [(2, 1, 1), (1, 2, 1), (0, 2, 1), (-1, 2, 1), (-1, 2, 0), (-2, 2, 0), (-3, 2, 0), (-4, 2, 0), (-5, 2, 0),
            (-6, 2, 0), (-7, 2, 0), (-8, 2, 0), (-8, 1, -1)]
_FA_REPEATER = (-7, 2, 0)


def _fulladder() -> _Layout:
    ha = _halfadder()
    (la, lb), (sum1, carry1) = ha.inputs, ha.outputs
    blocks = dict(ha.blocks)
    blocks[sum1] = STONE  # s1 = a xor b: strongly powered block instead of the lamp
    mx = 2 * carry1[0]  # mirror plane through the carry lamp, which both half adders share
    for (x, y, z), state in ha.blocks.items():
        q = (mx - x, y, z)
        if q in blocks and q != carry1:
            raise AssertionError(f"full adder: half adders overlap at {q}")
        blocks[q] = _mirror_x(state)
    port = (mx - la[0], la[1], la[2])
    blocks[port] = WIRE  # second half adder: its a input is fed by the s1 line
    for p in _FA_LINE:
        blocks[p] = REPEATER("east") if p == _FA_REPEATER else WIRE
        blocks.setdefault((p[0], p[1] - 1, p[2]), STONE)
    cin = (mx - lb[0], lb[1], lb[2])
    total = (mx - sum1[0], sum1[1], sum1[2])
    return _Layout(blocks, (la, lb, cin), (total, carry1))


_register(
    "fulladder-comparator", "a b c", "sum carry", {"sum": "a ^ b ^ c", "carry": "(a and b) or (c and (a ^ b))"},
    "Zwei halfadder-comparator, gespiegelt, teilen sich die Übertrags-Lampe (Übertrag = c1 oder c2). Die Summe "
    "des ersten (a xor b) versorgt einen Block; von ihm führt eine Leitung über die Schaltung (eine Ebene höher, "
    "mit Verstärker) zum a-Eingang des zweiten Halbaddierers, dessen b-Eingang ist der Hebel c. "
    "Verzögerung bis 6 gt; 108 Blöcke statt 270 der Fackel-PLA.",
    _fulladder)
