//! Copper bulb, note block, target, doors, trapdoors, fence gates, rails, lectern
//! (port of redstone/sim/blocks/outputs.py).

use crate::common::*;
use crate::data;
use crate::state::*;
use crate::world::*;
use rustc_hash::{FxHashMap, FxHashSet};

/// `_WORKS_ABOVE`: NoteBlockInstrument#worksAboveNoteBlock() (mob heads and the custom head).
fn works_above(instrument: &str) -> bool {
    matches!(instrument, "zombie" | "skeleton" | "creeper" | "dragon" | "wither_skeleton" | "piglin" | "custom_head")
}

/// Direction the oracle's FakePlayer looks at (yRot 0 = south), used by FenceGateBlock#useWithoutItem.
const PLAYER_DIRECTION: Dir = Dir::South;

const MAX_SEARCH_DEPTH: i32 = 8;

fn is_slope(shape: Option<Sym>) -> bool {
    matches!(
        shape,
        Some(sym::ASCENDING_EAST | sym::ASCENDING_WEST | sym::ASCENDING_NORTH | sym::ASCENDING_SOUTH)
    )
}

/// net.minecraft.world.level.block.RailState
struct RailState {
    pos: Pos,
    state: StateId,
    is_straight: bool,
    connections: Vec<Pos>,
}

fn rail_connections(p: Pos, shape: Sym) -> Vec<Pos> {
    let (n, s, w, e) = (p.offset(Dir::North), p.offset(Dir::South), p.offset(Dir::West), p.offset(Dir::East));
    match shape {
        sym::NORTH_SOUTH => vec![n, s],
        sym::EAST_WEST => vec![w, e],
        sym::ASCENDING_EAST => vec![w, e.above()],
        sym::ASCENDING_WEST => vec![w.above(), e],
        sym::ASCENDING_NORTH => vec![n.above(), s],
        sym::ASCENDING_SOUTH => vec![n, s.above()],
        sym::SOUTH_EAST => vec![e, s],
        sym::SOUTH_WEST => vec![w, s],
        sym::NORTH_WEST => vec![w, n],
        sym::NORTH_EAST => vec![e, n],
        // Python raises a KeyError for a shape that does not exist.
        _ => Vec::new(),
    }
}

impl RailState {
    fn has_connection(&self, rail_pos: Pos) -> bool {
        self.connections.iter().any(|p| p.x == rail_pos.x && p.z == rail_pos.z)
    }

    fn connects_to(&self, rail: &RailState) -> bool {
        self.has_connection(rail.pos)
    }

    fn can_connect_to(&self, rail: &RailState) -> bool {
        self.connects_to(rail) || self.connections.len() != 2
    }
}

impl World {
    // ------------------------------------------------------------------ copper bulb
    pub fn copper_bulb_check_and_flip(&mut self, pos: Pos, state: StateId) {
        let signal = self.has_neighbor_signal(pos);
        let info = self.info(state);
        if signal != info.powered() {
            let mut new = state;
            if !info.powered() {
                new = self.st.with_bool(new, sym::LIT, !info.lit());
            }
            let new = self.st.with_bool(new, sym::POWERED, signal);
            self.set_block_f(pos, new, UPDATE_ALL);
        }
    }

    // ------------------------------------------------------------------ note block
    /// outputs._instrument(state)
    pub fn instrument(&self, state: StateId) -> String {
        let name = self.st.block_name(self.info(state).name);
        let props: Vec<(&str, &str)> =
            self.st.props(state).iter().map(|(k, v)| (self.st.sym_str(*k), self.st.sym_str(*v))).collect();
        data::lookup(name, &props).instrument.to_owned()
    }

    fn note_block_set_instrument(&mut self, pos: Pos, state: StateId) -> StateId {
        let above = self.instrument(self.get(pos.above()));
        if works_above(&above) {
            let v = self.st.sym(&above);
            return self.st.with(state, sym::INSTRUMENT, v);
        }
        let below = self.instrument(self.get(pos.below()));
        let v = if works_above(&below) { sym::HARP } else { self.st.sym(&below) };
        self.st.with(state, sym::INSTRUMENT, v)
    }

