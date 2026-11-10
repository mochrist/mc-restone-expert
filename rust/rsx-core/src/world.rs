//! The simulated level, a port of redstone/sim/world.py (the Python module is the reference):
//! block storage, setBlock, neighbor/shape updates, scheduled ticks, block events and block entities.

use crate::common::*;
use crate::state::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::Ordering;
use std::collections::{BinaryHeap, VecDeque};

pub type BeId = usize;
pub type ItemId = u32;

// ---------------------------------------------------------------------------------- block storage
/// Dense box around the build plus a hash map for everything outside of it. Every cell also remembers
/// when it was last filled, so blocks can be listed in the insertion order of the Python dict.
#[derive(Default)]
pub struct Store {
    min: Pos,
    size: (i32, i32, i32),
    cells: Vec<StateId>,
    seq: Vec<u32>,
    overflow: FxHashMap<Pos, (StateId, u32)>,
    next_seq: u32,
    count: usize,
}

impl Default for Pos {
    fn default() -> Self {
        Pos::new(0, 0, 0)
    }
}

const MAX_DENSE_CELLS: i64 = 1 << 22;
const GROW_MARGIN: i32 = 3;

impl Store {
    #[inline]
    fn index(&self, pos: Pos) -> Option<usize> {
        let dx = pos.x.wrapping_sub(self.min.x) as u32;
        let dy = pos.y.wrapping_sub(self.min.y) as u32;
        let dz = pos.z.wrapping_sub(self.min.z) as u32;
        if dx < self.size.0 as u32 && dy < self.size.1 as u32 && dz < self.size.2 as u32 {
            Some(((dy * self.size.2 as u32 + dz) * self.size.0 as u32 + dx) as usize)
        } else {
            None
        }
    }

    #[inline]
    pub fn get(&self, pos: Pos) -> StateId {
        match self.index(pos) {
            Some(i) => self.cells[i],
            None if self.overflow.is_empty() => AIR,
            None => self.overflow.get(&pos).map(|e| e.0).unwrap_or(AIR),
        }
    }

    /// Make the dense box cover `lo..=hi` (plus a margin) if that stays within the size limit.
    pub fn reserve(&mut self, lo: Pos, hi: Pos) {
        let (mut nlo, mut nhi) = (
            Pos::new(lo.x - GROW_MARGIN, lo.y - GROW_MARGIN, lo.z - GROW_MARGIN),
            Pos::new(hi.x + GROW_MARGIN, hi.y + GROW_MARGIN, hi.z + GROW_MARGIN),
        );
        if !self.cells.is_empty() {
            let max = Pos::new(
                self.min.x + self.size.0 - 1,
                self.min.y + self.size.1 - 1,
                self.min.z + self.size.2 - 1,
            );
            nlo = Pos::new(nlo.x.min(self.min.x), nlo.y.min(self.min.y), nlo.z.min(self.min.z));
            nhi = Pos::new(nhi.x.max(max.x), nhi.y.max(max.y), nhi.z.max(max.z));
            if nlo == self.min && nhi == max {
                return;
            }
        }
        let size = (
            (nhi.x as i64 - nlo.x as i64 + 1),
            (nhi.y as i64 - nlo.y as i64 + 1),
            (nhi.z as i64 - nlo.z as i64 + 1),
        );
        if size.0 * size.1 * size.2 > MAX_DENSE_CELLS {
            return;
        }
        let mut grown = Store {
            min: nlo,
            size: (size.0 as i32, size.1 as i32, size.2 as i32),
            cells: vec![AIR; (size.0 * size.1 * size.2) as usize],
            seq: vec![0; (size.0 * size.1 * size.2) as usize],
            overflow: FxHashMap::default(),
            next_seq: self.next_seq,
            count: self.count,
        };
        for (i, &state) in self.cells.iter().enumerate() {
            if state != AIR {
                let i = i as i32;
                let x = i % self.size.0;
                let z = (i / self.size.0) % self.size.2;
                let y = i / (self.size.0 * self.size.2);
                let j = grown.index(Pos::new(self.min.x + x, self.min.y + y, self.min.z + z)).unwrap();
                grown.cells[j] = state;
                grown.seq[j] = self.seq[i as usize];
            }
        }
        for (pos, (state, seq)) in self.overflow.drain() {
            match grown.index(pos) {
                Some(j) => {
                    grown.cells[j] = state;
                    grown.seq[j] = seq;
                }
                None => {
                    grown.overflow.insert(pos, (state, seq));
                }
            }
        }
        *self = grown;
    }

