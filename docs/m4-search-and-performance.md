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

## Rust-Kern (2026-11-10, Session 7)

`rust/rsx-core` (PyO3, Modul `rsx_core`) ersetzt `sim/world.py` und alle Block-Komponenten. Umschalten mit
`RSX_SIM_CORE=python|rust|auto` (Standard `auto`: Rust, wenn installiert), `rsx --sim-core …` oder
`pytest --sim-core …`. Der Python-Kern bleibt Referenz.

Abnahme:
- alle 92 Golden Traces und die ganze Testsuite auf beiden Kernen grün;
- `tests/sim/test_core_equivalence.py` vergleicht beide Kerne **jeden Tick über die ganze Welt** (Blöcke,
  Block-Entities in Dict-Reihenfolge, geplante Ticks, Block-Events, Zahl der Neighbor-Updates; am Ende Notizen
  und Warnungen): alle Szenarien, alle Logik- und Sequenz-Vorlagen mit zufälligen Eingaben, die externen
  Fixtures und 150 zufällige Block-Soups (6×3×6, Kolben, Trichter, Schienen, Türen …, zufällige Klicks und
  `setblock`s). Dazu die statischen Fakten aller 35 723 Blockzustände der Blocktabelle.
- Einzige gefundene Abweichung: ein leeres Lesepult hat in Python `page = -1` (Clamp in `load({})`); Rust
  übernimmt das. Für das Signal ohne Buch ohne Folgen.

Messwerte (`scripts/bench_sim.py --sim-core …`, gleicher Rechner):

| Fall | Python | Rust | Faktor |
|---|---|---|---|
| repeater-ring, Ticks/s (angestoßen) | 4 361 | 655 630 | 150× |
| torch-repeater-4, Ticks/s | 3 663 | 569 801 | 156× |
| Neighbor-Updates/s | ~210 000 | ~32 Mio. | 150× |
| `rsx`-Analyse mux3-8 | 2,99 s | 0,06 s | 50× |
| `rsx`-Analyse seg7 | 8,03 s | 0,15 s | 54× |
| Testsuite | 80 s | 25 s | 3× |
| `rsx redesign examples/specs/composed/xor4.yaml` | 70 s | 8,7 s | 8× |

Nach dem Wechsel lag der Engpass von `rsx redesign` nicht mehr im Simulator (0,5 s von 8,7 s), sondern im
Router (`compose._near`: 27 Mengenabfragen pro BFS-Zelle, 22 Mio. Aufrufe). Ersetzt durch eine einmal
berechnete Hülle (`_halo`), Ergebnis identisch: **xor4 jetzt 3,3 s mit Rust** (57 s mit Python).
Verbleibend: BFS-Router in Python (~2 s, `Pos.__add__`), Simulator ~0,5 s. Die Grenze für breitere Suche ist
damit wieder die Suche selbst, nicht die Bewertung.

Hinweis: Session 5 maß für xor4 mit Python 26 s; heute 70 s (Pipeline seither erweitert, andere Last auf dem
Rechner möglich). Die Faktoren oben stammen aus Läufen direkt nacheinander.

## Entwurfssuche großer Funktionen (2026-11-16, Auftrag 03)

Messung vorher (`python -m cProfile`, Rust-Kern, Rechner nicht ruhig: weitere Agents liefen):

| Lauf | gesamt | Teile suchen | Bewertungen (davon Übergänge) | Kompaktieren | `Circuit.run` (davon Rust `tick`) |
|---|---|---|---|---|---|
| mux4 (6 Eingänge), `--time 60` | 61 s | 1 s | 32 s (22 s) | 54 s (Bewertung 26 s, `relocations` 27 s) | 29 s (2,8 s) |
| mux8 (11 Eingänge), `--time 300` | 913 s | 27 s | 869 s (788 s in 5 vollen Prüfungen) | 379 s (8 Varianten) | 846 s (24 s) |

Der Simulator selbst kostete fast nichts; **85–90 % der Bewertung lag in der Python-Schleife von `Circuit.run`**
(`_snapshot_changed`: jeden Tick alle geänderten Blöcke und alle Komparatoren als `Pos` nach Python holen, filtern,
vergleichen). Eine volle Prüfung des unkompaktierten mux8 (371 Blöcke) dauerte 78 s, die Schnellprüfung 2,5 s.

Umgesetzt:
- **(a) Übergänge ohne Doppelarbeit** (`evaluate._check_transitions`, `TRANSITIONS = "half"`): je Kombination nur
  die Hebel umlegen, die dort aus sind, und zurück; jeder gerichtete Übergang genau einmal. Simulierte Ticks der
  Beispiele −20 bis −45 %. Gegenprobe mit `scripts/bench_redesign.py --compare-transitions` (jede volle Prüfung
  zusätzlich mit allen Übergängen): über alle Beispiele außer cmp5/mux8 **kein Kandidat mit anderem Urteil oder
  anderer Verzögerung**. `tests/design/test_evaluate_cost.py` hält Läufe (31 statt 32 bei 4 Eingängen: mit allen
  Hebeln an gibt es nichts umzulegen) und Ticks (etwa die Hälfte der Übergangsticks) fest.
- **(c) Aufzeichnungsschleife im Rust-Kern** (`World.run_recording`; `Circuit.run` nutzt sie, wenn alle Aktionen
  Klicks sind; `Circuit.run_python` bleibt Referenz, Vergleich in `tests/analysis/test_run_loop.py` auf allen Logik-
  und Zeitvorlagen).
- (b) Stichprobe beim Kompaktieren und (d) Teile-Cache über Prozesse **nicht nötig**: mux8 liegt ohne sie weit unter
  10 min, die Teilesuche kostet 14 s. (b) hätte zudem die eingefrorenen `cmp-mux8`/`cmp-cmp5` verändern können.

Nachher:

| Lauf | vorher | nachher |
|---|---|---|
| eine volle Prüfung mux8 (371 Blöcke) | 78 s, 4 096 Läufe | 8,8 s, 4 095 Läufe, 1,44 Mio. Ticks |
| Schnellprüfung mux8 | 2,5 s | 1,4 s (Rest: Welt aufbauen, Anfangszustand nach Python) |
| `rsx redesign mux4` (Profil) | 61 s, Bewertungen 32 s | 36 s, Bewertungen 7 s |
| `rsx redesign mux8` (Standard `--time 60`) | 3 min 44 s; nichts kompaktiert (erste volle Prüfung > 60 s): 22×8×17, 371 Blöcke | 2 min 16 s; kompaktiert: 19×8×17, 350 Blöcke |
| mux8 ohne Zeitlimit (Budget 100, wie `scripts/compose_scenarios.py` und der slow-Test) | ~34 min | 12–13 min, unverändert 15×10×17, 354 Blöcke |
| cmp5 ohne Zeitlimit | ~15 min | 6 min, unverändert 16×8×23, 502 Blöcke |

Alle Beispiele (`scripts/bench_redesign.py`, ohne Zeitlimit, `PYTHONHASHSEED=0`): gleiche Kandidaten, gleiche
Maße, Blockzahlen und Verzögerungen wie vorher; `cmp-*`-Szenarien und Goldens unverändert (slow-Tests grün).

Neuer Engpass: die Suche beim Kompaktieren in Python (`compact.relocations` → `_dust_path`), bei mux8 mit
`--time 300` 354 s von 449 s. Sie prüft das Zeitlimit nicht, deshalb überzieht das Kompaktieren großer Entwürfe
es deutlich (449 s bei 300 s Limit).
