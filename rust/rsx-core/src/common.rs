//! Positions, directions and update flags (mirrors redstone.model.pos and redstone.sim.constants).

#[derive(Copy, Clone, PartialEq, Eq, Hash, Debug, PartialOrd, Ord)]
pub struct Pos {
    pub x: i32,
    pub y: i32,
    pub z: i32,
}

impl Pos {
    #[inline]
    pub const fn new(x: i32, y: i32, z: i32) -> Pos {
        Pos { x, y, z }
    }

    #[inline]
    pub fn offset(self, d: Dir) -> Pos {
        let (dx, dy, dz) = d.vec();
        Pos { x: self.x + dx, y: self.y + dy, z: self.z + dz }
    }

    #[inline]
    pub fn offset_n(self, d: Dir, n: i32) -> Pos {
        let (dx, dy, dz) = d.vec();
        Pos { x: self.x + dx * n, y: self.y + dy * n, z: self.z + dz * n }
    }

    #[inline]
    pub fn above(self) -> Pos {
        Pos { x: self.x, y: self.y + 1, z: self.z }
    }

    #[inline]
    pub fn below(self) -> Pos {
        Pos { x: self.x, y: self.y - 1, z: self.z }
    }

    /// Vec3i#hashCode: (y + z * 31) * 31 + x in 32-bit int arithmetic.
    #[inline]
    pub fn java_hash(self) -> i32 {
        self.y.wrapping_add(self.z.wrapping_mul(31)).wrapping_mul(31).wrapping_add(self.x)
    }

    /// HashMap#hash applied to the Java hash code: h ^ (h >>> 16).
    #[inline]
    pub fn java_spread(self) -> u32 {
        let h = self.java_hash() as u32;
        h ^ (h >> 16)
    }
}

/// The six directions in the declaration order of net.minecraft.core.Direction.
#[derive(Copy, Clone, PartialEq, Eq, Hash, Debug)]
#[repr(u8)]
pub enum Dir {
    Down = 0,
    Up = 1,
    North = 2,
    South = 3,
    West = 4,
    East = 5,
}

use Dir::*;

/// Direction.values()
pub const ALL_DIRECTIONS: [Dir; 6] = [Down, Up, North, South, West, East];
/// NeighborUpdater.UPDATE_ORDER
pub const UPDATE_ORDER: [Dir; 6] = [West, East, Down, Up, North, South];
/// BlockBehaviour.UPDATE_SHAPE_ORDER
pub const UPDATE_SHAPE_ORDER: [Dir; 6] = [West, East, North, South, Down, Up];
/// SignalGetter#getDirectSignalTo / hasNeighborSignal order
pub const SIGNAL_ORDER: [Dir; 6] = [Down, Up, North, South, West, East];
/// Direction.Plane.HORIZONTAL
pub const HORIZONTAL: [Dir; 4] = [North, East, South, West];
/// Direction.Plane.VERTICAL
pub const VERTICAL: [Dir; 2] = [Up, Down];

impl Dir {
    #[inline]
    pub fn vec(self) -> (i32, i32, i32) {
        match self {
            Down => (0, -1, 0),
            Up => (0, 1, 0),
            North => (0, 0, -1),
            South => (0, 0, 1),
            West => (-1, 0, 0),
            East => (1, 0, 0),
        }
    }

    #[inline]
    pub fn opposite(self) -> Dir {
        match self {
            Down => Up,
            Up => Down,
            North => South,
            South => North,
            West => East,
            East => West,
        }
    }

    #[inline]
    pub fn is_horizontal(self) -> bool {
        !matches!(self, Down | Up)
    }

    /// Rotate around the y axis, seen from above. Vertical directions stay as they are (the Python model
    /// raises for them; no caller passes one).
    #[inline]
    pub fn clockwise(self) -> Dir {
        match self {
            North => East,
            East => South,
            South => West,
            West => North,
            d => d,
        }
    }

    #[inline]
    pub fn counter_clockwise(self) -> Dir {
        match self {
            North => West,
            West => South,
            South => East,
            East => North,
            d => d,
        }
    }

    /// Direction#get3DDataValue
    #[inline]
    pub fn index(self) -> usize {
        self as usize
    }

    #[inline]
    pub fn from_index(i: usize) -> Dir {
        ALL_DIRECTIONS[i]
    }

    /// Index in Direction.Plane.HORIZONTAL order (N, E, S, W); vertical directions give 0.
    #[inline]
    pub fn horizontal_index(self) -> usize {
        match self {
            North => 0,
            East => 1,
            South => 2,
            West => 3,
            _ => 0,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Down => "down",
            Up => "up",
            North => "north",
            South => "south",
            West => "west",
            East => "east",
        }
    }

    pub fn from_name(name: &str) -> Option<Dir> {
        Some(match name {
            "down" => Down,
            "up" => Up,
            "north" => North,
            "south" => South,
            "west" => West,
            "east" => East,
            _ => return None,
        })
    }
}

// Block.UPDATE_* flags
pub const UPDATE_NEIGHBORS: u32 = 1;
pub const UPDATE_CLIENTS: u32 = 2;
pub const UPDATE_INVISIBLE: u32 = 4;
pub const UPDATE_IMMEDIATE: u32 = 8;
pub const UPDATE_KNOWN_SHAPE: u32 = 16;
pub const UPDATE_SUPPRESS_DROPS: u32 = 32;
pub const UPDATE_MOVE_BY_PISTON: u32 = 64;
pub const UPDATE_SKIP_SHAPE_UPDATE_ON_WIRE: u32 = 128;
pub const UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS: u32 = 256;
pub const UPDATE_SKIP_ON_PLACE: u32 = 512;
pub const UPDATE_ALL: u32 = UPDATE_NEIGHBORS | UPDATE_CLIENTS;

pub const UPDATE_LIMIT: i32 = 512;
/// Level#maxChainedNeighborUpdates, game rule default
pub const MAX_CHAINED_NEIGHBOR_UPDATES: u32 = 1_000_000;

// TickPriority
pub const PRIO_EXTREMELY_HIGH: i32 = -3;
pub const PRIO_VERY_HIGH: i32 = -2;
pub const PRIO_HIGH: i32 = -1;
pub const PRIO_NORMAL: i32 = 0;

/// Support types of BlockState#isFaceSturdy
pub const SUPPORT_FULL: usize = 0;
pub const SUPPORT_RIGID: usize = 1;
pub const SUPPORT_CENTER: usize = 2;
