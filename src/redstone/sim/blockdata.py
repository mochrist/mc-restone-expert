"""Static block properties the simulator needs for arbitrary (non-redstone) blocks.

ASSUMPTION: these are heuristics based on block names. They should be replaced by a table
dumped from the 26.3 server (isRedstoneConductor, isFaceSturdy, push reaction per state).
See knowledge/UNVERIFIED.md.
"""

from __future__ import annotations

from ..model import BlockState, Direction

# Blocks whose collision shape is not a full cube, or that explicitly are not conductors
# (Blocks.java: `.isRedstoneConductor(Blocks::never)`).
_NON_CONDUCTOR_HINTS = (
    "glass", "slab", "stairs", "fence", "wall", "door", "trapdoor", "pane", "bars", "leaves", "carpet",
    "button", "pressure_plate", "rail", "torch", "sign", "banner", "ladder", "vine", "lantern", "chain",
    "candle", "head", "skull", "flower", "sapling", "grass", "fern", "bush", "coral", "kelp", "seagrass",
    "redstone", "repeater", "comparator", "observer", "piston", "lever", "lamp", "target", "daylight",
    "hopper", "chest", "slime", "honey", "ice", "snow", "cactus", "cake", "bed", "anvil", "bell",
    "lectern", "cauldron", "composter", "enchanting", "brewing", "grindstone", "stonecutter", "campfire",
    "scaffolding", "sculk_sensor", "sculk_shrieker", "dispenser", "dropper", "barrel", "note_block",
    "tnt", "beacon", "conduit", "farmland", "dirt_path", "soul_sand", "mud", "bulb", "crafter",
    "moving_piston", "spawner", "lightning_rod", "pot", "amethyst_cluster", "bud", "dripleaf", "azalea",
)
# Full, solid, conducting blocks that would otherwise match a hint above.
_CONDUCTOR_EXCEPTIONS = {
    "redstone_ore", "deepslate_redstone_ore", "packed_ice", "blue_ice", "snow_block", "honeycomb_block",
    "dispenser", "dropper", "note_block", "target", "redstone_lamp", "crafter", "tnt", "barrel",
    "dirt", "grass_block", "mud_bricks", "packed_mud", "copper_bulb",
}


def is_conductor(state: BlockState) -> bool:
    if state.is_air:
        return False
    name = state.id
    if name in _CONDUCTOR_EXCEPTIONS or name.endswith("copper_bulb"):
        return True
    return not any(h in name for h in _NON_CONDUCTOR_HINTS)


def is_face_sturdy(state: BlockState, face: Direction) -> bool:
    """Whether the given face can support attached blocks (torches, levers, wire, diodes)."""
    if state.is_air:
        return False
    name = state.id
    if name.endswith("_slab"):
        t = state.get("type")
        return t == "double" or (t == "top" and face is Direction.UP) or (t == "bottom" and face is Direction.DOWN)
    if name in ("piston", "sticky_piston"):
        return state.get("extended") != "true" or face.label != state.get("facing")
    return is_conductor(state) or name in ("observer", "redstone_block", "hopper") or "glass" in name and "pane" not in name


def push_reaction(state: BlockState) -> str:
    """PushReaction of a state: normal, destroy, block, ignore or push_only."""
    if state.is_air:
        return "ignore"
    name = state.id
    if name in ("obsidian", "crying_obsidian", "respawn_anchor", "reinforced_deepslate", "bedrock", "barrier",
                "end_portal_frame", "enchanting_table", "ender_chest", "beacon", "spawner", "moving_piston",
                "piston_head") or "command_block" in name or "chest" in name or name in ("barrel", "furnace",
                "hopper", "dispenser", "dropper", "jukebox", "lectern", "beehive", "bee_nest"):
        return "block"
    if name in ("piston", "sticky_piston"):
        return "block" if state.get("extended") == "true" else "normal"
    if any(h in name for h in ("torch", "button", "lever", "redstone_wire", "repeater", "comparator", "carpet",
                               "flower", "sapling", "pressure_plate", "rail", "door", "sign", "banner", "lantern",
                               "pot", "head", "skull", "cake", "ladder", "vine", "scaffolding")):
        return "destroy"
    if name in ("glazed_terracotta",) or name.endswith("glazed_terracotta"):
        return "push_only"
    return "normal"
