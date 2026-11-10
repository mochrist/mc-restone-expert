"""German Markdown report for `rsx redesign`."""

from __future__ import annotations

from .evaluate import Constraints, Evaluation
from .spec import Spec


COMPOSE_PREFIX = "Komposition: "  # log entries of search.compose_candidates


def _size(c) -> str:
    return "{}×{}×{}".format(*c.size)


def _status(ev: Evaluation) -> str:
    if ev.ok:
        return "erfüllt"
    if not ev.correct:
        return "falsch: " + (ev.errors[0] if ev.errors else "?")
    return "verletzt: " + "; ".join(ev.violations)


def report(spec: Spec, constraints: Constraints, results: list[Evaluation], title: str,
           original: Evaluation | None = None, written: str | None = None, top: int = 10,
           compact_log: list[str] | None = None) -> str:
    lines = [f"# Redesign: {title}", "",
             "Java Edition 26.3. Jeder Kandidat wurde im Simulator für alle Eingangskombinationen und alle "
             "Einzel-Übergänge geprüft (der Simulator ist gegen das echte Spiel validiert).", "",
             "## Spezifikation", "",
             f"- Herkunft: {spec.source or 'Eingabe'}",
             f"- Eingänge: {', '.join(spec.inputs) or 'keine'}; Ausgänge: {', '.join(spec.outputs)}",
             f"- {'Verhalten' if hasattr(spec, 'trials') else 'Funktion'}: {spec.describe()}"]
    if hasattr(spec, "trials"):
        lines.append(f"- Geprüft in {len(spec.trials)} Testabläufen; Flanken dürfen ±{spec.delay_tolerance} gt, "
                     f"Pulslängen ±{spec.length_tolerance} gt abweichen")
    if getattr(spec, "max_delay", None) is not None:
        lines.append(f"- Verzögerung höchstens {spec.max_delay} gt (aus der Spezifikation)")
    lines += [f"- {n}" for n in spec.notes]
    lines += [f"- Constraints: {constraints.describe()}", ""]

    ok = [r for r in results if r.ok]
    lines += ["## Ergebnis", ""]
    if not results:
        lines.append("- Keine passende Vorlage für diese Funktion gefunden. (Komposition und Suche folgen in einem späteren Schritt.)")
    elif not ok:
        lines.append("- Kein Kandidat erfüllt Spezifikation und Constraints.")
    else:
        best = ok[0]
        c = best.candidate
        lines.append(f"- Bester Kandidat: **{c.name}** ({c.origin}), {_size(c)} = {c.volume} Blöcke Volumen, "
                     f"{c.block_count} Blöcke, " + (
                         f"Flanken höchstens {best.max_delay:+d} gt gegenüber dem Original."
                         if hasattr(spec, "trials") and spec.nominal_delay is None
                         else f"Verzögerung höchstens {best.max_delay} gt."))
        if c.description:
            lines.append(f"- Bauweise: {c.description}")
        if original is not None:
            o = original.candidate
            if c.volume < o.volume:
                lines.append(f"- Gegenüber dem Original ({_size(o)} = {o.volume}, {o.block_count} Blöcke): "
                             f"{100 * (o.volume - c.volume) // o.volume} % weniger Volumen.")
            elif c.block_count < o.block_count:
                lines.append(f"- Gleiches Volumen wie das Original ({_size(o)}), aber {o.block_count - c.block_count} "
                             f"Blöcke weniger ({o.block_count} → {c.block_count}).")
            else:
                lines.append(f"- Das Original ({_size(o)} = {o.volume}) ist nicht größer; keine Verkleinerung gefunden.")
            if original.max_delay is not None and best.max_delay is not None and best.max_delay != original.max_delay:
                lines.append(f"- Verzögerung: Original {original.max_delay} gt, neu {best.max_delay} gt.")
        mech = sorted(best.mechanics - {"observer_pulse"})
        if mech:
            lines.append(f"- Genutzte Sonderfälle: {', '.join(mech)}")
        if written:
            lines.append(f"- Exportiert: `{written}`")
    lines.append("")

    rows = results[:top]
    if original is not None:
        rows = rows + [original]
    if rows:
        lines += ["## Kandidaten", "", "| Rang | Name | Herkunft | Größe | Blöcke | Verzögerung | Status |",
                  "|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            c = r.candidate
            rank = "–" if r is original else str(i)
            delay = ("–" if r.max_delay is None else
                     f"{r.max_delay:+d} gt" if hasattr(spec, "trials") and spec.nominal_delay is None
                     else f"{r.max_delay} gt")
            lines.append(f"| {rank} | {c.name} | {c.origin} | {_size(c)} | {c.block_count} | {delay} | {_status(r)} |")
        lines.append("")
    composed = [x.removeprefix(COMPOSE_PREFIX) for x in compact_log or [] if x.startswith(COMPOSE_PREFIX)]
    compact_log = [x for x in compact_log or [] if not x.startswith(COMPOSE_PREFIX)]
    if composed:
        lines += ["## Komposition", "",
                  "Logik vor einem Baustein mit Zeitverhalten bzw. Speicher; je Paar die erste Verbindung, die "
                  "im Simulator die ganze Spezifikation erfüllt:", ""]
        lines += [f"- {s}" for s in composed]
        lines.append("")
    if compact_log:
        lines += ["## Kompaktierung", "",
                  "Schritte, die beim Verkleinern übernommen wurden (jeder Schritt im Simulator geprüft):", ""]
        lines += [f"- {s}" for s in compact_log[:30]]
        if len(compact_log) > 30:
            lines.append(f"- … und {len(compact_log) - 30} weitere")
        lines.append("")
    lines += ["## Hinweise", "",
              "- Verzögerungen sind vom Umlegen des Hebels bis zur letzten Änderung am Ausgang gemessen; eine "
              "Redstone-Lampe als Ausgang geht 4 gt nach dem Signal aus.",
              "- Positionsabhängiges Verhalten (Update-Reihenfolge von Staub) wurde an der Oracle-Position "
              "(0, 200, 0) simuliert.", ""]
    return "\n".join(lines)
