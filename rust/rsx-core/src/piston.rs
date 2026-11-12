//! Pistons: piston, sticky_piston, piston_head, moving_piston and the moving block entity
//! (port of redstone/sim/blocks/piston.py; the Python module is the reference).
//!
//! References (26.3, Mojang names): PistonBaseBlock, PistonHeadBlock, MovingPistonBlock,
//! PistonMovingBlockEntity, PistonStructureResolver. Entity movement is out of scope.

use crate::common::*;
use crate::data;
use crate::state::*;
use crate::world::*;
use rustc_hash::FxHashSet;

const TRIGGER_EXTEND: i32 = 0;
const TRIGGER_CONTRACT: i32 = 1;
const TRIGGER_DROP: i32 = 2;
const MAX_PUSH_DEPTH: usize = 12;

// World positions are absolute. They matter for the build height check in isPushable and the HashMap
// iteration order in moveBlocks (BlockPos#hashCode).
const MIN_Y: i32 = -64;
const MAX_Y: i32 = 319;

// ---------------------------------------------------------------------------------- PosHashMap
/// java.util.HashMap<BlockPos, BlockState> iteration order (no treeification; <= 13 entries in practice).
struct PosHashMap {
    cap: usize,
    buckets: Vec<Vec<(Pos, StateId)>>,
    size: usize,
}

impl PosHashMap {
    fn new() -> PosHashMap {
        PosHashMap { cap: 16, buckets: vec![Vec::new(); 16], size: 0 }
    }

    #[inline]
    fn bucket(&self, pos: Pos) -> usize {
        pos.java_spread() as usize & (self.cap - 1)
    }

    fn resize(&mut self) {
        let old: Vec<(Pos, StateId)> = self.buckets.drain(..).flatten().collect();
        self.cap *= 2;
        self.buckets = vec![Vec::new(); self.cap];
        for e in old {
            // split keeps relative order within each new bucket
            let b = self.bucket(e.0);
            self.buckets[b].push(e);
        }
    }

    fn put(&mut self, pos: Pos, value: StateId) {
        let b = self.bucket(pos);
        if let Some(e) = self.buckets[b].iter_mut().find(|e| e.0 == pos) {
            e.1 = value;
            return;
        }
        self.buckets[b].push((pos, value));
        if self.buckets[b].len() >= 9 && self.cap < 64 {
            // treeifyBin resizes small tables instead
            self.resize();
        }
        self.size += 1;
        if self.size > self.cap * 3 / 4 {
            self.resize();
        }
    }

    fn remove(&mut self, pos: Pos) {
        let b = self.bucket(pos);
        if let Some(i) = self.buckets[b].iter().position(|e| e.0 == pos) {
            self.buckets[b].remove(i);
            self.size -= 1;
        }
    }

    fn items(&self) -> Vec<(Pos, StateId)> {
        self.buckets.iter().flatten().copied().collect()
    }
}

// ---------------------------------------------------------------------------------- PistonStructureResolver
#[inline]
fn is_piston_base(w: &World, state: StateId) -> bool {
    w.info(state).kind == Kind::Piston
}

/// PistonBaseBlock#isPushable
fn is_pushable(w: &World, state: StateId, pos: Pos, direction: Dir, allow_destroyable: bool, connection_direction: Dir) -> bool {
    let y = pos.y;
    if !(MIN_Y..=MAX_Y).contains(&y) {
        return false;
    }
    let info = w.info(state);
    if info.is_air() {
        return true;
    }
    if direction == Dir::Down && y == MIN_Y {
        return false;
    }
    if direction == Dir::Up && y == MAX_Y {
        return false;
    }
    if info.kind != Kind::Piston {
        if info.flags & SF_UNBREAKABLE != 0 {
            return false; // getDestroySpeed == -1
        }
        let reaction = w.piston_push_reaction(state);
        if reaction == data::IMMOVEABLE {
            return false;
        }
        if reaction == data::POPPED {
            return allow_destroyable;
        }
        if reaction == data::PUSH {
            return direction == connection_direction;
        }
    } else if info.extended() {
        return false;
    }
    !(w.has_block_entity(info.kind) || info.flags & SF_DATA_BLOCK_ENTITY != 0)
}

