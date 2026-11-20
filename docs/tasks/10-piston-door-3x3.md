# 10 Kolbentür 3×3 im Katalog

Modell: Fable plant (diese Datei ausarbeiten, keine Programmänderung), danach Opus · hängt ab von: – ·
mittlere Priorität (Wunsch des Nutzers, Session 27)

## Ziel

Neuer Katalog-Eintrag `piston-door-3x3`: Eine Tür aus 9 Steinziegeln, drei breit und drei hoch, bündig in einer Wand.
Hebel an öffnet sie, Hebel aus schließt sie. Sie wird im Spiel aufgenommen wie die 2×2-Tür.

## Warum das schwer ist (Befund Session 27)

- Ein Kolben bewegt einen Block genau einen Schritt, ein klebriger Kolben zieht genau einen Block zurück. Bei 2×2
  reicht das (jeder Block einen Schritt in eine Tasche in der Wand, `catalog/entries.py: _piston_door_2x2`).
- Bei 3×3 kommt der **mittlere Block** mit einem Schritt nirgends hin: Ringsum stehen die acht anderen Türblöcke,
  vorn und hinten liegt der Durchgang. Er muss mindestens zwei Schritte gehen, also über einen doppelten
  Kolbenausfahrer (DPE, zwei Kolben hintereinander) oder eine Übergabe zwischen zwei Kolben, beides mit fester
  Reihenfolge beim Öffnen und umgekehrt beim Schließen.
- Schleimblöcke helfen nur begrenzt: Schiebegrenze 12 Blöcke, ein Zug ist auch damit nur ein Schritt, und Schleim
  hinter der Tür wäre von hinten sichtbar.

## Für die Planung (Fable)

Vor der Arbeit zu entscheiden und hier festzuhalten:

1. Bauweise: Welche Blöcke gehen wohin (z. B. obere Reihe hoch, untere runter, Mitte links/rechts, Mittelblock
   per DPE von unten oder oben)? Eine bekannte Community-Bauweise als Vorbild nennen (Quelle) und an unsere Zählweise
   anpassen (Stützblöcke, Ursprung (0, 200, 0)).
2. Ablaufplan in Ticks für Öffnen und Schließen: welcher Kolben wann (Verstärker-Verzögerungen) und welche
   Zwischenzustände erlaubt sind.
3. Was passiert bei schnellem Umlegen (die 2×2-Prüfung schaltet nach 2 und 4 gt zurück)? Darf die Tür dann stecken
   bleiben, oder muss die Steuerung das abfangen (z. B. Impuls erst nach voller Laufzeit annehmen)?
4. Zerlegung in Schritte, die einzeln prüfbar sind (erst Mittelblock allein mit DPE, dann Rahmen, dann Steuerung).

## Einstieg (für die Arbeit)

- `src/redstone/catalog/entries.py`: `_piston_door_2x2`, `_check_piston_door`, `Run`, `_settle`, Eintrag in `ENTRIES`.
- `scripts/catalog_scenarios.py: piston_door` als Vorbild für `cat-piston-door-3x3`.
- `tests/catalog/test_catalog.py`: Abnahme, Suche, alle Orte und Drehungen.
- Kolbenverhalten: `knowledge/` (Kolben, Quasi-Connectivity, Update-Reihenfolge); Golden Traces mit Kolben in
  `tests/golden/` zeigen, was der Simulator sicher kann.

## Abnahme

- `get("piston-door-3x3").accept()` leer: 10 Zyklen auf/zu mit vollem Durchgang (alle 9 Felder Luft bzw. Steinziegel),
  Zahl der Steinziegel bleibt gleich, Verhalten bei schnellem Umlegen wie in der Planung festgelegt.
- Alle Orte und Drehungen (`test_position_and_rotation_proof`), Suche „kolbentür 3x3“ findet den Eintrag.
- `cat-piston-door-3x3` im Spiel aufgenommen, Simulator identisch.

## Abbruch

Nach zwei Arbeits-Sessions keine Tür, die im Simulator die Abnahme besteht: Befund (welcher Schritt scheitert)
hierher schreiben, Zeile in `STATUS.md` als „blockiert“ markieren.
