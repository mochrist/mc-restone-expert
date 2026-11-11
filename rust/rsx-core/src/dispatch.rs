//! Behaviour dispatch by block kind: the methods of redstone.sim.block.Block and which subclass
//! overrides them. The per-kind code lives in basic.rs, wire.rs, diode.rs, torch.rs, piston.rs,
//! container.rs and outputs.rs.

use crate::common::*;
use crate::data;
use crate::state::*;
use crate::world::*;

impl World {
    // --- static properties -------------------------------------------------------------------
    /// Block#is_signal_source (the Python override per block class, not the data table).
    #[inline]
    pub fn is_signal_source(&self, kind: Kind) -> bool {
        match kind {
            Kind::Lever
            | Kind::Button
            | Kind::PressurePlate
            | Kind::RedstoneBlock
            | Kind::Repeater
            | Kind::Comparator
            | Kind::Torch
            | Kind::WallTorch
            | Kind::Observer
            | Kind::Target
            | Kind::Lectern
            | Kind::DaylightDetector
            | Kind::TrappedChest => true,
            Kind::Wire => self.wire_should_signal,
            _ => false,
        }
    }

    #[inline]
    pub fn has_block_entity(&self, kind: Kind) -> bool {
        matches!(
            kind,
            Kind::Comparator
                | Kind::MovingPiston
                | Kind::Barrel
                | Kind::Chest
                | Kind::TrappedChest
                | Kind::Dispenser
                | Kind::Hopper
                | Kind::Crafter
                | Kind::Lectern
                | Kind::DaylightDetector
        )
    }

    #[inline]
    pub fn has_analog_output_signal(&self, kind: Kind) -> bool {
        matches!(
            kind,
            Kind::Barrel
                | Kind::Chest
                | Kind::TrappedChest
                | Kind::Dispenser
                | Kind::Hopper
                | Kind::Crafter
                | Kind::CopperBulb
                | Kind::Lectern
                | Kind::Cake
        )
    }

    pub fn get_analog_output_signal(&mut self, pos: Pos, state: StateId, _direction: Dir) -> i32 {
        match self.info(state).kind {
            Kind::Barrel | Kind::Dispenser | Kind::Hopper | Kind::Crafter => self.container_analog_output(pos),
            Kind::Chest | Kind::TrappedChest => self.chest_analog_output(pos, state),
            Kind::CopperBulb => {
                if self.info_at(pos).lit() {
                    15
                } else {
                    0
                }
            }
            Kind::Lectern => self.lectern_analog_output(pos, state),
            // CakeBlock#getOutputSignal: (7 - bites) * 2
            Kind::Cake => (7 - self.st.get_int(state, sym::BITES, 0)) * 2,
            _ => 0,
        }
    }

    /// Block#new_block_entity
    pub fn new_block_entity(&mut self, _pos: Pos, state: StateId) -> Option<BeData> {
        let info = self.info(state);
        match info.kind {
            Kind::Comparator => Some(BeData::Comparator { output_signal: 0 }),
            Kind::Barrel | Kind::Chest | Kind::TrappedChest => {
                Some(BeData::Container(Container { size: 27, items: Vec::new(), kind: ContainerKind::Plain }))
            }
            Kind::Dispenser => {
                Some(BeData::Container(Container { size: 9, items: Vec::new(), kind: ContainerKind::Dispenser }))
            }
            Kind::Hopper => Some(BeData::Container(Container {
                size: 5,
                items: Vec::new(),
                kind: ContainerKind::Hopper { cooldown_time: -1, ticked_game_time: 0 },
            })),
            Kind::Crafter => Some(BeData::Container(Container {
                size: 9,
                items: Vec::new(),
                kind: ContainerKind::Crafter {
                    disabled_mask: 0,
                    triggered: self.st.get_bool(state, sym::TRIGGERED), // CrafterBlock#newBlockEntity
                    crafting_ticks_remaining: 0,
                },
            })),
            Kind::Lectern => Some(BeData::Lectern(Lectern { has_book: false, page: 0, page_count: 0 })),
            Kind::DaylightDetector => Some(BeData::Daylight),
            // moving_piston: only created through newMovingBlockEntity
            _ => None,
        }
    }

