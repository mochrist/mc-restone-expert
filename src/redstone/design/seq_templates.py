"""Library of simulator-verified building blocks with timing or memory (milestone M4).

Every template names a behaviour from `behaviour.CONSTRUCTORS` (monostable, pulse-extender, delay, t-flip-flop,
rs-latch, clock) and builds one `Candidate` per parametrisation together with the constructor parameters it
meets, e.g. `({"length": 8, "delay": 10}, candidate)`. Inputs are levers (`face=floor`, off) or stone buttons
(20 gt), the output is a redstone lamp where its 4-gt off delay does not hide the signal, otherwise the
component itself.

Non-clock layouts are stored in their settled state (`templates._settle`). Clocks are stored "frozen", as
schematics usually keep them: the world start with one update of every block (`Circuit.new_world(kick=True)`)
gets them running. tests/design/test_seq_templates.py evaluates every variant against its specification.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

from ..model import Grid, Pos
from .candidate import Candidate
from .templates import (COMPARATOR, LAMP, LEVER, REPEATER, STONE, TORCH, WALL_TORCH, WIRE, _copy_grid,
                        _grid_from_layout, _Layout, _settle, _supported)


@dataclass(frozen=True)
class SeqTemplate:
    name: str  # kebab-case, unique
    behaviour: str  # key in behaviour.CONSTRUCTORS
    inputs: tuple[str, ...]  # as in the constructor: ("in",), ("set", "reset") or ()
    input_kinds: tuple[str, ...]  # "lever" / "button"
    outputs: tuple[str, ...]  # ("out",)
    description: str  # German, construction
    variants: Callable[[], list[tuple[dict, Candidate]]]  # (constructor parameters, candidate) per parametrisation
    tags: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------------------------- block shorthands
BULB = "copper_bulb[lit=false,powered=false]"
REDSTONE_BLOCK = "redstone_block"


def BUTTON(facing: str = "north") -> str:
    return f"stone_button[face=floor,facing={facing},powered=false]"


def INPUT(kind: str, facing: str = "north") -> str:
    return BUTTON(facing) if kind == "button" else LEVER(facing)


def POWERED_REPEATER(facing: str, delay: int = 1) -> str:
    return f"repeater[delay={delay},facing={facing},locked=false,powered=true]"


def _support(blocks: dict) -> dict:
    """Stone under every component that needs a floor (buttons included)."""
    out = _supported(blocks)
    for (x, y, z), state in blocks.items():
        if state.startswith("stone_button") and (x, y - 1, z) not in out:
            out[(x, y - 1, z)] = STONE
    return out


def _shape_dust(grid: Grid) -> Grid:
    """Dust shapes as if placed by a player; all other states (power, lit, powered) stay as written."""
    import nbtlib

    from ..sim.blocks.wire import RedstoneWireBlock
    from ..sim.runner import ORACLE_ORIGIN
    from ..sim.world import World

    world = World()
    world.place_grid(grid, ORACLE_ORIGIN)
    wires = [p for p, s in grid.items() if s.id == "redstone_wire"]
    for _ in range(2):
        for p in wires:
            wp = p + ORACLE_ORIGIN
            block = world.block(world.get(wp))
            assert isinstance(block, RedstoneWireBlock)
            shaped = block.get_connection_state(world, block.cross_state(0), wp)
            world.blocks[wp] = shaped.with_(power=grid.get(p).get("power"))
    out = _copy_grid(grid)
    for p in wires:
        out.set(p, world.get(p + ORACLE_ORIGIN))
    for p, s in grid.items():
        if s.id == "comparator" and p not in out.block_entities:
            out.block_entities[p] = nbtlib.Compound({"id": nbtlib.String("minecraft:comparator"),
                                                     "OutputSignal": nbtlib.Int(0)})
    return out


SEQ_TEMPLATES: list[SeqTemplate] = []
Variant = tuple[dict, Callable[[], _Layout]]


def _register(name: str, behaviour: str, inputs: str, kinds: str, description: str, variants: list[Variant],
              settle: bool = True, tags: frozenset[str] = frozenset()) -> None:
    @cache
    def built(i: int) -> tuple[Grid, list[Pos], list[Pos]]:
        grid, ins, outs = _grid_from_layout(variants[i][1]())
        grid.meta.name = name
        grid.meta.description = description
        return (_settle(grid) if settle else _shape_dust(grid)), ins, outs

    def build_all() -> list[tuple[dict, Candidate]]:
        out = []
        for i, (params, _) in enumerate(variants):
            grid, ins, outs = built(i)
            label = ",".join(f"{k}={v}" for k, v in params.items() if k != "kind")
            out.append((dict(params), Candidate(
                name=f"{name}[{label}]", grid=_copy_grid(grid), inputs=list(ins), outputs=list(outs),
                description=description, origin=f"seq-template:{name}", tags=set(tags))))
        return out

    SEQ_TEMPLATES.append(SeqTemplate(name, behaviour, tuple(inputs.split()), tuple(kinds.split()), ("out",),
                                     description, build_all, frozenset(tags)))


def seq_templates_for(behaviour: str) -> list[SeqTemplate]:
    return [t for t in SEQ_TEMPLATES if t.behaviour == behaviour]


# =============================================================================================== templates
# Coordinates: x east, y up, z south. Components sit at y=1 on a stone floor added by _support.

# --- delay ----------------------------------------------------------------------------------------------------
def _repeater_line(n: int) -> _Layout:
    blocks = {(0, 1, 0): LEVER("east"), (n + 1, 1, 0): LAMP}
    for k in range(n):
        blocks[(1 + k, 1, 0)] = REPEATER("west", 1)
    return _Layout(_support(blocks), ((0, 1, 0),), ((n + 1, 1, 0),))


_register(
    "delay-repeater", "delay", "in", "lever",
    "Hebel, eine Reihe Verstärker auf Stufe 1 (je 2 gt), Lampe. Stufe 1 lässt auch 2-gt-Pulse unverändert "
    "durch; höhere Stufen würden kurze Pulse verlängern.",
    [({"delay": 2 * n}, (lambda n=n: _repeater_line(n))) for n in range(1, 9)])


_register(
    "delay-torch-pair", "delay", "in", "lever",
    "Zwei Fackeln übereinander: Der Hebel sitzt auf einem Block mit Wandfackel, darüber ein Block mit "
    "Standfackel, obendrauf die Lampe. Zwei Inverter, zusammen 4 gt.",
    [({"delay": 4}, lambda: _Layout({(0, 0, 0): STONE, (0, 1, 0): LEVER(), (1, 0, 0): WALL_TORCH("east"),
                                    (1, 1, 0): STONE, (1, 2, 0): TORCH, (1, 3, 0): LAMP},
                                   ((0, 1, 0),), ((1, 3, 0),)))])


# --- monostable: comparator subtraction --------------------------------------------------------------------------
def _side_path(blocks: dict, delays: list[int], x0: int = 2) -> None:
    """Loop from the dust at (x0, 1, 0) south and back north into the side of the comparator at (x0+1, 1, 0):
    column x0 going south, a dust corner, column x0+1 going north. Delays fill the columns (0 = dust); the
    last one sits right at the comparator side."""
    h = max(1, (len(delays) + 1) // 2)
    up = delays[-h:]  # travelled northwards, the last one at the comparator side
    down = [0] * (h - (len(delays) - h)) + delays[:-h]
    for k, d in enumerate(down):
        blocks[(x0, 1, 1 + k)] = REPEATER("north", d) if d else WIRE
    blocks[(x0, 1, h + 1)] = WIRE
    blocks[(x0 + 1, 1, h + 1)] = WIRE
    for k, d in enumerate(up):
        blocks[(x0 + 1, 1, h - k)] = REPEATER("south", d)


def _comparator_mono(kind: str, rear: int, side: list[int]) -> _Layout:
    """Input -> (repeater `rear` or dust) -> dust D -> comparator (subtract) -> lamp; D also reaches the side
    through `side`. The output is on from the rising edge until the delayed copy arrives at the side."""
    blocks = {(0, 1, 0): INPUT(kind, "east"), (1, 1, 0): REPEATER("west", rear) if rear else WIRE,
              (2, 1, 0): WIRE, (3, 1, 0): COMPARATOR("west"), (4, 1, 0): LAMP}
    _side_path(blocks, side)
    return _Layout(_support(blocks), ((0, 1, 0),), ((4, 1, 0),))


_register(
    "monostable-comparator", "monostable", "in", "lever",
    "Komparator im Subtraktionsmodus: Ein Verstärker (Stufe = Pulslänge/2) verlängert kurze Hebelpulse und "
    "speist den Rückeingang; über eine Schleife mit einem gleich langen Verstärker kommt dasselbe Signal "
    "verspätet an den Seiteneingang und schaltet den Ausgang wieder ab. Steigende Flanke, 4 bis 8 gt.",
    [({"length": 2 * a, "delay": 2 * a + 2, "kind": "lever"},
      (lambda a=a: _comparator_mono("lever", a, [a]))) for a in (2, 3, 4)])


def _button_side(length: int) -> list[int]:
    n = -(-length // 8)
    rest, out = length // 2, []
    for k in range(n):
        d = -(-rest // (n - k))
        out.append(d)
        rest -= d
    return out


_register(
    "monostable-comparator-button", "monostable", "in", "button",
    "Komparator im Subtraktionsmodus, Knopf über Staub direkt am Rückeingang; dasselbe Signal läuft über eine "
    "Verstärker-Schleife an den Seiteneingang und schaltet den Ausgang nach der Laufzeit der Schleife ab. "
    "Pulslänge bis 20 gt (so lang wie der Knopfpuls).",
    [({"length": n, "delay": 2, "kind": "button"}, (lambda n=n: _comparator_mono("button", 0, _button_side(n))))
     for n in (4, 6, 8, 10, 12, 16, 20)])


# --- monostable / pulse extender: copper bulb with feedback ------------------------------------------------------
def _bulb_delays(length: int) -> tuple[int, list[int]]:
    """Feedback loop for an output of `length` gt (= 2 + 2 * sum of delays): column height and delays."""
    total = (length - 2) // 2
    h = 1 if total <= 12 else 2
    n = 2 * h + 1
    return h, [total // n + (1 if k < total % n else 0) for k in range(n)]


def _bulb_mono(kind: str, length: int, bypass: bool = False) -> _Layout:
    """Rising edge -> 4-gt pulse (comparator subtraction) -> copper bulb turns on; a comparator reads it and
    lights the lamp; from the lamp a repeater loop leads back into the bulb and turns it off again.
    With `bypass`, the input reaches the lamp as well, exactly as late as the bulb signal (pulse extender)."""
    blocks = {(0, 1, 0): INPUT(kind, "east"), (1, 1, 0): REPEATER("west", 2), (2, 1, 0): WIRE,
              (3, 1, 0): COMPARATOR("west"), (4, 1, 0): BULB, (5, 1, 0): COMPARATOR("west", "compare"),
              (6, 1, 0): LAMP}
    _side_path(blocks, [2])
    h, delays = _bulb_delays(length)
    for k in range(h):  # down along x=6 (north), across, back along x=4 into the bulb
        blocks[(6, 1, -1 - k)] = REPEATER("south", delays[k])
    blocks[(6, 1, -1 - h)] = WIRE
    blocks[(5, 1, -1 - h)] = REPEATER("east", delays[h])
    blocks[(4, 1, -1 - h)] = WIRE
    for k in range(h):
        blocks[(4, 1, -h + k)] = REPEATER("north", delays[h + 1 + k])
    if bypass:  # dust (3,1,2) of the side loop carries the input delayed by 4 gt; two more repeaters: 8 gt
        blocks.update({(4, 1, 2): REPEATER("west", 1), (5, 1, 2): WIRE, (6, 1, 2): WIRE,
                       (6, 1, 1): REPEATER("south", 1)})
    return _Layout(_support(blocks), ((0, 1, 0),), ((6, 1, 0),))


_BULB_TEXT = ("Steigende Flanke wird per Komparator-Subtraktion zu einem 4-gt-Puls; der schaltet eine Kupferbirne "
              "ein (sie wechselt bei jeder steigenden Flanke). Ein Komparator liest die Birne und speist die Lampe, "
              "von der eine Verstärker-Schleife zurück in die Birne führt und sie wieder ausschaltet.")

_register(
    "monostable-copper-bulb", "monostable", "in", "lever",
    _BULB_TEXT + " Lange Pulse unabhängig von der Hebeldauer, 8 bis 40 gt.",
    [({"length": n, "delay": 8, "kind": "lever"}, (lambda n=n: _bulb_mono("lever", n)))
     for n in (8, 12, 16, 20, 26, 30, 40)])

_register(
    "monostable-copper-bulb-button", "monostable", "in", "button",
    _BULB_TEXT + " Mit Knopf, 8 bis 40 gt.",
    [({"length": n, "delay": 8, "kind": "button"}, (lambda n=n: _bulb_mono("button", n)))
     for n in (8, 16, 30, 40)])

_register(
    "pulse-extender-copper-bulb", "pulse-extender", "in", "lever",
    _BULB_TEXT + " Zusätzlich erreicht der Hebel die Lampe über zwei Verstärker genau so spät wie die Birne, "
    "lange Pulse kommen also unverändert durch. Mindestlänge 8 bis 40 gt.",
    [({"length": n, "delay": 8}, (lambda n=n: _bulb_mono("lever", n, bypass=True)))
     for n in (8, 12, 16, 20, 30, 40)])


# --- pulse extender: one repeater -------------------------------------------------------------------------------
_register(
    "pulse-extender-repeater", "pulse-extender", "in", "lever",
    "Ein einzelner Verstärker zwischen Hebel und Lampe verlängert jeden kürzeren Puls auf seine Verzögerung "
    "(Stufe x 2 gt); längere Pulse kommen unverändert durch. 2 bis 8 gt.",
    [({"length": 2 * d, "delay": 2 * d},
      (lambda d=d: _Layout(_support({(0, 1, 0): LEVER("east"), (1, 1, 0): REPEATER("west", d), (2, 1, 0): LAMP}),
                           ((0, 1, 0),), ((2, 1, 0),)))) for d in (1, 2, 3, 4)])


# --- t flip-flop ------------------------------------------------------------------------------------------------
def _bulb_tff(kind: str) -> _Layout:
    return _Layout(_support({(0, 1, 0): INPUT(kind, "east"), (1, 1, 0): BULB,
                             (2, 1, 0): COMPARATOR("west", "compare"), (3, 1, 0): LAMP}),
                   ((0, 1, 0),), ((3, 1, 0),))


_TFF_TEXT = ("Kupferbirne direkt am Eingang: Sie wechselt bei jeder steigenden Flanke zwischen an und aus. Ein "
             "Komparator liest sie aus (15 oder 0) und speist die Lampe. Verzögerung 2 gt.")
_register("t-flip-flop-copper-bulb", "t-flip-flop", "in", "lever", _TFF_TEXT,
          [({"delay": 2, "kind": "lever"}, lambda: _bulb_tff("lever"))])
_register("t-flip-flop-copper-bulb-button", "t-flip-flop", "in", "button", _TFF_TEXT,
          [({"delay": 2, "kind": "button"}, lambda: _bulb_tff("button"))])


# --- rs latch ---------------------------------------------------------------------------------------------------
def _rs_nor(kind: str) -> _Layout:
    """Two torches on blocks B1 (reset side) and B2 (set side), cross-connected by dust.

    Button: set reaches B2 over dust, reset reaches B1 through a repeater, so that setting (two torches) and
    resetting (repeater + torch) both take 4 gt. Lever: a 2-gt flick is too short to flip the torches, so set
    goes through a stage-2 repeater onto the dust and reset through a stage-3 repeater; both stretch the pulse
    and both paths take 8 gt. A repeater straight into B2 would power the dust of T1 through the block."""
    lever = kind == "lever"
    blocks = {
        (0, 1, 0): INPUT(kind, "east"), (1, 1, 0): REPEATER("west", 3 if lever else 1), (2, 1, 0): STONE,
        # stored reset: T1 off, T2 on and powering B1 through the dust
        (3, 1, 0): "redstone_wall_torch[facing=east,lit=false]", (4, 1, 0): WIRE, (4, 0, 0): LAMP,
        (4, 1, 1): WIRE, (4, 1, 2): STONE, (3, 1, 2): WALL_TORCH("west"),
        (2, 1, 2): "redstone_wire[east=side,north=side,power=15,south=none,west=none]",
        (2, 1, 1): "redstone_wire[east=none,north=side,power=14,south=side,west=none]", (5, 1, 2): WIRE,
    }
    if lever:
        blocks.update({(6, 1, 2): REPEATER("east", 2), (7, 1, 2): INPUT(kind, "west")})
        set_pos = (7, 1, 2)
    else:
        blocks[(6, 1, 2)] = INPUT(kind, "west")
        set_pos = (6, 1, 2)
    return _Layout(_support(blocks), (set_pos, (0, 1, 0)), ((4, 0, 0),))


_RS_TEXT = ("RS-NOR-Latch aus zwei Wandfackeln an zwei Blöcken, über Staub kreuzweise verbunden. Die Lampe unter "
            "dem Staub hinter der zweiten Fackel zeigt den Zustand.")
_register("rs-latch-torch", "rs-latch", "set reset", "button button",
          _RS_TEXT + " Knöpfe: set über Staub, reset über einen Verstärker, beide 4 gt.",
          [({"delay": 4, "kind": "button"}, lambda: _rs_nor("button"))])
_register("rs-latch-torch-lever", "rs-latch", "set reset", "lever lever",
          _RS_TEXT + " Hebel: set über Verstärker Stufe 2 auf den Staub, reset über Stufe 3; beide verlängern "
          "kurze Hebelpulse und brauchen 8 gt.",
          [({"delay": 8, "kind": "lever"}, lambda: _rs_nor("lever"))])


# --- clocks -----------------------------------------------------------------------------------------------------
_register(
    "clock-observer", "clock", "", "",
    "Zwei Observer schauen sich an und lösen sich gegenseitig aus. Ausgang ist der Observer selbst; eine Lampe "
    "bliebe wegen ihrer Ausschaltverzögerung dauerhaft an.",
    [({"period": 6, "on_ticks": 2}, lambda: _Layout({(0, 0, 0): "observer[facing=east,powered=false]",
                                                     (1, 0, 0): "observer[facing=west,powered=false]"},
                                                    (), ((0, 0, 0),)))],
    settle=False)


def _ring4(ds: tuple[int, int, int, int]) -> _Layout:
    d1, d2, d3, d4 = ds
    blocks = _supported({(0, 1, 0): WIRE, (1, 1, 0): POWERED_REPEATER("west", d1), (2, 1, 0): WIRE,
                         (2, 1, 1): REPEATER("north", d2), (2, 1, 2): WIRE, (1, 1, 2): REPEATER("east", d3),
                         (0, 1, 2): WIRE, (0, 1, 1): REPEATER("south", d4)})
    blocks[(0, 0, 0)] = LAMP
    return _Layout(blocks, (), ((0, 0, 0),))


_register(
    "clock-repeater-ring", "clock", "", "",
    "Ring aus vier Verstärkern mit Staub in den Ecken, ein Verstärker ist gespeichert an; der Puls läuft im Ring "
    "um. Periode = Summe der Verzögerungen, An-Zeit = längste Verzögerung. Lampe unter einer Ecke.",
    [({"period": 2 * sum(ds), "on_ticks": 2 * max(ds)}, (lambda ds=ds: _ring4(ds)))
     for ds in ((1, 1, 1, 1), (2, 1, 1, 1), (2, 2, 2, 2), (3, 3, 3, 3), (4, 4, 4, 4))],
    settle=False)


def _ring2(d: int) -> _Layout:
    blocks = _supported({(0, 1, 0): WIRE, (1, 1, 0): POWERED_REPEATER("west", d), (2, 1, 0): WIRE,
                         (2, 1, 1): WIRE, (1, 1, 1): REPEATER("east", d), (0, 1, 1): WIRE})
    blocks[(0, 0, 0)] = LAMP
    return _Layout(blocks, (), ((0, 0, 0),))


_register(
    "clock-repeater-pair", "clock", "", "",
    "Zwei gegenläufige Verstärker nebeneinander, an beiden Enden über Staub verbunden; einer ist gespeichert an. "
    "An- und Aus-Zeit je eine Verzögerung. Lampe unter einer Ecke.",
    [({"period": 4 * d, "on_ticks": 2 * d}, (lambda d=d: _ring2(d))) for d in (3, 4)],
    settle=False)


def _torch_clock(d: int) -> _Layout:
    blocks = _supported({(0, 1, 0): STONE, (0, 1, 1): WALL_TORCH("south"), (1, 1, 1): WIRE, (2, 1, 1): WIRE,
                         (2, 1, 0): WIRE, (1, 1, 0): REPEATER("east", d)})
    blocks[(2, 0, 1)] = LAMP
    return _Layout(blocks, (), ((2, 0, 1),))


_register(
    "clock-torch-repeater", "clock", "", "",
    "Wandfackel an einem Block, Staub im Bogen zurück, ein Verstärker versorgt den Block: Die Fackel schaltet "
    "sich verzögert selbst aus und wieder an. Ab Stufe 2 brennt sie nicht durch. Lampe unter dem Staub.",
    [({"period": 4 + 4 * d, "on_ticks": 2 + 2 * d}, (lambda d=d: _torch_clock(d))) for d in (2, 3, 4)],
    settle=False)


def _comparator_clock(da: int, db: int) -> _Layout:
    blocks = _supported({(0, 1, 0): REDSTONE_BLOCK, (1, 1, 0): COMPARATOR("west"), (2, 1, 0): LAMP,
                         (2, 1, 1): REPEATER("north", da), (2, 1, 2): WIRE, (1, 1, 2): WIRE,
                         (1, 1, 1): REPEATER("south", db)})
    return _Layout(blocks, (), ((2, 1, 0),))


_register(
    "clock-comparator", "clock", "", "",
    "Komparator im Subtraktionsmodus vor einem Redstone-Block, sein Ausgang läuft über die Lampe und zwei "
    "Verstärker zurück an den Seiteneingang und schaltet ihn ab. An- und Aus-Zeit gleich lang.",
    [({"period": 4 + 4 * (da + db), "on_ticks": 2 + 2 * (da + db)}, (lambda da=da, db=db: _comparator_clock(da, db)))
     for da, db in ((1, 1), (2, 1), (2, 2), (4, 4))],
    settle=False)
