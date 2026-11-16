# 07 Kleinere Grundbausteine per Offline-Suche

Modell: Opus · hängt ab von: nichts (01 hilft: Funde ortsfest prüfen) · zeitlich begrenzt auf zwei Sessions

## Ziel

Kleinere Vorlagen für die Bausteine, aus denen fast jeder Entwurf besteht: XOR unter 20 Blöcken (heute 28–33),
Mehrheit von 3 unter 40 (heute 58 als PLA). Nebenbei die kleinen Größenpunkte der alten Übergabe.

## Warum

Zusammengesetzte Entwürfe sind so groß wie ihre Teile plus Leitungen. Ein Addierer, ein Komparator, ein
Codeschloss enthalten viele XOR/AND-Stufen; jeder gesparte Block je Baustein zählt mehrfach. Eine SAT/SMT-Suche
nach Topologien (alter Plan) löst das nicht: die Topologie ist bekannt, die räumliche Bauweise ist das Problem.
Der Rust-Kern bewertet kleine Kandidaten in unter einer Millisekunde; das reicht für eine gezielte Mutationssuche.

## Einstieg

- Vorlagen: `src/redstone/design/templates.py` (`_register`, `_Layout`, `_xor2`, `_xor2_repeater`, `_supported`,
  `_settle`); Namen: `xor2-comparator`, `xor2-comparator-repeater`, `and2-torch`, `mux2-comparator-select` …
- Bewertung: `design/evaluate.py: evaluate(candidate, spec, full=False, stop_early=True)` als Schnellprüfung, danach voll.
- Züge, die es schon gibt: `design/compact.py` (`_cut` Ebene entfernen, `_without` Block entfernen, `shifts`,
  `rerouted`, `relocations`, `_local_key` gegen wiederholte Fehlversuche, `normalize`).
- Im Spiel prüfen: `scripts/template_scenarios.py` erzeugt `scenarios/tpl-*.yaml` für alle Vorlagen.
- Ansteuerbarkeit eines Eingangs durch eine Leitung: `design/decompose.py: drivable_first`.

## Schritte

1. `scripts/mine_templates.py <spec.yaml> [--box X,Y,Z] [--hours H] [--seed N]`:
   - Start: alle funktionierenden Kandidaten für die Spezifikation (Vorlagen, PLA, kompaktiert).
   - Züge: Block entfernen; Block durch ein anderes Bauteil aus einem kleinen Alphabet ersetzen (Stein, Staub,
     Fackel, Wandfackel 4 Richtungen, Verstärker 4 Richtungen, Komparator 4 Richtungen × 2 Modi, Luft); Block
     verschieben; Ebene schneiden; Hebel oder Lampe um ein Feld versetzen.
   - Annahme wie Simulated Annealing auf (Blockzahl, Volumen); nur funktionierende Kandidaten bleiben im
     Bestand, aber ein kleiner Anteil fast richtiger (ein falscher Fall der Wahrheitstabelle) darf als
     Zwischenschritt leben. Wiederholungen über einen Hash des Grids vermeiden.
   - Jeden Fund voll prüfen (`evaluate(..., full=True)`), nach Auftrag 01 zusätzlich `robust`, und als
     `.litematic` nach `.cache/mined/` schreiben; am Ende eine Tabelle (Blöcke, Maße, Verzögerung).
2. Läufe: XOR (2 Eingänge), XNOR, Mehrheit von 3, AND3, Halbaddierer, 2:1-Multiplexer. Je Spezifikation erst
   10 Minuten; nur wo es Funde gibt, länger.
3. Funde als Vorlagen eintragen (Zellen als Layout-Funktion, Beschreibung in Alltagssprache, Eingänge darauf
   prüfen, ob sie ansteuerbar sind), `scripts/template_scenarios.py` laufen lassen, neue `tpl-*` im Spiel aufnehmen.
4. Kleine Punkte, nur wenn Zeit bleibt und jeweils mit Neuaufnahme des betroffenen `cmp-*`-Szenarios:
   - mux8 wird beim Kompaktieren kaum kleiner (371 → 354 Blöcke, 10 hoch): in `_shannon` die mux2-Teile in
     einer Reihe statt übereinander anordnen (Reihenfolge der Layouts in `compose.chains`).
   - `drivable-pla` könnte `mux2-comparator-select` nutzen.

## Abnahme

- Tabelle der Funde in `docs/history.md`; mindestens eine neue, im Spiel bestätigte Vorlage, die kleiner ist als
  die bisher kleinste für dieselbe Funktion.
- `uv run pytest -q --slow` grün; alle `examples/specs/**` werden nicht größer (vorher/nachher festhalten).
- Geänderte `cmp-*`-Entwürfe (kleinere Bausteine ändern die Kompositionen!) neu aufgenommen und identisch.

## Fallstricke

- Neue Vorlagen ändern fast alle zusammengesetzten Entwürfe und damit eingefrorene Szenarien. Vor dem Eintragen
  `scripts/compose_scenarios.py` laufen lassen und sehen, welche `cmp-*` sich ändern; die Neuaufnahme (cmp5 und
  mux8 dauern Minuten bis eine halbe Stunde in der Suche) beim Nutzer ansagen.
- Ein Fund, der nur durch knappes Timing funktioniert, ist nichts wert: volle Prüfung mit Übergängen ist Pflicht.
- Eine Lampe direkt an einer Fackel oder ein Hebel direkt am Ausgang kann die Tabelle erfüllen, ohne dass sich
  der Baustein verketten lässt: für jeden Fund `drivable_first` und eine Verkettung hinter `buffer-dust` prüfen.

## Abbruch

Zwei Sessions ohne Fund unter den Zielwerten: Ergebnis (bester Fund je Funktion, Zahl der bewerteten Kandidaten)
notieren und schließen. Das Skript bleibt.
