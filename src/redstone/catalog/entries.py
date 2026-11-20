"""Catalog entries: layouts, settling and acceptance checks."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache

import nbtlib

from ..model import BlockState, Grid, Pos
from ..sim.runner import ORACLE_ORIGIN, apply_input

Xyz = tuple[int, int, int]
Action = tuple[int, Xyz, str]  # (tick, position in the grid, "use")


@dataclass(frozen=True)
class Built:
    grid: Grid
    ports: dict[str, Pos]  # named positions in the grid: inputs, door cells, chests, ...


@dataclass(frozen=True)
class Entry:
    key: str  # kebab-case, e.g. "piston-door-2x2"
    title: str  # German, everyday words
    keywords: tuple[str, ...]  # German and English search words (lower case)
    description: str  # German: what it does and how it is built
    usage: str  # German: how to use it in the world
    inputs: tuple[str, ...]  # port names of the levers/buttons the player uses
    layout: Callable[[], Built] = field(compare=False)  # unsettled layout
    check: Callable[[Built, Pos], list[str]] = field(compare=False)  # acceptance at an origin; returns problems
    notes: str = ""  # German: limits, e.g. "nur am Ursprung geprüft"
    display: tuple[tuple[str, str], ...] = ()  # (port, German name) shown in the GUI: inputs first, then outputs

    def built(self) -> Built:
        b = _settled(self.key)
        return Built(_copy_grid(b.grid), dict(b.ports))

    def build(self) -> Grid:
        return self.built().grid

    def placed(self, turns: int = 0) -> Built:
        """The settled build turned clockwise (seen from above) by `turns` quarter turns, ports turned with it."""
        from ..design.candidate import Candidate
        from ..design.compose import rotate

        b = self.built()
        names = list(b.ports)
        c = rotate(Candidate(name=self.key, grid=b.grid, inputs=[b.ports[n] for n in names], outputs=[]), turns)
        if c is None:
            raise ValueError(f"{self.key} cannot be turned")
        return Built(c.grid, dict(zip(names, c.inputs)))

    def accept(self, origin: Pos = ORACLE_ORIGIN, turns: int = 0) -> list[str]:
        """Problems of the acceptance check with the min corner at `origin`, turned by `turns` (empty = passed)."""
        return self.check(self.placed(turns), origin)


# --------------------------------------------------------------------------------------------- helpers
def _copy_grid(grid: Grid) -> Grid:
    out = Grid(tuple(grid.size), copy.deepcopy(grid.meta))
    for p, s in grid.items():
        out.set(p, s)
    out.block_entities = copy.deepcopy(grid.block_entities)
    return out


def _layout(blocks: dict[Xyz, str], ports: dict[str, Xyz], entities: dict[Xyz, dict] | None = None) -> Built:
    lo = [min(p[i] for p in blocks) for i in range(3)]
    hi = [max(p[i] for p in blocks) for i in range(3)]
    shift = Pos(*lo)
    grid = Grid(tuple(h - l + 1 for l, h in zip(lo, hi)))
    for p, state in blocks.items():
        grid.set(Pos(*p) - shift, state)
    for p, data in (entities or {}).items():
        grid.block_entities[Pos(*p) - shift] = data
    return Built(grid, {k: Pos(*p) - shift for k, p in ports.items()})


def items_nbt(block_id: str, items: list[tuple[int, str, int]]) -> nbtlib.Compound:
    return nbtlib.Compound({
        "id": nbtlib.String(block_id),
        "Items": nbtlib.List[nbtlib.Compound]([
            nbtlib.Compound({"Slot": nbtlib.Byte(s), "id": nbtlib.String(i), "count": nbtlib.Int(c)})
            for s, i, c in items
        ]),
    })


def _comparator_nbt(signal: int) -> nbtlib.Compound:
    return nbtlib.Compound({"id": nbtlib.String("minecraft:comparator"), "OutputSignal": nbtlib.Int(signal)})


def _settle(b: Built) -> Built:
    """Place the layout, give every block one update (as if just placed), run until idle and store the settled
    world (pistons may move: the whole box is copied). Container contents must not move while settling."""
    from ..analysis.experiment import Circuit
    from ..sim.constants import UPDATE_ALL
    from ..sim.core import World

    grid, origin = b.grid, ORACLE_ORIGIN
    world = World()
    world.place_grid(grid, origin)
    wires = [p + origin for p, s in grid.items() if s.id == "redstone_wire"]
    for _ in range(2):
        for p in wires:
            block = world.block(world.get(p))
            world.blocks[p] = block.get_connection_state(world, block.cross_state(0), p)
    positions = [p + origin for p, _ in grid.items()]
    for p in positions:
        state = world.get(p)
        world.neighbor_changed_with_state(state, p, world.block(state), False)
    for p in positions:
        world.update_neighbour_shapes(p, world.get(p), UPDATE_ALL)
    rec = Circuit(grid, origin).run([], max_ticks=400, quiet=12, world=world)
    if rec.settled_at is None:
        raise RuntimeError("build does not come to rest without input")
    out = Grid(tuple(grid.size), copy.deepcopy(grid.meta))
    sx, sy, sz = grid.size
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                p = Pos(x, y, z)
                state = world.get(p + origin)
                if not state.is_air:
                    out.set(p, state)
    for p, s in out.items():
        if s.id == "comparator":
            be = world.block_entities.get(p + origin)
            out.block_entities[p] = nbtlib.Compound({
                "id": nbtlib.String("minecraft:comparator"),
                "OutputSignal": nbtlib.Int(be.output_signal if be is not None else 0),
            })
        elif p in grid.block_entities:
            if container_items(world, p + origin) != _items_of(grid.block_entities[p]):
                raise RuntimeError(f"items at {p} moved while settling")
            out.block_entities[p] = copy.deepcopy(grid.block_entities[p])
    return Built(out, b.ports)


def _items_of(data) -> dict[int, tuple[str, int]]:
    out = {}
    for item in data.get("Items", []):
        item_id = str(item["id"])
        out[int(item.get("Slot", 0))] = (item_id if ":" in item_id else f"minecraft:{item_id}", int(item.get("count", 1)))
    return out


def container_items(world, pos: Pos) -> dict[int, tuple[str, int]]:
    """slot -> (item, count) of the container at `pos` (either core)."""
    be = world.block_entities.get(pos)
    if be is None:
        return {}
    out = {}
    for slot in range(int(getattr(be, "size", 27))):
        stack = be.get_item(slot)
        if stack:
            out[slot] = (str(stack[0]), int(stack[1]))
    return out


def totals(items: dict[int, tuple[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item, count in items.values():
        out[item] = out.get(item, 0) + count
    return out


class Run:
    """A built entry in a fresh simulator world at the oracle origin, driven tick by tick."""

    def __init__(self, grid: Grid, origin: Pos = ORACLE_ORIGIN) -> None:
        from ..sim.core import World

        self.origin = origin
        self.world = World()
        self.world.place_grid(grid, origin)
        self.tick_no = 0

    def use(self, pos: Pos) -> None:
        apply_input(self.world, "use", Pos(*pos) + self.origin, None)

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.world.tick()
            self.tick_no += 1

    def state(self, pos: Pos) -> BlockState:
        return self.world.get(Pos(*pos) + self.origin)

    def items(self, pos: Pos) -> dict[str, int]:
        return totals(container_items(self.world, Pos(*pos) + self.origin))


# ------------------------------------------------------------------------------------- piston door 2x2
DOOR = "stone_bricks"
STONE = "stone"
WIRE = "redstone_wire[east=side,north=side,power=0,south=side,west=side]"


def _piston_door_2x2() -> Built:
    """Wall plane z=0, opening x=2..3, y=1..2. Sticky pistons in the wall at x=0 and x=5 hold the door blocks in
    the opening while powered; a torch behind each piston pair powers it (the lower piston directly, the upper
    one through the block above the torch). The lever line (z=3) turns both torches off via repeaters into the
    torch blocks: lever on -> pistons retract -> the blocks slide into the wall next to the opening."""
    b: dict[Xyz, str] = {}
    for x in range(6):
        b[(x, 0, 0)] = STONE  # floor under the wall
        b[(x, 3, 0)] = DOOR  # lintel
        b[(x, -1, 3)] = STONE
        b[(x, 0, 3)] = WIRE
    for x, facing in ((0, "east"), (5, "west")):
        for y in (1, 2):
            b[(x, y, 0)] = f"sticky_piston[extended=false,facing={facing}]"
        b[(x, 0, 1)] = STONE  # torch block
        b[(x, 1, 1)] = "redstone_torch[lit=true]"
        b[(x, 2, 1)] = STONE  # powered by the torch, powers the upper piston
        b[(x, -1, 2)] = STONE
        b[(x, 0, 2)] = "repeater[delay=1,facing=south,locked=false,powered=false]"
    for x in (1, 4):
        for y in (1, 2):
            b[(x, y, 0)] = DOOR  # pushed into the opening while settling
    b[(2, -1, 4)] = STONE
    b[(2, 0, 4)] = "lever[face=floor,facing=south,powered=false]"
    ports = {"lever": (2, 0, 4)} | {f"door{i}": p for i, p in enumerate([(2, 1, 0), (3, 1, 0), (2, 2, 0), (3, 2, 0)])}
    ports |= {"pocket_left_low": (1, 1, 0), "pocket_right_high": (4, 2, 0)}
    ports |= {"piston_l1": (0, 1, 0), "piston_l2": (0, 2, 0), "piston_r1": (5, 1, 0), "piston_r2": (5, 2, 0)}
    return _layout(b, ports)


def _check_piston_door(b: Built, origin: Pos = ORACLE_ORIGIN) -> list[str]:
    problems: list[str] = []
    cells = [b.ports[f"door{i}"] for i in range(4)]
    for p in cells:
        if b.grid.get(p).id != DOOR:
            problems.append(f"stored state: no door block at {tuple(p)}")
    run = Run(b.grid, origin)
    run.step(5)

    def expect(open_: bool, when: str) -> None:
        for p in cells:
            s = run.state(p)
            if open_ and not s.is_air:
                problems.append(f"{when}: {tuple(p)} is {s.id}, expected air")
            if not open_ and s.id != DOOR:
                problems.append(f"{when}: {tuple(p)} is {s.id}, expected {DOOR}")
        non_wall = sum(1 for p, s in run.world.blocks.items() if s.id == DOOR)
        if non_wall != 4 + 6:
            problems.append(f"{when}: {non_wall} door/wall blocks, expected 10")

    lever = b.ports["lever"]
    for cycle in range(10):
        run.use(lever)
        run.step(20)
        expect(True, f"cycle {cycle} open")
        run.use(lever)
        run.step(20)
        expect(False, f"cycle {cycle} closed")
    for gap in (4, 2):  # fast flicking: open and close again after `gap` ticks, and the reverse
        run.use(lever)
        run.step(gap)
        run.use(lever)
        run.step(20)
        expect(False, f"flick {gap} gt from closed")
        run.use(lever)
        run.step(20)
        run.use(lever)
        run.step(gap)
        run.use(lever)
        run.step(20)
        expect(True, f"flick {gap} gt from open")
        run.use(lever)
        run.step(20)
    return problems


# --------------------------------------------------------------------------------- hidden door 1x2
def _rep(reads_from: str, delay: int = 1) -> str:
    return f"repeater[delay={delay},facing={reads_from},locked=false,powered=false]"


HIDDEN_OPEN = 60  # gt the door stays open (wooden button 30 gt + 30 gt delay line)


def _hidden_door_1x2() -> Built:
    """Wall plane z=0, opening x=2, y=1..2; sticky pistons at x=0 hold the two blocks in the opening (same
    piston/torch column as the 2x2 door). A wooden button on the front of the wall at x=4 (30 gt pulse) reaches
    the torch line twice: at once over repeater Rin and 30 gt later over a delay line of eight repeaters; the two
    meet behind Rin, so the door stays open for 60 gt and the delay line never feeds itself."""
    b: dict[Xyz, str] = {}
    for x in range(5):
        b[(x, 0, 0)] = STONE
        b[(x, 3, 0)] = DOOR
    for x in (3, 4):
        for y in (1, 2):
            b[(x, y, 0)] = DOOR
    for y in (1, 2):
        b[(0, y, 0)] = "sticky_piston[extended=false,facing=east]"
        b[(1, y, 0)] = DOOR  # pushed into the opening while settling
    b[(4, 1, -1)] = "oak_button[face=wall,facing=north,powered=false]"
    b[(0, 0, 1)] = STONE  # torch block
    b[(0, 1, 1)] = "redstone_torch[lit=true]"
    b[(0, 2, 1)] = STONE
    b[(4, 0, 1)] = STONE
    b[(4, 1, 1)] = WIRE  # next to the button block, steps down to A
    low = {(1, 0, 1): _rep("east"), (2, 0, 1): WIRE, (2, 0, 2): WIRE, (3, 0, 2): _rep("east"), (4, 0, 2): WIRE,
           (4, 0, 3): WIRE}
    for i, x in enumerate(range(5, 9)):
        low[(x, 0, 3)] = _rep("west", 2)  # D1..D4, 4 gt each
    for z in (3, 4, 5):
        low[(9, 0, z)] = WIRE
    for i, x in enumerate(range(8, 4, -1)):
        low[(x, 0, 5)] = _rep("east", 1 if x == 5 else 2)  # D5..D8: 7 x 4 gt + 2 gt = 30 gt
    for p in ((4, 0, 5), (3, 0, 5), (2, 0, 5), (2, 0, 4), (2, 0, 3)):
        low[p] = WIRE
    for (x, y, z), state in low.items():
        b[(x, y, z)] = state
        b[(x, y - 1, z)] = STONE
    ports = {"button": (4, 1, -1), "door0": (2, 1, 0), "door1": (2, 2, 0), "piston1": (0, 1, 0), "piston2": (0, 2, 0)}
    return _layout(b, ports)


def _check_hidden_door(b: Built, origin: Pos = ORACLE_ORIGIN) -> list[str]:
    problems: list[str] = []
    cells = [b.ports["door0"], b.ports["door1"]]
    run = Run(b.grid, origin)
    run.step(5)

    def expect(open_: bool, when: str) -> None:
        for p in cells:
            s = run.state(p)
            if open_ != s.is_air or (not open_ and s.id != DOOR):
                problems.append(f"{when} ({run.tick_no - start} gt after the press): {tuple(p)} is {s.id}")

    for repeat in range(3):
        start = run.tick_no
        run.use(b.ports["button"])
        run.step(12)
        expect(True, f"press {repeat}: opening")
        run.step(HIDDEN_OPEN - 16)
        expect(True, f"press {repeat}: still open")
        run.step(30)
        expect(False, f"press {repeat}: closed again")
        doors = sum(1 for s in run.world.blocks.values() if s.id == DOOR)
        if doors != 11:
            problems.append(f"press {repeat}: {doors} door/wall blocks, expected 11")
    return problems


# ----------------------------------------------------------------------------------------- item sorter
FILTER_ITEM = "minecraft:cobblestone"
OTHER_ITEM = "minecraft:dirt"
FILLER_ITEM = "minecraft:stick"
FILTER_START = 41  # + 4 filler items: comparator 2; one more filter item: 3


def _hopper(facing: str) -> str:
    return f"hopper[enabled=true,facing={facing}]"


CHEST = "chest[facing=north,type=single,waterlogged=false]"
BARREL = "barrel[facing=up,open=false]"
CONSTANT_ITEM = "minecraft:wooden_shovel"  # two in the barrel: comparator 2


def _sorter_slot(b: dict, ents: dict, ports: dict, x0: int, item: str, tag: str = "") -> None:
    """One sorter slot with its column at x = x0 + 1 (blocks, block entities and ports added in place; the
    overflow is left to the caller). One sorter slot. Input chest (top) -> hopper C -> overflow chest (east). The filter hopper F below C pulls
    only the filter item (its other four slots hold one filler item each) and faces into air, so it never
    pushes. Comparator Cf behind F reads it (41 filter + 4 filler = 2, 42 = 3); one dust lowers that to 1/2 at the
    side of comparator X (subtract mode), whose rear reads a barrel with two tools (2): X outputs 1 normally and
    powers the block behind hopper B below F, which keeps B locked; at 42 items X outputs 0, B pulls one item
    from F and F is back at 41. Hopper H below B pulls from B regardless of the lock and fills the target chest,
    so B does not keep the last item. A comparator inverts instead of a torch: a torch would burn out at one
    item every 8 ticks."""
    at = lambda x, y, z: (x0 + x, y, z)  # noqa: E731
    b |= {
        at(1, 3, 0): _hopper("east"),  # C
        at(1, 2, 0): _hopper("west"),  # F: faces air, never pushes
        at(1, 1, 0): "hopper[enabled=false,facing=down]",  # B: locked while X is on
        at(1, 0, 0): _hopper("down"),  # H
        at(1, -1, 0): CHEST,  # target
        at(1, 1, 1): STONE,  # lock block, powered by X
        at(1, 2, 1): "comparator[facing=north,mode=compare,powered=true]",  # Cf
        at(1, 1, 2): STONE,
        at(1, 2, 2): WIRE,
        at(0, 0, 2): STONE,
        at(0, 1, 2): WIRE,  # one step down, into the side of X
        at(0, 0, 1): STONE,
        at(0, 1, 1): "comparator[facing=west,mode=subtract,powered=true]",  # X
        at(-1, 1, 1): BARREL,
    }
    filt = [(0, item, FILTER_START)] + [(s, FILLER_ITEM, 1) for s in range(1, 5)]
    ents |= {at(1, 2, 0): items_nbt("minecraft:hopper", filt),
             at(-1, 1, 1): items_nbt("minecraft:barrel", [(0, CONSTANT_ITEM, 1), (1, CONSTANT_ITEM, 1)]),
             at(1, 2, 1): _comparator_nbt(2), at(0, 1, 1): _comparator_nbt(1)}
    ports |= {f"target{tag}": at(1, -1, 0), f"filter{tag}": at(1, 2, 0), f"comparator{tag}": at(1, 2, 1),
              f"lock{tag}": at(1, 1, 0), f"inverter{tag}": at(0, 1, 1)}


def _item_sorter() -> Built:
    """One sorter slot (`_sorter_slot`) with the input chest on top and the overflow chest east of C."""
    b: dict[Xyz, str] = {(1, 4, 0): CHEST, (2, 3, 0): CHEST}  # input, overflow
    ents: dict = {}
    ports: dict = {"input": (1, 4, 0), "overflow": (2, 3, 0)}
    _sorter_slot(b, ents, ports, 0, FILTER_ITEM)
    return _layout(b, ports, ents)


# several slots: one every SLOT_PITCH columns, the hoppers C joined by plain hoppers into a chain
SORTER_ITEMS = ("minecraft:cobblestone", "minecraft:andesite", "minecraft:granite", "minecraft:diorite")
SLOT_PITCH = 3


def _item_sorter_4() -> Built:
    """Four sorter slots side by side (one sort each, SORTER_ITEMS). The input chest sits on the first hopper C;
    every C passes the rest east, over two plain hoppers, to the next C; the last C fills the overflow chest.
    The barrel of a slot stands next to the lock block of the slot before it, which does not disturb either."""
    n = len(SORTER_ITEMS)
    last = 1 + SLOT_PITCH * (n - 1)
    b: dict[Xyz, str] = {(1, 4, 0): CHEST, (last + 1, 3, 0): CHEST}
    ents: dict = {}
    ports: dict = {"input": (1, 4, 0), "overflow": (last + 1, 3, 0)}
    for k, item in enumerate(SORTER_ITEMS):
        _sorter_slot(b, ents, ports, SLOT_PITCH * k, item, str(k + 1))
        if k < n - 1:
            for dx in range(1, SLOT_PITCH):
                b[(1 + SLOT_PITCH * k + dx, 3, 0)] = _hopper("east")
    return _layout(b, ports, ents)


SORTER_TICKS = 1400


def _check_item_sorter(b: Built, origin: Pos = ORACLE_ORIGIN) -> list[str]:
    """64 filter items and 64 others in one go, then the same mixed in small stacks across the input chest."""
    problems: list[str] = []
    mixed = [(s, FILTER_ITEM if s % 2 == 0 else OTHER_ITEM, 16 if s < 8 else 0) for s in range(9)]
    for name, load in (("sorted", [(0, FILTER_ITEM, 64), (1, OTHER_ITEM, 64)]),
                       ("mixed", [m for m in mixed if m[2]])):
        grid = _copy_grid(b.grid)
        grid.block_entities[b.ports["input"]] = items_nbt("minecraft:chest", load)
        run = Run(grid, origin)
        run.step(SORTER_TICKS)
        got = {k: run.items(b.ports[k]) for k in ("input", "overflow", "target", "filter")}
        n_filter = sum(c for _, i, c in load if i == FILTER_ITEM)
        want = {"input": {}, "overflow": {OTHER_ITEM: sum(c for _, i, c in load) - n_filter},
                "target": {FILTER_ITEM: n_filter}, "filter": {FILTER_ITEM: FILTER_START, FILLER_ITEM: 4}}
        for k in want:
            if got[k] != want[k]:
                problems.append(f"{name}: {k}: {got[k]}, expected {want[k]}")
    return problems


SORTER_4_TICKS = 2600


def _check_item_sorter_4(b: Built, origin: Pos = ORACLE_ORIGIN) -> list[str]:
    """Every sort and other items: 16 of each sort plus 32 others in small stacks across the input chest (mixed
    order), then 64 of the last sort alone (it passes all other slots)."""
    problems: list[str] = []
    sorts = list(SORTER_ITEMS)
    mixed = [(s, (sorts + [OTHER_ITEM])[s % 5], 8) for s in range(20)]
    mixed = [m for m in mixed if m[1] != OTHER_ITEM] + [m for m in mixed if m[1] == OTHER_ITEM][:4]
    mixed = [(s, i, c) for s, (_, i, c) in enumerate(mixed)]
    for name, load in (("mixed", mixed), ("last sort", [(0, sorts[-1], 64)])):
        grid = _copy_grid(b.grid)
        grid.block_entities[b.ports["input"]] = items_nbt("minecraft:chest", load)
        run = Run(grid, origin)
        run.step(SORTER_4_TICKS)
        count = lambda item: sum(c for _, i, c in load if i == item)  # noqa: E731
        want = {"input": {}, "overflow": {OTHER_ITEM: count(OTHER_ITEM)} if count(OTHER_ITEM) else {}}
        for k, item in enumerate(sorts, 1):
            want[f"target{k}"] = {item: count(item)} if count(item) else {}
            want[f"filter{k}"] = {item: FILTER_START, FILLER_ITEM: 4}
        for k, w in want.items():
            got = run.items(b.ports[k])
            if got != w:
                problems.append(f"{name}: {k}: {got}, expected {w}")
    return problems


# --------------------------------------------------------------------------------------------- registry
PROOF = ("Im echten Spiel aufgenommen (scenarios/cat-*); im Simulator an rund 50 Orten und in allen vier "
         "Drehungen geprüft.")
ENTRIES: list[Entry] = [
    Entry(
        key="piston-door-2x2",
        title="Kolbentür 2×2",
        keywords=("kolbentür", "kolben tür", "tür", "tor", "geheimtür", "eingang", "piston door", "door", "2x2"),
        description=("Eine Tür aus vier Steinziegeln, zwei Blöcke breit und zwei hoch, bündig in einer Wand. Vier "
                     "klebrige Kolben ziehen die Blöcke zur Seite in die Wand."),
        usage=("Hebel an: Die Tür geht auf. Hebel aus: Die Tür geht zu. Der Hebel steht hinter der Wand; die "
               "Technik (Fackeln, Verstärker, Redstone) liegt hinter und unter der Wand."),
        inputs=("lever",),
        layout=_piston_door_2x2,
        check=_check_piston_door,
        notes=PROOF,
        display=(("lever", "Hebel"), ("piston_l1", "Kolben links unten"), ("piston_l2", "Kolben links oben"),
                 ("piston_r1", "Kolben rechts unten"), ("piston_r2", "Kolben rechts oben")),
    ),
    Entry(
        key="hidden-door-1x2",
        title="Versteckte Tür 1×2",
        keywords=("versteckte tür", "geheimtür", "geheimgang", "tür", "knopf", "hidden door", "secret door", "1x2"),
        description=("Ein Durchgang, einen Block breit und zwei hoch, der wie ein Stück Wand aussieht. Zwei "
                     "klebrige Kolben ziehen die beiden Blöcke zur Seite in die Wand."),
        usage=("Holzknopf an der Wand drücken: Die Tür geht auf und schließt sich nach etwa 3 Sekunden von selbst. "
               "Die Technik (Fackel, eine Reihe Verstärker als Zeitschalter) liegt hinter der Wand."),
        inputs=("button",),
        layout=_hidden_door_1x2,
        check=_check_hidden_door,
        notes=PROOF + " Braucht einen Holzknopf (30 gt); ein Steinknopf ist zu kurz.",
        display=(("button", "Knopf"), ("piston1", "Kolben unten"), ("piston2", "Kolben oben")),
    ),
    Entry(
        key="item-sorter",
        title="Itemsortierer (ein Fach)",
        keywords=("itemsortierer", "sortierer", "sortieren", "sortiermaschine", "item sorter", "sorter", "lager",
                  "trichter", "hopper"),
        description=("Sortiert eine Sorte Gegenstände (hier Bruchstein) aus allem, was du in die obere Truhe legst, "
                     "in die untere Truhe. Alles andere landet in der Truhe daneben."),
        usage=("Lege Gegenstände in die obere Truhe. Bruchstein kommt unten an, der Rest in der Truhe daneben. Für "
               "eine andere Sorte: im Filter-Trichter (unter dem oberen Trichter) den Bruchstein durch 41 Stück "
               "der gewünschten Sorte ersetzen; die vier Stöcke bleiben liegen. Stöcke selbst nicht einsortieren. Die "
               "zwei Holzschaufeln im Fass hinter dem Filter gehören zur Schaltung: nicht herausnehmen."),
        inputs=(),
        layout=_item_sorter,
        check=_check_item_sorter,
        notes=PROOF + " Arbeitet ein Item pro 8 Ticks ab (2,5 pro Sekunde).",
        display=(("comparator", "Filter-Komparator"), ("inverter", "Sperre")),
    ),
    Entry(
        key="item-sorter-4",
        title="Itemsortierer (vier Fächer)",
        keywords=("itemsortierer", "sortierer", "sortieren", "sortiermaschine", "item sorter", "sorter", "lager",
                  "trichter", "hopper", "fächer", "mehrere", "vier", "4"),
        description=("Sortiert vier Sorten Gegenstände (hier Bruchstein, Andesit, Granit und Diorit) aus allem, was du "
                     "in die obere Truhe legst, in je eine eigene Truhe darunter. Alles andere landet in der Truhe am "
                     "Ende der Trichterreihe. Vier Fächer wie der Sortierer mit einem Fach, nebeneinander."),
        usage=("Lege Gegenstände in die obere Truhe. Jede der vier Sorten kommt in ihrer Truhe unten an, der Rest in "
               "der Truhe am Ende. Für eine andere Sorte: im Filter-Trichter des Fachs (unter der Trichterreihe) die "
               "41 Stück durch 41 der gewünschten Sorte ersetzen; die vier Stöcke bleiben liegen. Stöcke selbst nicht "
               "einsortieren. Die zwei Holzschaufeln in jedem Fass gehören zur Schaltung: nicht herausnehmen."),
        inputs=(),
        layout=_item_sorter_4,
        check=_check_item_sorter_4,
        notes=PROOF + " Arbeitet ein Item pro 8 Ticks ab (2,5 pro Sekunde).",
        display=tuple((f"comparator{k}", f"Filter {k}") for k in range(1, 5)),
    ),
]


@cache
def _settled(key: str) -> Built:
    entry = get(key)
    b = _settle(entry.layout())
    b.grid.meta.name = entry.key
    b.grid.meta.description = entry.title
    return b


def get(key: str) -> Entry:
    for e in ENTRIES:
        if e.key == key:
            return e
    raise KeyError(f"unknown catalog entry {key!r}")


def find(query: str) -> list[Entry]:
    """Entries whose key, title or keywords match any word of `query` (case-insensitive)."""
    words = [w for w in re.split(r"[\s,;]+", query.lower()) if len(w) >= 3]
    hits = []
    for e in ENTRIES:
        text = " ".join((e.key, e.title.lower(), *e.keywords))
        score = sum(1 for w in words if w in text)
        if score:
            hits.append((score, e))
    return [e for _, e in sorted(hits, key=lambda t: -t[0])]