#[derive(Copy, Clone, PartialEq, Eq)]
enum Sticky {
    No,
    Slime,
    Honey,
}

fn sticky_kind(w: &World, state: StateId) -> Sticky {
    let info = w.info(state);
    if info.kind != Kind::Plain {
        return Sticky::No;
    }
    match w.st.block_name(info.name) {
        "minecraft:slime_block" => Sticky::Slime,
        "minecraft:honey_block" => Sticky::Honey,
        _ => Sticky::No,
    }
}

#[inline]
fn is_sticky(w: &World, state: StateId) -> bool {
    sticky_kind(w, state) != Sticky::No
}

fn can_stick_to_each_other(w: &World, a: StateId, b: StateId) -> bool {
    let (ka, kb) = (sticky_kind(w, a), sticky_kind(w, b));
    if ka == Sticky::Honey && kb == Sticky::Slime {
        return false;
    }
    if ka == Sticky::Slime && kb == Sticky::Honey {
        return false;
    }
    ka != Sticky::No || kb != Sticky::No
}

#[inline]
fn same_axis(a: Dir, b: Dir) -> bool {
    a == b || a == b.opposite()
}

struct Resolver {
    piston_pos: Pos,
    piston_direction: Dir,
    extending: bool,
    push_direction: Dir,
    start_pos: Pos,
    to_push: Vec<Pos>,
    to_destroy: Vec<Pos>,
}

impl Resolver {
    fn new(piston_pos: Pos, direction: Dir, extending: bool) -> Resolver {
        let (push_direction, start_pos) = if extending {
            (direction, piston_pos.offset(direction))
        } else {
            (direction.opposite(), piston_pos.offset_n(direction, 2))
        };
        Resolver {
            piston_pos,
            piston_direction: direction,
            extending,
            push_direction,
            start_pos,
            to_push: Vec::new(),
            to_destroy: Vec::new(),
        }
    }

    fn resolve(&mut self, w: &World) -> bool {
        self.to_push.clear();
        self.to_destroy.clear();
        let next_state = w.get(self.start_pos);
        if !is_pushable(w, next_state, self.start_pos, self.push_direction, false, self.piston_direction) {
            if self.extending && w.piston_push_reaction(next_state) == data::POPPED {
                self.to_destroy.push(self.start_pos);
                return true;
            }
            return false;
        }
        if !self.add_block_line(w, self.start_pos, self.push_direction) {
            return false;
        }
        let mut i = 0;
        while i < self.to_push.len() {
            let pos = self.to_push[i];
            if is_sticky(w, w.get(pos)) && !self.add_branching_blocks(w, pos) {
                return false;
            }
            i += 1;
        }
        true
    }

    fn add_block_line(&mut self, w: &World, start: Pos, direction: Dir) -> bool {
        let back = self.push_direction.opposite();
        let mut next_state = w.get(start);
        if w.info(next_state).is_air() {
            return true;
        }
        if !is_pushable(w, next_state, start, self.push_direction, false, direction) {
            return true;
        }
        if start == self.piston_pos {
            return true;
        }
        if self.to_push.contains(&start) {
            return true;
        }
        let mut block_count: usize = 1;
        if block_count + self.to_push.len() > MAX_PUSH_DEPTH {
            return false;
        }
        while is_sticky(w, next_state) {
            let pos = start.offset_n(back, block_count as i32);
            let previous = next_state;
            next_state = w.get(pos);
            if w.info(next_state).is_air()
                || !can_stick_to_each_other(w, previous, next_state)
                || !is_pushable(w, next_state, pos, self.push_direction, false, back)
                || pos == self.piston_pos
            {
                break;
            }
            block_count += 1;
            if block_count + self.to_push.len() > MAX_PUSH_DEPTH {
                return false;
            }
        }
        let mut blocks_added: usize = 0;
        for i in (0..block_count).rev() {
            self.to_push.push(start.offset_n(back, i as i32));
            blocks_added += 1;
        }
        let mut i = 1;
        loop {
            let pos = start.offset_n(self.push_direction, i);
            if let Some(collision) = self.to_push.iter().position(|p| *p == pos) {
                self.reorder_list_at_collision(blocks_added, collision);
                let mut j = 0;
                while j < collision + blocks_added + 1 {
                    let p = self.to_push[j];
                    if is_sticky(w, w.get(p)) && !self.add_branching_blocks(w, p) {
                        return false;
                    }
                    j += 1;
                }
                return true;
            }
            let next_state = w.get(pos);
            if w.info(next_state).is_air() {
                return true;
            }
            if !is_pushable(w, next_state, pos, self.push_direction, true, self.push_direction) || pos == self.piston_pos {
                return false;
            }
            if w.piston_push_reaction(next_state) == data::POPPED {
                self.to_destroy.push(pos);
                return true;
            }
            if self.to_push.len() >= MAX_PUSH_DEPTH {
                return false;
            }
            self.to_push.push(pos);
            blocks_added += 1;
            i += 1;
        }
    }

