"""Explanations in everyday German for people who are not Redstone experts (rule based, no model call).

`plain_design(spec, evaluation)` describes a designed circuit, `plain_analysis(analysis)` an analysed one.
Both return short Markdown with four sections: what it does, how to operate it, size and material, good to know.
Technical words (comparator, PLA, decomposition, game ticks ...) stay out of the text; times are in seconds.
"""

from __future__ import annotations

import itertools
import re

GT_PER_SECOND = 20  # one game tick (gt) is 0.05 s


def seconds(gt: int | float) -> str:
    """'0,5 Sekunden' for 10 gt."""
    s = round(gt / GT_PER_SECOND, 2)
    text = f"{s:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text} Sekunde" if text == "1" else f"{text} Sekunden"


def _names(names: list[str]) -> str:
    q = [f"„{n}“" for n in names]
    return q[0] if len(q) == 1 else ", ".join(q[:-1]) + " und " + q[-1]


# ---------------------------------------------------------------------- logic functions
def _function_sentence(inputs: list[str], col: dict[tuple[bool, ...], bool], verb: str) -> str | None:
    """A sentence fragment for a recognised function ("… wenn a und b an sind"), None if there is no short form.
    `verb` is e.g. 'leuchtet'. Only for complete tables."""
    n = len(inputs)
    combos = list(itertools.product([False, True], repeat=n))
    if set(col) != set(combos):
        return None
    ones = {c for c in combos if col[c]}
    if not ones:
        return f"{verb} nie"
    if len(ones) == len(combos):
        return f"{verb} immer"
    q = _names(inputs)
    if n == 1:
        return f"{verb}, wenn {q} an ist" if (True,) in ones else f"{verb}, wenn {q} aus ist"
    if ones == {tuple([True] * n)}:
        return f"{verb}, wenn {q} alle an sind" if n > 2 else f"{verb}, wenn {q} an sind"
    if ones == set(combos) - {tuple([True] * n)}:
        return f"{verb}, solange nicht alle Schalter ({q}) an sind"
    if ones == {tuple([False] * n)}:
        return f"{verb}, wenn alle Schalter ({q}) aus sind"
    if ones == set(combos) - {tuple([False] * n)}:
        return f"{verb}, sobald mindestens einer der Schalter ({q}) an ist"
    if all(col[c] == (sum(c) % 2 == 1) for c in combos):
        return (f"{verb}, wenn genau einer von {q} an ist" if n == 2
                else f"{verb}, wenn eine ungerade Anzahl der Schalter ({q}) an ist")
    if n == 2 and all(col[c] == (c[0] == c[1]) for c in combos):
        return f"{verb}, wenn {q} gleich stehen (beide an oder beide aus)"
    return None


def _case_text(inputs: list[str], combo: tuple[bool, ...]) -> str:
    return ", ".join(f"{n} {'an' if b else 'aus'}" for n, b in zip(inputs, combo))


def _function_lines(inputs: list[str], out_name: str, col: dict[tuple[bool, ...], bool], verb: str,
                    complete: bool) -> list[str]:
    """Bullet lines for one output of a truth table."""
    head = f"Die Anzeige „{out_name}“"
    sentence = _function_sentence(inputs, col, verb) if complete else None
    lines = []
    if sentence:
        lines.append(f"- {head} {sentence}.")
    if len(inputs) <= 3 and not (sentence and len(inputs) == 1):
        if sentence is None:
            lines.append(f"- {head}:")
        for combo in sorted(col):
            lines.append(f"  - {_case_text(inputs, combo)}: {'leuchtet' if col[combo] else 'aus'}"
                         if verb == "leuchtet" else
                         f"  - {_case_text(inputs, combo)}: {'an' if col[combo] else 'aus'}")
    elif sentence is None:
        on = sum(1 for v in col.values() if v)
        lines.append(f"- {head} ist in {on} von {len(col)} Schalterstellungen an. Die genaue Liste steht unten bei "
                     "den Details.")
    return lines


# ---------------------------------------------------------------------- behaviour in words
def _gate_words(expr: str) -> str:
    expr = re.sub(r"\band\b", "und", expr)
    expr = re.sub(r"\bor\b", "oder", expr)
    expr = re.sub(r"\bnot\b", "nicht", expr)
    return expr


