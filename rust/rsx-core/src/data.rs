//! Static block properties from `blocks_26.3.json` and item stack sizes (mirrors redstone.sim.blockdata
//! and the stack table of redstone.sim.blocks.container). Loaded once per process by `init`.

use rustc_hash::FxHashMap;
use serde_json::Value;
use std::sync::OnceLock;

pub const PUSH_PULL: u8 = 0;
pub const PUSH: u8 = 1;
pub const POPPED: u8 = 2;
pub const IMMOVEABLE: u8 = 3;
pub const IGNORE_ENTITY: u8 = 4;

pub enum Val<T> {
    One(T),
    Per(Vec<T>),
}

impl<T: Copy> Val<T> {
    #[inline]
    pub fn at(&self, index: usize) -> T {
        match self {
            Val::One(v) => *v,
            Val::Per(v) => v[index],
        }
    }
}

pub struct BlockEntry {
    /// Property names and allowed values in the game's order (first = most significant digit).
    pub props: Vec<(String, Vec<String>)>,
    pub default: usize,
    pub conductor: Val<bool>,
    /// Face masks (bit = Direction index) for SupportType FULL, RIGID, CENTER.
    pub sturdy: [Val<u8>; 3],
    pub push: Val<u8>,
    pub block_entity: Val<bool>,
    pub unbreakable: Val<bool>,
}

pub struct BlockData {
    pub blocks: FxHashMap<String, BlockEntry>,
    pub stack_sizes: FxHashMap<String, i32>,
}

static DATA: OnceLock<BlockData> = OnceLock::new();

pub fn is_initialized() -> bool {
    DATA.get().is_some()
}

pub fn data() -> &'static BlockData {
    DATA.get().expect("rsx_core.init(blocks_json, stack_sizes_json) was not called")
}

fn push_code(s: &str) -> Result<u8, String> {
    Ok(match s {
        "push_pull" => PUSH_PULL,
        "push" => PUSH,
        "popped" => POPPED,
        "immoveable" => IMMOVEABLE,
        "ignore_entity" => IGNORE_ENTITY,
        other => return Err(format!("unknown push reaction {other:?}")),
    })
}

fn val<T>(v: &Value, key: &str, conv: impl Fn(&Value) -> Result<T, String>) -> Result<Val<T>, String> {
    let item = v.get(key).ok_or_else(|| format!("missing key {key}"))?;
    match item {
        Value::Array(items) => Ok(Val::Per(items.iter().map(&conv).collect::<Result<_, _>>()?)),
        single => Ok(Val::One(conv(single)?)),
    }
}

fn as_bool(v: &Value) -> Result<bool, String> {
    v.as_bool().ok_or_else(|| format!("expected bool, got {v}"))
}

fn as_mask(v: &Value) -> Result<u8, String> {
    v.as_u64().map(|x| x as u8).ok_or_else(|| format!("expected int, got {v}"))
}

fn as_push(v: &Value) -> Result<u8, String> {
    push_code(v.as_str().ok_or_else(|| format!("expected string, got {v}"))?)
}

pub fn init(blocks_json: &str, stacks_json: &str) -> Result<(), String> {
    if is_initialized() {
        return Ok(());
    }
    let root: Value = serde_json::from_str(blocks_json).map_err(|e| e.to_string())?;
    let table = root.get("blocks").and_then(Value::as_object).ok_or("no blocks table")?;
    let mut blocks = FxHashMap::default();
    for (name, entry) in table {
        let mut props = Vec::new();
        if let Some(p) = entry.get("props").and_then(Value::as_object) {
            for (pname, values) in p {
                let values = values
                    .as_array()
                    .ok_or("property values must be a list")?
                    .iter()
                    .map(|v| v.as_str().map(str::to_owned).ok_or("property value must be a string"))
                    .collect::<Result<Vec<_>, _>>()?;
                props.push((pname.clone(), values));
            }
        }
        let default = entry.get("default").and_then(Value::as_u64).unwrap_or(0) as usize;
        let v = entry.get("v").ok_or("no values")?;
        let be = |key: &str| val(v, key, as_bool).map_err(|e| format!("{name}: {e}"));
        let mask = |key: &str| val(v, key, as_mask).map_err(|e| format!("{name}: {e}"));
        blocks.insert(
            name.clone(),
            BlockEntry {
                props,
                default,
                conductor: be("conductor")?,
                sturdy: [mask("sturdy_full")?, mask("sturdy_rigid")?, mask("sturdy_center")?],
                push: val(v, "push", as_push).map_err(|e| format!("{name}: {e}"))?,
                block_entity: be("block_entity")?,
                unbreakable: be("unbreakable")?,
            },
        );
    }
    let stacks: Value = serde_json::from_str(stacks_json).map_err(|e| e.to_string())?;
    let mut stack_sizes = FxHashMap::default();
    if let Some(obj) = stacks.as_object() {
        for (size, names) in obj {
            let Ok(size) = size.parse::<i32>() else { continue };
            if let Some(names) = names.as_array() {
                for n in names {
                    if let Some(n) = n.as_str() {
                        stack_sizes.insert(format!("minecraft:{n}"), size);
                    }
                }
            }
        }
    }
    let _ = DATA.set(BlockData { blocks, stack_sizes });
    Ok(())
}

/// Default max stack size of an item (1, 16 or 64).
pub fn item_max_stack_size(item: &str) -> i32 {
    let sizes = &data().stack_sizes;
    let found = if item.contains(':') { sizes.get(item) } else { sizes.get(&format!("minecraft:{item}")) };
    found.copied().unwrap_or(64)
}

/// Raw table values of one block state.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct StateData {
    pub known: bool,
    pub conductor: bool,
    pub sturdy: [u8; 3],
    pub push: u8,
    pub block_entity: bool,
    pub unbreakable: bool,
}