    fn reorder_list_at_collision(&mut self, blocks_added: usize, collision: usize) {
        let n = self.to_push.len();
        let mut out = Vec::with_capacity(n);
        out.extend_from_slice(&self.to_push[..collision]);
        out.extend_from_slice(&self.to_push[n - blocks_added..]);
        out.extend_from_slice(&self.to_push[collision..n - blocks_added]);
        self.to_push = out;
    }

    fn add_branching_blocks(&mut self, w: &World, from_pos: Pos) -> bool {
        let from_state = w.get(from_pos);
        for d in ALL_DIRECTIONS {
            if same_axis(d, self.push_direction) {
                continue;
            }
            let npos = from_pos.offset(d);
            if can_stick_to_each_other(w, w.get(npos), from_state) && !self.add_block_line(w, npos, d) {
                return false;
            }
        }
        true
    }
}

// Blocks whose update can come with a change of the power a piston sees (see piston.py).
const POWER_SOURCES: &[&str] = &[
    "redstone_wire", "lever", "redstone_torch", "redstone_wall_torch", "repeater", "comparator", "observer",
    "redstone_block", "daylight_detector", "target", "tripwire_hook", "trapped_chest", "lectern",
    "sculk_sensor", "calibrated_sculk_sensor", "detector_rail", "lightning_rod", "moving_piston",
    "piston", "sticky_piston", "piston_head",
];

fn can_change_power(source_name: &str) -> bool {
    let name = source_name.strip_prefix("minecraft:").unwrap_or(source_name);
    POWER_SOURCES.contains(&name) || name.ends_with("_button") || name.ends_with("_pressure_plate")
}

/// Like can_change_power, but a removed conductor next to the piston may also have carried its power.
fn can_remove_power(source_name: &str) -> bool {
    if can_change_power(source_name) {
        return true;
    }
    // unknown block: do not claim a BUD
    data::default_state_is_conductor(source_name).unwrap_or(true)
}

impl World {
    #[inline]
    fn pbe(&self, be: BeId) -> Option<&PistonBe> {
        match &self.bes[be].data {
            BeData::Piston(b) => Some(b),
            _ => None,
        }
    }

    #[inline]
    fn pbe_mut(&mut self, be: BeId) -> Option<&mut PistonBe> {
        match &mut self.bes[be].data {
            BeData::Piston(b) => Some(b),
            _ => None,
        }
    }

    /// piston.get_piston_be
    fn get_piston_be(&mut self, pos: Pos) -> Option<BeId> {
        let be = self.get_block_entity(pos)?;
        if matches!(self.bes[be].data, BeData::Piston(_)) {
            Some(be)
        } else {
            None
        }
    }

    fn new_piston_be(&mut self, pos: Pos, moved_state: StateId, direction: Dir, extending: bool, is_source_piston: bool) -> BeId {
        self.create_be(
            pos,
            BeData::Piston(PistonBe {
                moved_state,
                direction,
                extending,
                is_source_piston,
                progress: 0.0,
                progress_o: 0.0,
                last_ticked: 0,
            }),
        )
    }

