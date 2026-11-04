"""Unit tests for pistons (knowledge/components/piston.md PIS-xxx, mechanics QC/BUD/ZT), built in small worlds."""

from pathlib import Path

import pytest

from redstone.model import BlockState, Direction, Pos
from redstone.sim import World, run
from redstone.sim.notes import notes_of
from redstone.sim.runner import ORACLE_ORIGIN
from redstone.verify import load_scenario

SCENARIOS = Path(__file__).parents[2] / "scenarios"

AIR = BlockState.parse("air")
STONE = BlockState.parse("stone")
RB = BlockState.parse("redstone_block")


def S(text: str) -> BlockState:
    return BlockState.parse(text)


def piston(facing="east", sticky=False, extended=False) -> BlockState:
    return S(f"{'sticky_piston' if sticky else 'piston'}[extended={str(extended).lower()},facing={facing}]")


def ticks(w: World, n: int) -> None:
    for _ in range(n):
        w.tick()


def extended(w: World, pos: Pos) -> bool:
    return w.get(pos).get_bool("extended")


def ids(w: World, *positions: Pos) -> list[str]:
    return [w.get(p).id for p in positions]


def notes(w: World) -> set[tuple[str, Pos]]:
    return {(n.kind, n.pos) for n in notes_of(w)}


P = Pos(0, 64, 0)  # piston position in most tests (inside the build limits)
E1, E2 = Pos(1, 64, 0), Pos(2, 64, 0)
BACK = Pos(-1, 64, 0)


def line_world(blocks: list[str], sticky: bool = False) -> World:
    """Piston at P facing east, the given blocks in front of it (x = 1, 2, ...)."""
    w = World()
    w.blocks[P] = piston(sticky=sticky)
    for i, b in enumerate(blocks, start=1):
        w.blocks[Pos(i, 64, 0)] = S(b)
    return w


# ---------------------------------------------------------------------- push limit and pushability
@pytest.mark.parametrize("n, moves", [(12, True), (13, False)])
def test_push_limit_is_12(n, moves):
    """PIS-013"""
    w = line_world(["stone"] * n)
    w.set_block(BACK, RB)
    ticks(w, 4)
    assert extended(w, P) is moves
    if moves:
        assert ids(w, E1) == ["piston_head"]
        assert all(w.get(Pos(x, 64, 0)) == STONE for x in range(2, 14))
    else:
        assert not w.block_events and all(w.get(Pos(x, 64, 0)) == STONE for x in range(1, 14))


@pytest.mark.parametrize("blocks", [
    ["obsidian"],  # IMMOVEABLE
    ["stone", "obsidian"],  # the line ends at an immovable block
    ["barrel"],  # block entity
    ["bedrock"],  # destroy speed -1
    ["piston_head[facing=east,short=false,type=normal]"],
])
def test_immovable_blocks_stop_the_piston(blocks):
    """PIS-014"""
    w = line_world(blocks)
    w.set_block(BACK, RB)
    ticks(w, 4)
    assert not extended(w, P)
    assert w.get(E1) == S(blocks[0])


def test_extended_piston_is_immovable_but_retracted_one_is_pushed():
    """PIS-014: a retracted piston counts as a normal block, an extended one does not move."""
    w = line_world(["piston[extended=false,facing=up]"])
    w.set_block(BACK, RB)
    ticks(w, 4)
    assert extended(w, P) and w.get(E2) == S("piston[extended=false,facing=up]")

    w = line_world(["piston[extended=true,facing=up]"])
    w.set_block(BACK, RB)
    ticks(w, 4)
    assert not extended(w, P)


def test_popped_block_ends_the_line_and_is_destroyed():
    """PIS-015: the torch is not counted towards the limit and is removed in the extend event."""
    w = line_world(["stone"] * 12 + ["torch"])
    w.set_block(BACK, RB)
    w.tick()
    assert extended(w, P)
    assert w.get(Pos(13, 64, 0)).id == "moving_piston"  # the last stone moves into the torch's place
    ticks(w, 3)
    assert w.get(Pos(13, 64, 0)) == STONE


# ---------------------------------------------------------------------- slime and honey
def slime_world(extra: dict[tuple[int, int, int], str], sticky=False) -> World:
    w = World()
    w.blocks[P] = piston(sticky=sticky)
    w.blocks[E1] = S("slime_block")
    for (x, y, z), b in extra.items():
        w.blocks[Pos(x, y, z)] = S(b)
    return w


