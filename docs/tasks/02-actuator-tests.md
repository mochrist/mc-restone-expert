# 02 Aktoren testen und im Spiel aufnehmen

Modell: Sonnet · hängt ab von: nichts

## Ziel

Die Ausgänge „Tür, Falltür, Kolben, Notenblock, Spender, Werfer statt Lampe“ haben Tests und je eine Aufnahme im
echten Spiel, und die Wunsch-Karten der Oberfläche bieten sie an.

## Warum

`src/redstone/design/actuators.py` (Session 19) ist ungetestet und nie im Spiel aufgenommen, wird aber vom
Assistenten bei fast jedem Wunsch benutzt (Codeschloss mit Eisentür, Türklingel mit Notenblock).

## Einstieg

- `design/actuators.py`: `ACTUATORS`, `with_output(cand, kind) -> (Candidate | None, Begründung)`. Zwei Wege:
  Block an Stelle der Lampe, sonst Lampe → Verstärker → Block. Geprüft wird gegen die Lampen-Fassung (`_traces`).
- `cli.run_redesign(..., output=…)` und `rsx redesign --output BLOCK`.
- Szenarien aus Entwürfen erzeugen: `scripts/compose_scenarios.py` (`scenario_for`, `table_scenario_for`, `main`).
- Sonden und Szenarioformat: `docs/scenario-format.md`.

## Schritte

1. `tests/design/test_actuators.py`:
   - Für jede Kombination aus Aktor (7) und Entwurf (`and2-torch`, `xor2-comparator`, bester Entwurf für
     `behaviour: t-flip-flop`, bester für `monostable, length: 8`) den heutigen Ausgang von `with_output`
     festhalten: entweder „geht“ (dann: Ausgangsblock hat die erwartete ID, `_traces` gleich der Lampen-Fassung)
     oder „geht nicht“. Laut Session 19 geht das Fackel-AND nicht mit Tür, Kolben, Spender; das ist dann der
     erwartete Wert, kein Fehler.
   - `with_output(cand, "gibtsnicht")` gibt `(None, …)`.
   - Ein Entwurf mit zwei Ausgängen (`halfadder-comparator`): beide bekommen den Aktor.
2. Skript `scripts/actuator_scenarios.py` nach dem Muster von `compose_scenarios.py`: für jeden Aktor ein
   Szenario `scenarios/act-<aktor>.yaml` mit einem Entwurf, bei dem er passt (XOR mit zwei Hebeln genügt), alle
   Kombinationen nacheinander im Abstand von 30 gt, Sonden auf den Aktor (`open`, `extended`, `triggered`,
   `powered`; beim Kolben auch auf den Block darüber).
3. Im Spiel aufnehmen: `uv run rsx oracle scenarios/act-*.yaml --golden` (Sperre beachten, ~1 min).
   `uv run rsx sim scenarios/act-<x>.yaml --diff` muss identisch sein. Die Szenarien laufen danach automatisch in
   `tests/sim/test_golden.py` mit.
4. Wunsch-Karten: in `src/redstone/gui/static/wizard.js` bekommt jeder Wunsch mit einer Lampe ein Feld „Was soll
   geschaltet werden?“ (Lampe, Eisentür, Falltür, Kolben, klebriger Kolben, Notenblock, Spender, Werfer; Texte in
   Alltagssprache). Der Wert geht als `output` in den Aufruf von `/api/redesign` (`app.js: searchOptions`,
   `docs/gui-api.md` ergänzen falls dort nicht genannt). Im Browser prüfen: Wunsch „Lampe nach Regel“ mit Eisentür.

## Abnahme

- `uv run pytest tests/design/test_actuators.py -q` grün; ganze Suite grün.
- Sieben neue Golden Traces, identisch zum Simulator.
- Screenshot der Wunsch-Karte mit Tür-Ergebnis an den Nutzer.

## Fallstricke

- Spender und Werfer sind leer: im Spiel wie im Simulator ändert sich nur `triggered`. Das genügt.
- Die Eisentür besteht aus zwei Blöcken; die Sonde gehört auf die untere Hälfte.
- Weicht eine Aufnahme vom Simulator ab, ist das ein Simulatorfehler (beide Kerne!). Nicht den Test anpassen:
  Befund mit Tick und Block notieren und beheben oder, wenn es nicht in einer Stunde gelingt, als eigene Zeile
  nach `docs/backlog.md` und den Aktor aus `ACTUATORS` nehmen (dann auch aus dem Systemprompt des Assistenten).

## Abbruch

Mehr als zwei Aktoren weichen im Spiel ab: aufhören, Befunde notieren, an Opus übergeben.
