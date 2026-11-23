//! Repeater planning of the torch PLA (`redstone.design.synth._plan_line`), moved here because the synthesis
//! calls it hundreds of thousands of times (77 % of the 4-bit adder search). Same greedy steps, so the same
//! repeaters as the Python version, which stays the reference (and the fallback without this core).

/// Marks a repeater cell that is powered (`synth._REP`).
const REP: i32 = 99;

/// `synth._simulate`: power of each cell (dust) with a single source injecting `strength` at cell `source`.
/// Cells before the source stay 0 (a repeater there is unpowered: -1), as in the Python version.
fn simulate(vals: &mut Vec<i32>, length: usize, source: i64, strength: i32, reps: &[bool]) {
    vals.clear();
    for i in 0..length {
        let prev = if i > 0 { vals[i - 1] } else { 0 };
        if reps[i] {
            vals.push(if prev == REP || prev >= 1 { REP } else { -1 });
            continue;
        }
        let inc = if prev == REP { 15 } else { (prev - 1).max(0) };
        let i = i as i64;
        vals.push(if i >= source { (if i == source { strength } else { 0 }).max(inc) } else { 0 });
    }
}

struct Line<'a> {
    length: usize,
    sources: &'a [(i64, i32)],
    need: &'a [i64],
    reps: Vec<bool>,
    vals: Vec<i32>,
}

impl Line<'_> {
    /// `ok` in `_plan_line`: every source alone powers every needed cell in [source, upto) without an
    /// unpowered repeater there, and (check_end) the cell before `upto`.
    fn ok(&mut self, upto: i64, check_end: bool) -> bool {
        for &(s, st) in self.sources {
            if s >= upto {
                continue;
            }
            simulate(&mut self.vals, self.length, s, st, &self.reps);
            let vals = &self.vals;
            let at = |i: i64| vals[i as usize];
            if (s.max(0)..upto).any(|i| at(i) == -1) {
                return false;
            }
            if self.need.iter().any(|&i| s <= i && i < upto && i >= 0 && at(i) < 1) {
                return false;
            }
            if check_end && at(upto - 1) != REP && at(upto - 1) < 1 {
                return false;
            }
        }
        true
    }
}

/// `synth._plan_line`: repeater cells for a line of `length` cells, or None. Greedy, each repeater as late as
/// possible. The result is sorted (the Python version returns a set).
pub fn plan_line(length: usize, sources: &[(i64, i32)], need: &[i64], allowed: &[i64]) -> Option<Vec<i64>> {
    let mut cand: Vec<i64> = allowed.iter().copied().filter(|&i| 0 < i && i < length as i64).collect();
    cand.sort_unstable();
    cand.dedup();
    let mut line = Line { length, sources, need, reps: vec![false; length], vals: Vec::with_capacity(length) };
    for k in 0..cand.len() {
        let a = cand[k];
        match cand.get(k + 1) {
            None => {
                if line.ok(length as i64, false) {
                    break;
                }
            }
            Some(&nxt) => {
                if line.ok(nxt, true) {
                    continue;
                }
            }
        }
        if !line.ok(a, true) {
            return None;
        }
        line.reps[a as usize] = true;
    }
    if !line.ok(length as i64, false) {
        return None;
    }
    Some((0..length as i64).filter(|&i| line.reps[i as usize]).collect())
}