    /// Block#get_piston_push_reaction (data::PUSH_PULL, PUSH, POPPED, IMMOVEABLE or IGNORE_ENTITY).
    #[inline]
    pub fn piston_push_reaction(&self, state: StateId) -> u8 {
        let info = self.info(state);
        match info.kind {
            Kind::Piston | Kind::PistonHead | Kind::MovingPiston => data::IMMOVEABLE,
            _ => info.push,
        }
    }

    /// BlockBehaviour#shouldRedstoneWireConnectTo; `direction` points from the wire to this block.
    #[inline]
    pub fn should_wire_connect_to(&self, state: StateId, direction: Option<Dir>) -> bool {
        let info = self.info(state);
        match info.kind {
            Kind::Wire => true,
            Kind::Repeater => {
                let facing = info.facing();
                direction == Some(facing) || direction == Some(facing.opposite())
            }
            Kind::Observer => direction == Some(info.facing()),
            kind => self.is_signal_source(kind) && direction.is_some(),
        }
    }

    // --- signals -----------------------------------------------------------------------------
    pub fn block_get_signal(&mut self, pos: Pos, state: StateId, direction: Dir) -> i32 {
        let info = self.info(state);
        match info.kind {
            Kind::Lever | Kind::Button | Kind::Lectern => 15 * info.powered() as i32,
            Kind::PressurePlate => self.plate_signal(state),
            Kind::RedstoneBlock => 15,
            Kind::Wire => self.wire_get_signal(pos, state, direction),
            Kind::Repeater | Kind::Comparator => {
                if info.facing() == direction {
                    self.diode_own_signal(pos, state)
                } else {
                    0
                }
            }
            Kind::Torch => 15 * (direction != Dir::Up && info.lit()) as i32,
            Kind::WallTorch => 15 * (info.facing() != direction && info.lit()) as i32,
            Kind::Observer => 15 * (info.facing_or(Dir::South) == direction && info.powered()) as i32,
            Kind::Target | Kind::DaylightDetector => info.power as i32,
            _ => 0,
        }
    }

    pub fn block_get_direct_signal(&mut self, pos: Pos, state: StateId, direction: Dir) -> i32 {
        let info = self.info(state);
        match info.kind {
            Kind::Lever | Kind::Button => {
                15 * (info.powered() && self.attached_direction(state) == direction) as i32
            }
            Kind::PressurePlate => {
                if direction == Dir::Up {
                    self.plate_signal(state)
                } else {
                    0
                }
            }
            Kind::Wire => {
                if self.wire_should_signal {
                    self.wire_get_signal(pos, state, direction)
                } else {
                    0
                }
            }
            Kind::Repeater | Kind::Comparator | Kind::Observer => self.block_get_signal(pos, state, direction),
            Kind::Torch | Kind::WallTorch => {
                if direction == Dir::Down {
                    self.block_get_signal(pos, state, direction)
                } else {
                    0
                }
            }
            Kind::Lectern => 15 * (direction == Dir::Up && info.powered()) as i32,
            _ => 0,
        }
    }

    // --- updates -----------------------------------------------------------------------------
    pub fn block_neighbor_changed(&mut self, pos: Pos, state: StateId, source: BlockId, moved: bool) {
        match self.info(state).kind {
            Kind::Air | Kind::Unmodeled | Kind::Plain => {}
            Kind::Lamp => self.lamp_neighbor_changed(pos, state),
            Kind::Wire => self.wire_neighbor_changed(pos, state),
            Kind::Repeater | Kind::Comparator => self.diode_neighbor_changed(pos, state),
            Kind::Torch | Kind::WallTorch => self.torch_neighbor_changed(pos, state),
            Kind::Piston => self.piston_neighbor_changed(pos, state, source),
            Kind::PistonHead => self.piston_head_neighbor_changed(pos, state, source),
            Kind::Dispenser => self.dispenser_neighbor_changed(pos, state),
            Kind::Crafter => self.crafter_neighbor_changed(pos, state),
            Kind::Hopper => self.hopper_check_powered_state(pos, state),
            Kind::CopperBulb => self.copper_bulb_check_and_flip(pos, state),
            Kind::NoteBlock => self.note_block_neighbor_changed(pos, state),
            Kind::Door => self.door_neighbor_changed(pos, state, source),
            Kind::TrapDoor => self.trapdoor_neighbor_changed(pos, state),
            Kind::FenceGate => self.fence_gate_neighbor_changed(pos, state),
            Kind::Rail | Kind::PoweredRail => self.rail_neighbor_changed(pos, state, source, moved),
            _ => {}
        }
    }

