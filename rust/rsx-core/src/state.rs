//! Interned block states. A state is a block name plus sorted `(key, value)` properties, exactly like
//! redstone.model.BlockState: states with different property sets are different states, and missing
//! properties get their defaults where the behaviour reads them.

use crate::common::*;
use crate::data;
use rustc_hash::FxHashMap;
use std::sync::OnceLock;

pub type StateId = u32;
pub type BlockId = u16;
/// `minecraft:air` without properties is always state 0 and block 0.
pub const AIR: StateId = 0;
pub const AIR_BLOCK: BlockId = 0;

#[derive(Copy, Clone, PartialEq, Eq, Hash, Debug, PartialOrd, Ord)]
pub struct Sym(pub u16);

const NUM_SYMS: u16 = 32;

macro_rules! define_syms {
    ($($id:ident => $s:literal),* $(,)?) => {
        #[allow(non_camel_case_types, clippy::upper_case_acronyms)]
        #[repr(u16)]
        enum SymIdx { $($id),* }
        /// Property keys and values known at compile time. `Sym(n)` for n < 32 is the decimal string of n.
        #[allow(dead_code)]
        pub mod sym {
            use super::{Sym, SymIdx, NUM_SYMS};
            $(pub const $id: Sym = Sym(SymIdx::$id as u16 + NUM_SYMS);)*
        }
        const KNOWN_SYMS: &[&str] = &[$($s),*];
    };
}

define_syms! {
    TRUE => "true", FALSE => "false",
    INVERTED => "inverted",
    POWERED => "powered", POWER => "power", LIT => "lit", FACING => "facing", FACE => "face",
    NORTH => "north", EAST => "east", SOUTH => "south", WEST => "west", UP => "up", DOWN => "down",
    NONE => "none", SIDE => "side",
    FLOOR => "floor", CEILING => "ceiling", WALL => "wall",
    DELAY => "delay", LOCKED => "locked", MODE => "mode", COMPARE => "compare", SUBTRACT => "subtract",
    EXTENDED => "extended", TYPE => "type", NORMAL => "normal", STICKY => "sticky", SHORT => "short",
    TRIGGERED => "triggered", ENABLED => "enabled", OPEN => "open", HALF => "half", LOWER => "lower",
    UPPER => "upper", IN_WALL => "in_wall", SHAPE => "shape", NOTE => "note", INSTRUMENT => "instrument",
    HAS_BOOK => "has_book", WATERLOGGED => "waterlogged", ORIENTATION => "orientation", CRAFTING => "crafting",
    NORTH_SOUTH => "north_south", EAST_WEST => "east_west",
    ASCENDING_EAST => "ascending_east", ASCENDING_WEST => "ascending_west",
    ASCENDING_NORTH => "ascending_north", ASCENDING_SOUTH => "ascending_south",
    SOUTH_EAST => "south_east", SOUTH_WEST => "south_west", NORTH_WEST => "north_west",
    NORTH_EAST => "north_east",
    SCULK_SENSOR_PHASE => "sculk_sensor_phase", INACTIVE => "inactive", ACTIVE => "active",
    COOLDOWN => "cooldown",
    HARP => "harp", LEFT => "left", RIGHT => "right", SINGLE => "single", BITES => "bites",
}

fn known_syms() -> &'static FxHashMap<&'static str, Sym> {
    static MAP: OnceLock<FxHashMap<&'static str, Sym>> = OnceLock::new();
    MAP.get_or_init(|| {
        let mut m = FxHashMap::default();
        for n in 0..NUM_SYMS {
            let s: &'static str = Box::leak(n.to_string().into_boxed_str());
            m.insert(s, Sym(n));
        }
        for (i, s) in KNOWN_SYMS.iter().enumerate() {
            m.insert(*s, Sym(i as u16 + NUM_SYMS));
        }
        m
    })
}

