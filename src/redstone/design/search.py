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
from .evaluate import Constraints, Evaluation, evaluate_any
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


def seq_candidates(spec, templates: list | None = None) -> list[Candidate]:
    """All variants of the timing/memory templates whose ports fit the spec (inputs permuted).

    Which variant really fits is decided by simulation only, so a template is tried even when its
    behaviour name differs (e.g. a monostable may meet a recorded spec)."""
    if templates is None:
        try:
            from .seq_templates import SEQ_TEMPLATES as templates
        except ImportError:  # library not available
            templates = []
    out = []
    for t in templates:
        if len(t.inputs) != len(spec.inputs) or len(t.outputs) != len(spec.outputs):
            continue
        for perm in itertools.permutations(range(len(spec.inputs))):
            if any(t.input_kinds[perm[i]] != k for i, k in enumerate(spec.input_kinds)):
                continue
            for params, base in t.variants():
                label = ", ".join(f"{k}={v}" for k, v in params.items() if k != "kind")
                out.append(replace(
                    base, name=f"{t.name}" + (f" ({label})" if label else ""),
                    inputs=[base.inputs[perm[i]] for i in range(len(spec.inputs))],
                    tags=set(base.tags) | set(t.tags), description=base.description or t.description,
                    origin=f"vorlage:{t.name}"))
            break  # one wiring per template
    return out


COMPOSE_LOGIC = 3  # best logic candidates tried in front of a building block
COMPOSE_BLOCKS = 4  # best building blocks tried behind the logic
COMPOSE_TRIES = 16  # layouts tried per pair before giving up


def compose_candidates(spec, constraints: Constraints | None = None, log: list[str] | None = None) -> list[Candidate]:
    """Candidates for a gated behaviour spec (`behaviour.gated`): a logic template or PLA for the gate in
    front of a timing/memory template for the inner spec, joined by `compose.chains`.

    Both parts are checked on their own first, so only working parts are combined; per pair the first
    layout that meets the whole spec is kept."""
    from .compose import chains
    from .report import COMPOSE_PREFIX
    from .synth import pla

    gate_spec = from_functions(list(spec.inputs), {"y": spec.gate})
    logic = template_candidates(gate_spec)
    synthesized = pla(gate_spec, name="pla-gate")
    if synthesized is not None:
        logic.append(synthesized)
    good_logic = [e for e in (evaluate_any(c, gate_spec) for c in logic) if e.correct]
    good_logic.sort(key=Evaluation.rank_key)
    blocks = [e for e in (evaluate_any(c, spec.inner) for c in seq_candidates(spec.inner)) if e.correct]
    blocks.sort(key=Evaluation.rank_key)
    out = []
    for le in good_logic[:COMPOSE_LOGIC]:
        for be in blocks[:COMPOSE_BLOCKS]:
            found = False
            for k, (_, cand) in enumerate(chains(le.candidate, 0, be.candidate, 0)):
                if k >= COMPOSE_TRIES:
                    break
                if evaluate_any(cand, spec, constraints, quick=True).correct:
                    out.append(cand)
                    found = True
                    break
            if log is not None:
                log.append(f"{COMPOSE_PREFIX}{le.candidate.name} → {be.candidate.name}: "
                           + ("verbunden" if found else "keine funktionierende Verbindung gefunden"))
    return out


def original_candidate(analysis: Analysis, title: str = "Original") -> Candidate:
    levers = [p for p in analysis.inputs if p.kind == "lever"]
    return Candidate(title, analysis.grid, [p.pos for p in levers], [o.pos for o in analysis.outputs],
                     description="die analysierte Bestandsschaltung", origin="original")


def redesign(spec: Spec, constraints: Constraints | None = None,
             extra: list[Candidate] | None = None, templates: list | None = None,
             compact_budget: int = 0, log: list[str] | None = None, synthesize: bool = True,
             time_limit: float | None = None) -> list[Evaluation]:
    """Evaluate all candidates and return them best first.

    Sources: templates (matched up to permutation), the generic torch PLA (`synth.pla`) and `extra`
    (e.g. the original). With compact_budget > 0 the PLA and every extra candidate are also compacted, with
    at most that many evaluations each and `time_limit` seconds in total; the steps go to `log`."""
    import time

    from .compact import compact
    from .synth import pla

    from .behaviour import BehaviourSpec

    constraints = constraints or Constraints()
    if isinstance(spec, BehaviourSpec):
        synthesized = None
        if spec.gate is not None:
            generated = compose_candidates(spec, constraints, log)
        else:
            generated = seq_candidates(spec, templates)
    else:
        synthesized = pla(spec) if synthesize else None
        generated = template_candidates(spec, templates)
    to_compact = ([synthesized] if synthesized is not None else []) + list(extra or [])
    candidates = generated + to_compact
    results = []
    for cand in candidates:
        quick = evaluate_any(cand, spec, constraints, quick=True)
        results.append(evaluate_any(cand, spec, constraints) if quick.correct else quick)
    if compact_budget:
        deadline = None if time_limit is None else time.perf_counter() + time_limit
        for cand in to_compact:
            left = None if deadline is None else deadline - time.perf_counter()
            if left is not None and left <= 0:
                if log is not None:
                    log.append(f"{cand.name}: nicht kompaktiert (Zeitlimit)")
                continue
            # constraints other than function and delay are checked on the result, not during shrinking
            small, steps = compact(cand, spec, Constraints(max_delay=constraints.max_delay), compact_budget, left)
            if log is not None:
                log.extend(f"{cand.name}: {s}" for s in steps)
            if small.grid is not cand.grid:
                results.append(evaluate_any(small, spec, constraints))
    results.sort(key=Evaluation.rank_key)
    return results
