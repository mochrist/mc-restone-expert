//! Rust simulator core for the redstone toolkit. `redstone.sim.rust_world` wraps the `World` class
//! below behind the interface of the Python reference simulator (redstone/sim/world.py).

pub mod basic;
pub mod common;
pub mod container;
pub mod data;
pub mod diode;
pub mod dispatch;
pub mod outputs;
pub mod piston;
pub mod state;
pub mod torch;
pub mod wire;
pub mod world;

use common::{Dir, Pos};
use pyo3::exceptions::{PyKeyError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString, PyTuple};
use rustc_hash::FxHashMap;
use state::{StateId, AIR};
use world::{BeData, BeId, ContainerKind, ItemStack};

type P3 = (i32, i32, i32);

#[inline]
fn pos(p: P3) -> Pos {
    Pos::new(p.0, p.1, p.2)
}

fn dir(index: usize) -> PyResult<Dir> {
    if index < 6 {
        Ok(Dir::from_index(index))
    } else {
        Err(PyValueError::new_err("direction index must be 0..5"))
    }
}

const MAX_HELD_STATE_OBJECTS: usize = 8192;

/// The simulated level. Positions are `(x, y, z)` tuples, directions are indices in Direction order
/// (down, up, north, south, west, east), block states are `BlockState` objects or their string form,
/// blocks are full names (`minecraft:lever`).
#[pyclass(unsendable, module = "rsx_core")]
struct World {
    w: world::World,
    /// `make_state(text) -> BlockState` and `make_pos(x, y, z) -> Pos`
    make_state: Py<PyAny>,
    make_pos: Py<PyAny>,
    /// The Python object handed out for each state.
    state_objs: Vec<Option<Py<PyAny>>>,
    /// Identity cache for BlockState objects passed in (kept alive in `held`).
    by_ptr: FxHashMap<usize, StateId>,
    held: Vec<Py<PyAny>>,
    scratch: String,
}

impl World {
    fn state_in(&mut self, obj: &Bound<'_, PyAny>) -> PyResult<StateId> {
        let ptr = obj.as_ptr() as usize;
        if let Some(id) = self.by_ptr.get(&ptr) {
            return Ok(*id);
        }
        if obj.is_instance_of::<PyString>() {
            let text: String = obj.extract()?;
            return Ok(self.w.st.intern_str(&text));
        }
        let name = obj.getattr("name")?;
        let name: &str = name.extract()?;
        self.scratch.clear();
        self.scratch.push_str(name);
        let props = obj.getattr("props")?;
        let mut first = true;
        for item in props.try_iter()? {
            let (k, v): (String, String) = item?.extract()?;
            self.scratch.push(if first { '[' } else { ',' });
            first = false;
            self.scratch.push_str(&k);
            self.scratch.push('=');
            self.scratch.push_str(&v);
        }
        if !first {
            self.scratch.push(']');
        }
        let id = self.w.st.intern_str(&self.scratch);
        let i = id as usize;
        if self.state_objs.len() <= i {
            self.state_objs.resize_with(i + 1, || None);
        }
        if self.state_objs[i].is_none() && self.w.st.str(id) == self.scratch {
            self.state_objs[i] = Some(obj.clone().unbind());
            self.by_ptr.insert(ptr, id);
        } else if self.held.len() < MAX_HELD_STATE_OBJECTS {
            self.held.push(obj.clone().unbind());
            self.by_ptr.insert(ptr, id);
        }
        Ok(id)
    }

    fn state_out(&mut self, py: Python<'_>, id: StateId) -> PyResult<Py<PyAny>> {
        let i = id as usize;
        if self.state_objs.len() <= i {
            self.state_objs.resize_with(i + 1, || None);
        }
        if let Some(obj) = &self.state_objs[i] {
            return Ok(obj.clone_ref(py));
        }
        let obj = self.make_state.call1(py, (self.w.st.str(id),))?;
        self.by_ptr.insert(obj.as_ptr() as usize, id);
        self.state_objs[i] = Some(obj.clone_ref(py));
        Ok(obj)
    }