    pub fn note_block_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir) -> StateId {
        if matches!(direction, Dir::Up | Dir::Down) {
            return self.note_block_set_instrument(pos, state);
        }
        state
    }

    pub fn note_block_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        let signal = self.has_neighbor_signal(pos);
        if signal != self.info(state).powered() {
            if signal {
                self.note_block_play_note(pos, state);
            }
            let new = self.st.with_bool(state, sym::POWERED, signal);
            self.set_block_f(pos, new, UPDATE_ALL);
        }
    }

    fn note_block_play_note(&mut self, pos: Pos, state: StateId) {
        let head = match self.st.get(state, sym::INSTRUMENT) {
            Some(v) => works_above(self.st.sym_str(v)),
            None => false,
        };
        if head || self.info_at(pos.above()).is_air() {
            let block = self.info(state).block;
            self.block_event(pos, block, 0, 0);
            self.game_event("note_block_play", pos, None);
        }
    }

    pub fn note_block_use(&mut self, pos: Pos, state: StateId) -> bool {
        let note = (self.st.get_int(state, sym::NOTE, 0) + 1) % 25;
        let state = self.st.with_int(state, sym::NOTE, note);
        self.set_block_f(pos, state, UPDATE_ALL);
        self.note_block_play_note(pos, state);
        true
    }

    // ------------------------------------------------------------------ target block
    pub fn target_on_place(&mut self, pos: Pos, state: StateId, old: StateId) {
        let info = self.info(state);
        if info.name != self.info(old).name && info.power > 0 && !self.has_scheduled_tick(pos, info.block) {
            let new = self.st.with_int(state, sym::POWER, 0);
            self.set_block_f(pos, new, UPDATE_CLIENTS | UPDATE_KNOWN_SHAPE);
        }
    }

    pub fn target_tick(&mut self, pos: Pos, state: StateId) {
        if self.info(state).power != 0 {
            let new = self.st.with_int(state, sym::POWER, 0);
            self.set_block_f(pos, new, UPDATE_ALL);
        }
    }

    // ------------------------------------------------------------------ doors, trapdoors, fence gates
    pub fn door_neighbor_changed(&mut self, pos: Pos, state: StateId, source: BlockId) {
        let info = self.info(state);
        let other = if self.st.get(state, sym::HALF) == Some(sym::LOWER) { Dir::Up } else { Dir::Down };
        let signal = self.has_neighbor_signal(pos) || self.has_neighbor_signal(pos.offset(other));
        if source != info.block && signal != info.powered() {
            if signal != self.st.get_bool(state, sym::OPEN) {
                self.game_event(if signal { "block_open" } else { "block_close" }, pos, None);
            }
            let new = self.st.with_bool(state, sym::POWERED, signal);
            let new = self.st.with_bool(new, sym::OPEN, signal);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        }
    }

    fn door_can_survive(&self, pos: Pos, state: StateId) -> bool {
        let below = pos.below();
        if self.st.get(state, sym::HALF) == Some(sym::LOWER) {
            return self.is_face_sturdy(below, Dir::Up, SUPPORT_FULL);
        }
        self.info_at(below).name == self.info(state).name
    }

    pub fn door_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir, neighbor_state: StateId) -> StateId {
        let half = self.st.get(state, sym::HALF);
        let lower = half == Some(sym::LOWER);
        if !matches!(direction, Dir::Up | Dir::Down) || lower != (direction == Dir::Up) {
            if lower && direction == Dir::Down && !self.door_can_survive(pos, state) {
                return AIR;
            }
            return state;
        }
        if self.info(neighbor_state).kind == Kind::Door && self.st.get(neighbor_state, sym::HALF) != half {
            // `with_(half=None)` cannot happen for a real door; keep the neighbor's state then.
            return match half {
                Some(h) => self.st.with(neighbor_state, sym::HALF, h),
                None => neighbor_state,
            };
        }
        AIR
    }

    pub fn door_use(&mut self, pos: Pos, state: StateId) -> bool {
        if self.info(state).param == 0 {
            return false;
        }
        let open = self.st.get_bool(state, sym::OPEN);
        let new = self.st.with_bool(state, sym::OPEN, !open);
        self.set_block_f(pos, new, UPDATE_CLIENTS | UPDATE_IMMEDIATE);
        self.game_event(if !open { "block_open" } else { "block_close" }, pos, None);
        true
    }

    pub fn trapdoor_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        let signal = self.has_neighbor_signal(pos);
        if signal != self.info(state).powered() {
            let mut state = state;
            if self.st.get_bool(state, sym::OPEN) != signal {
                state = self.st.with_bool(state, sym::OPEN, signal);
                self.game_event(if signal { "block_open" } else { "block_close" }, pos, None);
            }
            let new = self.st.with_bool(state, sym::POWERED, signal);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        }
    }

    pub fn trapdoor_use(&mut self, pos: Pos, state: StateId) -> bool {
        if self.info(state).param == 0 {
            return false;
        }
        let open = self.st.get_bool(state, sym::OPEN);
        let new = self.st.with_bool(state, sym::OPEN, !open);
        self.set_block_f(pos, new, UPDATE_CLIENTS);
        self.game_event(if !open { "block_open" } else { "block_close" }, pos, None);
        true
    }

    pub fn fence_gate_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        let signal = self.has_neighbor_signal(pos);
        if self.info(state).powered() != signal {
            let new = self.st.with_bool(state, sym::POWERED, signal);
            let new = self.st.with_bool(new, sym::OPEN, signal);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
            if self.st.get_bool(state, sym::OPEN) != signal {
                self.game_event(if signal { "block_open" } else { "block_close" }, pos, None);
            }
        }
    }

    pub fn fence_gate_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir, neighbor_state: StateId) -> StateId {
        let facing = self.info(state).facing();
        if direction.is_horizontal() && facing.is_horizontal() {
            let cw = facing.clockwise();
            if cw == direction || cw == direction.opposite() {
                let in_wall = self.info(neighbor_state).block_flags & BF_WALL != 0
                    || self.info_at(pos.offset(direction.opposite())).block_flags & BF_WALL != 0;
                return self.st.with_bool(state, sym::IN_WALL, in_wall);
            }
        }
        state
    }

    pub fn fence_gate_use(&mut self, pos: Pos, state: StateId) -> bool {
        let mut state = state;
        if self.st.get_bool(state, sym::OPEN) {
            state = self.st.with_bool(state, sym::OPEN, false);
        } else {
            if self.info(state).facing() == PLAYER_DIRECTION.opposite() {
                state = self.st.with(state, sym::FACING, Sym::dir(PLAYER_DIRECTION));
            }
            state = self.st.with_bool(state, sym::OPEN, true);
        }
        self.set_block_f(pos, state, UPDATE_CLIENTS | UPDATE_IMMEDIATE);
        let open = self.st.get_bool(state, sym::OPEN);
        self.game_event(if open { "block_open" } else { "block_close" }, pos, None);
        true
    }

    // ------------------------------------------------------------------ rails
    /// BaseRailBlock#isRail (#rails tag)
    fn is_rail(&self, state: StateId) -> bool {
        let info = self.info(state);
        if info.block_flags & BF_RAIL_IN_NAME == 0 {
            return false;
        }
        matches!(
            self.st.block_name(info.name),
            "minecraft:rail" | "minecraft:powered_rail" | "minecraft:detector_rail" | "minecraft:activator_rail"
        )
    }

    fn is_rail_at(&self, pos: Pos) -> bool {
        self.is_rail(self.get(pos))
    }

    /// Block#canSupportRigidBlock
    fn can_support_rigid(&self, pos: Pos) -> bool {
        self.is_face_sturdy(pos, Dir::Up, SUPPORT_RIGID)
    }

    /// `_straight(state)`: `state.id != "rail"`
    fn rail_is_straight(&self, state: StateId) -> bool {
        self.st.block_name(self.info(state).name) != "minecraft:rail"
    }

    fn rail_state(&self, pos: Pos, state: StateId) -> RailState {
        let shape = self.st.get(state, sym::SHAPE).unwrap_or(sym::NORTH_SOUTH);
        RailState { pos, state, is_straight: self.rail_is_straight(state), connections: rail_connections(pos, shape) }
    }

    fn rs_get_rail(&self, pos: Pos) -> Option<RailState> {
        for p in [pos, pos.above(), pos.below()] {
            let st = self.get(p);
            if self.is_rail(st) {
                return Some(self.rail_state(p, st));
            }
        }
        None
    }

    fn rs_has_rail(&self, pos: Pos) -> bool {
        self.is_rail_at(pos) || self.is_rail_at(pos.above()) || self.is_rail_at(pos.below())
    }

    fn rs_remove_soft_connections(&self, rail: &mut RailState) {
        let mut i = 0;
        while i < rail.connections.len() {
            match self.rs_get_rail(rail.connections[i]) {
                Some(other) if other.connects_to(rail) => {
                    rail.connections[i] = other.pos;
                    i += 1;
                }
                _ => {
                    rail.connections.remove(i);
                }
            }
        }
    }

    fn rs_count_potential_connections(&self, rail: &RailState) -> usize {
        HORIZONTAL.iter().filter(|d| self.rs_has_rail(rail.pos.offset(**d))).count()
    }

    fn rs_slope(&self, pos: Pos, mut shape: Option<Sym>) -> Option<Sym> {
        if shape == Some(sym::NORTH_SOUTH) {
            if self.is_rail_at(pos.offset(Dir::North).above()) {
                shape = Some(sym::ASCENDING_NORTH);
            }
            if self.is_rail_at(pos.offset(Dir::South).above()) {
                shape = Some(sym::ASCENDING_SOUTH);
            }
        }
        if shape == Some(sym::EAST_WEST) {
            if self.is_rail_at(pos.offset(Dir::East).above()) {
                shape = Some(sym::ASCENDING_EAST);
            }
            if self.is_rail_at(pos.offset(Dir::West).above()) {
                shape = Some(sym::ASCENDING_WEST);
            }
        }
        shape
    }

    fn rs_connect_to(&mut self, me: &mut RailState, rail_pos: Pos) {
        me.connections.push(rail_pos);
        let p = me.pos;
        let n = me.has_connection(p.offset(Dir::North));
        let s = me.has_connection(p.offset(Dir::South));
        let w = me.has_connection(p.offset(Dir::West));
        let e = me.has_connection(p.offset(Dir::East));
        let mut shape = None;
        if n || s {
            shape = Some(sym::NORTH_SOUTH);
        }
        if w || e {
            shape = Some(sym::EAST_WEST);
        }
        if !me.is_straight {
            if s && e && !n && !w {
                shape = Some(sym::SOUTH_EAST);
            }
            if s && w && !n && !e {
                shape = Some(sym::SOUTH_WEST);
            }
            if n && w && !s && !e {
                shape = Some(sym::NORTH_WEST);
            }
            if n && e && !s && !w {
                shape = Some(sym::NORTH_EAST);
            }
        }
        let shape = self.rs_slope(p, shape).unwrap_or(sym::NORTH_SOUTH);
        me.state = self.st.with(me.state, sym::SHAPE, shape);
        self.set_block_f(p, me.state, UPDATE_ALL);
    }

    fn rs_has_neighbor_rail(&self, me: &RailState, pos: Pos) -> bool {
        match self.rs_get_rail(pos) {
            None => false,
            Some(mut neighbor) => {
                self.rs_remove_soft_connections(&mut neighbor);
                neighbor.can_connect_to(me)
            }
        }
    }

    /// RailState#place
    fn rs_place(&mut self, me: &mut RailState, has_signal: bool, first: bool, default_shape: Option<Sym>) {
        let p = me.pos;
        let n = self.rs_has_neighbor_rail(me, p.offset(Dir::North));
        let s = self.rs_has_neighbor_rail(me, p.offset(Dir::South));
        let w = self.rs_has_neighbor_rail(me, p.offset(Dir::West));
        let e = self.rs_has_neighbor_rail(me, p.offset(Dir::East));
        let mut shape = None;
        let (ns, we) = (n || s, w || e);
        if ns && !we {
            shape = Some(sym::NORTH_SOUTH);
        }
        if we && !ns {
            shape = Some(sym::EAST_WEST);
        }
        let (se, sw, ne, nw) = (s && e, s && w, n && e, n && w);
        if !me.is_straight {
            if se && !n && !w {
                shape = Some(sym::SOUTH_EAST);
            }
            if sw && !n && !e {
                shape = Some(sym::SOUTH_WEST);
            }
            if nw && !s && !e {
                shape = Some(sym::NORTH_WEST);
            }
            if ne && !s && !w {
                shape = Some(sym::NORTH_EAST);
            }
        }
        if shape.is_none() {
            if ns && we {
                shape = default_shape;
            } else if ns {
                shape = Some(sym::NORTH_SOUTH);
            } else if we {
                shape = Some(sym::EAST_WEST);
            }
            if !me.is_straight {
                let order = if has_signal {
                    [(se, sym::SOUTH_EAST), (sw, sym::SOUTH_WEST), (ne, sym::NORTH_EAST), (nw, sym::NORTH_WEST)]
                } else {
                    [(nw, sym::NORTH_WEST), (ne, sym::NORTH_EAST), (sw, sym::SOUTH_WEST), (se, sym::SOUTH_EAST)]
                };
                for (cond, sh) in order {
                    if cond {
                        shape = Some(sh);
                    }
                }
            }
        }
        // Python fails without a shape property; a rail without one counts as north_south here.
        let shape = self.rs_slope(p, shape).or(default_shape).unwrap_or(sym::NORTH_SOUTH);
        me.connections = rail_connections(p, shape);
        me.state = self.st.with(me.state, sym::SHAPE, shape);
        if first || self.get(p) != me.state {
            self.set_block_f(p, me.state, UPDATE_ALL);
            for c in me.connections.clone() {
                if let Some(mut neighbor) = self.rs_get_rail(c) {
                    self.rs_remove_soft_connections(&mut neighbor);
                    if neighbor.can_connect_to(me) {
                        self.rs_connect_to(&mut neighbor, p);
                    }
                }
            }
        }
    }

    /// BaseRailBlock#updateDir
    fn rail_update_dir(&mut self, pos: Pos, state: StateId, first: bool) -> StateId {
        let mut rail = self.rail_state(pos, state);
        let has_signal = self.has_neighbor_signal(pos);
        let default_shape = self.st.get(state, sym::SHAPE);
        self.rs_place(&mut rail, has_signal, first, default_shape);
        rail.state
    }

    /// BaseRailBlock#update_state_on_place (called from on_place when the block changed)
    pub fn rail_update_state_on_place(&mut self, pos: Pos, state: StateId, moved: bool) {
        let info = self.info(state);
        let state = self.rail_update_dir(pos, state, true);
        if info.kind != Kind::Rail {
            self.neighbor_changed_with_state(state, pos, info.block, moved);
        }
    }

    fn rail_should_be_removed(&self, pos: Pos, shape: Option<Sym>) -> bool {
        if !self.can_support_rigid(pos.below()) {
            return true;
        }
        let d = match shape {
            Some(sym::ASCENDING_EAST) => Dir::East,
            Some(sym::ASCENDING_WEST) => Dir::West,
            Some(sym::ASCENDING_NORTH) => Dir::North,
            Some(sym::ASCENDING_SOUTH) => Dir::South,
            _ => return false,
        };
        !self.can_support_rigid(pos.offset(d))
    }

    /// BaseRailBlock#neighbor_changed (rail, powered_rail, activator_rail)
    pub fn rail_neighbor_changed(&mut self, pos: Pos, state: StateId, source: BlockId, moved: bool) {
        let info = self.info(state);
        if self.info_at(pos).name != info.name {
            return;
        }
        let shape = self.st.get(state, sym::SHAPE);
        if self.rail_should_be_removed(pos, shape) {
            self.remove_block(pos, moved);
        } else if info.kind == Kind::Rail {
            // RailBlock#updateState
            let source_kind = self.st.block(source).kind;
            if self.is_signal_source(source_kind) {
                let rail = self.rail_state(pos, state);
                if self.rs_count_potential_connections(&rail) == 3 {
                    self.rail_update_dir(pos, state, false);
                }
            }
        } else {
            self.powered_rail_update_state(pos, state);
        }
    }

    fn find_powered_rail_signal(&mut self, block: BlockId, pos: Pos, state: StateId, forward: bool, depth: i32) -> bool {
        if depth >= MAX_SEARCH_DEPTH {
            return false;
        }
        let Pos { mut x, mut y, mut z } = pos;
        let mut check_below = true;
        let mut shape = self.st.get(state, sym::SHAPE);
        match shape {
            Some(sym::NORTH_SOUTH) => z += if forward { 1 } else { -1 },
            Some(sym::EAST_WEST) => x += if forward { -1 } else { 1 },
            Some(sym::ASCENDING_EAST) => {
                if forward {
                    x -= 1;
                } else {
                    x += 1;
                    y += 1;
                    check_below = false;
                }
                shape = Some(sym::EAST_WEST);
            }
            Some(sym::ASCENDING_WEST) => {
                if forward {
                    x -= 1;
                    y += 1;
                    check_below = false;
                } else {
                    x += 1;
                }
                shape = Some(sym::EAST_WEST);
            }
            Some(sym::ASCENDING_NORTH) => {
                if forward {
                    z += 1;
                } else {
                    z -= 1;
                    y += 1;
                    check_below = false;
                }
                shape = Some(sym::NORTH_SOUTH);
            }
            Some(sym::ASCENDING_SOUTH) => {
                if forward {
                    z += 1;
                    y += 1;
                    check_below = false;
                } else {
                    z -= 1;
                }
                shape = Some(sym::NORTH_SOUTH);
            }
            _ => {}
        }
        self.is_same_rail_with_power(block, Pos::new(x, y, z), forward, depth, shape)
            || (check_below && self.is_same_rail_with_power(block, Pos::new(x, y - 1, z), forward, depth, shape))
    }

    fn is_same_rail_with_power(&mut self, block: BlockId, pos: Pos, forward: bool, depth: i32, direction: Option<Sym>) -> bool {
        let state = self.get(pos);
        let info = self.info(state);
        if info.name != block {
            return false;
        }
        let mine = self.st.get(state, sym::SHAPE);
        if direction == Some(sym::EAST_WEST)
            && matches!(mine, Some(sym::NORTH_SOUTH | sym::ASCENDING_NORTH | sym::ASCENDING_SOUTH))
        {
            return false;
        }
        if direction == Some(sym::NORTH_SOUTH)
            && matches!(mine, Some(sym::EAST_WEST | sym::ASCENDING_EAST | sym::ASCENDING_WEST))
        {
            return false;
        }
        if !info.powered() {
            return false;
        }
        self.has_neighbor_signal(pos) || self.find_powered_rail_signal(block, pos, state, forward, depth + 1)
    }

    /// PoweredRailBlock#updateState
    fn powered_rail_update_state(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        let powered = info.powered();
        let should = self.has_neighbor_signal(pos)
            || self.find_powered_rail_signal(info.name, pos, state, true, 0)
            || self.find_powered_rail_signal(info.name, pos, state, false, 0);
        if should != powered {
            let new = self.st.with_bool(state, sym::POWERED, should);
            self.set_block_f(pos, new, UPDATE_ALL);
            self.update_neighbors_at(pos.below(), info.block, None);
            if is_slope(self.st.get(state, sym::SHAPE)) {
                self.update_neighbors_at(pos.above(), info.block, None);
            }
        }
    }

    pub fn rail_affect_neighbors_after_removal(&mut self, pos: Pos, state: StateId, moved: bool) {
        if !moved {
            let info = self.info(state);
            if is_slope(self.st.get(state, sym::SHAPE)) {
                self.update_neighbors_at(pos.above(), info.block, None);
            }
            if info.kind != Kind::Rail {
                self.update_neighbors_at(pos, info.block, None);
                self.update_neighbors_at(pos.below(), info.block, None);
            }
        }
    }

    // ------------------------------------------------------------------ lectern
    /// LecternBlockEntity#getRedstoneSignal (float arithmetic as in the game)
    pub fn lectern_redstone_signal(&self, be: BeId) -> i32 {
        match &self.bes[be].data {
            BeData::Lectern(l) => {
                let progress = if l.page_count > 1 { l.page as f64 / (l.page_count as f64 - 1.0) } else { 1.0 };
                (progress * 14.0).floor() as i32 + l.has_book as i32
            }
            _ => 0,
        }
    }

    /// LecternBlock#get_analog_output_signal
    pub fn lectern_analog_output(&mut self, pos: Pos, state: StateId) -> i32 {
        let be = self.get_block_entity(pos);
        if self.st.get_bool(state, sym::HAS_BOOK) {
            if let Some(be) = be {
                if matches!(self.bes[be].data, BeData::Lectern(_)) {
                    return self.lectern_redstone_signal(be);
                }
            }
        }
        0
    }

    pub fn lectern_tick(&mut self, pos: Pos, state: StateId) {
        let new = self.st.with_bool(state, sym::POWERED, false);
        self.set_block_f(pos, new, UPDATE_ALL);
        let block = self.info(state).block;
        self.update_neighbors_at(pos.below(), block, None);
    }

    pub fn lectern_affect_neighbors_after_removal(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        if info.powered() {
            self.update_neighbors_at(pos.below(), info.block, None);
        }
    }
}

