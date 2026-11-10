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

2026-11-05, Python 3.12, Windows, ein Kern, `uv run python scripts/bench_sim.py` (nach den Hot-Path-Optimierungen
in `Pos.offset` und `World.get_signal`, die ~15–20 % brachten):

| Fall | Blöcke | Ticks/s (aktiv) | Neighbor-Updates/s | `rsx explain` |
|---|---|---|---|---|
| Repeater-Ring (Clock) | 17 | ~4 300 | ~210 000 | 0,10 s |
| Fackel-Repeater-Clock | 12 | ~3 600 | ~210 000 | 0,11 s |
| mux3-8 | 281 | (ruht) | – | 3,2 s |
| seg7 | 902 | (ruht) | – | 9,4 s |

Eine ruhende Welt kostet fast nichts (Millionen Ticks/s), bezahlt wird pro Block-Update.
Profil (mux3-8): >80 % der Zeit im Simulator-Kern (Neighbor-Updates, Signalabfragen, Staub-Neuberechnung).

Abschätzung für M4: Ein kleiner Kandidat (2–3 Eingänge, Wahrheitstabelle + Timing, ~10 Läufe à ~30 gt)
kostet in Python grob 10–30 ms, also etwa **30–100 Kandidaten/s**. Mit Vorfilter (abstraktes Modell)
reicht das für gezielte Suche über Templates; für breite evolutionäre Suche (10⁵–10⁶ exakte Bewertungen)
nicht. Dort wäre ein Rust-Kern (geschätzt 30–100×) der Hebel.

Stand der Entscheidung (2026-11-05): Der Nutzer ist offen für einen Rust-Kern. Er wird gebaut, sobald die
M4-Pipeline (Spezifikation → Kandidaten → Bewertung) in Python läuft und die Messung zeigt, dass die exakte
Bewertung der Engpass ist. Bis dahin bleibt die Schnittstelle des Kerns schmal (`World.place_grid`, `tick`,
`apply_input`, Snapshot), damit ein PyO3-Modul sie später 1:1 ersetzen kann.

## Messung nach Aufbau der Pipeline (2026-11-10, Session 5)

Die M4-Pipeline läuft vollständig in Python: Vorlagen, Fackel-PLA, Komposition (Logik vor Speicher,
Zerlegung `f = h(g(x_S), x_F)`, Ausgänge nebeneinander), Router, Bewertung im Simulator.

`rsx redesign examples/specs/composed/xor4.yaml` dauert 26 s. Aufteilung (Zeit pro Kandidat):

| Schritt | Aufrufe | Zeit |
|---|---|---|
| volle Bewertung PLA (470 Blöcke, 4 Eingänge) | 1 | 8,9 s |
| volle Bewertung Komposition pla → xor2 (199 Blöcke) | 1 | 4,4 s |
| Schnellprüfungen PLA / Kompositionen | 20 | 4,4 s |
| `normalize` (Einschwingen nach dem Zusammensetzen) | 18 | 1,8 s |
| Router, Platzierung, Logikminimierung | – | < 1 s |

**Über 90 % der Zeit liegen im Simulator-Kern** (Neighbor-Updates, Signalabfragen, Staub). Die Suche selbst
(BFS-Router, Zerlegung, Quine-McCluskey) kostet fast nichts. Auch die Testsuite ist dadurch von 25 s auf
~65 s gewachsen.

Folgerung: Die vereinbarte Bedingung für den Rust-Kern ist erfüllt. Die Pipeline läuft, und die exakte
Bewertung ist der Engpass. Breitere Suche (mehr Zerlegungen, mehr Layouts je Paar, Mutation/Kompaktieren
großer Entwürfe) scheitert derzeit an Sekunden pro Kandidat. Umfang wie geplant: nur `sim/world.py` und
die Block-Komponenten als PyO3-Modul hinter der schmalen Schnittstelle (`World.place_grid`, `tick`,
`apply_input`, Snapshot), Python-Simulator bleibt Referenz, alle Golden Traces müssen bestehen.