fn num_strs() -> &'static [&'static str] {
    static STRS: OnceLock<Vec<&'static str>> = OnceLock::new();
    STRS.get_or_init(|| {
        let known = known_syms();
        let mut v = vec![""; NUM_SYMS as usize];
        for (s, sym) in known {
            if sym.0 < NUM_SYMS {
                v[sym.0 as usize] = s;
            }
        }
        v
    })
}

impl Sym {
    #[inline]
    pub fn int(n: i32) -> Sym {
        debug_assert!((0..NUM_SYMS as i32).contains(&n));
        Sym(n as u16)
    }

    #[inline]
    pub fn bool(b: bool) -> Sym {
        if b {
            sym::TRUE
        } else {
            sym::FALSE
        }
    }

    pub fn dir(d: Dir) -> Sym {
        match d {
            Dir::Down => sym::DOWN,
            Dir::Up => sym::UP,
            Dir::North => sym::NORTH,
            Dir::South => sym::SOUTH,
            Dir::West => sym::WEST,
            Dir::East => sym::EAST,
        }
    }

    pub fn to_dir(self) -> Option<Dir> {
        Some(match self {
            sym::DOWN => Dir::Down,
            sym::UP => Dir::Up,
            sym::NORTH => Dir::North,
            sym::SOUTH => Dir::South,
            sym::WEST => Dir::West,
            sym::EAST => Dir::East,
            _ => return None,
        })
    }
}

/// What kind of behaviour a block has (one per Python Block subclass).
#[derive(Copy, Clone, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum Kind {
    Air,
    /// Not modeled: inert, uses the static property tables.
    Unmodeled,
    /// Registered with the default behaviour (slime and honey blocks).
    Plain,
    Lever,
    Button,
    PressurePlate,
    RedstoneBlock,
    Lamp,
    Wire,
    Repeater,
    Comparator,
    Torch,
    WallTorch,
    Observer,
    Piston,
    PistonHead,
    MovingPiston,
    Barrel,
    Chest,
    TrappedChest,
    Dispenser,
    Hopper,
    Crafter,
    CopperBulb,
    NoteBlock,
    Target,
    Door,
    TrapDoor,
    FenceGate,
    Rail,
    PoweredRail,
    Lectern,
    DaylightDetector,
    Cake,
    SculkSensor,
    CalibratedSculkSensor,
}

pub const BF_RAIL_IN_NAME: u8 = 1; // "rail" in state.name
pub const BF_TRAPDOOR_IN_ID: u8 = 2; // "trapdoor" in state.id
pub const BF_WALL: u8 = 4; // outputs._is_wall
pub const BF_IN_TABLE: u8 = 8;
pub const BF_WOOL: u8 = 16; // #wool
pub const BF_CARPET: u8 = 32; // wool carpets (dampen vibrations)
pub const BF_AMETHYST: u8 = 64; // #vibration_resonators

pub struct BlockInfo {
    pub name: Box<str>,
    pub kind: Kind,
    /// Kind parameter: button ticks, pressure plate time, 1 for sticky piston / dropper / open by hand.
    pub param: u16,
    /// Second kind parameter: 1 for weighted pressure plates.
    pub param2: u16,
    pub flags: u8,
    /// The behaviour object's identity: the block itself, or `minecraft:air` for the other air names.
    pub behaviour: BlockId,
}

const WOODS: &[&str] = &[
    "oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak", "bamboo",
    "crimson", "warped",
];

