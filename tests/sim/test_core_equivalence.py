"""Differential test: the Rust core must behave exactly like the Python reference core.

Every tick the complete world is compared: all block states, block entities (in dict order), scheduled ticks,
block events, the number of neighbor updates and, at the end, the mechanics notes and warnings. Sources:
all scenarios, all logic and sequential templates, the external fixtures and seeded random block soups.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest

from redstone.model import BlockState, Grid, Pos
from redstone.sim import blocks  # noqa: F401  (registers block behaviours)
from redstone.sim import core
from redstone.sim.notes import notes_of
from redstone.sim.runner import ORACLE_ORIGIN, apply_input
from redstone.sim.world import World as PythonWorld
from redstone.verify import load_scenario

if not core.rust_available():
    pytest.skip(f"Rust core not available: {core.rust_error()}", allow_module_level=True)

from redstone.sim.rust_world import RustWorld  # noqa: E402

ROOT = Path(__file__).parents[2]
SCENARIOS = sorted((ROOT / "scenarios").glob("*.yaml"))
EXTERNAL = ROOT / "tests" / "fixtures" / "external"

BE_FIELDS = ("output_signal", "size", "items", "cooldown_time", "ticked_game_time", "has_book", "page",
             "page_count", "moved_state", "direction", "extending", "is_source_piston", "progress", "progress_o",
             "last_ticked", "removed", "disabled_mask", "triggered", "crafting_ticks_remaining", "radius",
             "last_vibration_frequency", "current", "travel_time", "candidate", "candidate_tick")
_MISSING = object()


def _be_dump(be: Any) -> tuple:
    out = []
    for f in BE_FIELDS:
        v = getattr(be, f, _MISSING)
        if v is _MISSING:
            continue
        if f == "items":
            v = tuple((slot, tuple(entry)) for slot, entry in v.items())
        out.append((f, str(v) if not isinstance(v, (int, float, bool, tuple)) else v))
    return tuple(out)


def dump(world: Any) -> dict:
    return {
        "blocks": sorted((tuple(p), str(s)) for p, s in world.blocks.items()),
        "block_entities": [(tuple(p), _be_dump(be)) for p, be in world.block_entities.items()],
        "ticks": sorted((t.trigger_tick, t.priority, t.sub_tick, tuple(t.pos), t.block) for t in world._ticks),
        "block_events": [(tuple(e.pos), e.block, e.a, e.b) for e in world.block_events],
        "neighbor_updates": world.neighbor_update_count,
        "game_time": world.game_time,
    }


def _first_difference(a: dict, b: dict) -> str:
    for key in a:
        if a[key] != b[key]:
            if isinstance(a[key], list):
                sa, sb = set(a[key]), set(b[key])
                if sa != sb:
                    return f"{key}: python only {sorted(sa - sb)[:5]}, rust only {sorted(sb - sa)[:5]}"
                return f"{key}: same entries, different order"
            return f"{key}: python {a[key]!r}, rust {b[key]!r}"
    return ""


Step = tuple[str, Pos, BlockState | None]  # (action, absolute pos, state) applied before a tick


def _step(world, t: int, schedule: dict[int, list[Step]], last: bool):
    """Inputs of tick t, then the dump of the world, then the tick; (dump, exception name)."""
    try:
        for action, pos, state in schedule.get(t, ()):
            apply_input(world, action, pos, state)
        state = dump(world)
        if not last:
            world.tick()
        return state, None
    except Exception as e:  # both cores must fail the same way
        return None, type(e).__name__


def assert_same(grid: Grid, schedule: dict[int, list[Step]], ticks: int, origin: Pos = ORACLE_ORIGIN) -> None:
    """Both cores side by side, compared tick by tick (long scenarios would not fit in memory otherwise)."""
    py, rs = PythonWorld(), RustWorld()
    py.place_grid(grid, origin)
    rs.place_grid(grid, origin)
    for t in range(ticks + 1):
        (a, ea), (b, eb) = _step(py, t, schedule, t == ticks), _step(rs, t, schedule, t == ticks)
        assert ea == eb, f"tick {t}: exception: python {ea}, rust {eb}"
        if ea is not None:
            return
        assert a == b, f"tick {t}: {_first_difference(a, b)}"

    def notes(world):
        return sorted((n.tick, n.kind, tuple(n.pos), n.detail) for n in notes_of(world))

    assert notes(py) == notes(rs), "notes differ"
    assert list(py.warnings) == list(rs.warnings), "warnings differ"


# ------------------------------------------------------------------------------------------------ scenarios
MAX_SCENARIO_TICKS = 6000


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario(path: Path):
    scenario = load_scenario(path)
    schedule: dict[int, list[Step]] = {}
    for t in range(scenario.ticks + 1):
        for inp in scenario.inputs_at(t):
            schedule.setdefault(t, []).append((inp.action, Pos(*inp.pos) + ORACLE_ORIGIN, inp.state))
    # the long truth-table recordings (cmp5, mux8: every lever combination) repeat the same kind of step
    assert_same(scenario.grid, schedule, min(scenario.ticks, MAX_SCENARIO_TICKS))


# ------------------------------------------------------------------------------------------------ templates
def _toggle_schedule(inputs: list[Pos], origin: Pos, rng: random.Random, ticks: int, events: int) -> dict:
    schedule: dict[int, list[Step]] = {}
    for _ in range(events):
        t = rng.randrange(ticks - 10)
        schedule.setdefault(t, []).append(("use", inputs[rng.randrange(len(inputs))] + origin, None))
    return schedule


def _candidates():
    from redstone.design.seq_templates import SEQ_TEMPLATES
    from redstone.design.templates import TEMPLATES

    for tpl in TEMPLATES:
        yield pytest.param(tpl.build, id=f"tpl-{tpl.name}")
    for tpl in SEQ_TEMPLATES:
        yield pytest.param(lambda tpl=tpl: [c for _, c in tpl.variants()], id=f"seq-{tpl.name}")


@pytest.mark.parametrize("build", list(_candidates()))
def test_template(build):
    built = build()
    for i, cand in enumerate(built if isinstance(built, list) else [built]):
        if not cand.inputs:
            assert_same(cand.grid, {}, 80)
            continue
        rng = random.Random(i)
        assert_same(cand.grid, _toggle_schedule(cand.inputs, ORACLE_ORIGIN, rng, 120, 12), 120)


# ------------------------------------------------------------------------------------------------ fixtures
@pytest.mark.parametrize("name", ["mux3-8.litematic", "seg7.litematic", "piston-gate-3x3.litematic",
                                  "tripple-piston-extender.litematic"])
def test_external_fixture(name: str):
    from redstone.io import load

    path = EXTERNAL / name
    if not path.exists():
        pytest.skip(f"{name} missing, run: uv run python scripts/fetch_external_fixtures.py")
    grid = load(path)
    inputs = [p for p, s in grid.items() if s.id in ("lever", "stone_button", "oak_button")]
    if not inputs:
        pytest.skip("no inputs")
    assert_same(grid, _toggle_schedule(inputs, ORACLE_ORIGIN, random.Random(1), 100, 15), 100)


# ------------------------------------------------------------------------------------------------ random soups
DIRS = ("north", "east", "south", "west")
DIRS6 = DIRS + ("up", "down")


CRAFTER_ORIENTATIONS = ("down_east", "down_north", "up_west", "up_south", "west_up", "east_up", "north_up", "south_up")
CRAFTER_ITEMS = ("iron_ingot", "iron_ingot", "oak_planks", "birch_planks", "oak_log", "redstone", "iron_block", "stone")


def _crafter_data(rng: random.Random) -> dict:
    """Block entity data of a random crafter: a recipe-shaped grid or random items, some disabled slots."""
    kind = rng.choice(("iron", "sticks", "table", "log", "random", "random"))
    item = rng.choice(CRAFTER_ITEMS)
    if kind == "iron":
        slots, item = list(range(9)), rng.choice(("iron_ingot", "redstone"))
    elif kind == "sticks":
        col = rng.randrange(3)
        slots, item = [col + 3 * r for r in rng.choice(((0, 1), (1, 2)))], rng.choice(("oak_planks", "birch_planks"))
    elif kind == "table":
        slots, item = [s + o for s in (0, 3) for o in (0, 1)], "oak_planks"
        shift = rng.randrange(2)
        slots = [s + shift for s in slots]
    elif kind == "log":
        slots, item = [rng.randrange(9)], rng.choice(("oak_log", "iron_block"))
    else:
        slots = list(range(9)) if rng.random() < 0.3 else rng.sample(range(9), rng.randint(0, 5))
    stacks = [{"Slot": s, "id": f"minecraft:{item if rng.random() < 0.9 else rng.choice(CRAFTER_ITEMS)}",
               "count": rng.randint(1, 3)} for s in slots]
    free = [s for s in range(9) if s not in slots]
    disabled = [s for s in free if rng.random() < 0.3]
    return {"Items": stacks, "disabled_slots": disabled, "crafting_ticks_remaining": rng.choice((0, 0, 3))}


def _random_state(rng: random.Random) -> str:
    f, f6 = rng.choice(DIRS), rng.choice(DIRS6)
    side = lambda: rng.choice(("none", "side", "up"))  # noqa: E731
    return rng.choice([
        "stone", "stone", "stone", "glass", "redstone_block", "slime_block", "honey_block", "obsidian",
        "redstone_lamp[lit=false]", "target[power=0]", "note_block[instrument=harp,note=0,powered=false]",
        f"redstone_wire[east={side()},north={side()},power=0,south={side()},west={side()}]",
        f"redstone_wire[east={side()},north={side()},power=0,south={side()},west={side()}]",
        f"repeater[delay={rng.randint(1, 4)},facing={f},locked=false,powered=false]",
        f"comparator[facing={f},mode={rng.choice(('compare', 'subtract'))},powered=false]",
        "redstone_torch[lit=true]", f"redstone_wall_torch[facing={f},lit=true]",
        f"lever[face={rng.choice(('floor', 'wall'))},facing={f},powered=false]",
        f"stone_button[face=floor,facing={f},powered=false]",
        f"observer[facing={f6},powered=false]",
        f"piston[extended=false,facing={f6}]", f"sticky_piston[extended=false,facing={f6}]",
        "copper_bulb[lit=false,powered=false]",
        f"oak_trapdoor[facing={f},half=bottom,open=false,powered=false,waterlogged=false]",
        f"oak_fence_gate[facing={f},in_wall=false,open=false,powered=false]",
        f"powered_rail[powered=false,shape={rng.choice(('north_south', 'east_west'))},waterlogged=false]",
        f"activator_rail[powered=false,shape={rng.choice(('north_south', 'east_west'))},waterlogged=false]",
        f"hopper[enabled=true,facing={rng.choice(('down',) + DIRS)}]", "barrel[facing=up,open=false]",
        f"chest[facing={f},type={rng.choice(('single', 'left', 'right'))},waterlogged=false]",
        f"trapped_chest[facing={f},type={rng.choice(('single', 'left', 'right'))},waterlogged=false]",
        f"copper_chest[facing={f},type={rng.choice(('single', 'left', 'right'))},waterlogged=false]",
        f"dropper[facing={f6},triggered=false]", f"dispenser[facing={f6},triggered=false]",
        f"crafter[crafting=false,orientation={rng.choice(CRAFTER_ORIENTATIONS)},triggered=false]",
        f"crafter[crafting=false,orientation={rng.choice(CRAFTER_ORIENTATIONS)},triggered=false]",
        "daylight_detector[inverted=false,power=0]", "daylight_detector[inverted=true,power=9]",
        f"cake[bites={rng.randrange(7)}]", f"cake[bites={rng.randrange(7)}]",
        _SENSOR, _calibrated(f),
    ])


_SENSOR = "sculk_sensor[power=0,sculk_sensor_phase=inactive,waterlogged=false]"


def _calibrated(facing: str) -> str:
    return f"calibrated_sculk_sensor[facing={facing},power=0,sculk_sensor_phase=inactive,waterlogged=false]"


SOUP_SIZE = (6, 3, 6)


def _soup(seed: int) -> tuple[Grid, dict[int, list[Step]], int]:
    rng = random.Random(seed)
    sx, sy, sz = SOUP_SIZE
    grid = Grid((sx, sy + 1, sz))
    for x in range(sx):
        for z in range(sz):
            grid[Pos(x, 0, z)] = BlockState.parse("minecraft:stone")
            for y in range(1, sy + 1):
                if rng.random() < 0.55:
                    state = BlockState.parse(_random_state(rng))
                    grid[Pos(x, y, z)] = state
                    if state.id == "crafter":
                        grid.block_entities[Pos(x, y, z)] = _crafter_data(rng)
    ticks = 80
    schedule: dict[int, list[Step]] = {}
    usable = [p for p, s in grid.items() if s.id in ("lever", "stone_button", "note_block", "copper_bulb",
                                                      "oak_trapdoor", "oak_fence_gate", "comparator", "repeater",
                                                      "daylight_detector")]
    for _ in range(14):
        t = rng.randrange(ticks - 10)
        if usable and rng.random() < 0.6:
            target = rng.choice(usable)
            action = "step" if grid[target].id.endswith("_pressure_plate") and rng.random() < 0.8 else "use"
            schedule.setdefault(t, []).append((action, target + ORACLE_ORIGIN, None))
        else:
            pos = Pos(rng.randrange(sx), rng.randrange(1, sy + 1), rng.randrange(sz))
            state = BlockState.parse(rng.choice(["minecraft:air", "minecraft:redstone_block", _random_state(rng)]))
            schedule.setdefault(t, []).append(("setblock", pos + ORACLE_ORIGIN, state))
    return grid, schedule, ticks


@pytest.mark.parametrize("seed", range(150))
def test_random_soup(seed: int):
    grid, schedule, ticks = _soup(seed)
    assert_same(grid, schedule, ticks)


def _crafter_soup(seed: int) -> tuple[Grid, dict[int, list[Step]], int]:
    """Crafters next to levers, power blocks, hoppers, barrels and comparators (so that they really craft)."""
    rng = random.Random(1000 + seed)
    sx, sy, sz = SOUP_SIZE
    grid = Grid((sx, sy + 1, sz))
    palette = ["crafter", "crafter", "crafter", "barrel", "hopper", "comparator", "lever", "stone", "air", "air",
               "redstone_block", "chest"]
    for x in range(sx):
        for z in range(sz):
            grid[Pos(x, 0, z)] = BlockState.parse("minecraft:stone")
            for y in range(1, sy + 1):
                name = rng.choice(palette)
                if name == "crafter":
                    state = BlockState.parse(
                        f"crafter[crafting=false,orientation={rng.choice(CRAFTER_ORIENTATIONS)},triggered=false]")
                    grid.block_entities[Pos(x, y, z)] = _crafter_data(rng)
                elif name == "hopper":
                    state = BlockState.parse(f"hopper[enabled=true,facing={rng.choice(('down',) + DIRS)}]")
                elif name == "comparator":
                    state = BlockState.parse(f"comparator[facing={rng.choice(DIRS)},mode=compare,powered=false]")
                elif name == "lever":
                    state = BlockState.parse(f"lever[face=floor,facing={rng.choice(DIRS)},powered=false]")
                elif name == "barrel":
                    state = BlockState.parse("barrel[facing=up,open=false]")
                elif name == "chest":
                    state = BlockState.parse("chest[facing=north,type=single,waterlogged=false]")
                elif name == "air":
                    continue
                else:
                    state = BlockState.parse(name)
                grid[Pos(x, y, z)] = state
    ticks = 90
    levers = [p for p, s in grid.items() if s.id in ("lever", "comparator")]
    schedule: dict[int, list[Step]] = {}
    for _ in range(10):
        t = rng.randrange(ticks - 20)
        if levers and rng.random() < 0.6:
            schedule.setdefault(t, []).append(("use", rng.choice(levers) + ORACLE_ORIGIN, None))
        else:
            pos = Pos(rng.randrange(sx), rng.randrange(1, sy + 1), rng.randrange(sz))
            state = BlockState.parse(rng.choice(["minecraft:air", "minecraft:redstone_block", "minecraft:stone"]))
            schedule.setdefault(t, []).append(("setblock", pos + ORACLE_ORIGIN, state))
    return grid, schedule, ticks


@pytest.mark.parametrize("seed", range(80))
def test_crafter_soup(seed: int):
    grid, schedule, ticks = _crafter_soup(seed)
    assert_same(grid, schedule, ticks)


def _sculk_soup(seed: int) -> tuple[Grid, dict[int, list[Step]], int]:
    """Sculk sensors (also calibrated) among vibration sources, wool, carpets, amethyst, comparators and wire."""
    rng = random.Random(5000 + seed)
    sx, sy, sz = 8, 2, 8
    grid = Grid((sx, sy + 1, sz))
    palette = [
        _SENSOR, _SENSOR, _calibrated("north"), _calibrated("east"), _calibrated("south"), _calibrated("west"),
        "lever[face=floor,facing=north,powered=false]", "lever[face=floor,facing=east,powered=false]",
        "stone_button[face=floor,facing=north,powered=false]", "stone_pressure_plate[powered=false]",
        "note_block[instrument=harp,note=0,powered=false]", "daylight_detector[inverted=false,power=0]",
        "oak_trapdoor[facing=north,half=bottom,open=false,powered=false,waterlogged=false]",
        "oak_fence_gate[facing=north,in_wall=false,open=false,powered=false]",
        "dispenser[facing=up,triggered=false]", "dropper[facing=up,triggered=false]",
        "piston[extended=false,facing=up]", "sticky_piston[extended=false,facing=east]",
        "white_wool", "red_wool", "blue_carpet", "amethyst_block", "amethyst_block", "stone", "glass",
        "redstone_block", "air", "air", "air", "air", "air",
        f"comparator[facing={rng.choice(DIRS)},mode=compare,powered=false]",
        f"repeater[delay=1,facing={rng.choice(DIRS)},locked=false,powered=false]",
        "redstone_wire[east=none,north=none,power=0,south=none,west=none]",
    ]
    for x in range(sx):
        for z in range(sz):
            grid[Pos(x, 0, z)] = BlockState.parse("minecraft:stone")
            for y in range(1, sy + 1):
                name = rng.choice(palette)
                if name != "air":
                    grid[Pos(x, y, z)] = BlockState.parse(name)
    ticks = 120
    ids = ("lever", "stone_button", "note_block", "stone_pressure_plate", "oak_trapdoor", "oak_fence_gate",
           "daylight_detector", "comparator", "repeater")
    usable = [p for p, s in grid.items() if s.id in ids]
    schedule: dict[int, list[Step]] = {}
    for _ in range(12):
        t = rng.randrange(ticks - 40)
        if usable and rng.random() < 0.6:
            target = rng.choice(usable)
            action = "step" if grid[target].id.endswith("_pressure_plate") and rng.random() < 0.8 else "use"
            schedule.setdefault(t, []).append((action, target + ORACLE_ORIGIN, None))
        else:
            pos = Pos(rng.randrange(sx), rng.randrange(1, sy + 1), rng.randrange(sz))
            state = BlockState.parse(rng.choice(
                ["minecraft:air", "minecraft:redstone_block", "minecraft:white_wool", "minecraft:amethyst_block",
                 _SENSOR, _calibrated("north"), "minecraft:stone"]))
            schedule.setdefault(t, []).append(("setblock", pos + ORACLE_ORIGIN, state))
    return grid, schedule, ticks


@pytest.mark.parametrize("seed", range(120))
def test_sculk_soup(seed: int):
    grid, schedule, ticks = _sculk_soup(seed)
    assert_same(grid, schedule, ticks)


# ------------------------------------------------------------------------------------------------ static facts
def test_static_facts_of_all_states():
    """Rust state facts (conductor, sturdy faces, push reaction ...) equal the Python blocks for every state
    of every block in the block table, plus a few states with unusual or missing properties."""
    import itertools
    import json

    from redstone.model import Direction
    from redstone.sim.block import REGISTRY as PY_REGISTRY
    from redstone.sim import blockdata
    from redstone.sim.blockdata import DATA_FILE
    from redstone.sim.rust_world import REGISTRY as RS_REGISTRY

    table = json.loads(DATA_FILE.read_text(encoding="utf-8"))["blocks"]
    states = []
    for name, entry in table.items():
        props = entry.get("props", {})
        states.append(BlockState(name))  # all properties missing
        for combo in itertools.product(*props.values()):
            states.append(BlockState.of(name, dict(zip(props, combo))))
    states += [BlockState.parse(s) for s in ("minecraft:repeater[delay=9]", "minecraft:piston[foo=bar]",
                                             "minecraft:not_a_block", "minecraft:redstone_wire[power=3]")]
    mismatches = []
    for state in states:
        py, rs = PY_REGISTRY.get(state.name), RS_REGISTRY.get(state.name)
        checks = {
            "conductor": (py.is_conductor, rs.is_conductor),
            "signal_source": (py.is_signal_source, rs.is_signal_source),
            "block_entity": (py.has_block_entity, rs.has_block_entity),
            "analog_output": (py.has_analog_output_signal, rs.has_analog_output_signal),
            "push": (py.get_piston_push_reaction, rs.get_piston_push_reaction),
            "solid": (blockdata.is_solid, lambda st, rs=rs: rs._fact(st, "solid")),  # CakeBlock#canSurvive
        }
        for key, (f_py, f_rs) in checks.items():
            if f_py(state) != f_rs(state):
                mismatches.append(f"{state} {key}: python {f_py(state)}, rust {f_rs(state)}")
        for face in Direction:
            for support in ("full", "rigid", "center"):
                a, b = py.is_face_sturdy(state, face, support), rs.is_face_sturdy(state, face, support)
                if a != b:
                    mismatches.append(f"{state} sturdy {face} {support}: python {a}, rust {b}")
        if len(mismatches) > 20:
            break
    assert not mismatches, "\n".join(mismatches[:20])


# ------------------------------------------------------------------------------------------------ note block instrument
def test_note_block_instruments():
    below = ["stone", "sand", "glass", "white_wool", "gold_block", "clay", "packed_ice", "bone_block", "iron_block",
             "soul_sand", "pumpkin", "emerald_block", "hay_block", "glowstone", "copper_block", "oak_planks",
             "air", "zombie_head[rotation=0]", "zombie_wall_head[facing=north]", "white_carpet"]
    above = ["air", "zombie_head[rotation=0]", "player_head[rotation=4]", "creeper_wall_head[facing=east]", "stone"]
    grid = Grid((len(below), 4, 2))
    schedule: dict[int, list[Step]] = {}
    for x, name in enumerate(below):
        grid[Pos(x, 0, 0)] = BlockState.parse("minecraft:stone")
        grid[Pos(x, 1, 0)] = BlockState.parse(f"minecraft:{name}")
        grid[Pos(x, 2, 0)] = BlockState.parse("minecraft:note_block[instrument=harp,note=0,powered=false]")
        grid[Pos(x, 0, 1)] = BlockState.parse("minecraft:redstone_block")
        schedule.setdefault(2, []).append(("setblock", Pos(x, 3, 0) + ORACLE_ORIGIN,
                                           BlockState.parse(f"minecraft:{above[x % len(above)]}")))
        schedule.setdefault(4, []).append(("setblock", Pos(x, 1, 0) + ORACLE_ORIGIN,
                                           BlockState.parse(f"minecraft:{below[(x + 3) % len(below)]}")))
        schedule.setdefault(6, []).append(("use", Pos(x, 2, 0) + ORACLE_ORIGIN, None))
    assert_same(grid, schedule, 10)
