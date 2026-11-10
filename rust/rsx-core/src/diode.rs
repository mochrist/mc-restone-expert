//! Repeater and comparator (port of redstone/sim/blocks/diode.py). `facing` points to the input side.

use crate::common::*;
use crate::state::*;
use crate::world::*;

impl World {
    fn comparator_be_output(&self, pos: Pos) -> Option<i32> {
        match self.raw_block_entity(pos).map(|be| &self.bes[be].data) {
            Some(BeData::Comparator { output_signal }) => Some(*output_signal),
            _ => None,
        }
    }

    /// DiodeBlock#own_signal: the output signal while powered.
    pub fn diode_own_signal(&mut self, pos: Pos, state: StateId) -> i32 {
        let info = self.info(state);
        if !info.powered() {
            return 0;
        }
        match info.kind {
            Kind::Comparator => self.comparator_be_output(pos).unwrap_or(0),
            _ => 15,
        }
    }

    fn diode_can_survive_on(&self, below: Pos) -> bool {
        self.is_face_sturdy(below, Dir::Up, SUPPORT_RIGID)
    }

    pub fn diode_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir, neighbor_pos: Pos) -> StateId {
        if direction == Dir::Down && !self.diode_can_survive_on(neighbor_pos) {
            return AIR;
        }
        let info = self.info(state);
        if info.kind == Kind::Repeater && direction.is_horizontal() {
            let facing = info.facing();
            if direction != facing && direction != facing.opposite() {
                let locked = self.repeater_is_locked(pos, state);
                return self.st.with_bool(state, sym::LOCKED, locked);
            }
        }
        state
    }

    fn diode_base_input_signal(&mut self, pos: Pos, state: StateId) -> i32 {
        let d = self.info(state).facing();
        let target = pos.offset(d);
        let signal = self.get_signal(target, d);
        if signal >= 15 {
            return signal;
        }
        let t = self.info_at(target);
        signal.max(if t.kind == Kind::Wire { t.power as i32 } else { 0 })
    }

    fn diode_input_signal(&mut self, pos: Pos, state: StateId) -> i32 {
        let mut result = self.diode_base_input_signal(pos, state);
        if self.info(state).kind != Kind::Comparator {
            return result;
        }
        let d = self.info(state).facing();
        let mut target = pos.offset(d);
        let mut t = self.get(target);
        if self.has_analog_output_signal(self.info(t).kind) {
            let id = self.state_short_id(t);
            self.note("comparator_container", pos, &id);
            return self.get_analog_output_signal(target, t, d.opposite());
        }
        if result < 15 && self.info(t).conductor() {
            target = target.offset(d);
            t = self.get(target);
            // Item frames (entities) are not modeled.
            if self.has_analog_output_signal(self.info(t).kind) {
                let id = self.state_short_id(t);
                self.note("comparator_through_block", pos, &id);
                result = self.get_analog_output_signal(target, t, d.opposite());
            }
        }
        result
    }

    fn diode_alternate_signal(&mut self, pos: Pos, state: StateId) -> i32 {
        let info = self.info(state);
        let only_diodes = info.kind == Kind::Repeater;
        let d = info.facing();
        let (cw, ccw) = (d.clockwise(), d.counter_clockwise());
        let a = self.get_control_input_signal(pos.offset(cw), cw, only_diodes);
        let b = self.get_control_input_signal(pos.offset(ccw), ccw, only_diodes);
        a.max(b)
    }

    fn is_compare_mode(&self, state: StateId) -> bool {
        self.st.get(state, sym::MODE) == Some(sym::COMPARE)
    }

    fn is_subtract_mode(&self, state: StateId) -> bool {
        self.st.get(state, sym::MODE) == Some(sym::SUBTRACT)
    }

    fn diode_should_turn_on(&mut self, pos: Pos, state: StateId) -> bool {
        let inp = self.diode_input_signal(pos, state);
        if self.info(state).kind != Kind::Comparator {
            return inp > 0;
        }
        if inp == 0 {
            return false;
        }
        let side = self.diode_alternate_signal(pos, state);
        inp > side || (inp == side && self.is_compare_mode(state))
    }

    fn repeater_is_locked(&mut self, pos: Pos, state: StateId) -> bool {
        self.diode_alternate_signal(pos, state) > 0
    }

    fn repeater_delay(&self, state: StateId) -> i64 {
        self.st.get_int(state, sym::DELAY, 1) as i64 * 2
    }

    fn diode_should_prioritize(&self, pos: Pos, state: StateId) -> bool {
        let d = self.info(state).facing().opposite();
        let other = self.info_at(pos.offset(d));
        matches!(other.kind, Kind::Repeater | Kind::Comparator) && other.facing() != d
    }

    // --- updates -----------------------------------------------------------------------------
    pub fn repeater_tick(&mut self, pos: Pos, state: StateId) {
        if self.repeater_is_locked(pos, state) {
            self.note("repeater_lock", pos, "");
            return;
        }
        let info = self.info(state);
        let on = info.powered();
        let should = self.diode_should_turn_on(pos, state);
        if on && !should {
            let new = self.st.with_bool(state, sym::POWERED, false);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        } else if !on {
            let new = self.st.with_bool(state, sym::POWERED, true);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
            if !should {
                self.note("repeater_pulse_extend", pos, "");
                let delay = self.repeater_delay(state);
                self.schedule_tick(pos, info.block, delay, PRIO_VERY_HIGH);
            }
        }
    }

    pub fn diode_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        if self.info_at(pos).name != info.block {
            return;
        }
        if self.diode_can_survive_on(pos.below()) {
            if info.kind == Kind::Comparator {
                self.comparator_check_tick_on_neighbor(pos, state);
            } else {
                self.repeater_check_tick_on_neighbor(pos, state);
            }
        } else {
            self.remove_block(pos, false);
            for d in ALL_DIRECTIONS {
                self.update_neighbors_at(pos.offset(d), info.block, None);
            }
        }
    }

    fn repeater_check_tick_on_neighbor(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        let on = info.powered();
        if self.repeater_is_locked(pos, state) {
            if on != self.diode_should_turn_on(pos, state) {
                self.note("repeater_lock", pos, "");
            }
            return;
        }
        if on != self.diode_should_turn_on(pos, state) && !self.will_tick_this_tick(pos, info.block) {
            let priority = if self.diode_should_prioritize(pos, state) {
                PRIO_EXTREMELY_HIGH
            } else if on {
                PRIO_VERY_HIGH
            } else {
                PRIO_HIGH
            };
            let delay = self.repeater_delay(state);
            self.schedule_tick(pos, info.block, delay, priority);
        }
    }

    pub fn diode_update_neighbors_in_front(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        let d = info.facing();
        let front = pos.offset(d.opposite());
        self.neighbor_changed(front, info.block);
        self.update_neighbors_at_except_from_facing(front, info.block, d);
    }

    pub fn repeater_use(&mut self, pos: Pos, state: StateId) -> bool {
        let delay = self.st.get_int(state, sym::DELAY, 1) % 4 + 1;
        let new = self.st.with_int(state, sym::DELAY, delay);
        self.set_block3(pos, new); // setBlockAndUpdate
        true
    }

    // --- comparator ----------------------------------------------------------------------------
    fn comparator_calculate_output_signal(&mut self, pos: Pos, state: StateId) -> i32 {
        let inp = self.diode_input_signal(pos, state);
        if inp == 0 {
            return 0;
        }
        let alt = self.diode_alternate_signal(pos, state);
        if alt > inp {
            if self.is_compare_mode(state) {
                self.note("comparator_compare_block", pos, "");
            }
            return 0;
        }
        if self.is_subtract_mode(state) {
            if alt > 0 {
                self.note("comparator_subtract", pos, "");
            }
            inp - alt
        } else {
            inp
        }
    }

    pub fn comparator_use(&mut self, pos: Pos, state: StateId) -> bool {
        let mode = if self.is_compare_mode(state) { sym::SUBTRACT } else { sym::COMPARE };
        let new = self.st.with(state, sym::MODE, mode);
        self.set_block_f(pos, new, UPDATE_CLIENTS);
        if self.info_at(pos).name == self.info(state).block {
            self.comparator_refresh_output_state(pos, new);
        }
        true
    }

    fn comparator_check_tick_on_neighbor(&mut self, pos: Pos, state: StateId) {
        let info = self.info(state);
        if self.will_tick_this_tick(pos, info.block) {
            return;
        }
        let out = self.comparator_calculate_output_signal(pos, state);
        let old = self.comparator_be_output(pos).unwrap_or(0);
        if out != old || info.powered() != self.diode_should_turn_on(pos, state) {
            let priority = if self.diode_should_prioritize(pos, state) { PRIO_HIGH } else { PRIO_NORMAL };
            self.schedule_tick(pos, info.block, 2, priority);
        }
    }

    pub fn comparator_refresh_output_state(&mut self, pos: Pos, state: StateId) {
        let out = self.comparator_calculate_output_signal(pos, state);
        let mut old = 0;
        if let Some(be) = self.raw_block_entity(pos) {
            if let BeData::Comparator { output_signal } = &mut self.bes[be].data {
                old = *output_signal;
                *output_signal = out;
            }
        }
        if old != out || self.is_compare_mode(state) {
            let source_on = self.diode_should_turn_on(pos, state);
            let is_on = self.info(state).powered();
            if is_on && !source_on {
                let new = self.st.with_bool(state, sym::POWERED, false);
                self.set_block_f(pos, new, UPDATE_CLIENTS);
            } else if !is_on && source_on {
                let new = self.st.with_bool(state, sym::POWERED, true);
                self.set_block_f(pos, new, UPDATE_CLIENTS);
            }
            self.diode_update_neighbors_in_front(pos, state);
        }
    }
}