    pub fn on_place(&mut self, pos: Pos, state: StateId, old: StateId, moved: bool) {
        let block_changed = self.info(old).name != self.info(state).name;
        match self.info(state).kind {
            Kind::Wire => self.wire_on_place(pos, state, old),
            Kind::Repeater | Kind::Comparator => self.diode_update_neighbors_in_front(pos, state),
            Kind::Torch | Kind::WallTorch => self.torch_notify_neighbors(pos, state),
            Kind::Observer => self.observer_on_place(pos, state, old),
            Kind::Piston => self.piston_on_place(pos, state, old),
            Kind::Hopper => {
                if block_changed {
                    self.hopper_check_powered_state(pos, state)
                }
            }
            Kind::CopperBulb => {
                if block_changed {
                    self.copper_bulb_check_and_flip(pos, state)
                }
            }
            Kind::Target => self.target_on_place(pos, state, old),
            Kind::Rail | Kind::PoweredRail => {
                if block_changed {
                    self.rail_update_state_on_place(pos, state, moved)
                }
            }
            _ => {}
        }
    }

    pub fn affect_neighbors_after_removal(&mut self, pos: Pos, state: StateId, moved: bool) {
        let info = self.info(state);
        match info.kind {
            Kind::Lever | Kind::Button => {
                if !moved && info.powered() {
                    self.lever_update_neighbours(pos, state);
                }
            }
            Kind::PressurePlate => {
                if !moved && self.plate_signal(state) > 0 {
                    self.plate_update_neighbours(pos, state);
                }
            }
            Kind::Wire => self.wire_affect_neighbors_after_removal(pos, state, moved),
            Kind::Repeater | Kind::Comparator => {
                if !moved {
                    self.diode_update_neighbors_in_front(pos, state);
                }
            }
            Kind::Torch | Kind::WallTorch => {
                if !moved {
                    self.torch_notify_neighbors(pos, state);
                }
            }
            Kind::Observer => self.observer_affect_neighbors_after_removal(pos, state),
            Kind::PistonHead => self.piston_head_affect_neighbors_after_removal(pos, state),
            // Containers#updateNeighboursAfterDestroy
            Kind::Barrel | Kind::Chest | Kind::TrappedChest | Kind::Dispenser | Kind::Hopper | Kind::Crafter => {
                self.update_neighbour_for_output_signal(pos, info.block)
            }
            Kind::Rail | Kind::PoweredRail => self.rail_affect_neighbors_after_removal(pos, state, moved),
            Kind::Lectern => self.lectern_affect_neighbors_after_removal(pos, state),
            _ => {}
        }
    }