    fn pos_out(&self, py: Python<'_>, p: Pos) -> PyResult<Py<PyAny>> {
        self.make_pos.call1(py, (p.x, p.y, p.z))
    }

    fn block(&mut self, name: &str) -> state::BlockId {
        if name.contains(':') {
            self.w.st.block_id(name)
        } else {
            self.w.st.block_id(&format!("minecraft:{name}"))
        }
    }

    fn be(&self, id: BeId) -> PyResult<&world::BlockEntity> {
        self.w.bes.get(id).ok_or_else(|| PyKeyError::new_err("no such block entity"))
    }

    fn probe(&self, p: Pos) -> String {
        let state = self.w.get(p);
        let text = self.w.st.str(state);
        if self.w.info(state).kind == state::Kind::Comparator {
            let out = match self.w.raw_block_entity(p).map(|be| &self.w.bes[be].data) {
                Some(BeData::Comparator { output_signal }) => *output_signal,
                _ => 0,
            };
            format!("{text}|output={out}")
        } else {
            text.to_owned()
        }
    }
}

#[pymethods]
impl World {
    #[new]
    fn new(make_state: Py<PyAny>, make_pos: Py<PyAny>) -> PyResult<World> {
        if !data::is_initialized() {
            return Err(PyRuntimeError::new_err("call rsx_core.init(blocks_json, stack_sizes_json) first"));
        }
        Ok(World {
            w: world::World::new(),
            make_state,
            make_pos,
            state_objs: Vec::new(),
            by_ptr: FxHashMap::default(),
            held: Vec::new(),
            scratch: String::new(),
        })
    }

    // ------------------------------------------------------------------ construction
    /// `place_grid`: `items` is an iterable of `(pos, state)`; block entities are created with defaults.
    fn place_blocks(&mut self, items: &Bound<'_, PyAny>, origin: P3) -> PyResult<()> {
        let mut placed: Vec<(Pos, StateId)> = Vec::new();
        for item in items.try_iter()? {
            let item = item?;
            let p: P3 = item.get_item(0)?.extract()?;
            let state = self.state_in(&item.get_item(1)?)?;
            placed.push((Pos::new(p.0 + origin.0, p.1 + origin.1, p.2 + origin.2), state));
        }
        if let Some(first) = placed.first() {
            let (mut lo, mut hi) = (first.0, first.0);
            for (p, _) in &placed {
                lo = Pos::new(lo.x.min(p.x), lo.y.min(p.y), lo.z.min(p.z));
                hi = Pos::new(hi.x.max(p.x), hi.y.max(p.y), hi.z.max(p.z));
            }
            self.w.store.reserve(lo, hi);
        }
        for (p, state) in placed {
            self.w.place(p, state);
        }
        Ok(())
    }

    // ------------------------------------------------------------------ block access
    fn get(&mut self, py: Python<'_>, p: P3) -> PyResult<Py<PyAny>> {
        let id = self.w.get(pos(p));
        self.state_out(py, id)
    }

    fn get_str(&self, p: P3) -> &str {
        self.w.st.str(self.w.get(pos(p)))
    }

    fn contains(&self, p: P3) -> bool {
        self.w.get(pos(p)) != AIR
    }

    fn block_count(&self) -> usize {
        self.w.store.len()
    }

    /// `blocks.items()` in dict order.
    fn blocks_items(&mut self, py: Python<'_>) -> PyResult<Vec<(Py<PyAny>, Py<PyAny>)>> {
        let items = self.w.store.items();
        let mut out = Vec::with_capacity(items.len());
        for (p, s) in items {
            out.push((self.pos_out(py, p)?, self.state_out(py, s)?));
        }
        Ok(out)
    }

    /// `blocks[pos] = state` (no updates); an air state removes the block.
    fn set_raw(&mut self, p: P3, state: &Bound<'_, PyAny>) -> PyResult<()> {
        let s = self.state_in(state)?;
        self.w.set_raw(pos(p), s);
        Ok(())
    }