    /// Store a state (AIR removes the block), like `blocks[pos] = state` / `blocks.pop(pos)`.
    pub fn set(&mut self, pos: Pos, state: StateId) {
        let mut index = self.index(pos);
        if index.is_none() && state != AIR {
            self.reserve(pos, pos);
            index = self.index(pos);
        }
        match index {
            Some(i) => {
                let old = self.cells[i];
                if old == AIR && state != AIR {
                    self.next_seq += 1;
                    self.seq[i] = self.next_seq;
                    self.count += 1;
                } else if old != AIR && state == AIR {
                    self.count -= 1;
                }
                self.cells[i] = state;
            }
            None => {
                if state == AIR {
                    if self.overflow.remove(&pos).is_some() {
                        self.count -= 1;
                    }
                } else if let Some(e) = self.overflow.get_mut(&pos) {
                    e.0 = state;
                } else {
                    self.next_seq += 1;
                    self.overflow.insert(pos, (state, self.next_seq));
                    self.count += 1;
                }
            }
        }
    }

    pub fn len(&self) -> usize {
        self.count
    }

    /// All non-air blocks in the order a Python dict would list them.
    pub fn items(&self) -> Vec<(Pos, StateId)> {
        let mut out: Vec<(u32, Pos, StateId)> = Vec::with_capacity(self.count);
        let (sx, sz) = (self.size.0, self.size.2);
        for (i, &state) in self.cells.iter().enumerate() {
            if state != AIR {
                let i = i as i32;
                let pos = Pos::new(self.min.x + i % sx, self.min.y + i / (sx * sz), self.min.z + (i / sx) % sz);
                out.push((self.seq[i as usize], pos, state));
            }
        }
        for (pos, (state, seq)) in &self.overflow {
            out.push((*seq, *pos, *state));
        }
        out.sort_unstable_by_key(|e| e.0);
        out.into_iter().map(|(_, p, s)| (p, s)).collect()
    }
}

// ---------------------------------------------------------------------------------- records
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ScheduledTick {
    pub trigger_tick: i64,
    pub priority: i32,
    pub sub_tick: u64,
    pub pos: Pos,
    pub block: BlockId,
}

impl Ord for ScheduledTick {
    fn cmp(&self, other: &Self) -> Ordering {
        // BinaryHeap is a max-heap: reverse to pop the smallest (trigger tick, priority, sub tick).
        (other.trigger_tick, other.priority, other.sub_tick).cmp(&(self.trigger_tick, self.priority, self.sub_tick))
    }
}

