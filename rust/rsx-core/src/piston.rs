//! Pistons (port of redstone/sim/blocks/piston.py). STUB: to be implemented.

use crate::common::*;
use crate::state::*;
use crate::world::*;

impl World {
    pub fn piston_neighbor_changed(&mut self, _pos: Pos, _state: StateId, _source: BlockId) {}

    pub fn piston_on_place(&mut self, _pos: Pos, _state: StateId, _old: StateId) {}

    pub fn piston_trigger_event(&mut self, _pos: Pos, _state: StateId, _b0: i32, _b1: i32) -> bool {
        false
    }

    pub fn piston_head_neighbor_changed(&mut self, _pos: Pos, _state: StateId, _source: BlockId) {}

    pub fn piston_head_affect_neighbors_after_removal(&mut self, _pos: Pos, _state: StateId) {}

    pub fn piston_head_update_shape(&mut self, _pos: Pos, state: StateId, _direction: Dir) -> StateId {
        state
    }

    pub fn moving_piston_use(&mut self, _pos: Pos, _state: StateId) -> bool {
        false
    }

    /// PistonMovingBlockEntity#tick
    pub fn piston_be_tick(&mut self, _be: BeId) {}

    /// PistonMovingBlockEntity#finalTick
    pub fn piston_be_final_tick(&mut self, _be: BeId) {}

    /// First part of PistonBaseBlock#getNeighborSignal: the five sides except the front.
    pub fn piston_has_direct_signal(&mut self, _pos: Pos, _push_direction: Dir) -> bool {
        false
    }

    /// Second part of getNeighborSignal (quasi-connectivity).
    pub fn piston_has_qc_signal(&mut self, _pos: Pos) -> bool {
        false
    }

    /// piston.check_bud_states: note pistons resting in a BUD state.
    pub fn check_bud_states(&mut self) {}
}