    #[pyo3(signature = (p, state, flags=3, limit=512))]
    fn set_block(&mut self, p: P3, state: &Bound<'_, PyAny>, flags: u32, limit: i32) -> PyResult<bool> {
        let s = self.state_in(state)?;
        Ok(self.w.set_block(pos(p), s, flags, limit))
    }

    #[pyo3(signature = (p, moved_by_piston=false))]
    fn remove_block(&mut self, p: P3, moved_by_piston: bool) -> bool {
        self.w.remove_block(pos(p), moved_by_piston)
    }

    #[pyo3(signature = (p, limit=512))]
    fn destroy_block(&mut self, p: P3, limit: i32) -> bool {
        self.w.destroy_block(pos(p), limit)
    }

    fn update_or_destroy(&mut self, old: &Bound<'_, PyAny>, new: &Bound<'_, PyAny>, p: P3, flags: u32, limit: i32) -> PyResult<()> {
        let (old, new) = (self.state_in(old)?, self.state_in(new)?);
        self.w.update_or_destroy(old, new, pos(p), flags, limit);
        Ok(())
    }

    /// Positions changed by set_block since the last call, in order of their first change.
    fn take_dirty(&mut self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        self.w.take_dirty().into_iter().map(|p| self.pos_out(py, p)).collect()
    }

    // ------------------------------------------------------------------ the game tick
    fn tick(&mut self) {
        self.w.tick();
    }

    #[getter]
    fn get_game_time(&self) -> i64 {
        self.w.game_time
    }

    #[setter]
    fn set_game_time(&mut self, value: i64) {
        self.w.game_time = value;
    }

    #[getter]
    fn get_handling_tick(&self) -> bool {
        self.w.handling_tick
    }

    #[setter]
    fn set_handling_tick(&mut self, value: bool) {
        self.w.handling_tick = value;
    }

    fn is_idle(&self) -> bool {
        self.w.is_idle()
    }

    fn warnings(&self) -> Vec<String> {
        self.w.warnings.clone()
    }

    fn add_warning(&mut self, text: String) {
        self.w.warnings.push(text);
    }

    #[getter]
    fn neighbor_update_count(&self) -> u64 {
        self.w.stat_neighbor_updates
    }

    // ------------------------------------------------------------------ interaction
    /// `world.block(state).use_without_item(world, pos, state)`
    fn use_without_item(&mut self, p: P3, state: &Bound<'_, PyAny>) -> PyResult<bool> {
        let s = self.state_in(state)?;
        Ok(self.w.use_without_item(pos(p), s))
    }

    /// Runner input "use": right click on the block at `pos`.
    fn use_at(&mut self, p: P3) -> bool {
        let s = self.w.get(pos(p));
        self.w.use_without_item(pos(p), s)
    }

    // ------------------------------------------------------------------ neighbor updates
    #[pyo3(signature = (p, source, skip=None))]
    fn update_neighbors_at(&mut self, p: P3, source: &str, skip: Option<usize>) -> PyResult<()> {
        let source = self.block(source);
        let skip = skip.map(dir).transpose()?;
        self.w.update_neighbors_at(pos(p), source, skip);
        Ok(())
    }

    fn neighbor_changed(&mut self, p: P3, source: &str) {
        let source = self.block(source);
        self.w.neighbor_changed(pos(p), source);
    }

    fn neighbor_changed_with_state(&mut self, state: &Bound<'_, PyAny>, p: P3, source: &str, moved: bool) -> PyResult<()> {
        let s = self.state_in(state)?;
        let source = self.block(source);
        self.w.neighbor_changed_with_state(s, pos(p), source, moved);
        Ok(())
    }

