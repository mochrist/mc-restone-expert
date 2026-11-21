# 13 Parallele Entwurfssuche

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
2. **Parallelisierbare Stellen festlegen** (nach Messung), Kandidaten:
   - Kandidatenprüfung: Listen von Kandidaten, die unabhängig bewertet werden (`design/search.py`, `evaluate_any`).
   - Zweige der Zerlegung (`decompose._design_part`, verschiedene Splits) und der Synthese.
   - Kompaktier-Versuche (`compact.py`) und die Ortsprüfung (`design/robust.py`, Orte × Drehungen).
3. **Umsetzung mit Prozessen** (`concurrent.futures.ProcessPoolExecutor`, Start-Methode „spawn“ unter Windows):
   - Arbeit in Paketen schicken (nicht jeden Einzellauf), Kandidaten als kompakte Daten (Grid als Blockliste).
   - Ergebnisse in fester Reihenfolge auswerten (wie seriell), Abbruch („first match“) erst nach Reihenfolge entscheiden.
   - Kernzahl über `--jobs N` und Umgebungsvariable `RSX_JOBS`; Standard: Hälfte der Kerne, `1` = heutiges
     serielles Verhalten (Referenz für Tests).
   - Beobachter-Frames (`design/observe.py`) und Abbruch (`observe.cancelling`) müssen weiter funktionieren:
     Abbruch beendet auch die Arbeiter.
   - Rust-Kern in jedem Arbeiter initialisieren (`rsx_core.init`), Python-Kern ebenso möglich.
4. **Alternative prüfen (nur bewerten, nicht bauen, wenn 3. reicht):** free-threaded Python 3.13t/3.14t mit PyO3;
   Aufwand und Risiko notieren.
5. **GUI:** Suche im Server optional in einem eigenen Prozess (macht die Seite unabhängig von der Suche, siehe
   Auftrag 11); Frames und Abbruch über die Prozessgrenze.
6. Messung nachher (gleiche Tabelle), Ergebnisgleichheit für alle Beispiele (`scripts/bench_redesign.py --json`
   seriell gegen parallel vergleichen).

## Abnahme

- Für alle Beispiele in `examples/specs/`, `composed/`, `behaviour/`: bester Entwurf mit `--jobs 1` und
  `--jobs 8` identisch (Blöcke, Größe, Grid).
- Mindestens 3× schneller bei den vier großen Beispielen mit 8 Prozessen (Rechner möglichst ohne Spiel, Zahlen
  vorher/nachher notieren).
- Abbruch in der GUI beendet alle Arbeiter innerhalb von 2 s.
- `uv run pytest -q --slow` grün.

## Abbruch

Bringt die Parallelisierung nach Schritt 3 weniger als 1,5× (z. B. weil Kopieren der Kandidaten zu teuer ist):
Befund und Profil hierher, Zeile in `STATUS.md` als „blockiert“ markieren; dann zuerst die Engpässe nach Rust
verlagern (Weltaufbau, `_dust_path`).