impl PartialOrd for ScheduledTick {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BlockEvent {
    pub pos: Pos,
    pub block: BlockId,
    pub a: i32,
    pub b: i32,
}

#[derive(Clone, Debug)]
pub struct Note {
    pub tick: i64,
    pub kind: &'static str,
    pub pos: Pos,
    pub detail: String,
}

/// Kinds of mechanics notes (keys of redstone.sim.notes.MECHANICS).
pub const NOTE_KINDS: &[&str] = &[
    "repeater_lock",
    "repeater_pulse_extend",
    "comparator_subtract",
    "comparator_compare_block",
    "comparator_container",
    "comparator_through_block",
    "torch_burnout",
    "observer_pulse",
    "quasi_connectivity",
    "bud",
    "piston_spit",
    "zero_tick",
    "wire_locational",
];

// ---------------------------------------------------------------------------------- block entities
#[derive(Clone, Debug, PartialEq)]
pub struct ItemStack {
    pub slot: usize,
    pub item: ItemId,
    pub count: i32,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ContainerKind {
    /// ContainerBlockEntity (barrel)
    Plain,
    /// DispenserBlockEntity (dispenser and dropper)
    Dispenser,
    /// HopperBlockEntity
    Hopper { cooldown_time: i32, ticked_game_time: i64 },
}

/// ContainerBlockEntity and its subclasses. `items` keeps the insertion order of the Python dict
/// `slot -> [item, count]` (it decides the order of the float sum in `redstone_signal`).
#[derive(Clone, Debug, PartialEq)]
pub struct Container {
    pub size: usize,
    pub items: Vec<ItemStack>,
    pub kind: ContainerKind,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Lectern {
    pub has_book: bool,
    pub page: i32,
    pub page_count: i32,
}

/// PistonMovingBlockEntity
#[derive(Clone, Debug, PartialEq)]
pub struct PistonBe {
    pub moved_state: StateId,
    pub direction: Dir,
    pub extending: bool,
    pub is_source_piston: bool,
    pub progress: f64,
    pub progress_o: f64,
    pub last_ticked: i64,
}

#[derive(Clone, Debug, PartialEq)]
pub enum BeData {
    Comparator { output_signal: i32 },
    Container(Container),
    Lectern(Lectern),
    Piston(PistonBe),
}

#[derive(Clone, Debug)]
pub struct BlockEntity {
    pub removed: bool,
    pub pos: Pos,
    pub data: BeData,
}

impl BlockEntity {
    /// Class attribute `ticks` of the Python block entities.
    pub fn ticks(&self) -> bool {
        matches!(
            self.data,
            BeData::Piston(_) | BeData::Container(Container { kind: ContainerKind::Hopper { .. }, .. })
        )
    }
}

// ---------------------------------------------------------------------------------- neighbor updates
#[derive(Clone, Copy, Debug)]
enum Update {
    Simple { pos: Pos, source: BlockId },
    Full { state: StateId, pos: Pos, source: BlockId, moved: bool },
    Shape { direction: Dir, neighbor_state: StateId, pos: Pos, neighbor_pos: Pos, flags: u32, limit: i32 },
    Multi { pos: Pos, source: BlockId, skip: Option<Dir>, idx: u8 },
}

// ---------------------------------------------------------------------------------- the world
pub struct World {
    pub st: States,
    pub store: Store,
    pub game_time: i64,
    /// ServerLevel#handlingTick: block ticks through block events
    pub handling_tick: bool,
    sub_tick: u64,
    ticks: BinaryHeap<ScheduledTick>,
    pending: FxHashSet<(Pos, BlockId)>,
    running_this_tick: FxHashSet<(Pos, BlockId)>,
    pub block_events: VecDeque<BlockEvent>,
    /// All block entities ever created; `be_map` is the Python dict `block_entities`.
    pub bes: Vec<BlockEntity>,
    be_map: FxHashMap<Pos, (BeId, u32)>,
    be_seq: u32,
    /// Rebindable ticker wrappers (None = NULL_TICKER).
    wrappers: Vec<Option<BeId>>,
    be_tickers: Vec<usize>,
    pending_be_tickers: Vec<usize>,
    tickers_in_level: FxHashMap<Pos, usize>,
    ticking_block_entities: bool,
    stack: Vec<Update>,
    added_this_layer: Vec<Update>,
    update_count: u32,
    pub warnings: Vec<String>,
    /// Positions whose block state changed since the recorder last took them (in order, with repeats
    /// removed).
    dirty: Vec<Pos>,
    dirty_set: FxHashSet<Pos>,
    /// RedstoneWireBlock#shouldSignal: false only while the wire reads its block signal
    pub wire_should_signal: bool,
    /// RedstoneTorchBlock.RECENT_TOGGLES
    pub torch_toggles: VecDeque<(Pos, i64)>,
    pub notes: Vec<Note>,
    notes_seen: FxHashSet<(&'static str, Pos)>,
    pub item_names: Vec<Box<str>>,
    pub item_max_stack: Vec<i32>,
    item_by_name: FxHashMap<Box<str>, ItemId>,
    /// Number of executed neighbor updates (statistics for the benchmark).
    pub stat_neighbor_updates: u64,
}

impl Default for World {
    fn default() -> Self {
        Self::new()
    }
}

impl World {
    pub fn new() -> World {
        World {
            st: States::new(),
            store: Store::default(),
            game_time: 0,
            handling_tick: false,
            sub_tick: 0,
            ticks: BinaryHeap::new(),
            pending: FxHashSet::default(),
            running_this_tick: FxHashSet::default(),
            block_events: VecDeque::new(),
            bes: Vec::new(),
            be_map: FxHashMap::default(),
            be_seq: 0,
            wrappers: Vec::new(),
            be_tickers: Vec::new(),
            pending_be_tickers: Vec::new(),
            tickers_in_level: FxHashMap::default(),
            ticking_block_entities: false,
            stack: Vec::new(),
            added_this_layer: Vec::new(),
            update_count: 0,
            warnings: Vec::new(),
            dirty: Vec::new(),
            dirty_set: FxHashSet::default(),
            wire_should_signal: true,
            torch_toggles: VecDeque::new(),
            notes: Vec::new(),
            notes_seen: FxHashSet::default(),
            item_names: Vec::new(),
            item_max_stack: Vec::new(),
            item_by_name: FxHashMap::default(),
            stat_neighbor_updates: 0,
        }
    }

