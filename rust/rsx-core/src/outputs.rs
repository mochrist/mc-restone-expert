//! Copper bulb, note block, target, doors, trapdoors, fence gates, rails, lectern
//! (port of redstone/sim/blocks/outputs.py). STUB: to be implemented.

use crate::common::*;
use crate::state::*;
use crate::world::*;

impl World {
    pub fn copper_bulb_check_and_flip(&mut self, _pos: Pos, _state: StateId) {}

    pub fn note_block_neighbor_changed(&mut self, _pos: Pos, _state: StateId) {}

    pub fn note_block_update_shape(&mut self, _pos: Pos, state: StateId, _direction: Dir) -> StateId {
        state
    }

    pub fn note_block_use(&mut self, _pos: Pos, _state: StateId) -> bool {
        false
    }

    /// outputs._instrument(state)
    pub fn instrument(&self, _state: StateId) -> String {
        "harp".to_owned()
    }

    pub fn target_on_place(&mut self, _pos: Pos, _state: StateId, _old: StateId) {}

    pub fn target_tick(&mut self, _pos: Pos, _state: StateId) {}

    pub fn door_neighbor_changed(&mut self, _pos: Pos, _state: StateId, _source: BlockId) {}

    pub fn door_update_shape(&mut self, _pos: Pos, state: StateId, _direction: Dir, _neighbor_state: StateId) -> StateId {
        state
    }

    pub fn door_use(&mut self, _pos: Pos, _state: StateId) -> bool {
        false
    }

    pub fn trapdoor_neighbor_changed(&mut self, _pos: Pos, _state: StateId) {}

    pub fn trapdoor_use(&mut self, _pos: Pos, _state: StateId) -> bool {
        false
    }

    pub fn fence_gate_neighbor_changed(&mut self, _pos: Pos, _state: StateId) {}

    pub fn fence_gate_update_shape(&mut self, _pos: Pos, state: StateId, _direction: Dir, _neighbor_state: StateId) -> StateId {
        state
    }

    pub fn fence_gate_use(&mut self, _pos: Pos, _state: StateId) -> bool {
        false
    }

    /// BaseRailBlock#neighbor_changed (rail, powered_rail, activator_rail)
    pub fn rail_neighbor_changed(&mut self, _pos: Pos, _state: StateId, _source: BlockId, _moved: bool) {}

    /// BaseRailBlock#update_state_on_place (called from on_place when the block changed)
    pub fn rail_update_state_on_place(&mut self, _pos: Pos, _state: StateId, _moved: bool) {}

    pub fn rail_affect_neighbors_after_removal(&mut self, _pos: Pos, _state: StateId, _moved: bool) {}

    /// LecternBlock#get_analog_output_signal
    pub fn lectern_analog_output(&mut self, _pos: Pos, _state: StateId) -> i32 {
        0
    }

    pub fn lectern_tick(&mut self, _pos: Pos, _state: StateId) {}

    pub fn lectern_affect_neighbors_after_removal(&mut self, _pos: Pos, _state: StateId) {}
}
