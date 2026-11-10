//! Lever, buttons, pressure plates, redstone lamp (port of redstone/sim/blocks/basic.py).

use crate::common::*;
use crate::state::*;
use crate::world::*;

impl World {
    /// `set_block(pos, state)` with the Python defaults (flags UPDATE_ALL, limit UPDATE_LIMIT).
    #[inline]
    pub fn set_block3(&mut self, pos: Pos, state: StateId) -> bool {
        self.set_block(pos, state, UPDATE_ALL, UPDATE_LIMIT)
    }

    /// `set_block(pos, state, flags)` with the default limit.
    #[inline]
    pub fn set_block_f(&mut self, pos: Pos, state: StateId, flags: u32) -> bool {
        self.set_block(pos, state, flags, UPDATE_LIMIT)
    }

    /// FaceAttachedHorizontalDirectionalBlock#getConnectedDirection: points from the support to the block.
    pub fn attached_direction(&self, state: StateId) -> Dir {
        match self.st.get(state, sym::FACE) {
            Some(sym::CEILING) => Dir::Down,
            Some(sym::FLOOR) => Dir::Up,
            _ => self.info(state).facing(),
        }
    }

    // --- lever and button ----------------------------------------------------------------------
    pub fn lever_pull(&mut self, pos: Pos, state: StateId) {
        let powered = self.info(state).powered();
        let new = self.st.with_bool(state, sym::POWERED, !powered);
        self.set_block3(pos, new); // setBlockAndUpdate = flags 3
        self.lever_update_neighbours(pos, new);
    }

    pub fn lever_update_neighbours(&mut self, pos: Pos, state: StateId) {
        let front = self.attached_direction(state).opposite();
        let block = self.info(state).block;
        self.update_neighbors_at(pos, block, None);
        self.update_neighbors_at(pos.offset(front), block, None);
    }

    fn lever_can_survive(&self, pos: Pos, state: StateId) -> bool {
        let d = self.attached_direction(state).opposite();
        self.is_face_sturdy(pos.offset(d), d.opposite(), SUPPORT_FULL)
    }

    pub fn lever_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir) -> StateId {
        if self.attached_direction(state).opposite() == direction && !self.lever_can_survive(pos, state) {
            return AIR;
        }
        state
    }

    pub fn button_use(&mut self, pos: Pos, state: StateId) -> bool {
        let info = self.info(state);
        if info.powered() {
            return true;
        }
        let new = self.st.with_bool(state, sym::POWERED, true);
        self.set_block3(pos, new);
        self.lever_update_neighbours(pos, state);
        self.schedule_tick(pos, info.block, info.param as i64, PRIO_NORMAL);
        true
    }

    pub fn button_tick(&mut self, pos: Pos, state: StateId) {
        if self.info(state).powered() {
            // checkPressed with no arrow inside: release
            let new = self.st.with_bool(state, sym::POWERED, false);
            self.set_block3(pos, new);
            self.lever_update_neighbours(pos, state);
        }
    }

    // --- pressure plates -------------------------------------------------------------------------
    pub fn plate_signal(&self, state: StateId) -> i32 {
        let info = self.info(state);
        if info.param2 != 0 {
            info.power as i32
        } else {
            15 * info.powered() as i32
        }
    }

    fn plate_with_signal(&mut self, state: StateId, signal: i32) -> StateId {
        if self.info(state).param2 != 0 {
            self.st.with_int(state, sym::POWER, signal)
        } else {
            self.st.with_bool(state, sym::POWERED, signal > 0)
        }
    }

    pub fn plate_use(&mut self, pos: Pos, state: StateId) -> bool {
        if self.plate_signal(state) == 0 {
            let signal = if self.info(state).param2 != 0 { 1 } else { 15 };
            self.plate_check_pressed(pos, state, signal);
        }
        true
    }

    pub fn plate_tick(&mut self, pos: Pos, state: StateId) {
        if self.plate_signal(state) > 0 {
            self.plate_check_pressed(pos, state, 0); // nobody on the plate any more
        }
    }

    fn plate_check_pressed(&mut self, pos: Pos, state: StateId, signal: i32) {
        if self.plate_signal(state) != signal {
            let new = self.plate_with_signal(state, signal);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
            self.plate_update_neighbours(pos, state);
        }
        if signal > 0 {
            let info = self.info(state);
            self.schedule_tick(pos, info.block, info.param as i64, PRIO_NORMAL);
        }
    }

    pub fn plate_update_neighbours(&mut self, pos: Pos, state: StateId) {
        let block = self.info(state).block;
        self.update_neighbors_at(pos, block, None);
        self.update_neighbors_at(pos.below(), block, None);
    }

    pub fn plate_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir) -> StateId {
        if direction == Dir::Down {
            let below = pos.below();
            let survives = self.is_face_sturdy(below, Dir::Up, SUPPORT_RIGID)
                || self.is_face_sturdy(below, Dir::Up, SUPPORT_CENTER);
            if !survives {
                return AIR;
            }
        }
        state
    }

    // --- redstone lamp ---------------------------------------------------------------------------
    pub fn lamp_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        let lit = info.lit();
        if lit != self.has_neighbor_signal(pos) {
            if lit {
                self.schedule_tick(pos, info.block, 4, PRIO_NORMAL);
            } else {
                let new = self.st.with_bool(state, sym::LIT, true);
                self.set_block_f(pos, new, UPDATE_CLIENTS);
            }
        }
    }

    pub fn lamp_tick(&mut self, pos: Pos, state: StateId) {
        if self.info(state).lit() && !self.has_neighbor_signal(pos) {
            let new = self.st.with_bool(state, sym::LIT, false);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        }
    }
}