    /// Block#updateFromNeighbourShapes
    fn update_from_neighbour_shapes(&mut self, state: StateId, pos: Pos) -> StateId {
        let mut new = state;
        for d in UPDATE_SHAPE_ORDER {
            let npos = pos.offset(d);
            let nstate = self.get(npos);
            new = self.update_shape(pos, new, d, npos, nstate);
        }
        new
    }

    // ------------------------------------------------------------------ PistonBaseBlock
    pub fn piston_neighbor_changed(&mut self, pos: Pos, state: StateId, source: BlockId) {
        self.piston_check_if_extend(pos, state, Some(source));
    }

    pub fn piston_on_place(&mut self, pos: Pos, state: StateId, old: StateId) {
        if self.info(old).name != self.info(state).name && self.get_block_entity(pos).is_none() {
            self.piston_check_if_extend(pos, state, None);
        }
    }

    fn piston_check_if_extend(&mut self, pos: Pos, state: StateId, source: Option<BlockId>) {
        let info = self.info(state);
        let direction = info.facing();
        let extend = self.piston_get_neighbor_signal(pos, direction);
        let extended = info.extended();
        if extend && !extended {
            if Resolver::new(pos, direction, true).resolve(self) {
                self.block_event(pos, info.block, TRIGGER_EXTEND, direction.index() as i32);
                self.piston_note_activation(pos, direction, source);
            }
        } else if !extend && extended {
            if let Some(src) = source {
                if !can_remove_power(self.st.block_name(src)) {
                    self.note("bud", pos, "blieb unbestromt ausgefahren, bis ein Block-Update kam");
                }
            }
            let pushed_pos = pos.offset_n(direction, 2);
            let pushed_state = self.get(pushed_pos);
            let pushed_info = self.info(pushed_state);
            let mut event = TRIGGER_CONTRACT;
            if pushed_info.kind == Kind::MovingPiston && pushed_info.facing() == direction {
                if let Some(be) = self.get_piston_be(pushed_pos) {
                    let b = self.pbe(be).unwrap();
                    // get_progress(0.0) == progress_o
                    let progress = b.progress_o + 0.0 * (b.progress - b.progress_o);
                    if b.extending && (progress < 0.5 || self.game_time == b.last_ticked || self.handling_tick) {
                        event = TRIGGER_DROP;
                    }
                }
            }
            self.block_event(pos, info.block, event, direction.index() as i32);
        }
    }

    fn piston_get_neighbor_signal(&mut self, pos: Pos, push_direction: Dir) -> bool {
        self.piston_has_direct_signal(pos, push_direction) || self.piston_has_qc_signal(pos)
    }

    /// First part of PistonBaseBlock#getNeighborSignal: the five sides except the front.
    pub fn piston_has_direct_signal(&mut self, pos: Pos, push_direction: Dir) -> bool {
        for d in ALL_DIRECTIONS {
            if d != push_direction && self.has_signal(pos.offset(d), d) {
                return true;
            }
        }
        false
    }

    /// Second part of getNeighborSignal (quasi-connectivity): the position above counts like the piston.
    pub fn piston_has_qc_signal(&mut self, pos: Pos) -> bool {
        if self.has_signal(pos, Dir::Down) {
            return true;
        }
        let above = pos.above();
        for d in ALL_DIRECTIONS {
            if d != Dir::Down && self.has_signal(above.offset(d), d) {
                return true;
            }
        }
        false
    }

    /// Mechanics notes (analysis only, no influence on the simulation).
    fn piston_note_activation(&mut self, pos: Pos, direction: Dir, source: Option<BlockId>) {
        if self.piston_has_direct_signal(pos, direction) {
            return;
        }
        self.note("quasi_connectivity", pos, "");
        if let Some(src) = source {
            if !can_change_power(self.st.block_name(src)) {
                self.note("bud", pos, "fuhr erst nach einem Block-Update ohne Leistungsänderung aus");
            }
        }
    }