    fn neighbor_shape_changed(&mut self, direction: usize, p: P3, neighbor_pos: P3, neighbor_state: &Bound<'_, PyAny>, flags: u32, limit: i32) -> PyResult<()> {
        let s = self.state_in(neighbor_state)?;
        self.w.neighbor_shape_changed(dir(direction)?, pos(p), pos(neighbor_pos), s, flags, limit);
        Ok(())
    }

    #[pyo3(signature = (p, state, flags, limit=512))]
    fn update_neighbour_shapes(&mut self, p: P3, state: &Bound<'_, PyAny>, flags: u32, limit: i32) -> PyResult<()> {
        let s = self.state_in(state)?;
        self.w.update_neighbour_shapes(pos(p), s, flags, limit);
        Ok(())
    }

    fn update_neighbour_for_output_signal(&mut self, p: P3, source: &str) {
        let source = self.block(source);
        self.w.update_neighbour_for_output_signal(pos(p), source);
    }

    // ------------------------------------------------------------------ signals
    fn is_conductor(&self, p: P3) -> bool {
        self.w.is_conductor(pos(p))
    }

    fn is_face_sturdy(&self, p: P3, face: usize, support: usize) -> PyResult<bool> {
        if support > 2 {
            return Err(PyValueError::new_err("support must be 0 (full), 1 (rigid) or 2 (center)"));
        }
        Ok(self.w.is_face_sturdy(pos(p), dir(face)?, support))
    }

    fn get_signal(&mut self, p: P3, direction: usize) -> PyResult<i32> {
        Ok(self.w.get_signal(pos(p), dir(direction)?))
    }

    fn get_direct_signal(&mut self, p: P3, direction: usize) -> PyResult<i32> {
        Ok(self.w.get_direct_signal(pos(p), dir(direction)?))
    }

    fn get_direct_signal_to(&mut self, p: P3) -> i32 {
        self.w.get_direct_signal_to(pos(p))
    }

    fn has_neighbor_signal(&mut self, p: P3) -> bool {
        self.w.has_neighbor_signal(pos(p))
    }

    fn get_best_neighbor_signal(&mut self, p: P3) -> i32 {
        self.w.get_best_neighbor_signal(pos(p))
    }

    fn get_control_input_signal(&mut self, p: P3, direction: usize, only_diodes: bool) -> PyResult<i32> {
        Ok(self.w.get_control_input_signal(pos(p), dir(direction)?, only_diodes))
    }

    // ------------------------------------------------------------------ scheduled ticks, block events
    #[pyo3(signature = (p, block, delay, priority=0))]
    fn schedule_tick(&mut self, p: P3, block: &str, delay: i64, priority: i32) {
        let block = self.block(block);
        self.w.schedule_tick(pos(p), block, delay, priority);
    }

    fn has_scheduled_tick(&mut self, p: P3, block: &str) -> bool {
        let block = self.block(block);
        self.w.has_scheduled_tick(pos(p), block)
    }

    fn will_tick_this_tick(&mut self, p: P3, block: &str) -> bool {
        let block = self.block(block);
        self.w.will_tick_this_tick(pos(p), block)
    }

    fn clear_scheduled_ticks(&mut self) {
        self.w.clear_scheduled_ticks();
    }

    fn scheduled_tick_count(&self) -> usize {
        self.w.scheduled_tick_count()
    }

    /// Pending ticks as `(trigger_tick, priority, sub_tick, pos, block)` in running order.
    fn scheduled_ticks(&self, py: Python<'_>) -> PyResult<Vec<(i64, i32, u64, Py<PyAny>, String)>> {
        self.w
            .scheduled_ticks()
            .into_iter()
            .map(|t| Ok((t.trigger_tick, t.priority, t.sub_tick, self.pos_out(py, t.pos)?, self.w.st.block_name(t.block).to_owned())))
            .collect()
    }

    fn block_event(&mut self, p: P3, block: &str, a: i32, b: i32) {
        let block = self.block(block);
        self.w.block_event(pos(p), block, a, b);
    }

    fn block_event_count(&self) -> usize {
        self.w.block_events.len()
    }

