//! Sculk sensor and calibrated sculk sensor (port of redstone/sim/blocks/sculk.py, the Python module is the
//! reference): block, block entity, vibration system (listener, selector, ticker) and `World::game_event`.

use crate::common::*;
use crate::state::*;
use crate::world::*;

pub const SENSOR_RADIUS: i32 = 8;
pub const CALIBRATED_RADIUS: i32 = 16;
const COOLDOWN_TICKS: i64 = 10;
const SENSOR_ACTIVE_TICKS: i64 = 30;
const CALIBRATED_ACTIVE_TICKS: i64 = 10;

/// VibrationSystem#VIBRATION_FREQUENCY_FOR_EVENT (0 = ignored)
pub fn event_frequency(event: &str) -> i32 {
    if let Some(n) = event.strip_prefix("resonate_") {
        return match n.parse::<i32>() {
            Ok(i) if (1..=15).contains(&i) => i,
            _ => 0,
        };
    }
    match event {
        "step" | "swim" | "flap" => 1,
        "projectile_land" | "hit_ground" | "splash" | "bounce" => 2,
        "item_interact_finish" | "projectile_shoot" | "instrument_play" => 3,
        "entity_action" | "elytra_glide" | "unequip" => 4,
        "entity_dismount" | "equip" => 5,
        "entity_interact" | "shear" | "entity_mount" => 6,
        "entity_damage" => 7,
        "drink" | "eat" => 8,
        "container_close" | "block_close" | "block_deactivate" | "block_detach" => 9,
        "container_open" | "block_open" | "block_activate" | "block_attach" | "prime_fuse" | "note_block_play" => 10,
        "block_change" => 11,
        "block_destroy" | "fluid_pickup" => 12,
        "block_place" | "fluid_place" => 13,
        "entity_place" | "lightning_strike" | "teleport" => 14,
        "entity_die" | "explode" => 15,
        _ => 0,
    }
}

/// A vibration: frequency, distance (a Java float) and the position of the source.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Vibration {
    pub frequency: i32,
    pub distance: f32,
    pub origin: Pos,
}

/// SculkSensorBlockEntity with its VibrationSystem data and selector.
#[derive(Clone, Debug, PartialEq)]
pub struct SculkBe {
    pub radius: i32,
    pub last_vibration_frequency: i32,
    pub current: Option<Vibration>,
    pub travel_time: i32,
    pub candidate: Option<Vibration>,
    pub candidate_tick: i64,
}

impl SculkBe {
    pub fn new(radius: i32) -> SculkBe {
        SculkBe { radius, last_vibration_frequency: 0, current: None, travel_time: 0, candidate: None, candidate_tick: -1 }
    }
}

/// VibrationSystem.Listener#distanceBetweenInBlocks: (float) sqrt(BlockPos#distSqr)
fn distance_between(a: Pos, b: Pos) -> f32 {
    let (dx, dy, dz) = ((a.x - b.x) as i64, (a.y - b.y) as i64, (a.z - b.z) as i64);
    ((dx * dx + dy * dy + dz * dz) as f64).sqrt() as f32
}

/// VibrationSystem#getRedstoneStrengthForDistance
fn redstone_strength_for_distance(distance: f32, radius: i32) -> i32 {
    (15 - (15.0f64 / radius as f64 * distance as f64).floor() as i32).max(1)
}

fn frac(x: f64) -> f64 {
    x - x.floor()
}

fn sign(x: f64) -> i32 {
    (x > 0.0) as i32 - (x < 0.0) as i32
}

impl World {
    fn sculk_phase(&self, state: StateId) -> Sym {
        self.st.get(state, sym::SCULK_SENSOR_PHASE).unwrap_or(sym::INACTIVE)
    }

    fn sculk_be(&mut self, be: BeId) -> &mut SculkBe {
        match &mut self.bes[be].data {
            BeData::Sculk(s) => s,
            _ => unreachable!("not a sculk sensor block entity"),
        }
    }

