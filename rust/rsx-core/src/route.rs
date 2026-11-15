//! Breadth-first dust router of the design search (`redstone.design.compose._route`), moved here because the
//! searches call it tens of thousands of times. Same moves, same visiting order and so the same path as the
//! Python version, which stays the reference (and the fallback without this core).

use rustc_hash::FxHashSet;
use std::collections::VecDeque;

pub type P3 = (i32, i32, i32);

/// Horizontal steps in the order of `compose.HORIZONTAL`: east, south, west, north.
const HORIZONTAL: [P3; 4] = [(1, 0, 0), (0, 0, 1), (-1, 0, 0), (0, 0, -1)];
const FACES: [P3; 6] = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)];

#[inline]
fn add(a: P3, b: P3) -> P3 {
    (a.0 + b.0, a.1 + b.1, a.2 + b.2)
}

/// Dense flags over the search box grown by one block on every side (every lookup of the search falls in
/// it, except around a start outside the box); positions outside are looked up in `outside`.
struct Field {
    lo: P3,
    dims: (i32, i32, i32),
}

impl Field {
    fn index(&self, p: P3) -> Option<usize> {
        let (x, y, z) = (p.0 - self.lo.0, p.1 - self.lo.1, p.2 - self.lo.2);
        if x < 0 || y < 0 || z < 0 || x >= self.dims.0 || y >= self.dims.1 || z >= self.dims.2 {
            return None;
        }
        Some(((x * self.dims.1 + y) * self.dims.2 + z) as usize)
    }

    fn len(&self) -> usize {
        (self.dims.0 * self.dims.1 * self.dims.2) as usize
    }
}

struct Set<'a> {
    field: &'a Field,
    flags: Vec<bool>,
    outside: FxHashSet<P3>,
}

impl<'a> Set<'a> {
    fn new(field: &'a Field) -> Self {
        Set { field, flags: vec![false; field.len()], outside: FxHashSet::default() }
    }

    fn insert(&mut self, p: P3) {
        match self.field.index(p) {
            Some(i) => self.flags[i] = true,
            None => {
                self.outside.insert(p);
            }
        }
    }

    #[inline]
    fn contains(&self, p: P3) -> bool {
        match self.field.index(p) {
            Some(i) => self.flags[i],
            None => self.outside.contains(&p),
        }
    }
}

/// See `compose._over_itself`: n one or two blocks straight above or below c (in `slot`, START for the
/// start) or one of its ancestors, the start included.
fn over_itself(n: P3, c: P3, slot: u32, start: P3, cells: &[P3], prev: &[u32], field: &Field) -> bool {
    const START: u32 = u32::MAX - 1;
    let (mut p, mut s) = (c, slot);
    loop {
        if p.0 == n.0 && p.2 == n.2 && (1..=2).contains(&(p.1 - n.1).abs()) {
            return true;
        }
        if s == START {
            return false;
        }
        let parent = prev[field.index(p).unwrap()];
        if parent == START {
            p = start;
        } else {
            p = cells[parent as usize];
        }
        s = parent;
    }
}

/// See `compose._route`: the cells of the shortest dust path from `start` to one of `goals`, or None.
#[allow(clippy::too_many_arguments)]
pub fn route(start: P3, goals: &[P3], solid: &[P3], keep_clear: &[P3], lo: P3, hi: P3, tight: bool) -> Option<Vec<P3>> {
    let field = Field { lo: add(lo, (-1, -1, -1)), dims: (hi.0 - lo.0 + 3, hi.1 - lo.1 + 3, hi.2 - lo.2 + 3) };
    if field.dims.0 <= 0 || field.dims.1 <= 0 || field.dims.2 <= 0 {
        return None;
    }
    let inside = |c: P3| lo.0 <= c.0 && c.0 <= hi.0 && lo.1 <= c.1 && c.1 <= hi.1 && lo.2 <= c.2 && c.2 <= hi.2;
    let mut goal = Set::new(&field);
    for &g in goals {
        goal.insert(g);
    }
    let mut solids = Set::new(&field);
    for &s in solid {
        solids.insert(s);
    }
    solids.insert(add(start, (0, -1, 0)));
    let mut near = Set::new(&field);
    let mut near_floor = Set::new(&field);
    for &k in keep_clear {
        if tight {
            // faces and dust one step up or down; the floor only must not touch from below or the sides
            for f in FACES {
                near.insert(add(k, f));
                if f != (0, 1, 0) {
                    near_floor.insert(add(k, f));
                }
            }
            for (dx, dz) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
                near.insert(add(k, (dx, 1, dz)));
                near.insert(add(k, (dx, -1, dz)));
            }
        } else {
            for dx in -1..=1 {
                for dy in -1..=1 {
                    for dz in -1..=1 {
                        near.insert(add(k, (dx, dy, dz)));
                        near_floor.insert(add(k, (dx, dy, dz)));
                    }
                }
            }
        }
    }
    let ok = |c: P3| -> bool {
        let below = add(c, (0, -1, 0));
        if !inside(c) || solids.contains(c) || solids.contains(below) {
            return false;
        }
        goal.contains(c) || !(near.contains(c) || near_floor.contains(below))
    };

    // parent of each reached cell inside the field; START marks the start itself as parent
    const UNSEEN: u32 = u32::MAX;
    const START: u32 = u32::MAX - 1;
    let mut prev = vec![UNSEEN; field.len()];
    let mut cells: Vec<P3> = Vec::new(); // reached cells, the queue indexes into it
    let seen = |prev: &Vec<u32>, p: P3| -> bool {
        p == start || field.index(p).is_some_and(|i| prev[i] != UNSEEN)
    };
    let mut queue: VecDeque<(P3, u32)> = VecDeque::new(); // cell, its slot in `cells` (START for the start)
    queue.push_back((start, START));
    while let Some((c, slot)) = queue.pop_front() {
        if goal.contains(c) {
            let mut path = vec![c];
            let mut s = slot;
            while s != START {
                let p = cells[s as usize];
                let parent = prev[field.index(p).unwrap()];
                if parent == START {
                    break;
                }
                path.push(cells[parent as usize]);
                s = parent;
            }
            if c != start {
                path.push(start);
            }
            path.reverse();
            return Some(path);
        }
        for d in HORIZONTAL {
            let h = add(c, d);
            let mut steps = [h, h, h];
            let mut n_steps = 1;
            if c != start || tight {
                if !solids.contains(add(c, (0, 1, 0))) {
                    steps[n_steps] = add(h, (0, 1, 0));
                    n_steps += 1;
                }
                if !solids.contains(h) {
                    steps[n_steps] = add(h, (0, -1, 0));
                    n_steps += 1;
                }
            }
            for &n in &steps[..n_steps] {
                if seen(&prev, n) || (n.1 != c.1 && goal.contains(n)) {
                    continue;
                }
                if ok(n) && !over_itself(n, c, slot, start, &cells, &prev, &field) {
                    // ok(n) implies n inside the box, so it has a field index
                    let i = field.index(n).unwrap();
                    prev[i] = slot;
                    cells.push(n);
                    queue.push_back((n, (cells.len() - 1) as u32));
                }
            }
        }
    }
    None
}