    // ------------------------------------------------------------------ construction
    /// One block of `place_grid`: stored exactly as given, without any updates. The caller loads the
    /// block entity data afterwards (see `new_block_entity`).
    pub fn place(&mut self, pos: Pos, state: StateId) {
        if self.info(state).is_air() {
            return;
        }
        self.store.set(pos, state);
        let info = self.info(state);
        if self.st.needs_model(info.name) {
            let name = self.st.block_name(info.name).to_owned();
            if !self.warnings.iter().any(|w| w.split(' ').next() == Some(name.as_str())) {
                self.warnings.push(format!("{name} is not modeled by the simulator; treated as inert block"));
            }
        }
        if self.has_block_entity(info.kind) {
            if let Some(data) = self.new_block_entity(pos, state) {
                let be = self.create_be(pos, data);
                self.add_block_entity(pos, be);
            }
        }
    }

    // ------------------------------------------------------------------ block access
    #[inline]
    pub fn get(&self, pos: Pos) -> StateId {
        self.store.get(pos)
    }

    #[inline]
    pub fn info(&self, state: StateId) -> StateInfo {
        self.st.info(state)
    }

    #[inline]
    pub fn info_at(&self, pos: Pos) -> StateInfo {
        self.st.info(self.store.get(pos))
    }

    /// `blocks[pos] = state` from outside the simulation (tests, templates): no updates, no block entity.
    pub fn set_raw(&mut self, pos: Pos, state: StateId) {
        let state = if self.info(state).is_air() { AIR } else { state };
        self.store.set(pos, state);
    }

    pub fn item_id(&mut self, name: &str) -> ItemId {
        if let Some(id) = self.item_by_name.get(name) {
            return *id;
        }
        let id = self.item_names.len() as ItemId;
        self.item_names.push(name.into());
        self.item_max_stack.push(crate::data::item_max_stack_size(name));
        self.item_by_name.insert(name.into(), id);
        id
    }

    // ------------------------------------------------------------------ block entities
    pub fn create_be(&mut self, pos: Pos, data: BeData) -> BeId {
        self.bes.push(BlockEntity { removed: false, pos, data });
        self.bes.len() - 1
    }

    /// `world.block_entities.get(pos)`: the raw dict entry, removed or not.
    #[inline]
    pub fn raw_block_entity(&self, pos: Pos) -> Option<BeId> {
        if self.be_map.is_empty() {
            return None;
        }
        self.be_map.get(&pos).map(|e| e.0)
    }

    /// Level#getBlockEntity (removed block entities count as absent).
    pub fn get_block_entity(&mut self, pos: Pos) -> Option<BeId> {
        let be = self.raw_block_entity(pos)?;
        if self.bes[be].removed {
            self.be_map.remove(&pos);
            return None;
        }
        Some(be)
    }

    /// Positions and ids of `block_entities` in dict order.
    pub fn block_entity_items(&self) -> Vec<(Pos, BeId)> {
        let mut v: Vec<(u32, Pos, BeId)> = self.be_map.iter().map(|(p, (be, seq))| (*seq, *p, *be)).collect();
        v.sort_unstable_by_key(|e| e.0);
        v.into_iter().map(|(_, p, be)| (p, be)).collect()
    }

    pub fn block_entity_count(&self) -> usize {
        self.be_map.len()
    }

    /// Level#setBlockEntity / LevelChunk#addAndRegisterBlockEntity
    pub fn add_block_entity(&mut self, pos: Pos, be: BeId) {
        let state = self.get(pos);
        if !self.has_block_entity(self.info(state).kind) {
            let text = format!("block entity at ({},{},{}) but {} does not allow it", pos.x, pos.y, pos.z, self.st.str(state));
            self.warnings.push(text);
            return;
        }
        self.bes[be].removed = false;
        match self.be_map.get_mut(&pos) {
            Some(entry) => {
                let previous = entry.0;
                entry.0 = be;
                if previous != be {
                    self.bes[previous].removed = true;
                }
            }
            None => {
                self.be_seq += 1;
                self.be_map.insert(pos, (be, self.be_seq));
            }
        }
        self.update_block_entity_ticker(pos, be);
    }

    /// `world.set_block_entity(be)`
    pub fn set_block_entity(&mut self, be: BeId) {
        let pos = self.bes[be].pos;
        self.add_block_entity(pos, be);
    }