/// The registrations at the bottom of redstone/sim/blocks/*.py.
fn kind_of(name: &str) -> (Kind, u16, u16) {
    if data::is_air_name(name) {
        return (Kind::Air, 0, 0);
    }
    let Some(id) = name.strip_prefix("minecraft:") else {
        return (Kind::Unmodeled, 0, 0);
    };
    match id {
        "lever" => return (Kind::Lever, 0, 0),
        "stone_button" | "polished_blackstone_button" => return (Kind::Button, 20, 0),
        "stone_pressure_plate" | "polished_blackstone_pressure_plate" => return (Kind::PressurePlate, 20, 0),
        "light_weighted_pressure_plate" | "heavy_weighted_pressure_plate" => {
            return (Kind::PressurePlate, 10, 1)
        }
        "redstone_block" => return (Kind::RedstoneBlock, 0, 0),
        "redstone_lamp" => return (Kind::Lamp, 0, 0),
        "redstone_wire" => return (Kind::Wire, 0, 0),
        "repeater" => return (Kind::Repeater, 0, 0),
        "comparator" => return (Kind::Comparator, 0, 0),
        "redstone_torch" => return (Kind::Torch, 0, 0),
        "redstone_wall_torch" => return (Kind::WallTorch, 0, 0),
        "observer" => return (Kind::Observer, 0, 0),
        "piston" => return (Kind::Piston, 0, 0),
        "sticky_piston" => return (Kind::Piston, 1, 0),
        "piston_head" => return (Kind::PistonHead, 0, 0),
        "moving_piston" => return (Kind::MovingPiston, 0, 0),
        "slime_block" | "honey_block" => return (Kind::Plain, 0, 0),
        "barrel" => return (Kind::Barrel, 27, 0),
        "chest" | "copper_chest" | "exposed_copper_chest" | "weathered_copper_chest" | "oxidized_copper_chest"
        | "waxed_copper_chest" | "waxed_exposed_copper_chest" | "waxed_weathered_copper_chest"
        | "waxed_oxidized_copper_chest" => return (Kind::Chest, 27, 0),
        "trapped_chest" => return (Kind::TrappedChest, 27, 0),
        "dispenser" => return (Kind::Dispenser, 9, 0),
        "dropper" => return (Kind::Dispenser, 9, 1),
        "hopper" => return (Kind::Hopper, 5, 0),
        "crafter" => return (Kind::Crafter, 9, 0),
        "note_block" => return (Kind::NoteBlock, 0, 0),
        "target" => return (Kind::Target, 0, 0),
        "rail" => return (Kind::Rail, 0, 0),
        "powered_rail" | "activator_rail" => return (Kind::PoweredRail, 0, 0),
        "lectern" => return (Kind::Lectern, 0, 0),
        "daylight_detector" => return (Kind::DaylightDetector, 0, 0),
        "cake" => return (Kind::Cake, 0, 0),
        "sculk_sensor" => return (Kind::SculkSensor, 0, 0),
        "calibrated_sculk_sensor" => return (Kind::CalibratedSculkSensor, 0, 0),
        _ => {}
    }
    if let Some(wood) = id.strip_suffix("_button") {
        if WOODS.contains(&wood) {
            return (Kind::Button, 30, 0);
        }
    }
    if let Some(wood) = id.strip_suffix("_pressure_plate") {
        if WOODS.contains(&wood) {
            return (Kind::PressurePlate, 20, 0);
        }
    }
    // These are registered for every matching name of the block table only.
    if data::data().blocks.contains_key(name) {
        if id.ends_with("copper_bulb") {
            return (Kind::CopperBulb, 0, 0);
        }
        if id.ends_with("_trapdoor") {
            return (Kind::TrapDoor, (id != "iron_trapdoor") as u16, 0);
        }
        if id.ends_with("_door") {
            return (Kind::Door, (id != "iron_door") as u16, 0);
        }
        if id.ends_with("_fence_gate") {
            return (Kind::FenceGate, 0, 0);
        }
    }
    (Kind::Unmodeled, 0, 0)
}

pub const SF_AIR: u16 = 1; // state.is_air (by name)
pub const SF_CONDUCTOR: u16 = 2; // Block#is_conductor, kind overrides applied
pub const SF_POWERED: u16 = 4;
pub const SF_LIT: u16 = 8;
pub const SF_EXTENDED: u16 = 16;
pub const SF_DATA_BLOCK_ENTITY: u16 = 32; // blockdata.has_block_entity
pub const SF_UNBREAKABLE: u16 = 64; // blockdata.is_unbreakable
pub const SF_KNOWN: u16 = 128; // block is in the data table
pub const SF_SOLID: u16 = 256; // blockdata.is_solid (deprecated BlockState#isSolid)