    /// Queued block events as `(pos, block, a, b)`.
    fn block_events(&self, py: Python<'_>) -> PyResult<Vec<(Py<PyAny>, String, i32, i32)>> {
        self.w
            .block_events
            .iter()
            .map(|e| Ok((self.pos_out(py, e.pos)?, self.w.st.block_name(e.block).to_owned(), e.a, e.b)))
            .collect()
    }

    // ------------------------------------------------------------------ probes
    /// runner.probe_value: the state string, for comparators with `|output=N`.
    fn probe_value(&self, p: P3) -> String {
        self.probe(pos(p))
    }

    /// Probe values of all non-air blocks inside `lo..=hi`, as `(pos - origin, value)` in dict order.
    fn snapshot(&self, py: Python<'_>, lo: P3, hi: P3, origin: P3) -> PyResult<Vec<(Py<PyAny>, String)>> {
        let mut out = Vec::new();
        for (p, _) in self.w.store.items() {
            if lo.0 <= p.x && p.x <= hi.0 && lo.1 <= p.y && p.y <= hi.1 && lo.2 <= p.z && p.z <= hi.2 {
                let rel = Pos::new(p.x - origin.0, p.y - origin.1, p.z - origin.2);
                out.push((self.pos_out(py, rel)?, self.probe(p)));
            }
        }
        Ok(out)
    }

    /// Probe values for an iterable of positions (air gives `minecraft:air`).
    fn probe_values(&self, positions: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
        let mut out = Vec::new();
        for item in positions.try_iter()? {
            let p: P3 = item?.extract()?;
            out.push(self.probe(pos(p)));
        }
        Ok(out)
    }

    /// Positions of all comparators that have a block entity entry, in `block_entities` order.
    fn comparator_positions(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let mut out = Vec::new();
        for (p, _) in self.w.block_entity_items() {
            if self.w.info_at(p).kind == state::Kind::Comparator {
                out.push(self.pos_out(py, p)?);
            }
        }
        Ok(out)
    }

    // ------------------------------------------------------------------ block entities
    /// `block_entities.get(pos)`: the raw entry (may be a removed block entity).
    fn raw_block_entity(&self, p: P3) -> Option<BeId> {
        self.w.raw_block_entity(pos(p))
    }

    /// Level#getBlockEntity
    fn get_block_entity(&mut self, p: P3) -> Option<BeId> {
        self.w.get_block_entity(pos(p))
    }

    fn remove_block_entity(&mut self, p: P3) {
        self.w.remove_block_entity(pos(p));
    }

    fn block_entity_count(&self) -> usize {
        self.w.block_entity_count()
    }

    fn block_entity_items(&self, py: Python<'_>) -> PyResult<Vec<(Py<PyAny>, BeId)>> {
        self.w.block_entity_items().into_iter().map(|(p, be)| Ok((self.pos_out(py, p)?, be))).collect()
    }

