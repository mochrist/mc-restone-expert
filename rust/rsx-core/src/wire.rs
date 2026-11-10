//! Redstone wire with the default wire evaluator (port of redstone/sim/blocks/wire.py).
//!
//! Sides are handled as arrays in N, E, S, W order with 0 = none, 1 = side, 2 = up.

use crate::common::*;
use crate::state::*;
use crate::world::*;

const NONE: u8 = 0;
const SIDE: u8 = 1;
const UP: u8 = 2;

const SIDE_KEYS: [Sym; 4] = [sym::NORTH, sym::EAST, sym::SOUTH, sym::WEST];

fn side_sym(side: u8) -> Sym {
    match side {
        NONE => sym::NONE,
        SIDE => sym::SIDE,
        _ => sym::UP,
    }
}

#[inline]
fn is_cross(sides: [u8; 4]) -> bool {
    sides.iter().all(|s| *s != NONE)
}

#[inline]
fn is_dot(sides: [u8; 4]) -> bool {
    sides.iter().all(|s| *s == NONE)
}

/// Order in which dust that changed power calls updateNeighborsAt (knowledge DUST-017, DUST-018):
/// the wire position and its six neighbours (Direction.values()) are put into a `new HashSet<BlockPos>()`
/// and iterated. Seven entries never resize the 16-bucket table, so the order is by bucket, ties in
/// insertion order.
pub fn update_order(pos: Pos) -> [Pos; 7] {
    let mut items = [pos; 7];
    for (i, d) in ALL_DIRECTIONS.iter().enumerate() {
        items[i + 1] = pos.offset(*d);
    }
    let mut keyed = items.map(|p| (p.java_spread() & 15, p));
    // stable insertion sort by bucket
    for i in 1..7 {
        let mut j = i;
        while j > 0 && keyed[j - 1].0 > keyed[j].0 {
            keyed.swap(j - 1, j);
            j -= 1;
        }
    }
    keyed.map(|e| e.1)
}

impl World {
    /// `_wire_state(power, north, east, south, west)`: the full five-property wire state.
    pub fn wire_state(&mut self, power: i32, sides: [u8; 4]) -> StateId {
        let p = self.st.sym_int(power);
        self.st.state_of_name(
            "minecraft:redstone_wire",
            &[
                (sym::EAST, side_sym(sides[1])),
                (sym::NORTH, side_sym(sides[0])),
                (sym::POWER, p),
                (sym::SOUTH, side_sym(sides[2])),
                (sym::WEST, side_sym(sides[3])),
            ],
        )
    }

    /// RedStoneWireBlock.canSurviveOn: sturdy top face or a hopper.
    #[inline]
    fn wire_can_survive_on(&self, state: StateId) -> bool {
        let info = self.info(state);
        info.sturdy(Dir::Up, SUPPORT_FULL) || info.kind == Kind::Hopper
    }

    fn wire_can_survive(&self, pos: Pos) -> bool {
        self.wire_can_survive_on(self.get(pos.below()))
    }

    // --- connection shape ----------------------------------------------------------------------
    fn wire_connecting_side(&self, pos: Pos, direction: Dir, can_connect_up: bool) -> u8 {
        let relative_pos = pos.offset(direction);
        let relative_state = self.get(relative_pos);
        let rinfo = self.info(relative_state);
        if can_connect_up {
            let placeable_above = rinfo.block_flags & BF_TRAPDOOR_IN_ID != 0 || self.wire_can_survive_on(relative_state);
            if placeable_above && self.should_wire_connect_to(self.get(relative_pos.above()), None) {
                if rinfo.sturdy(direction.opposite(), SUPPORT_FULL) {
                    return UP;
                }
                return SIDE;
            }
        }
        if !self.should_wire_connect_to(relative_state, Some(direction))
            && (rinfo.conductor() || !self.should_wire_connect_to(self.get(relative_pos.below()), None))
        {
            return NONE;
        }
        SIDE
    }