pub const NO_FACING: u8 = 255;

/// Decoded, frequently read facts about one state.
#[derive(Copy, Clone, Debug)]
pub struct StateInfo {
    /// The state's block name.
    pub name: BlockId,
    /// The behaviour's block (differs from `name` only for cave_air and void_air).
    pub block: BlockId,
    pub kind: Kind,
    pub flags: u16,
    /// Block#is_face_sturdy masks for full, rigid, center (kind overrides applied).
    pub sturdy: [u8; 3],
    /// Raw blockdata push reaction (data::PUSH_PULL ...), without the piston overrides.
    pub push: u8,
    /// Property `facing` as a Direction index, NO_FACING if missing or not a direction.
    pub facing: u8,
    /// Property `power` (0 if missing).
    pub power: u8,
    /// Redstone wire sides in N, E, S, W order: 0 none (or missing), 1 side, 2 up.
    pub wire: [u8; 4],
    pub param: u16,
    pub param2: u16,
    pub block_flags: u8,
}

impl StateInfo {
    #[inline]
    pub fn is_air(&self) -> bool {
        self.flags & SF_AIR != 0
    }
    #[inline]
    pub fn conductor(&self) -> bool {
        self.flags & SF_CONDUCTOR != 0
    }
    #[inline]
    pub fn powered(&self) -> bool {
        self.flags & SF_POWERED != 0
    }
    #[inline]
    pub fn lit(&self) -> bool {
        self.flags & SF_LIT != 0
    }
    #[inline]
    pub fn extended(&self) -> bool {
        self.flags & SF_EXTENDED != 0
    }
    #[inline]
    pub fn sturdy(&self, face: Dir, support: usize) -> bool {
        self.sturdy[support] >> (face as u8) & 1 != 0
    }
    /// `Direction.from_name(state.get("facing", default))`
    #[inline]
    pub fn facing_or(&self, default: Dir) -> Dir {
        if self.facing == NO_FACING {
            default
        } else {
            Dir::from_index(self.facing as usize)
        }
    }
    /// `facing` with the usual default north.
    #[inline]
    pub fn facing(&self) -> Dir {
        self.facing_or(Dir::North)
    }
}

pub struct States {
    infos: Vec<StateInfo>,
    props: Vec<Box<[(Sym, Sym)]>>,
    strs: Vec<Box<str>>,
    by_str: FxHashMap<Box<str>, StateId>,
    pub blocks: Vec<BlockInfo>,
    block_by_name: FxHashMap<Box<str>, BlockId>,
    extra_syms: Vec<Box<str>>,
    extra_by_str: FxHashMap<Box<str>, Sym>,
    with_cache: FxHashMap<(StateId, Sym, Sym), StateId>,
}

impl Default for States {
    fn default() -> Self {
        Self::new()
    }
}

impl States {
    pub fn new() -> States {
        let mut s = States {
            infos: Vec::new(),
            props: Vec::new(),
            strs: Vec::new(),
            by_str: FxHashMap::default(),
            blocks: Vec::new(),
            block_by_name: FxHashMap::default(),
            extra_syms: Vec::new(),
            extra_by_str: FxHashMap::default(),
            with_cache: FxHashMap::default(),
        };
        let air = s.intern_str("minecraft:air");
        debug_assert_eq!(air, AIR);
        s
    }

    pub fn len(&self) -> usize {
        self.infos.len()
    }

    // --- symbols ---------------------------------------------------------------------------
    pub fn sym(&mut self, s: &str) -> Sym {
        if let Some(sym) = known_syms().get(s) {
            return *sym;
        }
        if let Some(sym) = self.extra_by_str.get(s) {
            return *sym;
        }
        let sym = Sym(NUM_SYMS + KNOWN_SYMS.len() as u16 + self.extra_syms.len() as u16);
        self.extra_syms.push(s.into());
        self.extra_by_str.insert(s.into(), sym);
        sym
    }

