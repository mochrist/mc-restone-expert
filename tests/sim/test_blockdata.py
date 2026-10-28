"""Spot checks of the static block table dumped from the 26.3 server (src/redstone/sim/data/blocks_26.3.json)."""

from __future__ import annotations

import warnings

import pytest

from redstone.model import BlockState, Direction
from redstone.sim import blockdata as bd

S = BlockState.of


def test_conductors() -> None:
    assert bd.is_conductor(S("stone"))
    assert bd.is_conductor(S("soul_sand"))  # full-block predicate, although the collision shape is lower
    assert bd.is_conductor(S("oak_slab", type="double"))
    assert not bd.is_conductor(S("oak_slab", type="top"))
    assert not bd.is_conductor(S("glass"))
    assert not bd.is_conductor(S("observer", facing="up"))
    assert not bd.is_conductor(S("redstone_block"))  # isRedstoneConductor(Blocks::never)
    assert not bd.is_conductor(S("piston"))
    assert not bd.is_conductor(S("tnt"))
    assert not bd.is_conductor(S("copper_bulb"))
    assert bd.is_conductor(S("target"))
    assert not bd.is_conductor(S("air"))


def test_signal_sources_and_analog() -> None:
    assert bd.is_signal_source(S("redstone_block"))
    assert bd.is_signal_source(S("observer"))
    assert bd.is_signal_source(S("redstone_wire"))
    assert not bd.is_signal_source(S("stone"))
    assert bd.has_analog_output_signal(S("hopper"))
    assert bd.has_analog_output_signal(S("composter"))
    assert not bd.has_analog_output_signal(S("comparator"))
    assert not bd.has_analog_output_signal(S("stone"))


@pytest.mark.parametrize(
    ("slab_type", "up", "down"), [("top", True, False), ("bottom", False, True), ("double", True, True)]
)
def test_slab_faces(slab_type: str, up: bool, down: bool) -> None:
    slab = S("smooth_stone_slab", type=slab_type)
    assert bd.is_face_sturdy(slab, Direction.UP) is up
    assert bd.is_face_sturdy(slab, Direction.DOWN) is down
    assert bd.is_face_sturdy(slab, Direction.NORTH) is (slab_type == "double")


def test_support_types() -> None:
    hopper = S("hopper")
    assert not bd.is_face_sturdy(hopper, Direction.UP)
    assert bd.is_face_sturdy(hopper, Direction.UP, "rigid")  # repeaters may stand on hoppers
    assert bd.can_wire_survive_on(hopper)
    wall = S("cobblestone_wall")
    assert not bd.is_face_sturdy(wall, Direction.UP)
    assert bd.is_face_sturdy(wall, Direction.UP, "center")  # torches on walls
    assert bd.can_support_center(wall, Direction.UP)
    assert bd.is_face_sturdy(S("glass"), Direction.UP)
    with pytest.raises(ValueError):
        bd.is_face_sturdy(wall, Direction.UP, "half")


def test_pistons() -> None:
    extended = S("piston", extended="true", facing="north")
    assert bd.push_reaction(extended) == "block"
    assert bd.push_reaction(S("sticky_piston", extended="false", facing="up")) == "normal"
    assert not bd.is_face_sturdy(extended, Direction.NORTH)
    assert bd.is_face_sturdy(extended, Direction.SOUTH)
    assert bd.is_face_sturdy(S("piston", extended="false", facing="north"), Direction.NORTH)


def test_push_reactions() -> None:
    assert bd.push_reaction(S("air")) == "ignore"
    assert bd.push_reaction(S("stone")) == "normal"
    assert bd.push_reaction(S("obsidian")) == "block"
    assert bd.push_reaction(S("bedrock")) == "block"  # unbreakable
    assert bd.push_reaction(S("chest")) == "block"  # block entity
    assert bd.push_reaction(S("redstone_wire")) == "destroy"
    assert bd.push_reaction(S("repeater")) == "destroy"
    assert bd.push_reaction(S("pumpkin")) == "destroy"
    assert bd.push_reaction(S("rail")) == "normal"
    assert bd.push_reaction(S("oak_trapdoor")) == "normal"
    assert bd.push_reaction(S("white_glazed_terracotta")) == "push_only"
    assert bd.piston_push_reaction(S("white_glazed_terracotta")) == "push"
    assert bd.push_reaction(S("slime_block")) == "normal"


def test_wire_connections() -> None:
    assert bd.should_wire_connect_to(S("redstone_block"), Direction.NORTH)
    assert not bd.should_wire_connect_to(S("redstone_block"), None)
    assert bd.should_wire_connect_to(S("redstone_wire"), None)
    assert not bd.should_wire_connect_to(S("stone"), Direction.NORTH)
    assert bd.is_trapdoor(S("iron_trapdoor"))


def test_misc_flags() -> None:
    assert bd.is_air(S("cave_air"))
    assert bd.is_replaceable(S("short_grass"))
    assert not bd.is_replaceable(S("stone"))
    assert bd.has_block_entity(S("comparator"))
    assert bd.is_collision_shape_full_block(S("stone"))
    assert not bd.is_collision_shape_full_block(S("soul_sand"))
    assert bd.is_solid_render(S("stone")) and not bd.is_solid_render(S("glass"))


def test_default_state_and_partial_states() -> None:
    assert bd.default_state("minecraft:repeater") == S("repeater", delay=1, facing="north", locked=False,
                                                        powered=False)
    # missing properties are taken from the default state (slab default: bottom)
    assert bd.is_face_sturdy(S("oak_slab"), Direction.DOWN)
    assert not bd.is_face_sturdy(S("oak_slab"), Direction.UP)
    assert "facing" in bd.properties("minecraft:observer")


def test_fallbacks() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert not bd.is_face_sturdy(S("oak_slab", type="sideways"), Direction.UP)  # -> default (bottom)
        assert bd.is_conductor(S("somemod:fancy_stone"))  # heuristic
    assert len(caught) == 2
