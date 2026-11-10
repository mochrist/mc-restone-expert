//! Containers, dispenser, dropper, hopper (port of redstone/sim/blocks/container.py and
//! dispenser_hopper.py).
//!
//! `Container::items` is the Python dict `slot -> [item, count]`: `set_slot` replaces in place or
//! appends, `del_slot` removes (insertion order is kept).

use crate::common::*;
use crate::state::*;
use crate::world::*;

/// Container#getMaxStackSize (Container.LARGE_MAX_STACK_SIZE)
const CONTAINER_MAX_STACK: i32 = 99;
const TRIGGER_DURATION: i64 = 4; // DispenserBlock.TRIGGER_DURATION
const MOVE_ITEM_SPEED: i32 = 8; // HopperBlockEntity.MOVE_ITEM_SPEED

impl Container {
    fn find(&self, slot: usize) -> Option<usize> {
        self.items.iter().position(|s| s.slot == slot)
    }

    fn get_slot(&self, slot: usize) -> Option<(ItemId, i32)> {
        self.find(slot).map(|i| (self.items[i].item, self.items[i].count))
    }

    /// `items[slot] = [item, count]`
    fn set_slot(&mut self, slot: usize, item: ItemId, count: i32) {
        match self.find(slot) {
            Some(i) => {
                self.items[i].item = item;
                self.items[i].count = count;
            }
            None => self.items.push(ItemStack { slot, item, count }),
        }
    }

    fn del_slot(&mut self, slot: usize) {
        if let Some(i) = self.find(slot) {
            self.items.remove(i);
        }
    }

    /// ContainerBlockEntity#shrink
    fn shrink(&mut self, slot: usize, n: i32) {
        if let Some(i) = self.find(slot) {
            self.items[i].count -= n;
            if self.items[i].count <= 0 {
                self.items.remove(i);
            }
        }
    }

    fn is_hopper(&self) -> bool {
        matches!(self.kind, ContainerKind::Hopper { .. })
    }
}

impl World {
    fn cont(&self, be: BeId) -> &Container {
        match &self.bes[be].data {
            BeData::Container(c) => c,
            _ => panic!("not a container block entity"),
        }
    }

    fn cont_mut(&mut self, be: BeId) -> &mut Container {
        match &mut self.bes[be].data {
            BeData::Container(c) => c,
            _ => panic!("not a container block entity"),
        }
    }

    fn is_container_be(&self, be: BeId) -> bool {
        matches!(self.bes[be].data, BeData::Container(_))
    }

    #[inline]
    fn item_max(&self, item: ItemId) -> i32 {
        self.item_max_stack[item as usize]
    }

    /// container_max_stack: min(99, item max)
    #[inline]
    fn container_max(&self, item: ItemId) -> i32 {
        CONTAINER_MAX_STACK.min(self.item_max(item))
    }

    /// BlockEntity#setChanged: comparators next to the container re-read it.
    fn container_set_changed(&mut self, be: BeId) {
        let pos = self.bes[be].pos;
        let state = self.get(pos);
        let info = self.info(state);
        if !info.is_air() {
            self.update_neighbour_for_output_signal(pos, info.block);
        }
    }

    /// HopperBlockEntity#getContainerAt; container entities (minecarts) are not modeled.
    fn get_container_at(&mut self, pos: Pos) -> Option<BeId> {
        let state = self.get(pos);
        let info = self.info(state);
        if !(self.has_block_entity(info.kind) || info.flags & SF_DATA_BLOCK_ENTITY != 0) {
            return None;
        }
        let be = self.get_block_entity(pos)?;
        if self.is_container_be(be) {
            Some(be)
        } else {
            None
        }
    }

    /// ContainerBlock#get_analog_output_signal: the redstone signal of the container at `pos`
    /// (raw `block_entities.get(pos)`, 0 if it is not a container).
    pub fn container_analog_output(&mut self, pos: Pos) -> i32 {
        match self.raw_block_entity(pos) {
            Some(be) if self.is_container_be(be) => self.container_redstone_signal(be),
            _ => 0,
        }
    }

    /// ContainerBlockEntity#redstone_signal (AbstractContainerMenu#getRedstoneSignalFromContainer)
    pub fn container_redstone_signal(&self, be: BeId) -> i32 {
        let c = self.cont(be);
        if c.size == 0 {
            return 0;
        }
        let mut fullness = 0.0f64;
        for s in &c.items {
            fullness += s.count as f64 / self.container_max(s.item) as f64;
        }
        fullness /= c.size as f64;
        // Mth.lerpDiscrete(fullness, 0, 15) = floor(f * 14) + (f > 0 ? 1 : 0)
        (fullness * 14.0).floor() as i32 + if fullness > 0.0 { 1 } else { 0 }
    }

