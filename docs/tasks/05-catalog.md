# 05 Katalog fertiger Bauwerke

Modell: Opus · hängt ab von: 01 (für die Prüfung an mehreren Positionen; ohne 01 nur am Ursprung prüfen und
das im Eintrag vermerken) · nicht gleichzeitig mit 04 (`gui/assistant.py`)

## Ziel

Der Assistent und die Oberfläche bieten einige fertige, geprüfte Bauwerke an, die sich nicht aus einer
Wahrheitstabelle oder einem Zeitverhalten herleiten lassen: zuerst eine 2×2-Kolbentür, einen Itemsortierer und
eine versteckte 1×2-Tür.

## Warum

Die häufigsten Laien-Wünsche („Kolbentür“, „Itemsortierer“) lehnt der Assistent heute ab
(`scripts/assistant_eval.py`, Fall `itemsortierer`). Die Entwurfssuche kann solche Bauwerke grundsätzlich nicht
finden: ihr Ausgang ist kein Lampenzustand, sondern bewegte Blöcke oder sortierte Items.

## Einstieg

- Vorlagen als Code: `src/redstone/design/templates.py` (`_Layout`, `_grid_from_layout`, `_settle`) und
  `seq_templates.py` zeigen, wie ein Bauwerk als Zellen-Wörterbuch entsteht und eingeschwungen wird.
- Simulator: Kolben (`sim/blocks/piston.py`), Trichter/Truhen/Komparator an Behältern
  (`sim/blocks/dispenser_hopper.py`, `container.py`, `chest.py`), alle im Spiel geprüft
  (`scenarios/piston-*`, `hopper-*`, `chest-*`: dort nachsehen, wie Items in Block-Entities stehen).
- Assistent: `gui/assistant.py: Chat._examples`, `_find`, Werkzeuge `find_examples`/`load_example`.
- Dateiliste der Oberfläche: `gui/server.py: State.files`.
- Echte Vergleichsstücke: `tests/fixtures/external/piston-gate-3x3.litematic` (nur ansehen: `uv run rsx dump …`,
  `uv run rsx explain …`; Lizenz unklar, nichts daraus kopieren).

## Schritte

1. Paket `src/redstone/catalog/`: `Entry` (Schlüssel, Titel, Stichworte, Beschreibung und Bedienung in
   Alltagssprache, `build() -> Grid`, Eingänge, Abnahme-Funktion) und `ENTRIES`. `uv run rsx catalog [name] [-o datei]`
   listet bzw. schreibt ein Bauwerk.
2. **Je Bauwerk zuerst die Abnahme als Test**, dann bauen, bis der Test im Simulator besteht:
   - 2×2-Kolbentür (vier klebrige Kolben, ein Hebel, bündig in einer Wand): Hebel an → die vier Zellen der
     Öffnung sind Luft; Hebel aus → dort stehen wieder die vier Blöcke; zehn Zyklen im Abstand von 20 gt und
     einmal mit 4 gt Abstand (schnelles Umlegen) lassen keinen Block liegen.
   - Itemsortierer, ein Fach (Trichter mit Filter-Items, Komparator, Fackel sperrt den unteren Trichter): 64
     Filter-Items und 64 andere in die Eingangstruhe → nach N Ticks liegen genau die Filter-Items in der
     Zieltruhe und die anderen im Überlauf; im Filter-Trichter liegt der Anfangsbestand.
   - Versteckte 1×2-Tür (zwei klebrige Kolben seitlich, Knopf, bleibt 3 s offen): Öffnung nach Knopfdruck Luft,
     nach Ablauf wieder zu.
3. Jedes Bauwerk als Szenario (`scenarios/cat-<name>.yaml`) im Spiel aufnehmen, identisch zum Simulator.
4. Nach Auftrag 01: Abnahme an den Ursprüngen und Drehungen aus `design/robust.py` wiederholen; ein Bauwerk, das
   nicht überall besteht, wird umgebaut (meist: gleiche Leitungslängen zu den Kolben, Verstärker davor) oder nicht aufgenommen.
5. Assistent: `find_examples` und `load_example` durchsuchen auch den Katalog (Stichworte); Systemprompt: Katalog
   nennen, Kolbentür und Itemsortierer aus der Liste „kann die App nicht“ streichen. Oberfläche: Reiter
   „Zum Einstieg“ zeigt die Katalog-Einträge mit Klarnamen.
6. `scripts/assistant_eval.py`: Fall `itemsortierer` erwartet jetzt einen geladenen Eintrag, neuer Fall „Kolbentür“.

## Abnahme

- `tests/catalog/test_catalog.py` grün (Abnahme jedes Eintrags, beide Kerne).
- Golden Traces der `cat-*`-Szenarien identisch.
- Im Browser: Eintrag laden, in der Simulation Hebel umlegen, Tür öffnet sich (Screenshot/GIF an den Nutzer).

## Fallstricke

- Klebrige Kolben lassen bei 1-Tick-Pulsen ihren Block liegen; die Abnahme mit schnellem Umlegen deckt das auf.
- Der Simulator hat keine Item-Entities: Der Sortierer darf nichts auswerfen; Überlauf geht in eine Truhe.
- Die Trichter-Reihenfolge und Abkühlzeiten sind im Simulator gegen das Spiel geprüft; wenn der Sortierer im
  Spiel anders läuft als im Simulator, ist das ein Simulatorfehler (Regeln in `docs/tasks/README.md`).
- Quasi-Connectivity nur nutzen, wenn nötig; im Eintrag vermerken.

## Abbruch

Je Bauwerk höchstens eine Session. Wird ein Bauwerk im Simulator nicht stabil, weglassen und in
`docs/backlog.md` notieren, woran es lag. Zwei Einträge genügen für den Abschluss.
