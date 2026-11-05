"""German Markdown explanation of an analysis. Every statement comes from a simulation experiment."""

from __future__ import annotations

from collections import Counter

from ..model import BlockState, Pos
from ..sim.notes import MECHANICS
from ..versions import TARGET_VERSION
from .analyze import Analysis, InputResponse
from .experiment import Recording, is_on

MAX_DIAGRAM_TICKS = 160
MAX_CHAIN = 30


def _state_diff(old: str, new: str) -> str:
    o_state, _, o_extra = old.partition("|")
    n_state, _, n_extra = new.partition("|")
    o, n = BlockState.parse(o_state), BlockState.parse(n_state)
    if o.name != n.name:
        return f"{o.id} → {n.id}"
    parts = [f"{k}={o.get(k)}→{v}" for k, v in n.props if o.get(k) != v]
    if o_extra != n_extra:
        parts.append(f"{o_extra or '-'}→{n_extra or '-'}")
    return ", ".join(parts)


def _diagram(rec: Recording, rows: list[tuple[str, Pos]], marks: list[int]) -> str:
    ticks = min(rec.ticks, MAX_DIAGRAM_TICKS) + 1
    width = max(len(n) for n, _ in rows)
    lines = [" " * width + " " + "".join(str(t // 10 % 10) if t % 10 == 0 else " " for t in range(ticks)),
             " " * width + " " + "".join(str(t % 10) for t in range(ticks)),
             " " * width + " " + "".join("v" if t in marks else " " for t in range(ticks))]
    for name, pos in rows:
        if pos not in rec.series:
            continue
        lines.append(f"{name:>{width}} " + "".join("#" if is_on(rec.value_at(pos, t)) else "_" for t in range(ticks)))
    if rec.ticks + 1 > ticks:
        lines.append(f"(gekürzt auf {ticks} von {rec.ticks + 1} Ticks)")
    return "\n".join(lines)


def _response_section(a: Analysis, r: InputResponse) -> list[str]:
    out = [f"### {r.input.name}: {r.input.kind} bei {r.input.pos}", ""]
    if r.oscillates:
        out.append("Nach diesem Eingang kommt die Schaltung nicht mehr zur Ruhe (läuft dauerhaft).")
    reacting = [x for x in r.reactions if x.kind != "keine Reaktion"]
    if not reacting:
        out.append("Kein Ausgang reagiert auf diesen Eingang.")
    for x in reacting:
        out.append(f"- **{x.output.name}** ({x.output.kind} {x.output.pos}): {x.kind}. {x.detail}")
    out.append("")
    out.append("Ablauf: " + ", ".join(f"Tick {s.tick}: {s.label}" for s in r.steps) + " (jeweils nach Ruhe).")
    out += ["", "```", _diagram(r.recording, [(r.input.name, r.input.pos)] + [(o.name, o.pos) for o in a.outputs],
                               [s.tick for s in r.steps]), "```", ""]
    if r.chain:
        out.append(f"Signalweg nach „{r.steps[0].label}“ (erste Änderung jedes Blocks, Zeit relativ zum Schritt):")
        out.append("")
        for dt, pos, block, old, new in r.chain[:MAX_CHAIN]:
            out.append(f"- +{dt} gt: {block} {pos} ({_state_diff(old, new)})")
        if len(r.chain) > MAX_CHAIN:
            out.append(f"- … {len(r.chain) - MAX_CHAIN} weitere Blöcke")
        out.append("")
    return out


def explain(a: Analysis, title: str | None = None) -> str:
    grid = a.grid
    inventory = Counter(s.id for _, s in grid.items())
    redstone = {k: v for k, v in inventory.items() if k in _REDSTONE_IDS or k.endswith(("_button", "_pressure_plate"))}
    lines = [f"# Analyse: {title or grid.meta.name or 'Schaltung'}", ""]
    lines.append(f"Java Edition {TARGET_VERSION}. Größe {grid.size.x}×{grid.size.y}×{grid.size.z} (x×y×z), "
                 f"{len(grid)} Blöcke. Alle Aussagen stammen aus Simulationsläufen; der Simulator ist gegen das "
                 "echte Spiel validiert (Golden Traces).")
    lines.append("")
    if redstone:
        lines.append("Komponenten: " + ", ".join(f"{n}× {k}" for k, n in sorted(redstone.items(), key=lambda kv: -kv[1])))
        lines.append("")
    lines.append("Eingänge: " + (", ".join(str(p) for p in a.inputs) or "keine gefunden"))
    lines.append("")
    lines.append("Ausgänge: " + (", ".join(str(p) for p in a.outputs) or "keine gefunden"))
    lines.append("")

    lines += ["## Zusammenfassung", ""]
    summary = []
    if a.clock:
        start = "läuft erst nach einem Anstoß (Block-Update)" if a.clock.needs_start else "läuft von selbst"
        summary.append(f"- **Clock**: Periode {a.clock.period} gt, davon {a.clock.on_ticks} gt an, {start} "
                       f"(gemessen an {a.clock.observed_at}).")
        if a.clock.stops_at is not None:
            summary[-1] += f" Der regelmäßige Takt endet bei Tick {a.clock.stops_at}" + (
                " (Fackel-Burnout)." if any(n.kind == "torch_burnout" for n in a.notes) else ".")
    elif a.oscillates:
        summary.append("- **Schwingt ohne Eingabe**, aber nicht mit fester Periode"
                       + (" (Fackel-Burnout)." if any(n.kind == "torch_burnout" for n in a.notes) else "."))
    for r in a.responses:
        for x in r.reactions:
            if x.kind != "keine Reaktion":
                summary.append(f"- {r.input.name} → {x.output.name}: {x.kind}")
    multi = _multi_input_outputs(a)
    for name in multi:
        summary.append(f"- {name} hängt von mehreren Eingängen ab: **{a.gates[name]}**")
    lines += summary or ["- Keine Reaktion an den Ausgängen gefunden."]
    lines.append("")

    if a.patterns:
        lines += ["## Erkannte Bausteine", ""]
        lines += [f"- {p}" for p in a.patterns]
        lines.append("")

    if a.truth_table and multi:
        levers = [p for p in a.inputs if p.kind == "lever"]
        lines += ["## Wahrheitstabelle (Ruhezustände, jede Kombination frisch simuliert)", ""]
        lines.append("| " + " | ".join(p.name for p in levers) + " | " + " | ".join(o.name for o in a.outputs) + " |")
        lines.append("|" + "---|" * (len(levers) + len(a.outputs)))
        for combo, outs in a.truth_table:
            lines.append("| " + " | ".join("1" if c else "0" for c in combo) + " | "
                         + " | ".join("1" if o else "0" for o in outs) + " |")
        lines.append("")

    for group_levers, outs, table in a.partial_tables:
        lines += [f"## Teil-Wahrheitstabelle für {', '.join(o.name for o in outs)}", ""]
        lines.append("| " + " | ".join(p.name for p in group_levers) + " | " + " | ".join(o.name for o in outs) + " |")
        lines.append("|" + "---|" * (len(group_levers) + len(outs)))
        for combo, vals in table:
            lines.append("| " + " | ".join("1" if c else "0" for c in combo) + " | "
                         + " | ".join("1" if v else "0" for v in vals) + " |")
        lines.append("")

    lines += ["## Verhalten je Eingang", ""]
    for r in a.responses:
        lines += _response_section(a, r)

    pulses = [r for r in a.pulse_responses if r.kind not in ("keine Reaktion auf Pulse", "Ausgang ist im Ruhezustand an")]
    if pulses:
        lengths = sorted({L for r in pulses for L in r.table})
        lines += ["## Pulsantwort", "",
                  "Jeder Hebel wird in einer frischen Welt für L gt eingeschaltet. Die Tabelle zeigt die Länge des "
                  "Ausgangspulses (– = kein Puls, ∞ = bleibt an, mehrere Pulse durch / getrennt).", ""]
        lines.append("| Eingang → Ausgang | " + " | ".join(f"{L}" for L in lengths) + " | Einordnung |")
        lines.append("|---|" + "---|" * len(lengths) + "---|")
        for r in pulses:
            cells = []
            for L in lengths:
                iv = r.table.get(L, [])
                cells.append("/".join("∞" if n is None else str(n) for _, n in iv) or "–")
            kind = r.kind + (f" ({r.detail})" if r.detail else "")
            lines.append(f"| {r.input.name} → {r.output.name} | " + " | ".join(cells) + f" | {kind} |")
        lines.append("")

    kinds = sorted({n.kind for n in a.notes})
    lines += ["## Genutzte Sonderfälle", ""]
    if kinds:
        for k in kinds:
            where = sorted({str(n.pos - _origin(a)) for n in a.notes if n.kind == k})
            lines.append(f"- {MECHANICS[k]} (bei {', '.join(where[:6])}{' …' if len(where) > 6 else ''})")
    else:
        lines.append("- Keine der erfassten Sonderfälle wurde in den Experimenten genutzt.")
    lines.append("")

    lines += ["## Hinweise", ""]
    hints = list(dict.fromkeys(a.warnings))
    hints.append("Positionsabhängiges Verhalten (z. B. die Update-Reihenfolge von Redstone-Staub) wurde an der "
                 "Oracle-Position (Min-Ecke 0, 200, 0) simuliert. An anderer Stelle in der Welt kann es abweichen.")
    lines += [f"- {h}" for h in hints]
    return "\n".join(lines) + "\n"


def _origin(a: Analysis) -> Pos:
    from ..sim.runner import ORACLE_ORIGIN

    return ORACLE_ORIGIN


def _multi_input_outputs(a: Analysis) -> list[str]:
    if not a.truth_table:
        return []
    out = []
    for i, port in enumerate(a.outputs):
        depends = 0
        n = len(a.truth_table[0][0])
        table = {c: o[i] for c, o in a.truth_table}
        for k in range(n):
            if any(table[c] != table[c[:k] + (not c[k],) + c[k + 1:]] for c in table):
                depends += 1
        if depends >= 2:
            out.append(port.name)
    return out


_REDSTONE_IDS = {
    "redstone_wire", "repeater", "comparator", "redstone_torch", "redstone_wall_torch", "observer", "piston",
    "sticky_piston", "lever", "redstone_lamp", "redstone_block", "target", "dropper", "dispenser", "hopper",
    "slime_block", "honey_block", "note_block", "daylight_detector", "lectern", "sculk_sensor", "copper_bulb",
}