    pub fn piston_trigger_event(&mut self, pos: Pos, state: StateId, b0: i32, b1: i32) -> bool {
        let info = self.info(state);
        let is_sticky_piston = info.param == 1;
        let direction = info.facing();
        let extended_state = self.st.with_bool(state, sym::EXTENDED, true);
        let extend = self.piston_get_neighbor_signal(pos, direction);
        let contract_or_drop = b0 == TRIGGER_CONTRACT || b0 == TRIGGER_DROP;
        if extend && contract_or_drop {
            self.set_block(pos, extended_state, 2, UPDATE_LIMIT);
            return false;
        }
        if !extend && b0 == TRIGGER_EXTEND {
            return false;
        }

        if b0 == TRIGGER_EXTEND {
            if !self.piston_move_blocks(pos, direction, true, is_sticky_piston) {
                return false;
            }
            self.set_block(pos, extended_state, 67, UPDATE_LIMIT);
            self.game_event("block_activate", pos, Some(extended_state));
        } else if contract_or_drop {
            if let Some(head_be) = self.get_piston_be(pos.offset(direction)) {
                let b = self.pbe(head_be).unwrap();
                if self.handling_tick && b.extending && b.is_source_piston && b.progress == 0.0 && b.progress_o == 0.0 {
                    // the head was created by an extend event earlier in this block-event phase (ZT-003)
                    self.note("zero_tick", pos, "");
                }
                self.piston_be_final_tick(head_be);
            }
            let ptype = if is_sticky_piston { sym::STICKY } else { sym::NORMAL };
            let moving_state =
                self.st.state_of_name("minecraft:moving_piston", &[(sym::FACING, Sym::dir(direction)), (sym::TYPE, ptype)]);
            self.set_block(pos, moving_state, 276, UPDATE_LIMIT);
            let moved_facing = Dir::from_index((b1 & 7) as usize);
            let moved = self.st.state_of(info.name, &[(sym::EXTENDED, sym::FALSE), (sym::FACING, Sym::dir(moved_facing))]);
            let be = self.new_piston_be(pos, moved, direction, false, true);
            self.set_block_entity(be);
            let moving_block = self.info(moving_state).block;
            self.update_neighbors_at(pos, moving_block, None);
            self.update_neighbour_shapes(pos, moving_state, 2, UPDATE_LIMIT);
            if is_sticky_piston {
                let two_pos = pos.offset_n(direction, 2);
                let moving = self.get(two_pos);
                let mut piston_piece = false;
                if self.info(moving).kind == Kind::MovingPiston {
                    if let Some(be) = self.get_piston_be(two_pos) {
                        let b = self.pbe(be).unwrap();
                        if b.direction == direction && b.extending {
                            self.piston_be_final_tick(be);
                            piston_piece = true;
                            // the pushed block stays at the extended position (PIS-010, PIS-012)
                            let moved_state = self.pbe(be).unwrap().moved_state;
                            let detail = self.state_short_id(moved_state);
                            self.note("piston_spit", pos, &detail);
                        }
                    }
                }
                if !piston_piece {
                    if b0 != TRIGGER_CONTRACT
                        || self.info(moving).is_air()
                        || !is_pushable(self, moving, two_pos, direction.opposite(), false, direction)
                        || (self.piston_push_reaction(moving) != data::PUSH_PULL && !is_piston_base(self, moving))
                    {
                        self.remove_block(pos.offset(direction), false);
                    } else {
                        self.piston_move_blocks(pos, direction, false, is_sticky_piston);
                    }
                }
            } else {
                self.remove_block(pos.offset(direction), false);
            }
            self.game_event("block_deactivate", pos, Some(moving_state));
        }
        true
    }

