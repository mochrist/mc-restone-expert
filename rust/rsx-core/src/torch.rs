//! Redstone torches (standing and wall) and the observer (port of redstone/sim/blocks/torch_observer.py).

use crate::common::*;
use crate::state::*;
use crate::world::*;

const RECENT_TOGGLE_TIMER: i64 = 60;
const MAX_RECENT_TOGGLES: usize = 8;
const RESTART_DELAY: i64 = 160;

impl World {
    fn torch_toggled_too_frequently(&mut self, pos: Pos, add: bool) -> bool {
        if add {
            self.torch_toggles.push_back((pos, self.game_time));
        }
        self.torch_toggles.iter().filter(|(p, _)| *p == pos).count() >= MAX_RECENT_TOGGLES
    }

    fn torch_has_neighbor_signal(&mut self, pos: Pos, state: StateId) -> bool {
        let info = self.info(state);
        if info.kind == Kind::WallTorch {
            let opp = info.facing().opposite();
            self.has_signal(pos.offset(opp), opp)
        } else {
            self.has_signal(pos.below(), Dir::Down)
        }
    }

    fn torch_can_survive(&self, pos: Pos, state: StateId) -> bool {
        let info = self.info(state);
        if info.kind == Kind::WallTorch {
            let f = info.facing();
            self.is_face_sturdy(pos.offset(f.opposite()), f, SUPPORT_FULL)
        } else {
            // BaseTorchBlock: canSupportCenter(below, UP)
            self.is_face_sturdy(pos.below(), Dir::Up, SUPPORT_CENTER)
        }
    }

    pub fn torch_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir) -> StateId {
        let info = self.info(state);
        let relevant = if info.kind == Kind::WallTorch { direction.opposite() == info.facing() } else { direction == Dir::Down };
        if relevant && !self.torch_can_survive(pos, state) {
            return AIR;
        }
        state
    }

    pub fn torch_notify_neighbors(&mut self, pos: Pos, state: StateId) {
        let block = self.info(state).block;
        for d in ALL_DIRECTIONS {
            self.update_neighbors_at(pos.offset(d), block, None);
        }
    }

    pub fn torch_tick(&mut self, pos: Pos, state: StateId) {
        let signal = self.torch_has_neighbor_signal(pos, state);
        while let Some((_, t)) = self.torch_toggles.front() {
            if self.game_time - *t > RECENT_TOGGLE_TIMER {
                self.torch_toggles.pop_front();
            } else {
                break;
            }
        }
        if self.info(state).lit() {
            if signal {
                let new = self.st.with_bool(state, sym::LIT, false);
                self.set_block3(pos, new);
                if self.torch_toggled_too_frequently(pos, true) {
                    self.note("torch_burnout", pos, "");
                    let block = self.info_at(pos).name;
                    self.schedule_tick(pos, block, RESTART_DELAY, PRIO_NORMAL);
                }
            }
        } else if !signal && !self.torch_toggled_too_frequently(pos, false) {
            let new = self.st.with_bool(state, sym::LIT, true);
            self.set_block3(pos, new);
        }
    }

    pub fn torch_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        if info.lit() == self.torch_has_neighbor_signal(pos, state) && !self.will_tick_this_tick(pos, info.block) {
            self.schedule_tick(pos, info.block, 2, PRIO_NORMAL);
        }
    }

    // --- observer ------------------------------------------------------------------------------
    pub fn observer_tick(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        if info.powered() {
            let new = self.st.with_bool(state, sym::POWERED, false);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        } else {
            let new = self.st.with_bool(state, sym::POWERED, true);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
            self.schedule_tick(pos, info.block, 2, PRIO_NORMAL);
        }
        self.observer_update_neighbors_in_front(pos, state);
    }

    pub fn observer_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir) -> StateId {
        let info = self.info(state);
        if info.facing_or(Dir::South) == direction && !info.powered() && !self.has_scheduled_tick(pos, info.block) {
            self.note("observer_pulse", pos, "");
            self.schedule_tick(pos, info.block, 2, PRIO_NORMAL);
        }
        state
    }

    fn observer_update_neighbors_in_front(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        let d = info.facing_or(Dir::South);
        let front = pos.offset(d.opposite());
        self.neighbor_changed(front, info.block);
        self.update_neighbors_at_except_from_facing(front, info.block, d);
    }

    pub fn observer_on_place(&mut self, pos: Pos, state: StateId, old: StateId) {
        let info = self.info(state);
        if info.name != self.info(old).name && info.powered() && !self.has_scheduled_tick(pos, info.block) {
            let new = self.st.with_bool(state, sym::POWERED, false);
            self.set_block_f(pos, new, UPDATE_CLIENTS | UPDATE_KNOWN_SHAPE);
            self.observer_update_neighbors_in_front(pos, new);
        }
    }

    pub fn observer_affect_neighbors_after_removal(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        if info.powered() && self.has_scheduled_tick(pos, info.block) {
            self.observer_update_neighbors_in_front(pos, state);
        }
    }
}
