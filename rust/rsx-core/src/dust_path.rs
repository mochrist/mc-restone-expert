//! Line search of the compaction (`redstone.design.compact._dust_path`), moved here because relocating a
//! building block lays its lines anew for every placement (70 % of the mux8 search). Same checks, same
//! visiting order and so the same path as the Python version, which stays the reference (and the fallback
//! without this core).

use rustc_hash::FxHashMap;
use std::collections::VecDeque;

pub type P3 = (i32, i32, i32);

/// What occupies a cell (`compact._plain`: a block that only carries or supports).
pub const PLAIN: u8 = 1;
pub const WIRE: u8 = 2;
pub const OTHER: u8 = 3;

/// `compact._FLAT`.
const FLAT: [P3; 4] = [(1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)];

#[inline]
fn add(a: P3, b: P3) -> P3 {
    (a.0 + b.0, a.1 + b.1, a.2 + b.2)
}

#[inline]
fn joined(c: P3, d: P3) -> bool {
    (c.0 - d.0).abs() + (c.2 - d.2).abs() == 1 && (c.1 - d.1).abs() <= 1
}

struct Search<'a> {
    states: &'a FxHashMap<P3, u8>,
    lo: P3,
    hi: P3,
}

impl Search<'_> {
    #[inline]
    fn get(&self, p: P3) -> Option<u8> {
        self.states.get(&p).copied()
    }

    #[inline]
    fn unplain(&self, p: P3) -> bool {
        matches!(self.get(p), Some(k) if k != PLAIN)
    }

    /// `ok` in `_dust_path`.
    fn ok(&self, c: P3, ends: &[P3]) -> bool {
        let (lo, hi) = (self.lo, self.hi);
        if !(lo.0 <= c.0 && c.0 <= hi.0 && lo.1 <= c.1 && c.1 <= hi.1 && lo.2 <= c.2 && c.2 <= hi.2) {
            return false;
        }
        if self.states.contains_key(&c) || self.states.contains_key(&add(c, (0, 1, 0))) {
            return false;
        }
        let f = add(c, (0, -1, 0));
        let floor = self.get(f);
        if matches!(floor, Some(k) if k != PLAIN) {
            return false;
        }
        for d in FLAT {
            let q = add(c, d);
            if ends.contains(&q) {
                continue;
            }
            if self.unplain(q) {
                return false;
            }
            for dy in [1, -1] {
                let r = (q.0, q.1 + dy, q.2);
                if self.get(r) == Some(WIRE) && !ends.contains(&r) {
                    return false;
                }
            }
            if ends.is_empty() && floor.is_none() && self.unplain(add(f, d)) {
                return false;
            }
        }
        if ends.is_empty() && floor.is_none() && self.unplain(add(f, (0, -1, 0))) {
            return false;
        }
        true
    }
}

/// `compact._clashes`.
fn clashes(q: P3, c: P3, prev: &FxHashMap<P3, Option<P3>>, ends: &[P3]) -> bool {
    for e in ends {
        if e.0 == q.0 && e.2 == q.2 && (e.1 - q.1).abs() <= 2 {
            return true;
        }
    }
    let mut p = Some(c);
    while let Some(x) = p {
        if x.0 == q.0 && x.2 == q.2 && (x.1 - q.1).abs() <= 2 {
            return true;
        }
        if x != c && joined(x, q) {
            return true;
        }
        p = prev.get(&x).copied().flatten();
    }
    false
}

/// `compact._dust_path`: shortest dust path from `start` to `goal` (both included) of at most `limit` cells
/// inside the box `lo`..`hi`, or None.
#[allow(clippy::too_many_arguments)]
pub fn dust_path(states: &FxHashMap<P3, u8>, start: P3, goal: P3, a: P3, b: P3, limit: i64, lo: P3,
                 hi: P3) -> Option<Vec<P3>> {
    let s = Search { states, lo, hi };
    if start == goal {
        return if s.ok(start, &[a, b]) { Some(vec![start]) } else { None };
    }
    if ((start.0 - goal.0).abs() + (start.2 - goal.2).abs()) as i64 >= limit {
        return None;
    }
    if !s.ok(start, &[a]) || !s.ok(goal, &[b]) {
        return None;
    }
    let ends = [a, b];
    let mut prev: FxHashMap<P3, Option<P3>> = FxHashMap::default();
    prev.insert(start, None);
    let mut queue: VecDeque<(P3, i64)> = VecDeque::new();
    queue.push_back((start, 1));
    let mut steps: Vec<P3> = Vec::with_capacity(3);
    while let Some((c, n)) = queue.pop_front() {
        if n >= limit {
            continue;
        }
        for d in FLAT {
            let h = add(c, d);
            steps.clear();
            steps.push(h);
            steps.push(add(h, (0, 1, 0)));
            if !states.contains_key(&h) {
                steps.push(add(h, (0, -1, 0)));
            }
            for &q in &steps {
                if prev.contains_key(&q) {
                    continue;
                }
                if q == goal && !clashes(q, c, &prev, &ends) {
                    let mut path = vec![q, c];
                    while let Some(Some(p)) = prev.get(path.last().unwrap()) {
                        path.push(*p);
                    }
                    path.reverse();
                    return Some(path);
                }
                if s.ok(q, &[]) && !clashes(q, c, &prev, &ends) {
                    prev.insert(q, Some(c));
                    queue.push_back((q, n + 1));
                }
            }
        }
    }
    None
}
