"""Generate candidates for a spec, evaluate them and rank them.

Stage 1 (now): templates of known compact gates, matched to the spec up to a permutation of inputs and
outputs. Every candidate is checked in the simulator; nothing is reported as working that was not simulated.
Later stages (docs/m4-search-and-performance.md): composition of templates, local search, SAT topology.
"""

from __future__ import annotations

import itertools
from dataclasses import replace

from ..analysis.analyze import Analysis
from . import observe
from .candidate import Candidate
from .evaluate import Constraints, Evaluation, evaluate_any
from .report import COMPOSE_PREFIX
from .spec import Spec, from_functions
from .observe import check

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
        check()  # a cancelled search stops here (observe.cancelling)
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


def template_candidates(spec: Spec, templates: list | None = None, first_inputs: bool = False) -> list[Candidate]:
    """Templates that compute the spec, one wiring each; with first_inputs one wiring per template input
    that can take the spec's first input (a composition drives that input, and not every template input
    can be driven)."""
    if templates is None:
        from .templates import TEMPLATES

        # "part" templates only where a decomposition asks for them by name (`decompose._shannon`)
        templates = [t for t in TEMPLATES if "part" not in t.tags]

    out = []
    for t in templates:
        matches = _matches(spec, _template_table(t))
        if not matches:
            continue
        if first_inputs:
            firsts = {}
            for m in matches:
                firsts.setdefault(m[0][0], m)
            chosen = list(firsts.values())
        else:
            chosen = matches[:1]  # one wiring per template is enough; the layout is the same
        for in_perm, out_perm in chosen:
            out.append(_wired(t, spec, in_perm, out_perm))
    return out


def _wired(t, spec: Spec, in_perm, out_perm) -> Candidate:
    base = t.build()
    wiring = ", ".join(f"{s}→{t.inputs[in_perm[i]]}" for i, s in enumerate(spec.inputs))
    return replace(
        base,
        inputs=[base.inputs[in_perm[i]] for i in range(len(spec.inputs))],
        outputs=[base.outputs[out_perm[j]] for j in range(len(spec.outputs))],
        tags=set(base.tags) | set(t.tags),
        description=base.description or t.description,
        origin=f"template:{t.name} ({wiring})" if len(spec.inputs) > 1 else f"template:{t.name}",
    )


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
            check()  # a cancelled search stops here (observe.cancelling)
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
COMPACT_COMPOSED = 2  # best working compositions that are compacted (with compact_budget > 0)
COMPACT_SKIP = 2  # generated designs more than this many times the volume of the best working one are not compacted


GUESS_INPUTS = 3  # gate functions are guessed for recorded specs with up to this many levers


def gate_expression(names: list[str], ones: list[tuple[bool, ...]]) -> str:
    """Minimal sum-of-products Python expression over `names` that is on exactly for `ones`."""
    from .synth import minimize

    terms = []
    for imp in minimize(len(names), ones):
        lits = [n if v else f"not {n}" for n, v in zip(names, imp) if v is not None]
        terms.append(" and ".join(lits) if lits else "True")
    return " or ".join(f"({t})" if " and " in t and len(terms) > 1 else t for t in terms)


def depends_on_all(table: dict[tuple[bool, ...], bool]) -> bool:
    """A complete truth table changes with every input somewhere (no input is ignored)."""
    n = len(next(iter(table)))
    return all(any(table[c] != table[c[:i] + (not c[i],) + c[i + 1:]] for c in table) for i in range(n))


def gate_functions(n: int):
    """Every gate function of n levers that is off when all levers are off and depends on all of them, as
    the list of combinations for which it is on (the candidates `gate_guesses` tries)."""
    combos = list(itertools.product([False, True], repeat=n))[1:]
    for bits in itertools.product([False, True], repeat=len(combos)):
        ones = [c for c, b in zip(combos, bits) if b]
        if ones and depends_on_all({c: (c in ones) for c in combos} | {(False,) * n: False}):
            yield ones


def _derived_inner(spec, gate: str):
    """The recorded trials as seen behind an ideal (zero-delay) gate: one lever 'in' that toggles whenever
    the gate value changes. Trials in which the gate never changes expect the block to stay idle."""
    from .behaviour import GATE_SLACK, BehaviourSpec, Trial
    from .spec import evaluate_expression

    trials = []
    for t in spec.trials:
        state = dict.fromkeys(spec.inputs, False)
        value, actions = False, []
        for tick, group in itertools.groupby(sorted(t.actions), key=lambda a: a[0]):
            for _, i in group:  # levers switched in the same tick change the gate together
                state[spec.inputs[i]] = not state[spec.inputs[i]]
            now = evaluate_expression(gate, state)
            if now != value:
                actions.append((tick, 0))
                value = now
        trials.append(Trial(t.name, actions, t.expected, t.length, t.periodic))
    return BehaviourSpec(["in"], ["lever"], list(spec.outputs), trials, f"Baustein hinter {gate}",
                         spec.delay_tolerance + GATE_SLACK, spec.length_tolerance + 2)