    /// Kind of a block entity: comparator, container, dispenser, hopper, lectern or piston.
    fn be_kind(&self, be: BeId) -> PyResult<&'static str> {
        Ok(match &self.be(be)?.data {
            BeData::Comparator { .. } => "comparator",
            BeData::Container(c) => match c.kind {
                ContainerKind::Plain => "container",
                ContainerKind::Dispenser => "dispenser",
                ContainerKind::Hopper { .. } => "hopper",
                ContainerKind::Crafter { .. } => "crafter",
            },
            BeData::Lectern(_) => "lectern",
            BeData::Daylight => "daylight",
            BeData::Piston(_) => "piston",
        })
    }

    /// One attribute of a block entity, named like in the Python classes.
    fn be_get(&mut self, py: Python<'_>, be: BeId, field: &str) -> PyResult<Py<PyAny>> {
        let entity = self.be(be)?.clone();
        let missing = || PyKeyError::new_err(format!("block entity has no attribute {field}"));
        macro_rules! py {
            ($v:expr) => {
                $v.into_pyobject(py)?.to_owned().into_any().unbind()
            };
        }
        Ok(match (field, &entity.data) {
            ("removed", _) => py!(entity.removed),
            ("pos", _) => self.pos_out(py, entity.pos)?,
            ("ticks", _) => py!(entity.ticks()),
            ("output_signal", BeData::Comparator { output_signal }) => py!(*output_signal),
            ("size", BeData::Container(c)) => py!(c.size),
            ("items", BeData::Container(c)) => {
                let d = PyDict::new(py);
                for stack in &c.items {
                    let entry = PyList::new(py, [py!(&*self.w.item_names[stack.item as usize]), py!(stack.count)])?;
                    d.set_item(stack.slot, entry)?;
                }
                d.into_any().unbind()
            }
            ("redstone_signal", BeData::Container(_)) => py!(self.w.container_redstone_signal(be)),
            ("cooldown_time", BeData::Container(c)) => match c.kind {
                ContainerKind::Hopper { cooldown_time, .. } => py!(cooldown_time),
                _ => return Err(missing()),
            },
            ("ticked_game_time", BeData::Container(c)) => match c.kind {
                ContainerKind::Hopper { ticked_game_time, .. } => py!(ticked_game_time),
                _ => return Err(missing()),
            },
            ("disabled_mask", BeData::Container(c)) => match c.kind {
                ContainerKind::Crafter { disabled_mask, .. } => py!(disabled_mask),
                _ => return Err(missing()),
            },
            ("triggered", BeData::Container(c)) => match c.kind {
                ContainerKind::Crafter { triggered, .. } => py!(triggered),
                _ => return Err(missing()),
            },
            ("crafting_ticks_remaining", BeData::Container(c)) => match c.kind {
                ContainerKind::Crafter { crafting_ticks_remaining, .. } => py!(crafting_ticks_remaining),
                _ => return Err(missing()),
            },
            ("has_book", BeData::Lectern(l)) => py!(l.has_book),
            ("page", BeData::Lectern(l)) => py!(l.page),
            ("page_count", BeData::Lectern(l)) => py!(l.page_count),
            ("moved_state", BeData::Piston(b)) => self.state_out(py, b.moved_state)?,
            ("direction", BeData::Piston(b)) => py!(b.direction as usize),
            ("extending", BeData::Piston(b)) => py!(b.extending),
            ("is_source_piston", BeData::Piston(b)) => py!(b.is_source_piston),
            ("progress", BeData::Piston(b)) => py!(b.progress),
            ("progress_o", BeData::Piston(b)) => py!(b.progress_o),
            ("last_ticked", BeData::Piston(b)) => py!(b.last_ticked),
            _ => return Err(missing()),
        })
    }

    /// Set one attribute of a block entity (see `be_get`; `items` takes `{slot: [item, count]}`).
    fn be_set(&mut self, be: BeId, field: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
        self.be(be)?;
        let missing = || PyKeyError::new_err(format!("block entity has no attribute {field}"));
        if field == "items" {
            let mut items = Vec::new();
            for (slot, entry) in value.cast::<PyDict>()?.iter() {
                let slot: usize = slot.extract()?;
                let name: String = entry.get_item(0)?.extract()?;
                let count: i32 = entry.get_item(1)?.extract()?;
                let item = self.w.item_id(&name);
                items.push(ItemStack { slot, item, count });
            }
            return match &mut self.w.bes[be].data {
                BeData::Container(c) => {
                    c.items = items;
                    Ok(())
                }
                _ => Err(missing()),
            };
        }
        if field == "moved_state" {
            let s = self.state_in(value)?;
            return match &mut self.w.bes[be].data {
                BeData::Piston(b) => {
                    b.moved_state = s;
                    Ok(())
                }
                _ => Err(missing()),
            };
        }
        let entity = &mut self.w.bes[be];
        match (field, &mut entity.data) {
            ("removed", _) => entity.removed = value.extract()?,
            ("output_signal", BeData::Comparator { output_signal }) => *output_signal = value.extract()?,
            ("cooldown_time", BeData::Container(c)) => match &mut c.kind {
                ContainerKind::Hopper { cooldown_time, .. } => *cooldown_time = value.extract()?,
                _ => return Err(missing()),
            },
            ("ticked_game_time", BeData::Container(c)) => match &mut c.kind {
                ContainerKind::Hopper { ticked_game_time, .. } => *ticked_game_time = value.extract()?,
                _ => return Err(missing()),
            },
            ("disabled_mask", BeData::Container(c)) => match &mut c.kind {
                ContainerKind::Crafter { disabled_mask, .. } => *disabled_mask = value.extract()?,
                _ => return Err(missing()),
            },
            ("triggered", BeData::Container(c)) => match &mut c.kind {
                ContainerKind::Crafter { triggered, .. } => *triggered = value.extract()?,
                _ => return Err(missing()),
            },
            ("crafting_ticks_remaining", BeData::Container(c)) => match &mut c.kind {
                ContainerKind::Crafter { crafting_ticks_remaining, .. } => *crafting_ticks_remaining = value.extract()?,
                _ => return Err(missing()),
            },
            ("has_book", BeData::Lectern(l)) => l.has_book = value.extract()?,
            ("page", BeData::Lectern(l)) => l.page = value.extract()?,
            ("page_count", BeData::Lectern(l)) => l.page_count = value.extract()?,
            ("direction", BeData::Piston(b)) => b.direction = dir(value.extract()?)?,
            ("extending", BeData::Piston(b)) => b.extending = value.extract()?,
            ("is_source_piston", BeData::Piston(b)) => b.is_source_piston = value.extract()?,
            ("progress", BeData::Piston(b)) => b.progress = value.extract()?,
            ("progress_o", BeData::Piston(b)) => b.progress_o = value.extract()?,
            ("last_ticked", BeData::Piston(b)) => b.last_ticked = value.extract()?,
            _ => return Err(missing()),
        }
        Ok(())
    }

    /// Create a moving piston block entity at `pos` and register it (scenario setup: a stored
    /// `moving_piston` gets no block entity from `place_blocks`).
    fn add_piston_block_entity(&mut self, p: P3) -> BeId {
        let be = self.w.create_be(
            pos(p),
            BeData::Piston(world::PistonBe {
                moved_state: AIR,
                direction: Dir::Down,
                extending: false,
                is_source_piston: false,
                progress: 0.0,
                progress_o: 0.0,
                last_ticked: 0,
            }),
        );
        self.w.add_block_entity(pos(p), be);
        be
    }

    /// container.add_item(world, source, container, item, count)
    #[pyo3(signature = (source, container, item, count=1))]
    fn add_item(&mut self, source: Option<BeId>, container: BeId, item: &str, count: i32) -> PyResult<i32> {
        self.be(container)?;
        let name = if item.contains(':') { item.to_owned() } else { format!("minecraft:{item}") };
        let item = self.w.item_id(&name);
        Ok(self.w.add_item(source.map(container::CRef::single), container::CRef::single(container), item, count))
    }

    // ------------------------------------------------------------------ notes
    /// Mechanics notes so far as `(tick, kind, pos, detail)`.
    fn notes(&self, py: Python<'_>) -> PyResult<Vec<(i64, &'static str, Py<PyAny>, String)>> {
        self.w.notes.iter().map(|n| Ok((n.tick, n.kind, self.pos_out(py, n.pos)?, n.detail.clone()))).collect()
    }

    /// The state checks of redstone.sim.notes (pistons resting in a BUD state).
    fn run_state_checks(&mut self) {
        self.w.check_bud_states();
    }

    // ------------------------------------------------------------------ block specific helpers
    /// RedstoneWireBlock#get_connection_state(world, state, pos)
    fn wire_get_connection_state(&mut self, py: Python<'_>, state: &Bound<'_, PyAny>, p: P3) -> PyResult<Py<PyAny>> {
        let s = self.state_in(state)?;
        let new = self.w.wire_get_connection_state(s, pos(p));
        self.state_out(py, new)
    }

    fn wire_update_power_strength(&mut self, p: P3, state: &Bound<'_, PyAny>) -> PyResult<()> {
        let s = self.state_in(state)?;
        self.w.wire_update_power_strength(pos(p), s);
        Ok(())
    }

    fn wire_calculate_target_strength(&mut self, p: P3) -> i32 {
        self.w.wire_calculate_target_strength(pos(p))
    }

    fn piston_has_direct_signal(&mut self, p: P3, push_direction: usize) -> PyResult<bool> {
        Ok(self.w.piston_has_direct_signal(pos(p), dir(push_direction)?))
    }

    fn piston_has_qc_signal(&mut self, p: P3) -> bool {
        self.w.piston_has_qc_signal(pos(p))
    }

    /// outputs._instrument(state)
    fn instrument(&mut self, state: &Bound<'_, PyAny>) -> PyResult<String> {
        let s = self.state_in(state)?;
        Ok(self.w.instrument(s))
    }

    /// Static facts about a state as the core sees them (for cross-checks against redstone.sim.blockdata).
    fn state_facts<'py>(&mut self, py: Python<'py>, state: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
        let s = self.state_in(state)?;
        let info = self.w.info(s);
        let d = PyDict::new(py);
        d.set_item("kind", format!("{:?}", info.kind))?;
        d.set_item("conductor", info.conductor())?;
        d.set_item("sturdy", PyTuple::new(py, info.sturdy)?)?;
        d.set_item("push", self.w.piston_push_reaction(s))?;
        d.set_item("raw_push", info.push)?;
        d.set_item("block_entity", info.flags & state::SF_DATA_BLOCK_ENTITY != 0)?;
        d.set_item("unbreakable", info.flags & state::SF_UNBREAKABLE != 0)?;
        d.set_item("known", info.flags & state::SF_KNOWN != 0)?;
        d.set_item("solid", info.flags & state::SF_SOLID != 0)?;
        d.set_item("signal_source", self.w.is_signal_source(info.kind))?;
        d.set_item("has_block_entity", self.w.has_block_entity(info.kind))?;
        d.set_item("analog_output", self.w.has_analog_output_signal(info.kind))?;
        d.set_item("needs_model", self.w.st.needs_model(info.name))?;
        Ok(d)
    }
}