def test_slime_carries_side_blocks_but_not_honey():
    """PIS-016"""
    w = slime_world({(1, 64, -1): "stone", (1, 65, 0): "glass", (1, 64, 1): "honey_block"})
    w.set_block(BACK, RB)
    ticks(w, 4)
    assert extended(w, P)
    assert w.get(E2).id == "slime_block"
    assert w.get(Pos(2, 64, -1)) == STONE and w.get(Pos(2, 65, 0)) == S("glass")
    assert w.get(Pos(1, 64, 1)).id == "honey_block"  # slime and honey do not stick
    assert w.get(Pos(1, 64, -1)).is_air and w.get(Pos(1, 65, 0)).is_air


def test_blocks_carried_by_slime_count_towards_the_limit():
    """PIS-016: slime + 11 stones in line = 12 moves; one stone stuck to the side makes it 13."""
    line = {(x, 64, 0): "stone" for x in range(2, 13)}
    w = slime_world(line)
    w.set_block(BACK, RB)
    ticks(w, 2)
    assert extended(w, P)

    w = slime_world({**line, (1, 64, 1): "stone"})
    w.set_block(BACK, RB)
    ticks(w, 2)
    assert not extended(w, P)


def test_sticky_piston_pulls_slime_structure_back():
    w = slime_world({(1, 64, -1): "stone"}, sticky=True)
    w.set_block(BACK, RB)
    ticks(w, 4)
    assert w.get(E2).id == "slime_block" and w.get(Pos(2, 64, -1)) == STONE
    w.set_block(BACK, AIR)
    ticks(w, 4)
    assert not extended(w, P)
    assert w.get(E1).id == "slime_block" and w.get(Pos(1, 64, -1)) == STONE
    assert w.get(E2).is_air and w.get(Pos(2, 64, -1)).is_air


# ---------------------------------------------------------------------- sticky pulses (PIS-004, PIS-012, PIS-018)
def pulse(pulse_ticks: int, sticky: bool) -> World:
    """Player places the power at game time 0 and removes it after ``pulse_ticks`` ticks."""
    w = line_world(["stone"], sticky=sticky)
    w.set_block(BACK, RB)
    ticks(w, pulse_ticks)
    w.set_block(BACK, AIR)
    ticks(w, 6)
    return w


@pytest.mark.parametrize("n, dropped", [(1, True), (2, True), (3, False), (4, False)])
def test_sticky_piston_drops_its_block_on_short_pulses(n, dropped):
    w = pulse(n, sticky=True)
    assert not extended(w, P)
    if dropped:
        assert w.get(E1).is_air and w.get(E2) == STONE
        assert ("piston_spit", P) in notes(w)
    else:
        assert w.get(E1) == STONE and w.get(E2).is_air
        assert ("piston_spit", P) not in notes(w)


def test_drop_event_is_chosen_while_the_block_is_still_moving():
    w = line_world(["stone"], sticky=True)
    w.set_block(BACK, RB)
    w.tick()  # extend event in tick 1, block entity progress 0 -> 0.5
    w.set_block(BACK, AIR)
    assert [ev.a for ev in w.block_events] == [2]  # TRIGGER_DROP
    w.tick()
    assert w.get(E2) == STONE  # finalTick placed it at once


def test_normal_piston_pushes_to_the_end_on_a_short_pulse():
    w = pulse(1, sticky=False)
    assert not extended(w, P)
    assert w.get(E1).is_air and w.get(E2) == STONE
    assert not notes(w)


# ---------------------------------------------------------------------- start delay (PIS-019)
def test_player_action_moves_in_the_next_tick():
    w = line_world(["stone"])
    w.set_block(BACK, RB)
    assert not extended(w, P) and len(w.block_events) == 1
    w.tick()
    assert extended(w, P) and w.get(E2).id == "moving_piston"


def test_power_from_a_scheduled_tick_moves_in_the_same_tick():
    w = line_world(["stone"])
    for x in (-2, -1):
        w.blocks[Pos(x, 63, 0)] = STONE
    rep = Pos(-1, 64, 0)
    w.blocks[rep] = S("repeater[delay=1,facing=west,locked=false,powered=false]")
    w.set_block(Pos(-2, 64, 0), RB)
    history = []
    for _ in range(3):
        w.tick()
        history.append((w.game_time, w.get(rep).get_bool("powered"), extended(w, P)))
    assert history == [(1, False, False), (2, True, True), (3, True, True)]