def gate_guesses(spec, log: list[str] | None = None) -> list:
    """For a recorded behaviour spec with several levers and one output: every gate function g (off when all
    levers are off, depending on all levers) for which some timing/memory block, driven by g without delay,
    reproduces the recording. Returns gated specs (gate, inner = the derived one-lever spec) with the blocks
    that passed, as (spec, [Evaluation]). This is the cheap first stage; `compose_candidates` builds and
    checks the real layouts.

    The gates the analysis found (`spec.gate_hints`) come first; beyond GUESS_INPUTS levers only they are
    tried (there are 2^(2^n - 1) functions)."""
    from dataclasses import replace as dc_replace

    n = len(spec.inputs)
    hints = list(dict.fromkeys(spec.gate_hints))
    if (spec.gate is not None or n < 2 or (n > GUESS_INPUTS and not hints) or len(spec.outputs) != 1
            or any(k != "lever" for k in spec.input_kinds) or any(t.periodic for t in spec.trials)):
        return []
    gates = hints + ([g for g in (gate_expression(list(spec.inputs), ones) for ones in gate_functions(n))
                      if g not in hints] if n <= GUESS_INPUTS else [])
    blocks_all = None
    out = []
    for gate in gates:
        inner = _derived_inner(spec, gate)
        if blocks_all is None:
            blocks_all = seq_candidates(inner)
        passed = [e for e in (evaluate_any(c, inner) for c in blocks_all) if e.correct]
        if passed:
            passed.sort(key=Evaluation.rank_key)
            out.append((dc_replace(spec, gate=gate, inner=inner), passed))
            if log is not None:
                log.append(f"{COMPOSE_PREFIX}Vermutung {gate}: passt zu " + ", ".join(e.candidate.name for e in passed[:3]))
    return out


def compose_candidates(spec, constraints: Constraints | None = None, log: list[str] | None = None,
                       blocks: list | None = None) -> list[Candidate]:
    """Candidates for a gated behaviour spec (`behaviour.gated`): a logic template or PLA for the gate in
    front of a timing/memory template for the inner spec, joined by `compose.chains`.

    Both parts are checked on their own first, so only working parts are combined; per pair the first
    layout that meets the whole spec is kept."""
    from .compose import chains
    from .synth import pla

    gate_spec = from_functions(list(spec.inputs), {"y": spec.gate})
    logic = template_candidates(gate_spec)
    synthesized = pla(gate_spec, name="pla-gate")
    if synthesized is not None:
        logic.append(synthesized)
    good_logic = [e for e in (evaluate_any(c, gate_spec) for c in logic) if e.correct]
    good_logic.sort(key=Evaluation.rank_key)
    if blocks is None:
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
    (e.g. the original). With compact_budget > 0 the COMPACT_COMPOSED best working compositions, the PLA and
    every extra candidate are also compacted, with at most that many evaluations each and `time_limit` seconds
    in total; the steps go to `log`. Compositions and the PLA are skipped when they are more than COMPACT_SKIP
    times as large as the best working design found so far."""
    import time

    from .compact import compact
    from .synth import pla

    from .behaviour import BehaviourSpec

    constraints = constraints or Constraints()
    composed: list[Candidate] = []  # compositions and decompositions of smaller parts
    if isinstance(spec, BehaviourSpec):
        synthesized = None
        if spec.gate is not None:
            generated = composed = compose_candidates(spec, constraints, log)
        else:
            generated = seq_candidates(spec, templates)
            for gated_spec, blocks in gate_guesses(spec, log):
                composed += compose_candidates(gated_spec, constraints, log, blocks)
            generated += composed
    else:
        synthesized = pla(spec) if synthesize else None
        generated = template_candidates(spec, templates)
        if synthesize:
            from .decompose import decomposed, parallel, shared

            composed = decomposed(spec, log=log) + shared(spec, log=log) + parallel(spec, log=log)
            generated += composed
    to_compact = ([synthesized] if synthesized is not None else []) + list(extra or [])
    candidates = generated + to_compact
    results = []
    for cand in candidates:
        quick = evaluate_any(cand, spec, constraints, quick=True)
        results.append(evaluate_any(cand, spec, constraints) if quick.correct else quick)
        observe.frame(cand, "compose", cand.name, results[-1].ok)
    if compact_budget:
        # the best working compositions as well (first: they are built from parts with air and lines in between
        # and shrink the most); generated designs far larger than the best working one so far are skipped
        ids = {id(c) for c in composed}
        best = sorted((r for r in results if r.correct and id(r.candidate) in ids), key=Evaluation.rank_key)
        own = [r.candidate for r in best[:COMPACT_COMPOSED]] + to_compact[:1 if synthesized is not None else 0]
        to_compact = own + list(extra or [])
        smallest = min((r.candidate.volume for r in results if r.ok), default=None)
        deadline = None if time_limit is None else time.perf_counter() + time_limit
        for k, cand in enumerate(to_compact):
            left = None if deadline is None else deadline - time.perf_counter()
            if left is not None and left <= 0:
                if log is not None:
                    log.append(f"{cand.name}: nicht kompaktiert (Zeitlimit)")
                continue
            if k < len(own) and smallest is not None and cand.volume > COMPACT_SKIP * smallest:
                if log is not None:
                    log.append(f"{cand.name}: nicht kompaktiert (mehr als {COMPACT_SKIP}× so groß wie der beste Entwurf)")
                continue
            # constraints other than function and delay are checked on the result, not during shrinking
            small, steps = compact(cand, spec, Constraints(max_delay=constraints.max_delay), compact_budget, left)
            if log is not None:
                log.extend(f"{cand.name}: {s}" for s in steps)
            if small.grid is not cand.grid:
                ev = evaluate_any(small, spec, constraints)
                results.append(ev)
                if ev.ok:
                    smallest = min(smallest or ev.candidate.volume, ev.candidate.volume)
    results.sort(key=Evaluation.rank_key)
    return results
