# 12 Kleinere Entwürfe

Modell: Opus · hängt ab von: – · mittlere Priorität (Wunsch des Nutzers, Session 28: „für wann anders“)

## Ziel

Die Entwurfssuche (`rsx redesign`) liefert für größere Schaltungen deutlich kleinere Baupläne. Messgröße: Blöcke
(Stützblöcke mitgezählt) und Volumen der Beispiele in `examples/specs/` und `examples/specs/composed/`.
Zielwert: Summe der Blöcke über die Messliste unten mindestens 25 % kleiner, kein Beispiel größer, alle Entwürfe
weiter ortsfest (`design/robust.py`) und im Spiel bestätigt.

## Ausgangslage (Zahlen vor Beginn nachrechnen, Skript `scripts/bench_redesign.py`)

| Beispiel | Blöcke heute | Quelle |
|---|---|---|
| xor | 17 | `xor2-stacked`, Auftrag 07 |
| xor4 | 55 | Auftrag 07 |
| Mehrheit von 3 | 58 | PLA, Auftrag 07 (Ziel dort: unter 40) |
| mux4 / mux8 | 111 / 354 | Session mit Router in Rust |
| cmp5 | 75 | Kompaktieren |
| addsub2 | 638 (25×5×17) | Auftrag 08 |
| addsub4 | 5452 (91×7×54) | Auftrag 08 |

## Wo die Größe herkommt (Befunde aus `docs/backlog.md`, „M4 Entwurf“ und „Kleinere Bausteine“)

1. **Grundbausteine sind groß.** Mehrheit 3, XNOR, AND3, Halbaddierer, mux2 haben keine kleinen Vorlagen. Bekannter
   Engpass: ein stark versorgter Block (Hebel daran, Verstärker davor) speist jeden Staub daneben.
2. **Zerlegung wählt nach Volumen.** `decompose._pairs` und `_design_part` nehmen das Paar mit dem kleinsten
   Volumen; ein PLA als Teil schlägt so eine Kaskade kleiner Stufen (addsub4: PLA 7 Eingänge statt Bit-Kaskade;
   kleinstes G zuerst gäbe 4622 Blöcke, aber mehr Volumen).
3. **Kaskaden liegen in einer Linie.** Stufen nebeneinander statt hintereinander würden Leitungen sparen.
4. **Kompaktieren hat nur kleine Züge.** Es fehlen große Züge (ganze Stufen neu anordnen); `compact.relocations`
   (`_dust_path`, Python) ist bei großen Entwürfen der Engpass und überzieht `--time`.

## Schritte

1. Messliste festlegen und Ausgangszahlen nachrechnen (Blöcke, Volumen, Laufzeit nur als Größenordnung: der Nutzer
   spielt nebenbei). Ergebnis als Tabelle in diesen Auftrag.
2. **Bausteine:** mit `scripts/mine_templates.py` (Muster: `scripts/enum_xor.py`) kleinere Vorlagen für Mehrheit 3,
   XNOR, AND3, Halbaddierer, mux2 suchen. Idee des Nutzers: bekannte Bauweisen aus Wiki/Community als Startentwürfe
   (eigene Zählweise mit Stützblöcken beachten). Jede neue Vorlage: ortsfest, ansteuerbar, `tpl-*` neu aufnehmen.
3. **Wahl in der Zerlegung:** Auswahl nach Blöcken statt Volumen (oder gewichtet) ausprobieren; addsub4 als
   Prüfstein. Kaskadenstufen nebeneinander anordnen (Variante in `compose`).
4. **Kompaktieren:** Zeitlimit in `relocations` prüfen, `_dust_path` nach Rust (beide Kerne bleiben gleich), danach
   einen großen Zug „Stufe verschieben“.
5. Nach jedem Teil: Messliste erneut, betroffene `cmp-*`/`tpl-*` neu erzeugen und im Spiel aufnehmen
   (`uv run rsx oracle … --golden`, Läufe über 5 Minuten vorher ansagen).

## Abnahme

- Tabelle vorher/nachher für die Messliste; Summe der Blöcke mindestens 25 % kleiner, kein Beispiel größer.
- Alle geänderten Entwürfe ortsfest und im Spiel aufgenommen, Simulator identisch.
- `uv run pytest -q --slow` grün (Entwurfssuche geändert).

## Abbruch

Nach zwei Arbeits-Sessions weniger als 10 % gespart: Befund (welcher Hebel was brachte) hierher schreiben, Zeile in
`STATUS.md` als „blockiert“ markieren.