    fn piston_move_blocks(&mut self, piston_pos: Pos, direction: Dir, extending: bool, is_sticky_piston: bool) -> bool {
        let arm_pos = piston_pos.offset(direction);
        if !extending && self.info_at(arm_pos).kind == Kind::PistonHead {
            self.set_block(arm_pos, AIR, 276, UPDATE_LIMIT);
        }
        let mut resolver = Resolver::new(piston_pos, direction, extending);
        if !resolver.resolve(self) {
            return false;
        }
        let mut delete_after_move = PosHashMap::new();
        let to_push = std::mem::take(&mut resolver.to_push);
        let mut to_push_shapes: Vec<StateId> = Vec::with_capacity(to_push.len());
        for &p in &to_push {
            let st = self.get(p);
            to_push_shapes.push(st);
            delete_after_move.put(p, st);
        }
        let to_destroy = std::mem::take(&mut resolver.to_destroy);
        let mut to_update: Vec<StateId> = Vec::with_capacity(to_push.len() + to_destroy.len());
        let push_direction = if extending { direction } else { direction.opposite() };

        for &p in to_destroy.iter().rev() {
            let st = self.get(p);
            // dropResources: items are not simulated
            self.set_block(p, AIR, 18, UPDATE_LIMIT);
            self.game_event("block_destroy", p, Some(st));
            to_update.push(st);
        }

        for i in (0..to_push.len()).rev() {
            let st = self.get(to_push[i]);
            let p = to_push[i].offset(push_direction);
            delete_after_move.remove(p);
            let actual = self
                .st
                .state_of_name("minecraft:moving_piston", &[(sym::FACING, Sym::dir(direction)), (sym::TYPE, sym::NORMAL)]);
            self.set_block(p, actual, 324, UPDATE_LIMIT);
            let be = self.new_piston_be(p, to_push_shapes[i], direction, extending, false);
            self.set_block_entity(be);
            to_update.push(st);
        }

        if extending {
            let ptype = if is_sticky_piston { sym::STICKY } else { sym::NORMAL };
            let head = self.st.state_of_name(
                "minecraft:piston_head",
                &[(sym::FACING, Sym::dir(direction)), (sym::SHORT, sym::FALSE), (sym::TYPE, ptype)],
            );
            let moving =
                self.st.state_of_name("minecraft:moving_piston", &[(sym::FACING, Sym::dir(direction)), (sym::TYPE, ptype)]);
            delete_after_move.remove(arm_pos);
            self.set_block(arm_pos, moving, 324, UPDATE_LIMIT);
            let be = self.new_piston_be(arm_pos, head, direction, true, true);
            self.set_block_entity(be);
        }

        let entries = delete_after_move.items();
        for &(p, _) in &entries {
            self.set_block(p, AIR, 82, UPDATE_LIMIT);
        }
        for &(p, old) in &entries {
            self.update_indirect_neighbour_shapes(p, old, 2, UPDATE_LIMIT);
            self.update_neighbour_shapes(p, AIR, 2, UPDATE_LIMIT);
            self.update_indirect_neighbour_shapes(p, AIR, 2, UPDATE_LIMIT);
        }

        let mut idx = 0;
        for &p in to_destroy.iter().rev() {
            let st = to_update[idx];
            idx += 1;
            self.affect_neighbors_after_removal(p, st, false);
            self.update_indirect_neighbour_shapes(p, st, 2, UPDATE_LIMIT);
            let block = self.info(st).block;
            self.update_neighbors_at(p, block, None);
        }
        for i in (0..to_push.len()).rev() {
            let block = self.info(to_update[idx]).block;
            self.update_neighbors_at(to_push[i], block, None);
            idx += 1;
        }
        if extending {
            let head_block = self.st.block_id("minecraft:piston_head");
            self.update_neighbors_at(arm_pos, head_block, None);
        }
        true
    }

    /// piston.check_bud_states: note pistons resting in a BUD state (quasi-powered but retracted, or
    /// unpowered but extended).
    pub fn check_bud_states(&mut self) {
        let events: FxHashSet<Pos> = self.block_events.iter().map(|ev| ev.pos).collect();
        for (pos, state) in self.store.items() {
            let info = self.info(state);
            if info.kind != Kind::Piston || events.contains(&pos) {
                continue;
            }
            let direction = info.facing();
            let powered = self.piston_get_neighbor_signal(pos, direction);
            if info.extended() {
                if !powered && self.info_at(pos.offset(direction)).kind == Kind::PistonHead {
                    self.note("bud", pos, "unbestromt, aber ausgefahren");
                }
            } else if powered
                && !self.piston_has_direct_signal(pos, direction)
                && Resolver::new(pos, direction, true).resolve(self)
            {
                self.note("bud", pos, "per Quasi-Connectivity bestromt, aber eingefahren");
            }
        }
    }