def test_power_from_the_block_entity_phase_moves_in_the_next_tick():
    """Piston A pushes a redstone block next to piston B; it arrives in the block entity phase."""
    w = World()
    a, b = Pos(0, 64, 5), Pos(3, 64, 5)
    w.blocks[a] = piston()
    w.blocks[Pos(1, 64, 5)] = RB
    w.blocks[b] = piston()
    w.set_block(Pos(-1, 64, 5), RB)
    arrived = b_extended = None
    for _ in range(8):
        w.tick()
        if arrived is None and w.get(Pos(2, 64, 5)) == RB:
            arrived = w.game_time
            assert not extended(w, b) and len(w.block_events) == 1
        if b_extended is None and extended(w, b):
            b_extended = w.game_time
    assert arrived == 3  # extend event in tick 1, the block arrives 2 gt later (PIS-007)
    assert b_extended == arrived + 1


# ---------------------------------------------------------------------- quasi-connectivity and BUD
def qc_world() -> World:
    w = World()
    w.blocks[P] = piston()
    w.set_block(Pos(0, 66, 0), RB)  # two above: powers the position above the piston
    return w


def test_qc_power_needs_a_block_update():
    """QC-007, BUD-004: the piston is quasi-powered but only extends after an update at its position."""
    w = qc_world()
    base = w.block(w.get(P))
    assert base.has_qc_signal(w, P) and not base.has_direct_signal(w, P, Direction.EAST)
    ticks(w, 5)
    assert not extended(w, P) and not w.block_events
    assert ("bud", P) in notes(w)  # resting BUD state (state check)

    w = qc_world()
    ticks(w, 3)
    w.set_block(Pos(0, 64, 1), STONE)  # block update next to the piston
    w.tick()
    assert extended(w, P)
    assert {("quasi_connectivity", P), ("bud", P)} <= notes(w)
    assert [n.detail for n in notes_of(w) if n.kind == "bud"] == [
        "fuhr erst nach einem Block-Update ohne Leistungsänderung aus"]


def test_qc_piston_stays_extended_without_update():
    """QC-008"""
    w = qc_world()
    w.set_block(Pos(0, 64, 1), STONE)
    ticks(w, 4)
    w.set_block(Pos(0, 66, 0), AIR)
    ticks(w, 4)
    assert extended(w, P)
    w.set_block(Pos(0, 64, -1), S("glass"))  # update from a non-conductor
    ticks(w, 4)
    assert not extended(w, P)
    assert {n.detail for n in notes_of(w) if n.kind == "bud"} == {
        "fuhr erst nach einem Block-Update ohne Leistungsänderung aus"}  # one note per piston


def test_unpowered_but_extended_piston_is_noted_as_bud():
    w = qc_world()
    w.set_block(Pos(0, 64, 1), STONE)
    ticks(w, 4)
    w.blocks.pop(Pos(0, 66, 0))  # power gone without any update
    assert [n.detail for n in notes_of(w) if n.kind == "bud" and n.pos == P] == [
        "fuhr erst nach einem Block-Update ohne Leistungsänderung aus"]
    w2 = line_world(["stone"])
    w2.set_block(BACK, RB)
    ticks(w2, 4)
    w2.blocks.pop(BACK)
    assert [(n.kind, n.detail) for n in notes_of(w2)] == [("bud", "unbestromt, aber ausgefahren")]


@pytest.mark.parametrize("block", ["glass", "stone"])
def test_retraction_after_unrelated_update_is_a_bud(block):
    w = line_world(["stone"])
    w.set_block(BACK, RB)
    ticks(w, 4)
    w.blocks.pop(BACK)  # power gone without any update
    w.set_block(Pos(0, 64, -1), S(block))  # update source: the air that was there before
    ticks(w, 4)
    assert not extended(w, P)
    assert [(n.kind, n.detail) for n in notes_of(w)] == [
        ("bud", "blieb unbestromt ausgefahren, bis ein Block-Update kam")]


def test_removing_a_powered_conductor_is_not_a_bud():
    """The removed stone carried the repeater's power into the piston: an ordinary retraction."""
    w = line_world(["stone"])
    w.blocks[BACK] = STONE
    w.blocks[Pos(-2, 63, 0)] = STONE
    w.blocks[Pos(-2, 64, 0)] = S("repeater[delay=1,facing=west,locked=false,powered=false]")
    w.set_block(Pos(-3, 64, 0), RB)
    ticks(w, 4)
    assert extended(w, P)
    w.set_block(BACK, AIR)
    ticks(w, 4)
    assert not extended(w, P)
    assert not notes(w)


