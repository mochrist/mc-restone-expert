"""Unit tests for dispenser, dropper, hopper and container helpers (26.3 code, knowledge DDH-*)."""

from redstone.model import BlockState, Pos
from redstone.sim import World
from redstone.sim.blocks.container import add_item as _py_add_item
from redstone.sim.blocks.container import container_max_stack, item_max_stack_size
from redstone.sim.blocks.dispenser_hopper import HopperBlockEntity

P = Pos(0, 10, 0)


def add_item(world: World, source, container, item: str, count: int = 1) -> int:
    """container.add_item on either core (the Rust core takes block entity ids)."""
    if hasattr(world, "_c"):
        return world._c.add_item(None if source is None else source._id, container._id, item, count)
    return _py_add_item(world, source, container, item, count)


def _is_hopper(be) -> bool:
    return isinstance(be, HopperBlockEntity) or getattr(be, "kind", None) == "hopper"


def _place(world: World, pos: Pos, state: str, items: list[tuple[int, str, int]] = (), **extra) -> object:
    world.set_block(pos, BlockState.parse(state), 818 | 2)
    be = world.get_block_entity(pos)
    if be is not None:
        be.load({"Items": [{"Slot": s, "id": i, "count": c} for s, i, c in items], **extra})
    return be


def test_item_stack_sizes():
    assert item_max_stack_size("minecraft:stone") == 64
    assert item_max_stack_size("ender_pearl") == 16
    assert item_max_stack_size("minecraft:iron_sword") == 1
    assert item_max_stack_size("minecraft:red_shulker_box") == 1
    assert item_max_stack_size("minecraft:white_banner") == 16
    assert container_max_stack("minecraft:stone") == 64


def test_add_item_merges_then_fills_free_slot():
    w = World()
    barrel = _place(w, P, "barrel[facing=up,open=false]", [(0, "minecraft:stone", 63)])
    assert add_item(w, None, barrel, "minecraft:stone", 2) == 0
    assert barrel.items == {0: ["minecraft:stone", 64], 1: ["minecraft:stone", 1]}


def test_hopper_pulls_from_container_above_and_sets_cooldown():
    w = World()
    hopper = _place(w, P, "hopper[enabled=true,facing=down]")
    barrel = _place(w, Pos(0, 11, 0), "barrel[facing=up,open=false]", [(3, "minecraft:stone", 2)])
    w.tick()
    assert hopper.items == {0: ["minecraft:stone", 1]}
    assert barrel.items == {3: ["minecraft:stone", 1]}
    assert hopper.cooldown_time == 8
    for _ in range(7):
        w.tick()
    assert barrel.items == {3: ["minecraft:stone", 1]}
    w.tick()
    assert barrel.items == {}


def test_hopper_does_not_push_into_full_container():
    w = World()
    hopper = _place(w, P, "hopper[enabled=true,facing=east]", [(0, "minecraft:stone", 1)])
    target = _place(w, Pos(1, 10, 0), "hopper[enabled=false,facing=down]",
                    [(i, "minecraft:iron_sword", 1) for i in range(5)])
    w.tick()
    assert hopper.items == {0: ["minecraft:stone", 1]}
    assert hopper.cooldown_time == 0  # nothing moved: no cooldown
    assert len(target.items) == 5


def test_custom_cooldown_is_kept_on_receive():
    w = World()
    target = _place(w, P, "hopper[enabled=true,facing=down]", TransferCooldown=20)
    assert _is_hopper(target)
    add_item(w, None, target, "minecraft:stone")
    assert target.cooldown_time == 20


def test_empty_dispenser_does_nothing_but_triggers():
    w = World()
    _place(w, P, "dispenser[facing=down,triggered=false]")
    w.set_block(Pos(1, 10, 0), BlockState.parse("redstone_block"))
    assert w.get(P).get_bool("triggered")
    for _ in range(5):
        w.tick()
    assert w.get_block_entity(P).items == {}


def test_hopper_lock_has_no_quasi_connectivity():
    w = World()
    _place(w, P, "hopper[enabled=true,facing=down]")
    w.set_block(Pos(1, 11, 0), BlockState.parse("redstone_block"))  # next to the position above the hopper
    w.set_block(Pos(-1, 10, 0), BlockState.parse("stone"))  # block update at the hopper
    assert w.get(P).get_bool("enabled")
    w.set_block(Pos(1, 10, 0), BlockState.parse("redstone_block"))
    assert not w.get(P).get_bool("enabled")
