# 13 Schnellere Entwurfssuche: Engpässe nach Rust, dann parallel

Modell: Opus · hängt ab von: – · vor Auftrag 12 (dessen Suchen nach kleineren Bausteinen profitieren direkt)

## Ziel

`rsx redesign` (und die Suche in der GUI) nutzt mehrere Kerne und ist bei großen Beispielen deutlich schneller,
Ziel: mindestens 3× bei mux8, cmp5, addsub2 und dem 4-Bit-Addierer (`.cache/gui/specs/addierer4.yaml`, sonst
neu anlegen wie in `tests/gui/test_server.py: ADDER4`). **Die Ergebnisse bleiben exakt gleich** (gleicher bester
Entwurf, gleiche Blockzahl), sonst ändern sich im Spiel geprüfte Entwürfe.

## Hintergrund (Session 28)

- Threads helfen kaum: Die GIL lässt nur einen Thread Python ausführen. Seit Auftrag 11 gibt der Rust-Kern die GIL
  während `run_recording` frei, aber Weltaufbau (`place_grid`, Block-Entities), Zerlegung (`decompose.py`,
  Schleifen über alle Teilmengen) und Synthese (`synth.py: _plan_line`, `_simulate`) sind reines Python. Im Profil
  des 4-Bit-Addierers lag die meiste Zeit in `synth._plan_line`/`_simulate` und in den Split-Aufzählungen.
- Rechner des Nutzers: 16 logische Kerne; er spielt oft nebenbei (Messungen nur als Größenordnung, Kernzahl
  begrenzen).

## Schritte

1. **Messen, wo die Zeit hingeht.** Profil (cProfile, ggf. py-spy) für die vier Beispiele: Anteil Simulation
   (`analysis/experiment.py: Circuit.run`), Weltaufbau, Zerlegung, Synthese, Router, Kompaktieren. Tabelle hierher.
   Zahl der Simulatorläufe (`Evaluation.runs`) als zeitunabhängige Größe mitschreiben.
2. **Engpässe festlegen** (nach Messung). Pro Stelle in die Tabelle: Anteil an der Zeit, ob sie schmal und stabil ist
   (feste Eingaben/Ausgaben, ändert sich voraussichtlich nicht mit Auftrag 12) und ob sie parallel laufen kann.
   Kandidaten für Rust: Weltaufbau bzw. eine geklonte Rust-Welt je `Circuit` (statt `place_grid` und
   Block-Entities je Lauf), `_dust_path`, Router (`compose._route`, BFS-Kern gibt es schon in
   `rust/rsx-core/src/route.rs`), eventuell `synth._simulate`. **Nicht** nach Rust: die Logik von Zerlegung,
   Synthese und Suche (Auswahl, Reihenfolge, Abbruchregeln), die bleibt in Python.
   Kandidaten für Parallelität: Kandidatenprüfung (`design/search.py`, `evaluate_any`), Zweige der Zerlegung
   (`decompose._design_part`, verschiedene Splits) und der Synthese, Kompaktier-Versuche (`compact.py`),
   Ortsprüfung (`design/robust.py`, Orte × Drehungen).
3. **Engpässe nach Rust** (nur die Stellen aus 2. mit großem Anteil, größte zuerst):
   - Jede Rust-Funktion gibt während der Rechnung die GIL frei (`py.detach`, wie `run_recording`).
   - Die Python-Fassung bleibt als Referenz; Umschalten wie beim Kern (`--sim-core python|rust`). Ein
     Vergleichstest (Muster: `tests/sim/test_core_equivalence.py`) prüft auf allen Vorlagen und Beispielen,
     dass beide Fassungen exakt dasselbe liefern.
   - Nach jeder Stelle neu messen; aufhören, sobald die Stelle nicht mehr unter den größten Posten ist.
4. **Parallelität, zuerst mit Threads** (`concurrent.futures.ThreadPoolExecutor`): Weil die heißen Teile nach 3.
   ohne GIL laufen, reichen vielleicht Threads. Vorteil: kein Kopieren der Kandidaten, Frames
   (`design/observe.py`) und Abbruch (`observe.cancelling`, pro Thread) funktionieren wie heute.
   - Ergebnisse in fester Reihenfolge auswerten (wie seriell), Abbruch („first match“) erst nach Reihenfolge
     entscheiden.
   - Kernzahl über `--jobs N` und Umgebungsvariable `RSX_JOBS`; Standard: Hälfte der Kerne, `1` = heutiges
     serielles Verhalten (Referenz für Tests).
   - Abbruch beendet alle Arbeiter.
5. **Prozesse nur, wenn Threads nicht reichen** (unter 3× trotz 3.): `ProcessPoolExecutor`, Start-Methode
   „spawn“ unter Windows, Arbeit in Paketen (nicht jeden Einzellauf), Kandidaten als kompakte Daten (Grid als
   Blockliste), Rust-Kern in jedem Arbeiter initialisieren (`rsx_core.init`); Frames und Abbruch über die
   Prozessgrenze. Gleiche Regeln wie in 4.
6. **Alternative prüfen (nur bewerten, nicht bauen):** free-threaded Python 3.13t/3.14t mit PyO3; Aufwand und
   Risiko notieren.
7. **GUI:** Nutzt die Suche Prozesse (5.), läuft sie im Server in einem eigenen Prozess (macht die Seite
   unabhängig von der Suche, siehe Auftrag 11). Mit Threads reicht der heutige Aufbau, solange
   `scripts/gui_latency.py` während der 4-Bit-Addierer-Suche unter 1 s bleibt.
8. Messung nachher (gleiche Tabelle, Spalten: seriell Python, seriell mit Rust-Engpässen, parallel),
   Ergebnisgleichheit für alle Beispiele (`scripts/bench_redesign.py --json` seriell gegen parallel vergleichen).

## Abnahme

- Für alle Beispiele in `examples/specs/`, `composed/`, `behaviour/`: bester Entwurf mit `--jobs 1` und
  `--jobs 8` identisch (Blöcke, Größe, Grid), ebenso mit Python- und Rust-Fassung der portierten Engpässe.
- Vergleichstests für jede nach Rust verlagerte Stelle.
- Mindestens 3× schneller bei den vier großen Beispielen mit 8 Arbeitern gegenüber vorher (Rechner möglichst
  ohne Spiel, Zahlen vorher/nachher notieren); Anteil von Rust-Engpässen und Parallelität getrennt ausweisen.
- Abbruch in der GUI beendet alle Arbeiter innerhalb von 2 s.
- `uv run pytest -q --slow` grün.

## Abbruch

Bringen Rust-Engpässe und Parallelität (Threads, notfalls Prozesse) zusammen weniger als 1,5×, oder lässt sich eine
Rust-Fassung nicht exakt gleich zur Python-Referenz machen: Befund und Profil hierher, Zeile in `STATUS.md` als
„blockiert“ markieren.