    pub fn sym_str(&self, sym: Sym) -> &str {
        let i = sym.0 as usize;
        if i < NUM_SYMS as usize {
            num_strs()[i]
        } else if i < NUM_SYMS as usize + KNOWN_SYMS.len() {
            KNOWN_SYMS[i - NUM_SYMS as usize]
        } else {
            &self.extra_syms[i - NUM_SYMS as usize - KNOWN_SYMS.len()]
        }
    }

    /// Symbol of a small non-negative integer (property values such as power or note).
    pub fn sym_int(&mut self, n: i32) -> Sym {
        if (0..NUM_SYMS as i32).contains(&n) {
            Sym(n as u16)
        } else {
            self.sym(&n.to_string())
        }
    }

    // --- blocks ----------------------------------------------------------------------------
    pub fn block_id(&mut self, name: &str) -> BlockId {
        if let Some(id) = self.block_by_name.get(name) {
            return *id;
        }
        let id = self.blocks.len() as BlockId;
        let (kind, param, param2) = kind_of(name);
        let short = data::block_id(name);
        let mut flags = 0;
        if name.contains("rail") {
            flags |= BF_RAIL_IN_NAME;
        }
        if short.contains("trapdoor") {
            flags |= BF_TRAPDOOR_IN_ID;
        }
        if short.ends_with("_wall") && !short.contains("wall_") {
            flags |= BF_WALL;
        }
        if data::data().blocks.contains_key(name) {
            flags |= BF_IN_TABLE;
        }
        if name.starts_with("minecraft:") {
            const COLORS: [&str; 16] = [
                "white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan",
                "purple", "blue", "brown", "green", "red", "black",
            ];
            if short.strip_suffix("_wool").is_some_and(|c| COLORS.contains(&c)) {
                flags |= BF_WOOL;
            } else if short.strip_suffix("_carpet").is_some_and(|c| COLORS.contains(&c)) {
                flags |= BF_CARPET;
            } else if short == "amethyst_block" {
                flags |= BF_AMETHYST;
            }
        }
        self.blocks.push(BlockInfo { name: name.into(), kind, param, param2, flags, behaviour: id });
        self.block_by_name.insert(name.into(), id);
        if kind == Kind::Air && id != AIR_BLOCK {
            self.blocks[id as usize].behaviour = AIR_BLOCK;
        }
        id
    }

    #[inline]
    pub fn block(&self, id: BlockId) -> &BlockInfo {
        &self.blocks[id as usize]
    }

    #[inline]
    pub fn block_name(&self, id: BlockId) -> &str {
        &self.blocks[id as usize].name
    }

    /// Registry#needs_model: unknown block that may well have redstone behaviour (used for warnings).
    pub fn needs_model(&self, id: BlockId) -> bool {
        const INERT_OK_HINTS: &[&str] = &[
            "stone", "wool", "concrete", "planks", "log", "glass", "dirt", "slab", "terracotta", "bricks",
            "deepslate", "cobble", "sand", "gravel", "obsidian", "ore", "quartz", "copper", "wood",
            "iron_block", "gold_block", "diamond_block", "emerald_block", "netherrack",
        ];
        let b = self.block(id);
        if !matches!(b.kind, Kind::Unmodeled | Kind::Air) || b.name.ends_with("air") {
            return false;
        }
        let short = b.name.split_once(':').map(|(_, s)| s).unwrap_or(&b.name);
        !INERT_OK_HINTS.iter().any(|h| short.contains(h))
    }

    // --- states ----------------------------------------------------------------------------
    #[inline]
    pub fn info(&self, id: StateId) -> StateInfo {
        self.infos[id as usize]
    }