/// blockdata._lookup: state index is mixed radix over the listed properties; missing properties take the
/// default state's value, unknown properties or values fall back to the default state.
fn state_index(entry: &BlockEntry, props: &[(&str, &str)]) -> usize {
    if entry.props.is_empty() {
        return 0;
    }
    let mut used = 0usize;
    let mut index = 0usize;
    let mut stride = 1usize;
    for (name, values) in entry.props.iter().rev() {
        let n = values.len();
        let digit = match props.iter().find(|(k, _)| k == name) {
            None => (entry.default / stride) % n,
            Some((_, value)) => {
                used += 1;
                match values.iter().position(|v| v == value) {
                    Some(d) => d,
                    None => return entry.default,
                }
            }
        };
        index += digit * stride;
        stride *= n;
    }
    if used != props.len() {
        return entry.default;
    }
    index
}

pub fn block_id(name: &str) -> &str {
    name.strip_prefix("minecraft:").unwrap_or(name)
}

pub fn is_air_name(name: &str) -> bool {
    matches!(name, "minecraft:air" | "minecraft:cave_air" | "minecraft:void_air")
}

pub fn lookup(name: &str, props: &[(&str, &str)]) -> StateData {
    match data().blocks.get(name) {
        Some(entry) => {
            let i = state_index(entry, props);
            StateData {
                known: true,
                conductor: entry.conductor.at(i),
                sturdy: [entry.sturdy[0].at(i), entry.sturdy[1].at(i), entry.sturdy[2].at(i)],
                push: entry.push.at(i),
                block_entity: entry.block_entity.at(i),
                unbreakable: entry.unbreakable.at(i),
            }
        }
        None => {
            let mut mask = 0u8;
            for face in 0..6 {
                if guess_face_sturdy(name, props, face) {
                    mask |= 1 << face;
                }
            }
            StateData {
                known: false,
                conductor: guess_conductor(name),
                sturdy: [mask; 3],
                push: guess_push_reaction(name),
                block_entity: false,
                unbreakable: false,
            }
        }
    }
}

/// `blockdata.is_conductor(blockdata.default_state(name))`; None for a block missing from the table.
pub fn default_state_is_conductor(name: &str) -> Option<bool> {
    data().blocks.get(name).map(|e| e.conductor.at(e.default))
}

// --- heuristics for blocks missing from the table ---------------------------------------------

const NON_CONDUCTOR_HINTS: &[&str] = &[
    "glass", "slab", "stairs", "fence", "wall", "door", "trapdoor", "pane", "bars", "leaves", "carpet",
    "button", "pressure_plate", "rail", "torch", "sign", "banner", "ladder", "vine", "lantern", "chain",
    "candle", "head", "skull", "flower", "sapling", "grass", "fern", "bush", "coral", "kelp", "seagrass",
    "redstone", "repeater", "comparator", "observer", "piston", "lever", "lamp", "target", "daylight",
    "hopper", "chest", "slime", "honey", "ice", "snow", "cactus", "cake", "bed", "anvil", "bell",
    "lectern", "cauldron", "composter", "enchanting", "brewing", "grindstone", "stonecutter", "campfire",
    "scaffolding", "sculk_sensor", "sculk_shrieker", "dispenser", "dropper", "barrel", "note_block",
    "tnt", "beacon", "conduit", "farmland", "dirt_path", "soul_sand", "mud", "bulb", "crafter",
    "moving_piston", "spawner", "lightning_rod", "pot", "amethyst_cluster", "bud", "dripleaf", "azalea",
];

const CONDUCTOR_EXCEPTIONS: &[&str] = &[
    "redstone_ore", "deepslate_redstone_ore", "packed_ice", "blue_ice", "snow_block", "honeycomb_block",
    "dispenser", "dropper", "note_block", "target", "redstone_lamp", "crafter", "tnt", "barrel",
    "dirt", "grass_block", "mud_bricks", "packed_mud", "copper_bulb",
];

pub fn guess_conductor(name: &str) -> bool {
    if is_air_name(name) {
        return false;
    }
    let id = block_id(name);
    if CONDUCTOR_EXCEPTIONS.contains(&id) || id.ends_with("copper_bulb") {
        return true;
    }
    !NON_CONDUCTOR_HINTS.iter().any(|h| id.contains(h))
}

fn guess_face_sturdy(name: &str, props: &[(&str, &str)], face: usize) -> bool {
    if is_air_name(name) {
        return false;
    }
    let id = block_id(name);
    if id.ends_with("_slab") {
        let t = props.iter().find(|(k, _)| *k == "type").map(|(_, v)| *v);
        return t == Some("double") || (t == Some("top") && face == 1) || (t == Some("bottom") && face == 0);
    }
    guess_conductor(name) || (id.contains("glass") && !id.contains("pane"))
}

fn guess_push_reaction(name: &str) -> u8 {
    if is_air_name(name) {
        return PUSH_PULL; // "ignore" maps to push_pull
    }
    let id = block_id(name);
    if id.contains("command_block")
        || id.contains("chest")
        || matches!(id, "obsidian" | "crying_obsidian" | "bedrock" | "barrier")
    {
        return IMMOVEABLE;
    }
    const DESTROY: &[&str] = &[
        "torch", "button", "lever", "redstone_wire", "repeater", "comparator", "carpet", "flower", "sapling",
        "pressure_plate", "rail", "door", "sign", "banner",
    ];
    if DESTROY.iter().any(|h| id.contains(h)) {
        return POPPED;
    }
    if id.ends_with("glazed_terracotta") {
        return PUSH;
    }
    PUSH_PULL
}