    /// LevelChunk#updateBlockEntityTicker: one rebindable ticker wrapper per position.
    fn update_block_entity_ticker(&mut self, pos: Pos, be: BeId) {
        if !self.bes[be].ticks() {
            self.remove_block_entity_ticker(pos);
            return;
        }
        match self.tickers_in_level.get(&pos) {
            Some(&w) => self.wrappers[w] = Some(be),
            None => {
                let w = self.wrappers.len();
                self.wrappers.push(Some(be));
                self.tickers_in_level.insert(pos, w);
                // Level#addBlockEntityTicker
                if self.ticking_block_entities {
                    self.pending_be_tickers.push(w);
                } else {
                    self.be_tickers.push(w);
                }
            }
        }
    }

    fn remove_block_entity_ticker(&mut self, pos: Pos) {
        if let Some(w) = self.tickers_in_level.remove(&pos) {
            self.wrappers[w] = None; // NULL_TICKER: reports removed, dropped on the next iteration
        }
    }

    /// LevelChunk#removeBlockEntity
    pub fn remove_block_entity(&mut self, pos: Pos) {
        if let Some((be, _)) = self.be_map.remove(&pos) {
            self.bes[be].removed = true;
        }
        self.remove_block_entity_ticker(pos);
    }

    fn wrapper_removed(&self, w: usize) -> bool {
        match self.wrappers[w] {
            None => true,
            Some(be) => self.bes[be].removed,
        }
    }

    // ------------------------------------------------------------------ setBlock
    /// Level#setBlock including LevelChunk#setBlockState.
    pub fn set_block(&mut self, pos: Pos, state: StateId, flags: u32, limit: i32) -> bool {
        let old = self.get(pos);
        if old == state {
            return false;
        }
        let new_info = self.info(state);
        let old_info = self.info(old);
        self.store.set(pos, if new_info.is_air() { AIR } else { state });
        if self.dirty_set.insert(pos) {
            self.dirty.push(pos);
        }
        let block_changed = old_info.name != new_info.name;
        let moved = flags & UPDATE_MOVE_BY_PISTON != 0;

        if block_changed && self.has_block_entity(old_info.kind) {
            if flags & UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS == 0 {
                if let Some(be) = self.get_block_entity(pos) {
                    self.be_pre_remove_side_effects(be, pos, old);
                }
            }
            self.remove_block_entity(pos);
        }

        if (block_changed || new_info.block_flags & BF_RAIL_IN_NAME != 0) && (flags & UPDATE_NEIGHBORS != 0 || moved) {
            self.affect_neighbors_after_removal(pos, old, moved);
        }

        if self.info_at(pos).name != new_info.name {
            return false;
        }
        if flags & UPDATE_SKIP_ON_PLACE == 0 {
            self.on_place(pos, state, old, moved);
        }
        if self.has_block_entity(new_info.kind) && self.info_at(pos).name == new_info.name {
            match self.get_block_entity(pos) {
                None => {
                    if let Some(data) = self.new_block_entity(pos, state) {
                        let be = self.create_be(pos, data);
                        self.add_block_entity(pos, be);
                    }
                }
                Some(be) => self.update_block_entity_ticker(pos, be),
            }
        }

        // Level#setBlock, after the chunk update
        if self.get(pos) != state {
            return true;
        }
        if flags & UPDATE_NEIGHBORS != 0 {
            self.update_neighbors_at(pos, old_info.block, None);
            if self.has_analog_output_signal(new_info.kind) {
                self.update_neighbour_for_output_signal(pos, new_info.block);
            }
        }
        if flags & UPDATE_KNOWN_SHAPE == 0 && limit > 0 {
            let nflags = flags & !(UPDATE_NEIGHBORS | UPDATE_SUPPRESS_DROPS);
            self.update_indirect_neighbour_shapes(pos, old, nflags, limit - 1);
            self.update_neighbour_shapes(pos, state, nflags, limit - 1);
            self.update_indirect_neighbour_shapes(pos, state, nflags, limit - 1);
        }
        true
    }

    pub fn remove_block(&mut self, pos: Pos, moved_by_piston: bool) -> bool {
        self.set_block(pos, AIR, UPDATE_ALL | if moved_by_piston { UPDATE_MOVE_BY_PISTON } else { 0 }, UPDATE_LIMIT)
    }

    pub fn destroy_block(&mut self, pos: Pos, limit: i32) -> bool {
        if self.info_at(pos).is_air() {
            return false;
        }
        self.set_block(pos, AIR, UPDATE_ALL, limit)
    }