    #[inline]
    pub fn info_ref(&self, id: StateId) -> &StateInfo {
        &self.infos[id as usize]
    }

    pub fn str(&self, id: StateId) -> &str {
        &self.strs[id as usize]
    }

    pub fn props(&self, id: StateId) -> &[(Sym, Sym)] {
        &self.props[id as usize]
    }

    /// `state.get(key)`
    #[inline]
    pub fn get(&self, id: StateId, key: Sym) -> Option<Sym> {
        self.props[id as usize].iter().find(|(k, _)| *k == key).map(|(_, v)| *v)
    }

    /// `state.get_bool(key)`: false if missing.
    #[inline]
    pub fn get_bool(&self, id: StateId, key: Sym) -> bool {
        self.get(id, key) == Some(sym::TRUE)
    }

    /// `state.get_int(key, default)`; a value that is not an integer counts as the default.
    pub fn get_int(&self, id: StateId, key: Sym, default: i32) -> i32 {
        match self.get(id, key) {
            None => default,
            Some(v) if v.0 < NUM_SYMS => v.0 as i32,
            Some(v) => self.sym_str(v).parse().unwrap_or(default),
        }
    }

    /// Parse the string form `name[k=v,...]` (BlockState.parse) and intern it.
    pub fn intern_str(&mut self, text: &str) -> StateId {
        if let Some(id) = self.by_str.get(text) {
            return *id;
        }
        let trimmed = text.trim();
        let (name, rest) = match trimmed.find('[') {
            Some(i) => (&trimmed[..i], trimmed[i + 1..].strip_suffix(']').unwrap_or(&trimmed[i + 1..])),
            None => (trimmed, ""),
        };
        let mut props = Vec::new();
        for part in rest.split(',') {
            if part.is_empty() {
                continue;
            }
            let (k, v) = part.split_once('=').unwrap_or((part, ""));
            let k = self.sym(k.trim());
            let v = self.sym(v.trim());
            props.push((k, v));
        }
        let id = if name.contains(':') {
            self.intern_parts(name, props)
        } else {
            self.intern_parts(&format!("minecraft:{name}"), props)
        };
        if !self.by_str.contains_key(text) {
            self.by_str.insert(text.into(), id);
        }
        id
    }

    /// `BlockState.of(name, props)`: properties are sorted by key.
    pub fn intern_parts(&mut self, name: &str, mut props: Vec<(Sym, Sym)>) -> StateId {
        // Later duplicates win, like a dict.
        let mut unique: Vec<(Sym, Sym)> = Vec::with_capacity(props.len());
        for (k, v) in props.drain(..) {
            match unique.iter_mut().find(|p| p.0 == k) {
                Some(p) => p.1 = v,
                None => unique.push((k, v)),
            }
        }
        let mut props = unique;
        props.sort_by(|a, b| self.sym_str(a.0).cmp(self.sym_str(b.0)));
        let mut text = String::with_capacity(name.len() + 16 * props.len());
        text.push_str(name);
        if !props.is_empty() {
            text.push('[');
            for (i, (k, v)) in props.iter().enumerate() {
                if i > 0 {
                    text.push(',');
                }
                text.push_str(self.sym_str(*k));
                text.push('=');
                text.push_str(self.sym_str(*v));
            }
            text.push(']');
        }
        if let Some(id) = self.by_str.get(text.as_str()) {
            return *id;
        }
        let id = self.infos.len() as StateId;
        let info = self.make_info(name, &props);
        self.infos.push(info);
        self.props.push(props.into_boxed_slice());
        self.strs.push(text.as_str().into());
        self.by_str.insert(text.into_boxed_str(), id);
        id
    }

    /// `BlockState.of(block name, key=value, ...)` for a block that is already interned.
    pub fn state_of(&mut self, block: BlockId, props: &[(Sym, Sym)]) -> StateId {
        let name: Box<str> = self.block_name(block).into();
        self.intern_parts(&name, props.to_vec())
    }

