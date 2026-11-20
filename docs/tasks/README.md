# Aufträge

Jede Datei in diesem Ordner ist ein abgeschlossener Auftrag für eine oder wenige Sessions. Die Reihenfolge und
das vorgesehene Modell stehen in der Tabelle in `STATUS.md`. Die Aufträge wurden in Session 22 (Fable 5.2)
geplant; sie nennen Einstiegsstellen und Abnahme, damit niemand die Vorgeschichte (`docs/history.md`) lesen muss.

## So wird ein Auftrag bearbeitet

1. Den Auftrag **ganz** lesen, dann die unter „Einstieg“ genannten Stellen im Code.
2. Tests sparsam (der Nutzer will Tempo): Keine Ausgangsmessung, wenn der letzte Commit laut `docs/history.md`
   grün war. Während der Arbeit nur die betroffenen Testdateien. Die volle Suite `uv run pytest -q` (~70 s)
   einmal vor dem Abschluss. `--slow` (~40 min) nur, wenn die Abnahme es verlangt oder die Entwurfssuche
   (`design/decompose.py`, `search.py`, `compose.py`, `synth.py`) geändert wurde, dann im Hintergrund laufen
   lassen und derweil weiterarbeiten.
3. Die Schritte der Reihe nach; nach jedem sinnvollen Teil committen (Commit-Nachrichten englisch).
4. Die Abnahme des Auftrags ausführen und das Ergebnis (Zahlen, nicht „läuft“) notieren.
5. Abschluss: Auftragsdatei löschen, Zeile in `STATUS.md` entfernen, 3–6 Zeilen oben in `docs/history.md`.
   Bleibt etwas offen, die Datei stattdessen kürzen auf das, was noch fehlt.

## Regeln für alle Aufträge

- **Nur den Auftrag bearbeiten.** Auffälligkeiten nebenbei kommen als Zeile nach `docs/backlog.md`.
- **Beide Simulatorkerne.** Jede Änderung am Simulator landet in `src/redstone/sim/` und in `rust/rsx-core/`;
  `tests/sim/test_core_equivalence.py` muss grün bleiben. Nach Rust-Änderungen:
  `uv pip install --reinstall-package rsx-core ./rust/rsx-core`.
- **Im Spiel geprüfte Entwürfe sind eingefroren.** Ändert sich ein Entwurf hinter `scenarios/tpl-*`, `seq-*`,
  `pla-*` oder `cmp-*`, muss das Szenario neu erzeugt und neu aufgenommen werden (`uv run rsx oracle
  scenarios/<x>.yaml --golden`). Eine Abweichung Simulator ↔ Spiel ist ein Fehler im Simulator: melden und
  beheben, nie das Golden an den Simulator anpassen.
- **Oracle:** fester Port und festes Verzeichnis, also nie zwei Läufe zugleich; Sperre `mkdir .cache/oracle.lock`
  (danach `rmdir`). Läufe über 5 Minuten vorher beim Nutzer ansagen (er spielt oft am selben Rechner).
- **Zeiten** sind nur belastbar, wenn der Rechner sonst nichts tut. Im Zweifel Größen, Blockzahlen und Zahl der
  Simulatorläufe (`Evaluation.runs`) vergleichen statt Sekunden.
- **Abbruchkriterium.** Jeder Auftrag nennt eines. Ist es erreicht: Befund in den Auftrag schreiben, die Zeile in
  `STATUS.md` mit „blockiert: <Grund>“ markieren und aufhören.
- **Nicht raten.** Existiert eine genannte Funktion nicht mehr, zuerst suchen (`grep`), dann den Auftrag
  berichtigen. Zahlen im Auftrag, die als „nachrechnen“ markiert sind, vor der Verwendung prüfen.
- **Sprache:** Antworten, Berichte und Oberflächentexte deutsch; Code, Bezeichner und Commits englisch.
  Texte der Oberfläche in Alltagssprache (der Nutzer ist kein Redstone-Profi).
- **GUI-Änderungen** im Browser prüfen (Chrome-Erweiterung oder Headless-Screenshot, Befehl in `STATUS.md`),
  Screenshots dem Nutzer schicken.

## Begriffe

- **Kandidat** (`design/candidate.py: Candidate`): Grid plus Positionen der Eingänge (Hebel/Knöpfe) und Ausgänge (Lampen).
- **Spezifikation**: Wahrheitstabelle (`design/spec.py: Spec`) oder Zeitverhalten (`design/behaviour.py: BehaviourSpec`).
- **Bewertung** (`design/evaluate.py: evaluate`, `evaluate_any`): simuliert einen Kandidaten gegen die
  Spezifikation; `quick`/`full=False` prüft nur jede Kombination aus frischer Welt, die volle Prüfung auch Übergänge.
- **Oracle**: Fabric-Server in `oracle/`, nimmt Szenarien im echten Spiel auf (Golden Traces in `tests/golden/`).
- **Ursprung**: Simulator und Oracle setzen jede Schaltung mit der Min-Ecke auf (0, 200, 0) (`sim/runner.py: ORACLE_ORIGIN`).
