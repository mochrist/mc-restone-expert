"""Generate candidates for a spec, evaluate them and rank them.

Stage 1 (now): templates of known compact gates, matched to the spec up to a permutation of inputs and
outputs. Every candidate is checked in the simulator; nothing is reported as working that was not simulated.
Later stages (docs/m4-search-and-performance.md): composition of templates, local search, SAT topology.
"""

from __future__ import annotations

import itertools
from dataclasses import replace

from ..analysis.analyze import Analysis
from .candidate import Candidate
from .evaluate import Constraints, Evaluation, evaluate
from .spec import Spec, from_functions

MAX_PERMUTED_INPUTS = 4


def _template_table(template) -> Spec:
    return from_functions(list(template.inputs), dict(template.function))


def _matches(spec: Spec, tspec: Spec) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """All (input perm, output perm) with spec(x)[j] == template(x permuted)[out_perm[j]].

    in_perm[i] is the template input that spec input i is wired to."""
    n, m = len(spec.inputs), len(spec.outputs)
    if len(tspec.inputs) != n or len(tspec.outputs) != m or n > MAX_PERMUTED_INPUTS:
        return []
    found = []
    for in_perm in itertools.permutations(range(n)):
        for out_perm in itertools.permutations(range(m)):
            ok = True
            for combo, outs in spec.table.items():
                tcombo = [False] * n
                for i, b in enumerate(combo):
                    tcombo[in_perm[i]] = b
                touts = tspec.table[tuple(tcombo)]
                if any(outs[j] != touts[out_perm[j]] for j in range(m)):
                    ok = False
                    break
            if ok:
                found.append((in_perm, out_perm))
    return found


def template_candidates(spec: Spec, templates: list | None = None) -> list[Candidate]:
    if templates is None:
        from .templates import TEMPLATES as templates

    out = []
    for t in templates:
        matches = _matches(spec, _template_table(t))
        if not matches:
            continue
        in_perm, out_perm = matches[0]  # one wiring per template is enough; the layout is the same
        base = t.build()
        wiring = ", ".join(f"{s}→{t.inputs[in_perm[i]]}" for i, s in enumerate(spec.inputs))
        out.append(replace(
            base,
            inputs=[base.inputs[in_perm[i]] for i in range(len(spec.inputs))],
            outputs=[base.outputs[out_perm[j]] for j in range(len(spec.outputs))],
            tags=set(base.tags) | set(t.tags),
            description=base.description or t.description,
            origin=f"template:{t.name} ({wiring})" if len(spec.inputs) > 1 else f"template:{t.name}",
        ))
    return out


def original_candidate(analysis: Analysis, title: str = "Original") -> Candidate:
    levers = [p for p in analysis.inputs if p.kind == "lever"]
    return Candidate(title, analysis.grid, [p.pos for p in levers], [o.pos for o in analysis.outputs],
                     description="die analysierte Bestandsschaltung", origin="original")


def redesign(spec: Spec, constraints: Constraints | None = None,
             extra: list[Candidate] | None = None, templates: list | None = None,
             compact_budget: int = 0, log: list[str] | None = None) -> list[Evaluation]:
    """Evaluate all candidates (templates + extra) and return them best first.

    With compact_budget > 0 every correct extra candidate (e.g. the original) is also compacted with at
    most that many evaluations; the steps are appended to `log`."""
    from .compact import compact

    constraints = constraints or Constraints()
    candidates = template_candidates(spec, templates) + list(extra or [])
    results = []
    for cand in candidates:
        quick = evaluate(cand, spec, constraints, full=False, stop_early=True)
        results.append(evaluate(cand, spec, constraints) if quick.correct else quick)
    if compact_budget:
        for cand in extra or []:
            # constraints other than function and delay are checked on the result, not during shrinking
            small, steps = compact(cand, spec, Constraints(max_delay=constraints.max_delay), compact_budget)
            if log is not None:
                log.extend(f"{cand.name}: {s}" for s in steps)
            if small.grid is not cand.grid:
                results.append(evaluate(small, spec, constraints))
    results.sort(key=Evaluation.rank_key)
    return results