/// Load the block table and the item stack sizes (JSON texts). Must be called once before creating a World.
#[pyfunction]
fn init(blocks_json: &str, stack_sizes_json: &str) -> PyResult<()> {
    data::init(blocks_json, stack_sizes_json).map_err(PyValueError::new_err)
}

#[pyfunction]
fn is_initialized() -> bool {
    data::is_initialized()
}

/// wire.update_order(pos): the order in which dust that changed power updates its neighbours.
#[pyfunction]
fn update_order(p: P3) -> Vec<P3> {
    wire::update_order(pos(p)).iter().map(|p| (p.x, p.y, p.z)).collect()
}

/// Vec3i#hashCode
#[pyfunction]
fn block_pos_hash(p: P3) -> i32 {
    pos(p).java_hash()
}

#[pyfunction]
fn item_max_stack_size(item: &str) -> i32 {
    data::item_max_stack_size(item)
}

#[pymodule]
fn rsx_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<World>()?;
    m.add_function(wrap_pyfunction!(init, m)?)?;
    m.add_function(wrap_pyfunction!(is_initialized, m)?)?;
    m.add_function(wrap_pyfunction!(update_order, m)?)?;
    m.add_function(wrap_pyfunction!(block_pos_hash, m)?)?;
    m.add_function(wrap_pyfunction!(item_max_stack_size, m)?)?;
    m.add("NOTE_KINDS", world::NOTE_KINDS.to_vec())?;
    m.add("API_VERSION", 1)?;
    Ok(())
}
