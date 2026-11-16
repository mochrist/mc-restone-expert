# 04 Druckplatte als Auslöser, danach Tageslichtsensor

Modell: Teil 1 Sonnet, Teil 2 Opus · hängt ab von: nichts (Teil 2 von Teil 1) · nicht gleichzeitig mit 05
(beide ändern `gui/assistant.py`) und nicht gleichzeitig mit 01/02 an `cli.run_redesign`

## Ziel

Der Wunsch „Tür geht auf, wenn ich auf eine Druckplatte trete“ liefert einen geprüften Entwurf statt einer Absage.

## Warum

Der Assistent muss heute Druckplatten und Sensoren ablehnen (`gui/assistant.py: SYSTEM`, Absatz „Ehrlichkeit“;
Fall `druckplatte` in `scripts/assistant_eval.py`). Für Laien sind das die naheliegendsten Auslöser.

## Einstieg

- Muster: `src/redstone/design/actuators.py` (dasselbe für Ausgänge: Variante bauen, im Simulator gegen die
  Ausgangsfassung prüfen, deutsche Begründung zurückgeben).
- Simulator-Aktion `step` (Entity betritt die Platte und verlässt sie sofort): `docs/scenario-format.md`,
  `sim/runner.py: apply_input`, `PressurePlateBlock` in `sim/blocks/basic.py`. `Circuit.run` setzt für Platten
  automatisch `step` statt `use` ein (`analysis/experiment.py`).
- Eingänge der Entwürfe: Hebel oder Knopf, Position in `Candidate.inputs`. Vorlagen setzen Boden-Hebel
  (`lever[face=floor,…]`), ansteuerbare PLAs Wandhebel (`face=wall`).
- `cli.run_redesign(..., output=…)` zeigt, wie eine nachträgliche Änderung in Bericht und Ergebnis kommt.

## Teil 1: Druckplatte (Sonnet)

1. `src/redstone/design/sensors.py` mit `SENSORS` (Schlüssel `stone_pressure_plate`, `oak_pressure_plate`;
   deutsches Etikett) und `with_input(cand, kind) -> (Candidate | None, Begründung)`:
   - Nur für Entwürfe, deren Eingänge Knöpfe sind oder deren Verhalten ein Impuls ist (`monostable`,
     `pulse-extender`, `t-flip-flop`, `rs-latch` mit `kind: button`). Eine Platte ist ein Taster, kein Schalter;
     für Hebel-Logik („bleibt an“) gibt die Funktion `None` mit Begründung zurück.
   - Boden-Knopf oder Boden-Hebel: Platte in dieselbe Zelle (der Block darunter ist da). Wand-Eingang: Platte
     auf einen freien Platz neben dem Block, an dem der Eingang hängt, mit Stein darunter; passt das nicht, `None`.
   - Prüfung: dieselbe Folge von Betätigungen einmal mit der Ausgangsfassung (Knopf, `use`) und einmal mit Platte
     (`step`); Ausgänge müssen am Ende jeder Phase gleich sein und gleich oft einschalten. Die Pulslänge der
     Platte weicht vom Knopf ab (Steinknopf 20 gt, Holzknopf 30 gt, Platte prüft alle 20 gt): deshalb nur
     Endzustand und Zahl der Einschaltungen vergleichen, nicht die Zeitpunkte.
2. `cli.run_redesign(..., input=…)`, `rsx redesign --input BLOCK`, `/api/redesign` Feld `input`
   (`gui/server.py`, `docs/gui-api.md`), Berichtsabschnitt „Eingang“ analog zu „Ausgang“.
3. Assistent: `tools_schema` (Parameter `input` bei `design_circuit` und `shrink_circuit`), Systemprompt: Platte
   ist möglich für Impuls-Wünsche; ehrlich sagen, dass die Platte nur im Simulator geprüft ist, nicht im echten
   Spiel. Wunsch-Karten (`wizard.js`): bei Wünschen mit Knopf die Auswahl „Knopf / Druckplatte“.
4. `tests/design/test_sensors.py` (Monoflop 8 gt mit Platte geht; AND mit zwei Hebeln gibt `None`);
   `scripts/assistant_eval.py`: Fall `druckplatte` erwartet jetzt `[["monostable", "pulse-extender"], ["pressure_plate"]]`.

Abnahme Teil 1: Tests grün; `uv run rsx redesign examples/behaviour/monoflop.yaml --input stone_pressure_plate
--output iron_door -o .cache/tuer.litematic` liefert einen Entwurf; `uv run python scripts/assistant_eval.py`
(braucht den Schlüssel in `.env`, kostet API-Aufrufe: einmal am Ende) zeigt den Fall als gelungen; Screenshot
der Wunsch-Karte an den Nutzer.

## Teil 2: Tageslichtsensor (Opus)

Erst beginnen, wenn Teil 1 abgenommen ist. Der Simulator kennt nur eine feste Tageszeit
(`sim/blocks/daylight.py`, Rust `outputs.rs`; Szenariofeld `game_time`).

1. Aktion `time <ticks>` im Szenarioformat: setzt die Tageszeit; Simulator in beiden Kernen (der Sensor rechnet
   alle 20 gt neu, Phase `game_time % 20`), Oracle per `time set` zwischen zwei Ticks (`ScenarioRun.java`).
   Wissensbasis: `knowledge/components/daylight-detector.md` (DAY-001…006) um die Aussagen zur Tageszeit ergänzen.
2. Szenario `daylight-time.yaml` (Sensor normal und invertiert, Zeiten 0, 6000, 12000, 13000, 18000, 23000) im
   Spiel aufnehmen; Simulator muss übereinstimmen.
3. `sensors.py`: `daylight_detector` und `daylight_detector_inverted` als Eingang („an, wenn es Tag/Nacht
   ist“): Sensor mit freiem Himmel, dahinter ein Verstärker (das Signal ist analog), dann der bisherige Eingang.
   Prüfung mit `time` statt `use`.

Abnahme Teil 2: Golden identisch auf beiden Kernen; Wunsch „Lampe geht nachts an“ liefert einen Entwurf.

## Fallstricke

- `use` auf einer Platte tut im Spiel nichts; in Szenarien für das Oracle kommt `step` nicht vor (keine Entities).
- Holzplatten reagieren im Spiel auch auf Items, Steinplatten nur auf Lebewesen: nur im Text erwähnen.
- Die Tageslicht-Messung hängt vom Himmelslicht über dem Sensor ab (Annäherung, DAY-006): der Entwurf darf nichts über den Sensor bauen.

## Abbruch

Teil 2: Stimmen Simulator und Spiel nach einer Session nicht überein, Aktion `time` behalten, den Sensor als
Eingang nicht anbieten und den Befund notieren.