    /// Block#updateOrDestroy
    pub fn update_or_destroy(&mut self, old: StateId, new: StateId, pos: Pos, flags: u32, limit: i32) {
        if new != old {
            if self.info(new).is_air() {
                self.destroy_block(pos, limit);
            } else {
                self.set_block(pos, new, flags & !UPDATE_SUPPRESS_DROPS, limit);
            }
        }
    }

    pub fn take_dirty(&mut self) -> Vec<Pos> {
        self.dirty_set.clear();
        std::mem::take(&mut self.dirty)
    }

    // ------------------------------------------------------------------ neighbor updates
    pub fn update_neighbors_at(&mut self, pos: Pos, source: BlockId, skip: Option<Dir>) {
        let idx = if Some(UPDATE_ORDER[0]) == skip { 1 } else { 0 };
        self.add_and_run(Update::Multi { pos, source, skip, idx });
    }

    pub fn update_neighbors_at_except_from_facing(&mut self, pos: Pos, source: BlockId, skip: Dir) {
        self.update_neighbors_at(pos, source, Some(skip));
    }

    pub fn neighbor_changed(&mut self, pos: Pos, source: BlockId) {
        self.add_and_run(Update::Simple { pos, source });
    }

    pub fn neighbor_changed_with_state(&mut self, state: StateId, pos: Pos, source: BlockId, moved: bool) {
        self.add_and_run(Update::Full { state, pos, source, moved });
    }

    pub fn neighbor_shape_changed(&mut self, direction: Dir, pos: Pos, neighbor_pos: Pos, neighbor_state: StateId, flags: u32, limit: i32) {
        self.add_and_run(Update::Shape { direction, neighbor_state, pos, neighbor_pos, flags, limit });
    }

    /// BlockStateBase#updateNeighbourShapes
    pub fn update_neighbour_shapes(&mut self, pos: Pos, state: StateId, flags: u32, limit: i32) {
        for d in UPDATE_SHAPE_ORDER {
            self.neighbor_shape_changed(d.opposite(), pos.offset(d), pos, state, flags, limit);
        }
    }

    /// Level#updateNeighbourForOutputSignal: wake comparators next to or behind a conductor.
    pub fn update_neighbour_for_output_signal(&mut self, pos: Pos, source: BlockId) {
        for d in HORIZONTAL {
            let mut rel = pos.offset(d);
            let mut st = self.get(rel);
            if self.info(st).kind == Kind::Comparator {
                self.neighbor_changed_with_state(st, rel, source, false);
            } else if self.info(st).conductor() {
                rel = rel.offset(d);
                st = self.get(rel);
                if self.info(st).kind == Kind::Comparator {
                    self.neighbor_changed_with_state(st, rel, source, false);
                }
            }
        }
    }

    #[inline]
    fn execute_update(&mut self, state: StateId, pos: Pos, source: BlockId, moved: bool) {
        self.stat_neighbor_updates += 1;
        self.block_neighbor_changed(pos, state, source, moved);
    }

    fn execute_shape_update(&mut self, direction: Dir, pos: Pos, neighbor_pos: Pos, neighbor_state: StateId, flags: u32, limit: i32) {
        let current = self.get(pos);
        if flags & UPDATE_SKIP_SHAPE_UPDATE_ON_WIRE != 0 && self.info(current).kind == Kind::Wire {
            return;
        }
        let new = self.update_shape(pos, current, direction, neighbor_pos, neighbor_state);
        self.update_or_destroy(current, new, pos, flags, limit);
    }

    fn add_and_run(&mut self, update: Update) {
        let running = self.update_count > 0;
        let too_many = self.update_count >= MAX_CHAINED_NEIGHBOR_UPDATES;
        self.update_count += 1;
        if !too_many {
            if running {
                self.added_this_layer.push(update);
            } else {
                self.stack.push(update);
            }
        }
        if !running {
            self.run_updates();
        }
    }

    /// CollectingNeighborUpdater#runUpdates (depth-first stack).
    fn run_updates(&mut self) {
        while !self.stack.is_empty() || !self.added_this_layer.is_empty() {
            while let Some(u) = self.added_this_layer.pop() {
                self.stack.push(u);
            }
            let top = self.stack.len() - 1;
            while self.added_this_layer.is_empty() {
                if !self.run_next(top) {
                    self.stack.pop();
                    break;
                }
            }
        }
        self.stack.clear();
        self.added_this_layer.clear();
        self.update_count = 0;
    }