def _behaviour_text(spec) -> list[str]:
    kind = getattr(spec, "kind", "") or ""
    out = _names(spec.outputs) if spec.outputs else "der Ausgang"
    if spec.gate and spec.inner is not None:
        inner = _behaviour_text(spec.inner)
        return [f"- Der Baustein reagiert nur auf die Bedingung: {_gate_words(spec.gate)}."] + inner
    m = re.search(r"(\d+)", kind)
    n = int(m.group(1)) if m else None
    if kind.startswith("Monoflop") and n is not None:
        return [f"- Sobald du den Auslöser einschaltest, gibt der Ausgang {out} einen einzigen kurzen Impuls von "
                f"{seconds(n)} ab. Wie lange du ihn gedrückt hältst, spielt keine Rolle."]
    if kind.startswith("Pulsverl") and n is not None:
        return [f"- Der Ausgang {out} bleibt mindestens {seconds(n)} an. Hältst du den Auslöser länger, bleibt er "
                "so lange an."]
    if kind.startswith("Verz") and n is not None:
        return [f"- Der Ausgang {out} folgt dem Auslöser, aber erst {seconds(n)} später."]
    if kind.startswith("T-Flip"):
        return [f"- Bei jedem Einschalten wechselt der Ausgang {out}: einmal betätigt ist er an, noch einmal "
                "betätigt wieder aus."]
    if kind.startswith("RS-Latch"):
        s = spec.inputs
        a, b = (s[0], s[1]) if len(s) > 1 else ("set", "reset")
        return [f"- Ein Speicher: Der Auslöser „{a}“ schaltet den Ausgang {out} an, er bleibt an, bis du "
                f"„{b}“ betätigst."]
    if kind.startswith("Clock") and len(re.findall(r"\d+", kind)) >= 2:
        period, on = (int(x) for x in re.findall(r"\d+", kind)[:2])
        return [f"- Der Ausgang {out} blinkt von selbst: alle {seconds(period)} geht er für {seconds(on)} an."]
    return ["- Die Schaltung zeigt dasselbe Zeitverhalten wie die ursprüngliche Schaltung (Pulse, Verzögerung, "
            "Speicher)."]


# ---------------------------------------------------------------------- common parts
def _input_kind_word(sid: str) -> str:
    if sid == "lever":
        return "Hebel"
    if sid.endswith("_button"):
        return "Knopf"
    if sid.endswith("_pressure_plate"):
        return "Druckplatte"
    if sid == "daylight_detector":
        return "Tageslichtsensor"
    return "Schalter"


def _input_lines(items: list[tuple[str, str]]) -> list[str]:
    """items: (name, block id)."""
    if not items:
        return ["- Es gibt nichts zu bedienen: Die Schaltung läuft von selbst."]
    lines = []
    for name, sid in items:
        word = _input_kind_word(sid)
        how = {"Hebel": "umlegen (an oder aus)", "Knopf": "kurz drücken",
               "Druckplatte": "betreten oder etwas darauflegen",
               "Tageslichtsensor": "schaltet von selbst nach der Tageszeit, braucht freien Himmel"}.get(word, "betätigen")
        lines.append(f"- {word} „{name}“: {how}.")
    return lines


def _size_lines(grid, size, block_count: int) -> list[str]:
    from ..gui.materials import materials

    x, y, z = size
    lines = [f"- Größe: {x} Blöcke breit (Ost–West), {y} hoch und {z} tief (Nord–Süd); insgesamt {block_count} Blöcke."]
    top = materials(grid)[:5]
    if top:
        lines.append("- Am meisten gebraucht: " + ", ".join(f"{m['count']}× {m['label']}" for m in top) + ".")
    return lines


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"## {title}", ""] + lines + [""]


# ---------------------------------------------------------------------- designs
def plain_design(spec, evaluation) -> str:
    """Everyday-German description of a designed circuit (`spec`: Spec or BehaviourSpec, `evaluation`: its Evaluation)."""
    cand = evaluation.candidate
    grid = cand.grid
    out_blocks = [grid.get(p).id if p is not None else "" for p in cand.outputs]
    lamp = bool(out_blocks) and all(b == "redstone_lamp" for b in out_blocks)
    verb = "leuchtet" if lamp else "ist an"

    if hasattr(spec, "trials"):
        what = _behaviour_text(spec)
    else:
        what = []
        for i, name in enumerate(spec.outputs):
            col = {c: spec.table[c][i] for c in spec.combos()}
            what += _function_lines(spec.inputs, name, col, verb, not spec.partial)
        if spec.partial:
            what.append("- Für alle anderen Schalterstellungen ist egal, was passiert.")
    ins = [(n, grid.get(p).id) for n, p in zip(spec.inputs, cand.inputs)]
    use = _input_lines(ins)
    shown = _names(spec.outputs) if spec.outputs else ""
    if shown:
        use.append(("- Das Ergebnis siehst du an der Lampe " if lamp else "- Das Ergebnis zeigt der Ausgang ")
                   + shown + ".")

    know = []
    delay = evaluation.max_delay
    relative = hasattr(spec, "trials") and getattr(spec, "nominal_delay", None) is None
    if delay is not None and not relative and delay > 0:
        know.append(f"- Nach dem Umlegen dauert es höchstens {seconds(delay)}, bis sich der Ausgang ändert.")
    if lamp and not hasattr(spec, "trials"):
        know.append("- Eine Redstone-Lampe geht erst etwa 0,2 Sekunden nach dem Signal aus.")
    mech = sorted(evaluation.mechanics - {"observer_pulse"})
    if mech:
        know.append("- Der Entwurf nutzt Eigenheiten des Spiels. Bau ihn genau nach Plan nach; er wurde im "
                    "Simulator geprüft.")
    if not evaluation.ok:
        reasons = evaluation.violations or evaluation.errors
        know.append("- Achtung: Dieser Entwurf erfüllt nicht alle Vorgaben" + (f" ({reasons[0]})." if reasons else "."))
    for w in cand.notes if hasattr(cand, "notes") else []:
        know.append(f"- {w}")
    if not know:
        know.append("- Nichts Besonderes: Bau ihn nach Plan nach und probiere ihn aus.")

    lines = []
    lines += _section("Was es tut", what)
    lines += _section("So bedienst du es", use)
    lines += _section("Größe und Material", _size_lines(grid, cand.size, cand.block_count))
    lines += _section("Gut zu wissen", know)
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------- analyses
_REACTIONS = (
    ("folgt dem Eingang", "geht an und aus wie der Schalter"),
    ("invertiert", "macht das Gegenteil des Schalters (Schalter an: aus, Schalter aus: an)"),
    ("T-Flip-Flop", "wechselt bei jedem Betätigen zwischen an und aus"),
    ("Pulsgenerator", "gibt bei jedem Betätigen nur einen kurzen Impuls ab"),
    ("Speicher", "geht an und bleibt an (merkt sich das Signal)"),
    ("Puls", "gibt einen kurzen Impuls ab"),
)