    pub fn state_of_name(&mut self, name: &str, props: &[(Sym, Sym)]) -> StateId {
        self.intern_parts(name, props.to_vec())
    }

    /// `state.with_(key=value)`
    pub fn with(&mut self, id: StateId, key: Sym, value: Sym) -> StateId {
        if let Some(found) = self.with_cache.get(&(id, key, value)) {
            return *found;
        }
        let mut props = self.props[id as usize].to_vec();
        match props.iter_mut().find(|(k, _)| *k == key) {
            Some(p) => p.1 = value,
            None => props.push((key, value)),
        }
        let name: Box<str> = self.block_name(self.infos[id as usize].name).into();
        let new = self.intern_parts(&name, props);
        self.with_cache.insert((id, key, value), new);
        new
    }

    pub fn with_bool(&mut self, id: StateId, key: Sym, value: bool) -> StateId {
        self.with(id, key, Sym::bool(value))
    }

    pub fn with_int(&mut self, id: StateId, key: Sym, value: i32) -> StateId {
        let v = self.sym_int(value);
        self.with(id, key, v)
    }

    fn make_info(&mut self, name: &str, props: &[(Sym, Sym)]) -> StateInfo {
        let block = self.block_id(name);
        let (kind, param, param2, block_flags, behaviour) = {
            let b = self.block(block);
            (b.kind, b.param, b.param2, b.flags, b.behaviour)
        };
        let str_props: Vec<(&str, &str)> = props.iter().map(|(k, v)| (self.sym_str(*k), self.sym_str(*v))).collect();
        let d = data::lookup(name, &str_props);
        let find = |key: Sym| props.iter().find(|(k, _)| *k == key).map(|(_, v)| *v);
        let mut flags = 0u16;
        let is_air = data::is_air_name(name);
        if is_air {
            flags |= SF_AIR;
        }
        let facing = find(sym::FACING).and_then(Sym::to_dir);
        // Kind overrides of Block#is_conductor and Block#is_face_sturdy.
        let mut conductor = d.conductor;
        let mut sturdy = d.sturdy;
        match kind {
            Kind::Air | Kind::Wire | Kind::MovingPiston => {
                conductor = false;
                sturdy = [0; 3];
            }
            Kind::Piston => conductor = false,
            Kind::PistonHead => {
                conductor = false;
                sturdy = [1 << (facing.unwrap_or(Dir::North) as u8); 3];
            }
            _ => {}
        }
        if conductor {
            flags |= SF_CONDUCTOR;
        }
        if find(sym::POWERED) == Some(sym::TRUE) {
            flags |= SF_POWERED;
        }
        if find(sym::LIT) == Some(sym::TRUE) {
            flags |= SF_LIT;
        }
        if find(sym::EXTENDED) == Some(sym::TRUE) {
            flags |= SF_EXTENDED;
        }
        if d.block_entity {
            flags |= SF_DATA_BLOCK_ENTITY;
        }
        if d.unbreakable {
            flags |= SF_UNBREAKABLE;
        }
        if d.known {
            flags |= SF_KNOWN;
        }
        if d.solid {
            flags |= SF_SOLID;
        }
        let power = match find(sym::POWER) {
            Some(v) if v.0 < NUM_SYMS => v.0 as u8,
            Some(v) => self.sym_str(v).parse().unwrap_or(0),
            None => 0,
        };
        let side = |key: Sym| match find(key) {
            None | Some(sym::NONE) => 0u8,
            Some(sym::UP) => 2,
            Some(_) => 1,
        };
        StateInfo {
            name: block,
            block: behaviour,
            kind,
            flags,
            sturdy,
            push: d.push,
            facing: facing.map(|d| d as u8).unwrap_or(NO_FACING),
            power,
            wire: [side(sym::NORTH), side(sym::EAST), side(sym::SOUTH), side(sym::WEST)],
            param,
            param2,
            block_flags,
        }
    }
}