    /// RedStoneWireBlock#getConnectionState for a wire whose current sides are `sides`.
    fn wire_connection_sides(&self, sides: [u8; 4], pos: Pos) -> [u8; 4] {
        let was_dot = is_dot(sides);
        // getMissingConnections starts from the default state (no connections)
        let can_connect_up = !self.is_conductor(pos.above());
        let mut out = [NONE; 4];
        for (i, d) in HORIZONTAL.iter().enumerate() {
            out[i] = self.wire_connecting_side(pos, *d, can_connect_up);
        }
        if was_dot && is_dot(out) {
            return out;
        }
        let (north, east, south, west) = (out[0] != NONE, out[1] != NONE, out[2] != NONE, out[3] != NONE);
        let north_south_empty = !north && !south;
        let east_west_empty = !east && !west;
        if !west && north_south_empty {
            out[3] = SIDE;
        }
        if !east && north_south_empty {
            out[1] = SIDE;
        }
        if !north && east_west_empty {
            out[0] = SIDE;
        }
        if !south && east_west_empty {
            out[2] = SIDE;
        }
        out
    }

    pub fn wire_get_connection_state(&mut self, state: StateId, pos: Pos) -> StateId {
        let info = self.info(state);
        let sides = self.wire_connection_sides(info.wire, pos);
        self.wire_state(info.power as i32, sides)
    }

    pub fn wire_update_shape(&mut self, pos: Pos, state: StateId, direction: Dir, _neighbor_pos: Pos, neighbor_state: StateId) -> StateId {
        if direction == Dir::Down {
            return if self.wire_can_survive_on(neighbor_state) { state } else { AIR };
        }
        if direction == Dir::Up {
            return self.wire_get_connection_state(state, pos);
        }
        let info = self.info(state);
        let i = direction.horizontal_index();
        let side = self.wire_connecting_side(pos, direction, !self.is_conductor(pos.above()));
        if (side != NONE) == (info.wire[i] != NONE) && !is_cross(info.wire) {
            return self.st.with(state, SIDE_KEYS[i], side_sym(side));
        }
        let mut sides = [SIDE; 4];
        sides[i] = side;
        let sides = self.wire_connection_sides(sides, pos);
        self.wire_state(info.power as i32, sides)
    }

    pub fn wire_update_indirect_neighbour_shapes(&mut self, pos: Pos, state: StateId, flags: u32, limit: i32) {
        let info = self.info(state);
        for (i, d) in HORIZONTAL.iter().enumerate() {
            let side_pos = pos.offset(*d);
            if info.wire[i] != NONE && self.info_at(side_pos).kind != Kind::Wire {
                let below = side_pos.below();
                if self.info_at(below).kind == Kind::Wire {
                    let npos = below.offset(d.opposite());
                    let nstate = self.get(npos);
                    self.neighbor_shape_changed(d.opposite(), below, npos, nstate, flags, limit);
                }
                let above = side_pos.above();
                if self.info_at(above).kind == Kind::Wire {
                    let npos = above.offset(d.opposite());
                    let nstate = self.get(npos);
                    self.neighbor_shape_changed(d.opposite(), above, npos, nstate, flags, limit);
                }
            }
        }
    }

    // --- power (DefaultRedstoneWireEvaluator) --------------------------------------------------
    /// DefaultRedstoneWireEvaluator#updatePowerStrength (orientation null).
    pub fn wire_update_power_strength(&mut self, pos: Pos, state: StateId) {
        let target = self.wire_calculate_target_strength(pos);
        let info = self.info(state);
        if info.power as i32 != target {
            if self.get(pos) == state {
                let new = self.st.with_int(state, sym::POWER, target);
                self.set_block_f(pos, new, UPDATE_CLIENTS);
            }
            for p in update_order(pos) {
                self.update_neighbors_at(p, info.block, None);
            }
        }
    }

    pub fn wire_calculate_target_strength(&mut self, pos: Pos) -> i32 {
        self.wire_should_signal = false;
        let block_signal = self.get_best_neighbor_signal(pos);
        self.wire_should_signal = true;
        if block_signal == 15 {
            15
        } else {
            block_signal.max(self.wire_incoming_wire_signal(pos))
        }
    }

    #[inline]
    fn wire_power_at(&self, pos: Pos) -> i32 {
        let info = self.info_at(pos);
        if info.kind == Kind::Wire {
            info.power as i32
        } else {
            0
        }
    }