def _reaction_text(kind: str) -> str | None:
    if kind in ("keine Reaktion", ""):
        return None
    for key, text in _REACTIONS:
        if kind.startswith(key):
            return text
    return "reagiert unregelmäßig"


def plain_analysis(analysis) -> str:
    """Everyday-German description of an analysed circuit (`analysis.analyze.Analysis`)."""
    a = analysis
    grid = a.grid
    out_ids = {o.name: grid.get(o.pos).id for o in a.outputs}
    lamps = {n for n, b in out_ids.items() if b == "redstone_lamp"}
    what: list[str] = []
    if a.clock:
        what.append(f"- Die Schaltung blinkt von selbst: alle {seconds(a.clock.period)} ist der Ausgang für "
                    f"{seconds(a.clock.on_ticks)} an."
                    + (" Sie startet erst, wenn ein Block daneben verändert wird." if a.clock.needs_start else ""))
    elif a.oscillates:
        what.append("- Die Schaltung läuft ohne Eingabe immer weiter und wechselt dabei unregelmäßig.")
    gated = {b.output.name for b in a.gated}
    levers = [p for p in a.inputs if p.kind == "lever"]
    done: set[str] = set()
    if a.truth_table and len(levers) >= 2:
        names = [p.name for p in levers]
        for i, o in enumerate(a.outputs):
            if o.name in gated:
                continue
            col = {c: outs[i] for c, outs in a.truth_table}
            if len(set(col.values())) < 2 or not _depends_on_two(col):
                continue
            what += _function_lines(names, o.name, col, "leuchtet" if o.name in lamps else "ist an", True)
            done.add(o.name)
    for r in a.responses:
        for x in r.reactions:
            text = _reaction_text(x.kind)
            if text and x.output.name not in done:
                what.append(f"- Wenn du „{r.input.name}“ betätigst, {text.replace('Schalter', 'Auslöser')}: "
                            f"Ausgang „{x.output.name}“.")
    for b in a.gated:
        what.append(f"- Ausgang „{b.output.name}“ reagiert nur, wenn eine Bedingung der Schalter erfüllt ist "
                    f"({_gate_words(b.gate)}).")
    if not what:
        what.append("- An den gefundenen Ausgängen ändert sich bei den Versuchen nichts.")

    ins = [(p.name, grid.get(p.pos).id) for p in a.inputs]
    use = _input_lines(ins)
    if a.outputs:
        use.append("- Das Ergebnis siehst du an: " + _names([o.name for o in a.outputs]) + ".")

    know = []
    delays = [d for r in a.responses for x in r.reactions for d in x.delays if d is not None]
    if delays:
        know.append(f"- Der Ausgang reagiert nach etwa {seconds(min(delays))} bis {seconds(max(delays))}."
                    if min(delays) != max(delays) else f"- Der Ausgang reagiert nach etwa {seconds(delays[0])}.")
    know += [f"- {w}" for w in dict.fromkeys(a.warnings)]
    if not know:
        know.append("- Nichts Besonderes: Die Schaltung wurde im Simulator durchprobiert.")

    lines = []
    lines += _section("Was es tut", what)
    lines += _section("So bedienst du es", use)
    lines += _section("Größe und Material", _size_lines(grid, tuple(grid.size), len(grid)))
    lines += _section("Gut zu wissen", know)
    return "\n".join(lines).rstrip() + "\n"


def _depends_on_two(col: dict[tuple[bool, ...], bool]) -> bool:
    n = len(next(iter(col)))
    used = 0
    for k in range(n):
        if any(col[c] != col[c[:k] + (not c[k],) + c[k + 1:]] for c in col):
            used += 1
    return used >= 2