    // --- BlockGetter#isBlockInLine + traverseBlocks ----------------------------------------------
    fn wool_in_line(&self, from: [f64; 3], to: [f64; 3]) -> bool {
        if from == to {
            return false;
        }
        let lerp = |delta: f64, start: f64, end: f64| start + delta * (end - start);
        let t = [lerp(-1.0e-7, to[0], from[0]), lerp(-1.0e-7, to[1], from[1]), lerp(-1.0e-7, to[2], from[2])];
        let f = [lerp(-1.0e-7, from[0], to[0]), lerp(-1.0e-7, from[1], to[1]), lerp(-1.0e-7, from[2], to[2])];
        let (mut cx, mut cy, mut cz) = (f[0].floor() as i32, f[1].floor() as i32, f[2].floor() as i32);
        let hit = |x: i32, y: i32, z: i32| self.info_at(Pos::new(x, y, z)).block_flags & BF_WOOL != 0;
        if hit(cx, cy, cz) {
            return true;
        }
        let (dx, dy, dz) = (t[0] - f[0], t[1] - f[1], t[2] - f[2]);
        let (sx, sy, sz) = (sign(dx), sign(dy), sign(dz));
        let big = f64::MAX;
        let t_dx = if sx == 0 { big } else { sx as f64 / dx };
        let t_dy = if sy == 0 { big } else { sy as f64 / dy };
        let t_dz = if sz == 0 { big } else { sz as f64 / dz };
        let mut tx = t_dx * if sx > 0 { 1.0 - frac(f[0]) } else { frac(f[0]) };
        let mut ty = t_dy * if sy > 0 { 1.0 - frac(f[1]) } else { frac(f[1]) };
        let mut tz = t_dz * if sz > 0 { 1.0 - frac(f[2]) } else { frac(f[2]) };
        while tx <= 1.0 || ty <= 1.0 || tz <= 1.0 {
            if tx < ty {
                if tx < tz {
                    cx += sx;
                    tx += t_dx;
                } else {
                    cz += sz;
                    tz += t_dz;
                }
            } else if ty < tz {
                cy += sy;
                ty += t_dy;
            } else {
                cz += sz;
                tz += t_dz;
            }
            if hit(cx, cy, cz) {
                return true;
            }
        }
        false
    }

    /// VibrationSystem.Listener#isOccluded: blocked only when wool is in the way for each of the six start
    /// points nudged by 1e-5 from the center of the source block.
    fn sculk_is_occluded(&self, origin: Pos, dest: Pos) -> bool {
        let nudge = 1.0e-5f32 as f64;
        let to = [dest.x as f64 + 0.5, dest.y as f64 + 0.5, dest.z as f64 + 0.5];
        for d in ALL_DIRECTIONS {
            let v = d.vec();
            let start = [
                origin.x as f64 + 0.5 + nudge * v.0 as f64,
                origin.y as f64 + 0.5 + nudge * v.1 as f64,
                origin.z as f64 + 0.5 + nudge * v.2 as f64,
            ];
            if !self.wool_in_line(start, to) {
                return false;
            }
        }
        true
    }

    // --- LevelAccessor#gameEvent -----------------------------------------------------------------
    /// Post a game event at the center of `pos`; `affected` is the context's block state. Only vibration
    /// listeners exist in the simulator and they are independent of each other.
    pub fn game_event(&mut self, event: &str, pos: Pos, affected: Option<StateId>) {
        if self.block_entity_count() == 0 {
            return;
        }
        let frequency = event_frequency(event);
        if frequency == 0 {
            return;
        }
        let listeners: Vec<BeId> = self
            .block_entity_items()
            .into_iter()
            .map(|(_, be)| be)
            .filter(|&be| !self.bes[be].removed && matches!(self.bes[be].data, BeData::Sculk(_)))
            .collect();
        for be in listeners {
            self.sculk_on_game_event(be, event, frequency, pos, affected);
        }
    }

    /// VibrationSystem.Listener#handleGameEvent
    fn sculk_on_game_event(&mut self, be: BeId, event: &str, frequency: i32, origin: Pos, affected: Option<StateId>) {
        let (radius, busy) = {
            let s = self.sculk_be(be);
            (s.radius, s.current.is_some())
        };
        if busy {
            return;
        }
        if let Some(a) = affected {
            if self.info(a).block_flags & (BF_WOOL | BF_CARPET) != 0 {
                return; // User#isValidVibration
            }
        }
        let dest = self.bes[be].pos;
        let (dx, dy, dz) = ((origin.x - dest.x) as i64, (origin.y - dest.y) as i64, (origin.z - dest.z) as i64);
        let d2 = dx * dx + dy * dy + dz * dz;
        if d2 > (radius as i64) * (radius as i64) {
            return;
        }
        let state = self.get(dest);
        if origin == dest && (event == "block_destroy" || event == "block_place") {
            return;
        }
        if self.sculk_phase(state) != sym::INACTIVE {
            return; // SculkSensorBlock#canActivate
        }
        if radius == CALIBRATED_RADIUS {
            let back = self.info(state).facing_or(Dir::North).opposite();
            let wanted = self.get_signal(dest.offset(back), back);
            if wanted != 0 && frequency != wanted {
                return;
            }
        }
        if self.sculk_is_occluded(origin, dest) {
            return;
        }
        let distance = (d2 as f64).sqrt() as f32;
        let tick = self.game_time;
        let s = self.sculk_be(be);
        // VibrationSelector#addCandidate
        if let Some(c) = s.candidate {
            if tick != s.candidate_tick {
                return;
            }
            if !(distance < c.distance || (distance == c.distance && frequency > c.frequency)) {
                return;
            }
        }
        s.candidate = Some(Vibration { frequency, distance, origin });
        s.candidate_tick = tick;
    }