    // ------------------------------------------------------------------ PistonHeadBlock
    fn piston_head_is_fitting_base(&self, arm: StateId, base: StateId) -> bool {
        let sticky_base = self.st.get(arm, sym::TYPE) != Some(sym::NORMAL);
        let base_info = self.info(base);
        base_info.kind == Kind::Piston
            && (base_info.param == 1) == sticky_base
            && base_info.extended()
            && self.st.get(base, sym::FACING) == self.st.get(arm, sym::FACING)
    }

    fn piston_head_can_survive(&self, pos: Pos, state: StateId) -> bool {
        let base = self.get(pos.offset(self.info(state).facing().opposite()));
        self.piston_head_is_fitting_base(state, base)
            || (self.info(base).kind == Kind::MovingPiston
                && self.st.get(base, sym::FACING) == self.st.get(state, sym::FACING))
    }

    pub fn piston_head_neighbor_changed(&mut self, pos: Pos, state: StateId, source: BlockId) {
        if self.piston_head_can_survive(pos, state) {
            self.neighbor_changed(pos.offset(self.info(state).facing().opposite()), source);
        }
    }

    pub fn piston_head_affect_neighbors_after_removal(&mut self, pos: Pos, state: StateId) {
        let base_pos = pos.offset(self.info(state).facing().opposite());
        if self.piston_head_is_fitting_base(state, self.get(base_pos)) {
            self.destroy_block(base_pos, UPDATE_LIMIT);
        }
    }

    pub fn piston_head_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir) -> StateId {
        if direction.opposite() == self.info(state).facing() && !self.piston_head_can_survive(pos, state) {
            return AIR;
        }
        state
    }

    // ------------------------------------------------------------------ MovingPistonBlock
    pub fn moving_piston_use(&mut self, pos: Pos, _state: StateId) -> bool {
        if self.get_block_entity(pos).is_none() {
            self.remove_block(pos, false);
            return true;
        }
        false
    }

    // ------------------------------------------------------------------ PistonMovingBlockEntity
    /// PistonMovingBlockEntity#tick (via BoundTickingBlockEntity, which requires a moving_piston)
    pub fn piston_be_tick(&mut self, be: BeId) {
        let pos = self.bes[be].pos;
        if self.info_at(pos).kind != Kind::MovingPiston {
            return;
        }
        let game_time = self.game_time;
        let Some(b) = self.pbe_mut(be) else { return };
        b.last_ticked = game_time;
        b.progress_o = b.progress;
        if b.progress_o >= 1.0 {
            let moved_state = b.moved_state;
            self.remove_block_entity(pos);
            self.bes[be].removed = true;
            if self.info_at(pos).kind == Kind::MovingPiston {
                let mut new = self.update_from_neighbour_shapes(moved_state, pos);
                if self.info(new).is_air() {
                    self.set_block(pos, moved_state, 340, UPDATE_LIMIT);
                    self.update_or_destroy(moved_state, new, pos, UPDATE_ALL, UPDATE_LIMIT);
                } else {
                    if self.st.get(new, sym::WATERLOGGED) == Some(sym::TRUE) {
                        new = self.st.with_bool(new, sym::WATERLOGGED, false);
                    }
                    self.set_block(pos, new, 67, UPDATE_LIMIT);
                    let block = self.info(new).block;
                    self.neighbor_changed(pos, block);
                }
            }
        } else {
            b.progress = (b.progress + 0.5).min(1.0);
        }
    }

    /// PistonMovingBlockEntity#finalTick
    pub fn piston_be_final_tick(&mut self, be: BeId) {
        let pos = self.bes[be].pos;
        let Some(b) = self.pbe_mut(be) else { return };
        if b.progress_o < 1.0 {
            b.progress = 1.0;
            b.progress_o = 1.0;
            let (moved_state, is_source_piston) = (b.moved_state, b.is_source_piston);
            self.remove_block_entity(pos);
            self.bes[be].removed = true;
            if self.info_at(pos).kind == Kind::MovingPiston {
                let new = if is_source_piston { AIR } else { self.update_from_neighbour_shapes(moved_state, pos) };
                self.set_block(pos, new, UPDATE_ALL, UPDATE_LIMIT);
                let block = self.info(new).block;
                self.neighbor_changed(pos, block);
            }
        }
    }
}