def test_directly_powered_piston_has_no_qc_or_bud_note():
    w = line_world(["stone"])
    w.set_block(BACK, RB)
    ticks(w, 4)
    w.set_block(BACK, AIR)
    ticks(w, 4)
    assert not extended(w, P)
    assert not notes(w)


def test_qc_by_a_repeater_is_noted_without_bud():
    """A repeater pointing into the position above the piston powers it by QC and updates the piston itself
    (it updates the neighbours of the block in front)."""
    w = World()
    w.blocks[P] = piston()
    w.blocks[Pos(-1, 64, 0)] = STONE  # carries the repeater; the repeater does not power it
    w.blocks[Pos(-1, 65, 0)] = S("repeater[delay=1,facing=west,locked=false,powered=false]")
    w.set_block(Pos(-2, 65, 0), RB)
    ticks(w, 2)
    assert extended(w, P)
    assert notes(w) == {("quasi_connectivity", P)}


# ---------------------------------------------------------------------- 0-tick (ZT-003/004/005)
def zero_tick_world(sticky: bool) -> tuple[World, Pos, Pos]:
    """Lever powers B directly and S (facing up, below the lever) by QC. S pops the lever in its extend event,
    which runs after B's, so B extends and loses power in the same block-event phase."""
    w = World()
    s, lever, b = Pos(1, 64, 0), Pos(1, 65, 0), Pos(2, 65, 0)
    w.blocks[s] = piston("up")
    w.blocks[lever] = S("lever[face=wall,facing=north,powered=false]")
    w.blocks[Pos(1, 65, 1)] = STONE
    w.blocks[b] = piston("east", sticky=sticky)
    w.blocks[Pos(3, 65, 0)] = STONE
    w.block(w.get(lever)).use_without_item(w, lever, w.get(lever))
    return w, s, b


def test_zero_tick_sticky_piston_teleports_the_block():
    w, s, b = zero_tick_world(sticky=True)
    w.tick()
    assert w.get(Pos(1, 65, 0)).id == "moving_piston"  # S pushed the (popped) lever position
    assert w.get(b).id == "moving_piston"  # B is already retracting
    assert w.get(Pos(4, 65, 0)) == STONE  # placed at once by finalTick
    assert w.get(Pos(3, 65, 0)).is_air
    assert {("zero_tick", b), ("piston_spit", b), ("quasi_connectivity", s)} <= notes(w)


def test_zero_tick_normal_piston_block_keeps_moving():
    w, s, b = zero_tick_world(sticky=False)
    w.tick()
    assert w.get(Pos(4, 65, 0)).id == "moving_piston"
    ticks(w, 3)
    assert w.get(Pos(4, 65, 0)) == STONE and w.get(b) == piston("east")
    assert ("zero_tick", b) in notes(w) and ("piston_spit", b) not in notes(w)


def test_ordinary_retraction_is_not_a_zero_tick():
    w = pulse(1, sticky=True)
    assert ("zero_tick", P) not in notes(w)


# ---------------------------------------------------------------------- notes from the scenarios
def _scenario_notes(name: str) -> set[tuple[str, tuple[int, int, int]]]:
    _, w = run(load_scenario(SCENARIOS / f"{name}.yaml"))
    return {(n.kind, tuple(n.pos - ORACLE_ORIGIN)) for n in notes_of(w)}


def test_notes_zero_tick_scenario():
    assert _scenario_notes("zero-tick-piston") == {
        ("quasi_connectivity", (1, 1, 0)), ("quasi_connectivity", (1, 1, 3)),
        ("zero_tick", (2, 2, 0)), ("zero_tick", (2, 2, 3)), ("piston_spit", (2, 2, 0)),
    }


def test_notes_sticky_pulse_scenario():
    """Only the 1 gt and 2 gt sticky pulses drop their block."""
    assert _scenario_notes("sticky-pulse-lengths") == {("piston_spit", (1, 1, 0)), ("piston_spit", (1, 1, 2))}


def test_notes_qc_bud_scenario():
    assert _scenario_notes("qc-bud") == {("quasi_connectivity", (1, 1, 0)), ("bud", (1, 1, 0))}