    /// container.add_item (HopperBlockEntity#addItem). Returns the count that did not fit.
    pub fn add_item(&mut self, source: Option<BeId>, container: BeId, item: ItemId, count: i32) -> i32 {
        let mut count = count;
        let size = self.cont(container).size;
        for slot in 0..size {
            if count <= 0 {
                break;
            }
            count = self.try_move_in_item(source, container, item, count, slot);
        }
        count
    }

    /// HopperBlockEntity#tryMoveInItem
    fn try_move_in_item(&mut self, source: Option<BeId>, container: BeId, item: ItemId, count: i32, slot: usize) -> i32 {
        let mut count = count;
        let current = self.cont(container).get_slot(slot);
        let was_empty = self.cont(container).items.is_empty();
        let mut success = false;
        let item_max = self.item_max(item);
        match current {
            None => {
                let n = count.min(self.container_max(item));
                self.cont_mut(container).set_slot(slot, item, n);
                count = 0;
                success = true;
            }
            Some((cur_item, cur_count)) if cur_item == item && cur_count <= item_max => {
                let moved = count.min(item_max - cur_count);
                count -= moved;
                self.cont_mut(container).set_slot(slot, cur_item, cur_count + moved);
                success = moved > 0;
            }
            _ => {}
        }
        if success {
            if was_empty {
                self.hopper_on_item_received(container, source);
            }
            self.container_set_changed(container);
        }
        count
    }

    /// HopperBlockEntity#on_item_received: an empty hopper that receives an item waits (DDH-011).
    fn hopper_on_item_received(&mut self, hopper: BeId, source: Option<BeId>) {
        let source_ticked = source.and_then(|s| match &self.bes[s].data {
            BeData::Container(Container { kind: ContainerKind::Hopper { ticked_game_time, .. }, .. }) => {
                Some(*ticked_game_time)
            }
            _ => None,
        });
        if let BeData::Container(Container { kind: ContainerKind::Hopper { cooldown_time, ticked_game_time }, .. }) =
            &mut self.bes[hopper].data
        {
            if *cooldown_time > MOVE_ITEM_SPEED {
                return;
            }
            let skip = match source_ticked {
                Some(t) if *ticked_game_time >= t => 1,
                _ => 0,
            };
            *cooldown_time = MOVE_ITEM_SPEED - skip;
        }
    }

    // ------------------------------------------------------------------ dispenser / dropper
    /// DispenserBlock#neighborChanged, including quasi-connectivity (DDH-001, DDH-002, QC-002)
    pub fn dispenser_neighbor_changed(&mut self, pos: Pos, state: StateId) {
        let should_trigger = self.has_neighbor_signal(pos) || self.has_neighbor_signal(pos.offset(Dir::Up));
        let is_triggered = self.st.get_bool(state, sym::TRIGGERED);
        if should_trigger && !is_triggered {
            let block = self.info(state).block;
            self.schedule_tick(pos, block, TRIGGER_DURATION, PRIO_NORMAL);
            let new = self.st.with_bool(state, sym::TRIGGERED, true);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        } else if !should_trigger && is_triggered {
            let new = self.st.with_bool(state, sym::TRIGGERED, false);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        }
    }

    /// DispenserBlock#tick: dispense without re-checking power (DDH-003).
    pub fn dispenser_tick(&mut self, pos: Pos, state: StateId) {
        let dropper = self.info(state).param2 == 1;
        let Some(be) = self.get_block_entity(pos) else { return };
        if !matches!(self.bes[be].data, BeData::Container(Container { kind: ContainerKind::Dispenser, .. })) {
            return;
        }
        // ASSUMPTION (as in Python): the first non-empty slot instead of a random one.
        let Some(slot) = self.cont(be).items.iter().map(|s| s.slot).min() else { return };
        let (item, mut count) = self.cont(be).get_slot(slot).unwrap();
        if dropper {
            // DropperBlock#dispenseFrom: insert one item into a container in front, otherwise drop it (DDH-006)
            let st = self.get(pos);
            let direction = self.info(st).facing_or(Dir::North);
            match self.get_container_at(pos.offset(direction)) {
                None => count -= 1,
                Some(into) => {
                    if self.add_item(Some(be), into, item, 1) == 0 {
                        count -= 1;
                    }
                }
            }
        } else {
            // ASSUMPTION: every item uses DefaultDispenseItemBehavior (throws one item).
            count -= 1;
        }
        // BaseContainerBlockEntity#setItem (always notifies comparators)
        if count > 0 {
            self.cont_mut(be).set_slot(slot, item, count);
        } else {
            self.cont_mut(be).del_slot(slot);
        }
        self.container_set_changed(be);
    }

    // ------------------------------------------------------------------ hopper
    /// HopperBlock#checkPoweredState: no quasi-connectivity, no delay (DDH-007, QC-009).
    pub fn hopper_check_powered_state(&mut self, pos: Pos, state: StateId) {
        let should_be_on = !self.has_neighbor_signal(pos);
        if should_be_on != self.st.get_bool(state, sym::ENABLED) {
            let new = self.st.with_bool(state, sym::ENABLED, should_be_on);
            self.set_block_f(pos, new, UPDATE_CLIENTS);
        }
    }