// ---------------------------------------------------------------------------------- daylight detector
/// Sun angle in degrees at overworld clock time 0 (docs: redstone/sim/blocks/daylight.py).
const DAYLIGHT_SUN_ANGLE: f64 = 282.3711;
/// Level#skyDarken at that time (clear weather).
const DAYLIGHT_SKY_DARKEN: i32 = 0;
const DAYLIGHT_MAX_Y: i32 = 319;

impl World {
    /// Sky light at `pos` (ASSUMPTION, see redstone/sim/blocks/daylight.py): 15 minus the distance through
    /// cells without a redstone conductor to the nearest cell with open sky above.
    fn daylight_sky_light(&self, pos: Pos) -> i32 {
        let low = pos.y - 15;
        let mut tops: FxHashMap<(i32, i32), i32> = FxHashMap::default();
        let mut is_open = |p: Pos| {
            let top = *tops.entry((p.x, p.z)).or_insert_with(|| {
                (low..=DAYLIGHT_MAX_Y).rev().find(|&y| self.is_conductor(Pos { x: p.x, y, z: p.z })).unwrap_or(low - 1)
            });
            p.y > top
        };
        let mut seen: FxHashSet<Pos> = FxHashSet::default();
        seen.insert(pos);
        let mut level = vec![pos];
        for dist in 0..16 {
            if level.iter().any(|&p| is_open(p)) {
                return 15 - dist;
            }
            if dist == 15 {
                break;
            }
            let mut next = Vec::new();
            for &p in &level {
                for d in [Dir::Down, Dir::Up, Dir::North, Dir::South, Dir::West, Dir::East] {
                    let q = p.offset(d);
                    if seen.insert(q) && !self.is_conductor(q) {
                        next.push(q);
                    }
                }
            }
            level = next;
        }
        0
    }

