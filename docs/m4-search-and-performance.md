# M4: Suchalgorithmen und Performance (Designnotiz)

Stand: 2026-10-28. Ergebnis einer Diskussion mit dem Nutzer, ob eine Neuschreibung in Rust lohnt.
Diese Notiz gilt als Leitlinie für M4. Bei neuen Messwerten aktualisieren.

## Entscheidung

**Keine Neuschreibung in Rust.** Python bleibt für alles. Nur der Simulator-Kern wird eventuell später
portiert, und zwar erst, wenn eine Messung zeigt, dass er der Engpass der M4-Suche ist.

## Begründung

| Kriterium | Effekt einer Rust-Neuschreibung |
|---|---|
| Qualität der Ergebnisse | kein direkter Vorteil. Qualität = Korrektheit des Simulators (über Golden Traces abgesichert) + Güte der Suche. Eine Neuschreibung birgt das Risiko, dass alles tick-genau Validierte (Wire-HashSet-Reihenfolge, Kolben, Tick-Prioritäten) neu stimmen muss. |
| Geschwindigkeit | geschätzt (nicht gemessen) 30–100× schneller. Für M3 (Analyse, wenige hundert Ticks) irrelevant. Für M4 entscheidend, wenn Millionen Kandidaten geprüft werden. |
| Token-Verbrauch | Rust allein kostet eher mehr Tokens (längerer Code, Compiler-Runden, einmaliger Neubau). Der große Spareffekt kommt aus **algorithmischer** Kandidatenerzeugung statt Vorschlägen des Modells: Laufzeit kostet keine Tokens. |

Auch Rust schafft keine Brute-Force-Suche: Schon 3×3×3 mit etwa 30 sinnvollen Zuständen pro Feld ergibt
rund 30²⁷ Möglichkeiten. Die Algorithmen entscheiden, nicht die Sprache.

## Algorithmen für M4 (Priorität)

1. **Zweistufige Bewertung:**
   - Ein schnelles abstraktes Modell (statischer Power-Graph: welcher Block kann welchen powern, Verzögerungen auf Gatter-Ebene) verwirft die meisten Kandidaten billig.
   - Nur Überlebende laufen durch den exakten Tick-Simulator.
   - Die finalen Kandidaten laufen optional zusätzlich im Oracle.
2. **Topologie vor Platzierung:**
   - Ein SAT/SMT-Solver (z. B. z3) bestimmt zuerst, welche Bauteile mit welchen Verzögerungen und Seiteneingängen nötig sind.
   - Danach wird die räumliche Anordnung auf dem Raster mit Pruning gesucht.
3. **Gezielte Suche statt Blind-Suche:** Evolutionäre Verfahren oder MCTS, ausgehend von einer Vorlagen-Bibliothek bekannter Kompakt-Bauweisen statt vom leeren Raum.
4. **Caching und Symmetrien:**
   - Drehungen und Spiegelungen gelten als äquivalent.
   - Bekannte Teilschaltungen und Bewertungen werden zwischengespeichert.
5. **Rolle des Modells (Claude):** Spezifikation formulieren, Vorlagen und Ideen liefern, Ergebnisse bewerten und erklären. Keine Massen-Kandidatenerzeugung über Tokens.

## Vorgehen beim Thema Performance

1. Zu Beginn von M4 die aktuelle Simulator-Geschwindigkeit messen (Ticks/s, Block-Updates/s, Kandidaten/s für eine typische Bewertung) und hier eintragen.
2. Erst profilieren, wenn die Suche läuft. Wenn der Simulator der Engpass ist: nur den Kern (`sim/world.py` und Komponenten) als Rust-Erweiterung über PyO3/maturin nachbauen. Er muss dieselben Golden Traces bestehen (`tests/sim/test_golden.py`), die Python-Version bleibt als Referenz.
3. Als Messlatte und Ideenquelle `azazo1/redstone-rs` ansehen (Rust-Simulator für 26.1.2, keine Lizenz: nur ansehen und gegen unsere Golden Traces benchmarken, keinen Code übernehmen).

## Messwerte

_noch keine_