    fn wire_incoming_wire_signal(&self, pos: Pos) -> i32 {
        let mut wire_signal = 0;
        let above_conductor = self.is_conductor(pos.above());
        for d in HORIZONTAL {
            let npos = pos.offset(d);
            let ninfo = self.info_at(npos);
            if ninfo.kind == Kind::Wire {
                wire_signal = wire_signal.max(ninfo.power as i32);
            }
            let n_conductor = ninfo.conductor();
            if n_conductor && !above_conductor {
                wire_signal = wire_signal.max(self.wire_power_at(npos.above()));
            } else if !n_conductor {
                wire_signal = wire_signal.max(self.wire_power_at(npos.below()));
            }
        }
        (wire_signal - 1).max(0)
    }

    // --- signals -----------------------------------------------------------------------------
    pub fn wire_get_signal(&mut self, pos: Pos, state: StateId, direction: Dir) -> i32 {
        if !self.wire_should_signal || direction == Dir::Down {
            return 0;
        }
        let info = self.info(state);
        let power = info.power as i32;
        if power == 0 {
            return 0;
        }
        if direction != Dir::Up {
            let sides = self.wire_connection_sides(info.wire, pos);
            if sides[direction.opposite().horizontal_index()] == NONE {
                return 0;
            }
        }
        power
    }

    // --- placement / removal / updates ---------------------------------------------------------
    fn wire_check_corner_change_at(&mut self, pos: Pos, block: BlockId) {
        if self.info_at(pos).kind == Kind::Wire {
            self.update_neighbors_at(pos, block, None);
            for d in ALL_DIRECTIONS {
                self.update_neighbors_at(pos.offset(d), block, None);
            }
        }
    }

    fn wire_update_neighbors_of_neighboring_wires(&mut self, pos: Pos, block: BlockId) {
        for d in HORIZONTAL {
            self.wire_check_corner_change_at(pos.offset(d), block);
        }
        for d in HORIZONTAL {
            let target = pos.offset(d);
            if self.is_conductor(target) {
                self.wire_check_corner_change_at(target.above(), block);
            } else {
                self.wire_check_corner_change_at(target.below(), block);
            }
        }
    }

    pub fn wire_on_place(&mut self, pos: Pos, state: StateId, old: StateId) {
        if self.info(old).name != self.info(state).name {
            let block = self.info(state).block;
            self.wire_update_power_strength(pos, state);
            for d in VERTICAL {
                self.update_neighbors_at(pos.offset(d), block, None);
            }
            self.wire_update_neighbors_of_neighboring_wires(pos, block);
        }
    }

    pub fn wire_affect_neighbors_after_removal(&mut self, pos: Pos, state: StateId, moved: bool) {
        if !moved {
            let block = self.info(state).block;
            for d in ALL_DIRECTIONS {
                self.update_neighbors_at(pos.offset(d), block, None);
            }
            self.wire_update_power_strength(pos, state);
            self.wire_update_neighbors_of_neighboring_wires(pos, block);
        }
    }

    pub fn wire_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        if self.wire_can_survive(pos) {
            self.wire_update_power_strength(pos, state);
        } else {
            self.remove_block(pos, false); // dropResources + removeBlock(pos, false)
        }
    }

    // --- interaction ---------------------------------------------------------------------------
    pub fn wire_use(&mut self, pos: Pos, state: StateId) -> bool {
        let info = self.info(state);
        if is_cross(info.wire) || is_dot(info.wire) {
            let start = if is_cross(info.wire) { [NONE; 4] } else { [SIDE; 4] };
            let sides = self.wire_connection_sides(start, pos);
            let new = self.wire_state(info.power as i32, sides);
            if new != state {
                self.set_block_f(pos, new, UPDATE_ALL);
                // updatesOnShapeChange
                for (i, d) in HORIZONTAL.iter().enumerate() {
                    let rel = pos.offset(*d);
                    if (info.wire[i] != NONE) != (sides[i] != NONE) && self.is_conductor(rel) {
                        self.update_neighbors_at_except_from_facing(rel, info.block, d.opposite());
                    }
                }
                return true;
            }
        }
        false
    }
}