    /// Run the next step of the update at stack index `top`; false when it is finished.
    fn run_next(&mut self, top: usize) -> bool {
        match self.stack[top] {
            Update::Simple { pos, source } => {
                let state = self.get(pos);
                self.execute_update(state, pos, source, false);
                false
            }
            Update::Full { state, pos, source, moved } => {
                self.execute_update(state, pos, source, moved);
                false
            }
            Update::Shape { direction, neighbor_state, pos, neighbor_pos, flags, limit } => {
                self.execute_shape_update(direction, pos, neighbor_pos, neighbor_state, flags, limit);
                false
            }
            Update::Multi { pos, source, skip, idx } => {
                let d = UPDATE_ORDER[idx as usize];
                let mut next = idx + 1;
                if (next as usize) < UPDATE_ORDER.len() && Some(UPDATE_ORDER[next as usize]) == skip {
                    next += 1;
                }
                if let Update::Multi { idx, .. } = &mut self.stack[top] {
                    *idx = next;
                }
                let npos = pos.offset(d);
                let state = self.get(npos);
                self.execute_update(state, npos, source, false);
                (next as usize) < UPDATE_ORDER.len()
            }
        }
    }

    // ------------------------------------------------------------------ signals (SignalGetter)
    #[inline]
    pub fn is_conductor(&self, pos: Pos) -> bool {
        self.info_at(pos).conductor()
    }

    /// BlockState#isFaceSturdy(level, pos, face, SupportType)
    #[inline]
    pub fn is_face_sturdy(&self, pos: Pos, face: Dir, support: usize) -> bool {
        self.info_at(pos).sturdy(face, support)
    }

    pub fn get_direct_signal(&mut self, pos: Pos, direction: Dir) -> i32 {
        let st = self.get(pos);
        self.block_get_direct_signal(pos, st, direction)
    }

    pub fn get_direct_signal_to(&mut self, pos: Pos) -> i32 {
        let mut result = 0;
        for d in SIGNAL_ORDER {
            let p = pos.offset(d);
            let st = self.get(p);
            if st == AIR {
                continue; // air gives no signal
            }
            let s = self.block_get_direct_signal(p, st, d);
            if s > result {
                result = s;
                if result >= 15 {
                    return result;
                }
            }
        }
        result
    }

    pub fn get_signal(&mut self, pos: Pos, direction: Dir) -> i32 {
        let st = self.get(pos);
        let signal = self.block_get_signal(pos, st, direction);
        if signal >= 15 || !self.info(st).conductor() {
            return signal;
        }
        signal.max(self.get_direct_signal_to(pos))
    }

    #[inline]
    pub fn has_signal(&mut self, pos: Pos, direction: Dir) -> bool {
        self.get_signal(pos, direction) > 0
    }

    pub fn has_neighbor_signal(&mut self, pos: Pos) -> bool {
        for d in SIGNAL_ORDER {
            if self.get_signal(pos.offset(d), d) > 0 {
                return true;
            }
        }
        false
    }

    pub fn get_best_neighbor_signal(&mut self, pos: Pos) -> i32 {
        let mut best = 0;
        for d in ALL_DIRECTIONS {
            let s = self.get_signal(pos.offset(d), d);
            if s >= 15 {
                return 15;
            }
            best = best.max(s);
        }
        best
    }

    pub fn get_control_input_signal(&mut self, pos: Pos, direction: Dir, only_diodes: bool) -> i32 {
        let st = self.get(pos);
        let info = self.info(st);
        if only_diodes {
            return if matches!(info.kind, Kind::Repeater | Kind::Comparator) { self.get_direct_signal(pos, direction) } else { 0 };
        }
        match info.kind {
            Kind::RedstoneBlock => 15,
            Kind::Wire => info.power as i32,
            kind => {
                if self.is_signal_source(kind) {
                    self.get_direct_signal(pos, direction)
                } else {
                    0
                }
            }
        }
    }

    // ------------------------------------------------------------------ scheduled ticks
    pub fn schedule_tick(&mut self, pos: Pos, block: BlockId, delay: i64, priority: i32) {
        if !self.pending.insert((pos, block)) {
            return;
        }
        self.sub_tick += 1;
        self.ticks.push(ScheduledTick { trigger_tick: self.game_time + delay, priority, sub_tick: self.sub_tick, pos, block });
    }

    #[inline]
    pub fn has_scheduled_tick(&self, pos: Pos, block: BlockId) -> bool {
        self.pending.contains(&(pos, block))
    }

    #[inline]
    pub fn will_tick_this_tick(&self, pos: Pos, block: BlockId) -> bool {
        !self.running_this_tick.is_empty() && self.running_this_tick.contains(&(pos, block))
    }