    /// The strength DaylightDetectorBlock#updateSignalStrength would set.
    pub fn daylight_target(&self, pos: Pos, state: StateId) -> i32 {
        let mut target = (self.daylight_sky_light(pos) - DAYLIGHT_SKY_DARKEN).max(0);
        if self.st.get(state, sym::INVERTED) == Some(sym::TRUE) {
            target = 15 - target;
        } else if target > 0 {
            let mut sun = DAYLIGHT_SUN_ANGLE * (std::f64::consts::PI / 180.0);
            let offset = if sun < std::f64::consts::PI { 0.0 } else { std::f64::consts::PI * 2.0 };
            sun += (offset - sun) * 0.2;
            target = (target as f64 * sun.cos() + 0.5).floor() as i32;
        }
        target.clamp(0, 15)
    }

    fn daylight_update_signal_strength(&mut self, pos: Pos, state: StateId) {
        let target = self.daylight_target(pos, state);
        if self.info(state).power as i32 != target {
            let new = self.st.with_int(state, sym::POWER, target);
            self.set_block_f(pos, new, UPDATE_ALL);
        }
    }

    /// DaylightDetectorBlock#useWithoutItem: flags 2 (no neighbor updates), then update at once.
    pub fn daylight_use(&mut self, pos: Pos, state: StateId) -> bool {
        let inverted = self.st.get(state, sym::INVERTED) == Some(sym::TRUE);
        let new = self.st.with_bool(state, sym::INVERTED, !inverted);
        self.set_block_f(pos, new, UPDATE_CLIENTS);
        self.game_event("block_change", pos, Some(new));
        self.daylight_update_signal_strength(pos, new);
        true
    }

    /// DaylightDetectorBlock#tickEntity
    pub fn daylight_be_tick(&mut self, be: BeId) {
        let pos = self.bes[be].pos;
        let state = self.get(pos);
        if self.info(state).kind != Kind::DaylightDetector {
            return;
        }
        if self.game_time % 20 == 0 {
            self.daylight_update_signal_strength(pos, state);
        }
    }
}