    fn hopper_cooldown(&self, be: BeId) -> i32 {
        match &self.cont(be).kind {
            ContainerKind::Hopper { cooldown_time, .. } => *cooldown_time,
            _ => -1,
        }
    }

    fn hopper_set_cooldown(&mut self, be: BeId, value: i32) {
        if let ContainerKind::Hopper { cooldown_time, .. } = &mut self.cont_mut(be).kind {
            *cooldown_time = value;
        }
    }

    /// HopperBlockEntity#tick (pushItemsTick, DDH-009, DDH-012)
    pub fn hopper_be_tick(&mut self, be: BeId) {
        let pos = self.bes[be].pos;
        let state = self.get(pos);
        if self.info(state).kind != Kind::Hopper {
            return;
        }
        let now = self.game_time;
        let cd = self.hopper_cooldown(be) - 1;
        if let ContainerKind::Hopper { cooldown_time, ticked_game_time } = &mut self.cont_mut(be).kind {
            *cooldown_time = cd;
            *ticked_game_time = now;
        }
        if cd <= 0 {
            self.hopper_set_cooldown(be, 0);
            self.hopper_try_move_items(be, state);
        }
    }

    /// HopperBlockEntity#tryMoveItems (DDH-008, DDH-010, DDH-013)
    fn hopper_try_move_items(&mut self, be: BeId, state: StateId) -> bool {
        if self.hopper_cooldown(be) > 0 || !self.st.get_bool(state, sym::ENABLED) {
            return false;
        }
        let mut changed = false;
        if !self.cont(be).items.is_empty() {
            changed = self.hopper_eject_items(be, state);
        }
        if !self.hopper_inventory_full(be) {
            let sucked = self.hopper_suck_in_items(be);
            changed |= sucked;
        }
        if changed {
            self.hopper_set_cooldown(be, MOVE_ITEM_SPEED);
            let pos = self.bes[be].pos;
            let block = self.info(state).block;
            self.update_neighbour_for_output_signal(pos, block);
            return true;
        }
        false
    }

    fn hopper_inventory_full(&self, be: BeId) -> bool {
        let c = self.cont(be);
        c.items.len() == c.size && c.items.iter().all(|s| s.count == self.item_max(s.item))
    }

    /// HopperBlockEntity#isFullContainer
    fn is_full_container(&self, be: BeId) -> bool {
        let c = self.cont(be);
        for slot in 0..c.size {
            match c.get_slot(slot) {
                None => return false,
                Some((item, count)) if count < self.item_max(item) => return false,
                _ => {}
            }
        }
        true
    }

    /// HopperBlockEntity#ejectItems
    fn hopper_eject_items(&mut self, be: BeId, state: StateId) -> bool {
        let pos = self.bes[be].pos;
        let facing = self.info(state).facing_or(Dir::North);
        let Some(target) = self.get_container_at(pos.offset(facing)) else { return false };
        if self.is_full_container(target) {
            return false;
        }
        for slot in 0..self.cont(be).size {
            let Some((item, _)) = self.cont(be).get_slot(slot) else { continue };
            self.cont_mut(be).shrink(slot, 1); // HopperBlockEntity#removeItem does not call setChanged
            if self.add_item(Some(be), target, item, 1) == 0 {
                self.container_set_changed(target);
                return true;
            }
            // restore the original stack
            let c = self.cont_mut(be);
            match c.get_slot(slot) {
                Some((i, n)) => c.set_slot(slot, i, n + 1),
                None => c.set_slot(slot, item, 1),
            }
        }
        false
    }

    /// HopperBlockEntity#suckInItems from a container above; item entities are not modeled.
    fn hopper_suck_in_items(&mut self, be: BeId) -> bool {
        let pos = self.bes[be].pos;
        let Some(source) = self.get_container_at(pos.offset(Dir::Up)) else { return false };
        let source_is_hopper = self.cont(source).is_hopper();
        for slot in 0..self.cont(source).size {
            let Some((item, _)) = self.cont(source).get_slot(slot) else { continue };
            self.cont_mut(source).shrink(slot, 1);
            if !source_is_hopper {
                self.container_set_changed(source);
            }
            if self.add_item(Some(source), be, item, 1) == 0 {
                self.container_set_changed(source);
                return true;
            }
            let c = self.cont_mut(source);
            match c.get_slot(slot) {
                Some((i, n)) => c.set_slot(slot, i, n + 1),
                None => {
                    c.set_slot(slot, item, 1);
                    if !source_is_hopper {
                        self.container_set_changed(source);
                    }
                }
            }
        }
        false
    }
}