    // --- VibrationSystem.Ticker#tick -------------------------------------------------------------
    pub fn sculk_be_tick(&mut self, be: BeId) {
        let game_time = self.game_time;
        let s = self.sculk_be(be);
        if s.current.is_none() && s.candidate.is_some() && s.candidate_tick < game_time {
            s.current = s.candidate.take();
            s.travel_time = s.current.unwrap().distance.floor() as i32; // User#calculateTravelTimeInTicks
        }
        if s.current.is_some() {
            s.travel_time = (s.travel_time - 1).max(0);
            if s.travel_time <= 0 {
                self.sculk_receive(be);
            }
        }
    }

    fn sculk_receive(&mut self, be: BeId) {
        let (vibration, radius) = {
            let s = self.sculk_be(be);
            (s.current.unwrap(), s.radius)
        };
        let pos = self.bes[be].pos;
        let distance = distance_between(vibration.origin, pos);
        let state = self.get(pos);
        let kind = self.info(state).kind;
        if matches!(kind, Kind::SculkSensor | Kind::CalibratedSculkSensor) && self.sculk_phase(state) == sym::INACTIVE {
            self.sculk_be(be).last_vibration_frequency = vibration.frequency;
            let power = redstone_strength_for_distance(distance, radius);
            self.sculk_activate(pos, state, power, vibration.frequency);
        }
        self.sculk_be(be).current = None;
    }

    // --- the block ---------------------------------------------------------------------------------
    pub fn sculk_new_be(kind: Kind) -> SculkBe {
        SculkBe::new(if kind == Kind::CalibratedSculkSensor { CALIBRATED_RADIUS } else { SENSOR_RADIUS })
    }

    fn sculk_update_neighbours(&mut self, pos: Pos, block: BlockId) {
        self.update_neighbors_at(pos, block, None);
        self.update_neighbors_at(pos.below(), block, None);
    }

    pub fn sculk_on_place(&mut self, pos: Pos, state: StateId, block_changed: bool) {
        let info = self.info(state);
        if block_changed && info.power > 0 && !self.has_scheduled_tick(pos, info.block) {
            let new = self.st.with_int(state, sym::POWER, 0);
            self.set_block_f(pos, new, 18);
        }
    }

    pub fn sculk_affect_neighbors_after_removal(&mut self, pos: Pos, state: StateId) {
        if self.sculk_phase(state) == sym::ACTIVE {
            let block = self.info(state).block;
            self.sculk_update_neighbours(pos, block);
        }
    }

    pub fn sculk_analog_output(&mut self, pos: Pos, state: StateId) -> i32 {
        if self.sculk_phase(state) != sym::ACTIVE {
            return 0;
        }
        match self.get_block_entity(pos) {
            Some(be) => match &self.bes[be].data {
                BeData::Sculk(s) => s.last_vibration_frequency,
                _ => 0,
            },
            None => 0,
        }
    }

    pub fn sculk_tick(&mut self, pos: Pos, state: StateId) {
        let phase = self.sculk_phase(state);
        if phase != sym::ACTIVE {
            if phase == sym::COOLDOWN {
                let new = self.st.with(state, sym::SCULK_SENSOR_PHASE, sym::INACTIVE);
                self.set_block3(pos, new);
            }
        } else {
            let block = self.info(state).block;
            let new = self.st.with(state, sym::SCULK_SENSOR_PHASE, sym::COOLDOWN);
            let new = self.st.with_int(new, sym::POWER, 0);
            self.set_block3(pos, new);
            self.schedule_tick(pos, block, COOLDOWN_TICKS, PRIO_NORMAL);
            self.sculk_update_neighbours(pos, block);
        }
    }

    fn sculk_activate(&mut self, pos: Pos, state: StateId, power: i32, frequency: i32) {
        let info = self.info(state);
        let new = self.st.with(state, sym::SCULK_SENSOR_PHASE, sym::ACTIVE);
        let new = self.st.with_int(new, sym::POWER, power);
        self.set_block3(pos, new);
        let ticks = if info.kind == Kind::CalibratedSculkSensor { CALIBRATED_ACTIVE_TICKS } else { SENSOR_ACTIVE_TICKS };
        self.schedule_tick(pos, info.block, ticks, PRIO_NORMAL);
        self.sculk_update_neighbours(pos, info.block);
        // tryResonateVibration: amethyst blocks next to the sensor repeat the vibration
        for d in ALL_DIRECTIONS {
            let rel = pos.offset(d);
            let rel_state = self.get(rel);
            if self.info(rel_state).block_flags & BF_AMETHYST != 0 {
                self.game_event(&format!("resonate_{frequency}"), rel, Some(rel_state));
            }
        }
    }
}