    /// The new state of this block after its neighbor in `direction` changed shape.
    pub fn update_shape(&mut self, pos: Pos, state: StateId, direction: Dir, neighbor_pos: Pos, neighbor_state: StateId) -> StateId {
        match self.info(state).kind {
            Kind::Lever | Kind::Button => self.lever_update_shape(pos, state, direction),
            Kind::PressurePlate => self.plate_update_shape(pos, state, direction),
            Kind::Wire => self.wire_update_shape(pos, state, direction, neighbor_pos, neighbor_state),
            Kind::Repeater | Kind::Comparator => self.diode_update_shape(pos, state, direction, neighbor_pos),
            Kind::Torch | Kind::WallTorch => self.torch_update_shape(pos, state, direction),
            Kind::Observer => self.observer_update_shape(pos, state, direction),
            Kind::PistonHead => self.piston_head_update_shape(pos, state, direction),
            Kind::NoteBlock => self.note_block_update_shape(pos, state, direction),
            Kind::Door => self.door_update_shape(pos, state, direction, neighbor_state),
            // CakeBlock#updateShape/canSurvive: gone when the block below is not solid
            Kind::Cake if direction == Dir::Down && self.info_at(pos.below()).flags & SF_SOLID == 0 => AIR,
            Kind::FenceGate => self.fence_gate_update_shape(pos, state, direction, neighbor_state),
            Kind::Chest | Kind::TrappedChest => self.chest_update_shape(state, direction, neighbor_state),
            _ => state,
        }
    }

    pub fn update_indirect_neighbour_shapes(&mut self, pos: Pos, state: StateId, flags: u32, limit: i32) {
        if self.info(state).kind == Kind::Wire {
            self.wire_update_indirect_neighbour_shapes(pos, state, flags, limit);
        }
    }

    pub fn block_tick(&mut self, pos: Pos, state: StateId) {
        match self.info(state).kind {
            Kind::Button => self.button_tick(pos, state),
            Kind::PressurePlate => self.plate_tick(pos, state),
            Kind::Lamp => self.lamp_tick(pos, state),
            Kind::Repeater => self.repeater_tick(pos, state),
            Kind::Comparator => self.comparator_refresh_output_state(pos, state),
            Kind::Torch | Kind::WallTorch => self.torch_tick(pos, state),
            Kind::Observer => self.observer_tick(pos, state),
            Kind::Dispenser => self.dispenser_tick(pos, state),
            Kind::Crafter => self.crafter_tick(pos, state),
            Kind::Target => self.target_tick(pos, state),
            Kind::Lectern => self.lectern_tick(pos, state),
            _ => {}
        }
    }

    pub fn trigger_event(&mut self, pos: Pos, state: StateId, a: i32, b: i32) -> bool {
        match self.info(state).kind {
            Kind::Piston => self.piston_trigger_event(pos, state, a, b),
            Kind::NoteBlock => true, // sound and particles only
            _ => false,
        }
    }

    /// Player right click without an item. Returns true if the block reacted.
    pub fn use_without_item(&mut self, pos: Pos, state: StateId) -> bool {
        match self.info(state).kind {
            Kind::Lever => {
                self.lever_pull(pos, state);
                true
            }
            Kind::Button => self.button_use(pos, state),
            Kind::PressurePlate => self.plate_use(pos, state),
            Kind::Wire => self.wire_use(pos, state),
            Kind::Repeater => self.repeater_use(pos, state),
            Kind::Comparator => self.comparator_use(pos, state),
            Kind::MovingPiston => self.moving_piston_use(pos, state),
            Kind::NoteBlock => self.note_block_use(pos, state),
            Kind::Door => self.door_use(pos, state),
            Kind::TrapDoor => self.trapdoor_use(pos, state),
            Kind::FenceGate => self.fence_gate_use(pos, state),
            Kind::DaylightDetector => self.daylight_use(pos, state),
            _ => false,
        }
    }

    // --- block entities ----------------------------------------------------------------------
    pub fn tick_block_entity(&mut self, be: BeId) {
        match &self.bes[be].data {
            BeData::Piston(_) => self.piston_be_tick(be),
            BeData::Daylight => self.daylight_be_tick(be),
            BeData::Container(Container { kind: ContainerKind::Hopper { .. }, .. }) => self.hopper_be_tick(be),
            BeData::Container(Container { kind: ContainerKind::Crafter { .. }, .. }) => self.crafter_be_tick(be),
            _ => {}
        }
    }

    /// `pre_remove_side_effects` of the block entity (only the moving piston has one).
    pub fn be_pre_remove_side_effects(&mut self, be: BeId, _pos: Pos, _old: StateId) {
        if matches!(self.bes[be].data, BeData::Piston(_)) {
            self.piston_be_final_tick(be);
        }
    }
}