    pub fn clear_scheduled_ticks(&mut self) {
        self.ticks.clear();
        self.pending.clear();
    }

    pub fn scheduled_tick_count(&self) -> usize {
        self.ticks.len()
    }

    /// Pending ticks in the order they would run.
    pub fn scheduled_ticks(&self) -> Vec<ScheduledTick> {
        let mut v: Vec<ScheduledTick> = self.ticks.iter().copied().collect();
        v.sort_unstable_by(|a, b| b.cmp(a));
        v
    }

    fn run_block_ticks(&mut self) {
        let mut to_run: Vec<ScheduledTick> = Vec::new();
        while let Some(t) = self.ticks.peek() {
            if t.trigger_tick > self.game_time {
                break;
            }
            let t = self.ticks.pop().unwrap();
            self.pending.remove(&(t.pos, t.block));
            to_run.push(t);
        }
        if to_run.is_empty() {
            return;
        }
        self.running_this_tick.clear();
        self.running_this_tick.extend(to_run.iter().map(|t| (t.pos, t.block)));
        for t in to_run {
            self.running_this_tick.remove(&(t.pos, t.block));
            let state = self.get(t.pos);
            if self.info(state).name == t.block {
                // ServerLevel#tickBlock
                self.block_tick(t.pos, state);
            }
        }
        self.running_this_tick.clear();
    }

    // ------------------------------------------------------------------ block events
    pub fn block_event(&mut self, pos: Pos, block: BlockId, a: i32, b: i32) {
        let ev = BlockEvent { pos, block, a, b };
        if !self.block_events.contains(&ev) {
            self.block_events.push_back(ev);
        }
    }

    fn run_block_events(&mut self) {
        while let Some(ev) = self.block_events.pop_front() {
            let state = self.get(ev.pos);
            if self.info(state).name == ev.block {
                self.trigger_event(ev.pos, state, ev.a, ev.b);
            }
        }
    }

    // ------------------------------------------------------------------ block entity ticking
    /// Level#tickBlockEntities
    fn tick_block_entities(&mut self) {
        self.ticking_block_entities = true;
        if !self.pending_be_tickers.is_empty() {
            let pending = std::mem::take(&mut self.pending_be_tickers);
            self.be_tickers.extend(pending);
        }
        let mut i = 0;
        while i < self.be_tickers.len() {
            let w = self.be_tickers[i];
            if self.wrapper_removed(w) {
                self.be_tickers.remove(i);
                continue;
            }
            if let Some(be) = self.wrappers[w] {
                self.tick_block_entity(be);
            }
            i += 1;
        }
        self.ticking_block_entities = false;
    }

    /// Not part of the game: no scheduled ticks, no block events and no block entity with pending work
    /// (redstone.analysis.experiment.world_is_idle).
    pub fn is_idle(&self) -> bool {
        if !self.ticks.is_empty() || !self.block_events.is_empty() {
            return false;
        }
        for &w in self.be_tickers.iter().chain(self.pending_be_tickers.iter()) {
            let Some(be) = self.wrappers[w] else { continue };
            let be = &self.bes[be];
            if be.removed {
                continue;
            }
            match &be.data {
                // A hopper without cooldown has found nothing to move.
                BeData::Container(Container { kind: ContainerKind::Hopper { cooldown_time, .. }, .. }) => {
                    if *cooldown_time > 0 {
                        return false;
                    }
                }
                _ => return false,
            }
        }
        true
    }

    // ------------------------------------------------------------------ the game tick
    /// One game tick (ServerLevel#tick, redstone-relevant phases only).
    pub fn tick(&mut self) {
        self.handling_tick = true;
        self.game_time += 1;
        self.run_block_ticks();
        self.run_block_events();
        self.handling_tick = false;
        self.tick_block_entities();
    }

    // ------------------------------------------------------------------ mechanics notes
    /// redstone.sim.notes.note: the first occurrence per (kind, position) is recorded.
    pub fn note(&mut self, kind: &'static str, pos: Pos, detail: &str) {
        debug_assert!(NOTE_KINDS.contains(&kind));
        if !self.notes_seen.insert((kind, pos)) {
            return;
        }
        self.notes.push(Note { tick: self.game_time, kind, pos, detail: detail.to_owned() });
    }

    /// `state.id`: the name without the `minecraft:` namespace.
    pub fn state_short_id(&self, state: StateId) -> String {
        crate::data::block_id(self.st.block_name(self.info(state).name)).to_owned()
    }
}
