//! Containers, dispenser, dropper, hopper (port of redstone/sim/blocks/container.py and
//! dispenser_hopper.py). STUB: to be implemented.

use crate::common::*;
use crate::state::*;
use crate::world::*;

impl World {
    /// ContainerBlock#get_analog_output_signal: the redstone signal of the container at `pos`
    /// (raw `block_entities.get(pos)`, 0 if it is not a container).
    pub fn container_analog_output(&mut self, _pos: Pos) -> i32 {
        0
    }

    /// ContainerBlockEntity#redstone_signal
    pub fn container_redstone_signal(&self, _be: BeId) -> i32 {
        0
    }

    /// container.add_item (HopperBlockEntity#addItem). Returns the count that did not fit.
    pub fn add_item(&mut self, _source: Option<BeId>, _container: BeId, _item: ItemId, count: i32) -> i32 {
        count
    }

    pub fn dispenser_neighbor_changed(&mut self, _pos: Pos, _state: StateId) {}

    pub fn dispenser_tick(&mut self, _pos: Pos, _state: StateId) {}

    /// HopperBlock#checkPoweredState
    pub fn hopper_check_powered_state(&mut self, _pos: Pos, _state: StateId) {}

    /// HopperBlockEntity#tick
    pub fn hopper_be_tick(&mut self, _be: BeId) {}
}
