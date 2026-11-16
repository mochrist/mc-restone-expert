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

## Teil 1: Druckplatte – erledigt (Session 23)

`design/sensors.py` (`SENSORS`, `with_input(cand, kind, spec)`, `button_spec`), `rsx redesign --input`, Feld
`input` in `/api/redesign` und im Assistenten, Wunsch-Karten. Nur im Simulator geprüft (Oracle kennt kein `step`).
Hinweise für Teil 2 vom Bearbeiter:
- Sensor: Python `sim/blocks/daylight.py` (`if world.game_time % 20 == 0`), Rust `outputs.rs`.
- `Circuit.run` setzt bei Platten `step` statt `use` (`analysis/experiment.py`); eine Aktion `time` braucht eine
  Stelle in `runner.apply_input` mit Rust-Gegenstück (wie `step_at` in `sim/rust_world.py`).
- `sensors.py`: Sensor = weiterer Eintrag in `SENSORS` plus eigene Variante; `_traces` unterscheidet die
  Betätigung schon nach Blockart. „An, wenn Nacht“ ist ein Zustand, kein Druck: eigene Spec-Variante nötig
  (`button_spec` passt nicht). Neue Eingangsarten in `evaluate_behaviour` zulassen (Zeile mit
  `_button`/`_pressure_plate`) und mit `robust.check` prüfen.

## Teil 2: Tageslichtsensor (Opus)

Der Simulator kennt nur eine feste Tageszeit
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
