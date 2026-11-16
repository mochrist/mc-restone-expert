# 06 Berichte in Alltagssprache, Bauanleitung als Bild, große Entwürfe flüssig

Modell: Sonnet · hängt ab von: nichts · drei unabhängige Teile, jeder für sich abschließbar

## Ziel

Die Reiter „Verstehen“ und „Entwerfen“ zeigen zuerst eine kurze Erklärung, die ein Laie versteht; die
Bauanleitung gibt es als druckbare Datei mit einem Bild je Ebene; Entwürfe mit 500–900 Blöcken ruckeln nicht.

## Warum

Der Nutzer ist kein Redstone-Profi (Rückmeldung Session 19). Die Berichte von `rsx explain` und `rsx redesign`
sind fachsprachlich; nur der Assistent übersetzt sie, und der braucht einen API-Schlüssel.

## Einstieg

- Berichte: `src/redstone/design/report.py: report`, `src/redstone/analysis/explain.py`; Daten dahinter:
  `Evaluation`, `Candidate` (`description`, `origin`, `size`, `block_count`), `Analysis` (`analysis/analyze.py`).
- Server: `gui/tools.py: explain`, `guide`, `export`; `gui/server.py` (`/api/explain`, `/api/redesign`,
  `/api/export`); Vertrag `docs/gui-api.md`.
- Oberfläche: `gui/static/docs.js` (Markdown-Renderer), `app.js`, `layers2d.js` (Ebenen-Ansicht), `blocks3d.js`
  (3D, three.js 0.160), `blockstyle.js` (Farben), `gui/materials.py` (deutsche Blocknamen).

## Teil A: Erklärung in Alltagssprache (regelbasiert, kein Modellaufruf)

1. `src/redstone/render/plain.py`: `plain_design(spec, evaluation) -> str` und `plain_analysis(analysis) -> str`,
   je vier kurze Abschnitte: „Was es tut“ (aus der Spezifikation: z. B. „Die Lampe leuchtet, wenn a und b an
   sind“, bei bis zu 3 Eingängen als Liste der Fälle; Zeiten in Sekunden), „So bedienst du es“ (Eingänge mit
   Art und Namen), „Größe und Material“ (Maße, Blockzahl, die fünf häufigsten Blöcke mit deutschen Namen aus
   `gui/materials.py`), „Gut zu wissen“ (Verzögerung in Sekunden; Warnungen nur, wenn vorhanden). Keine Wörter
   wie Komparator, PLA, Zerlegung, gt ohne Erklärung.
2. `/api/explain` und das Ergebnis von `/api/redesign` liefern zusätzlich das Feld `plain`; die Reiter zeigen es
   oben, der Fachbericht steht darunter eingeklappt („Details für Fortgeschrittene“).
3. Tests `tests/unit/test_plain.py`: XOR, Monoflop 8 gt, Blinker; kein Fachwort aus einer Verbotsliste im Text.

## Teil B: Bauanleitung zum Drucken

1. `gui/tools.py: guide_html(grid, title) -> str`: eine eigenständige HTML-Datei, je Ebene (von unten nach oben)
   ein SVG-Raster mit denselben Farben und Symbolen wie die Ebenen-Ansicht, Legende, Materialliste, Hinweis zur
   Blickrichtung (Norden oben). Blöcke der Ebene darunter blass als Orientierung.
2. `/api/export?format=guide-html` und ein Knopf „Bauanleitung drucken“ im Reiter „Nachbauen“.
3. Test: Datei enthält ein `<svg>` je Ebene; Richtungen von Verstärkern stimmen für alle vier `facing`.

## Teil C: Große Entwürfe

1. Messen: `uv run rsx gui examples/…` mit dem Entwurf von `cmp5` (533 Blöcke) und
   `tests/fixtures/external/seg7.litematic` (902): Bilder je Sekunde beim Drehen (Chrome Performance), Zeit bis zum ersten Bild.
2. `blocks3d.js`: ein `InstancedMesh` je Blockform und Material statt eines Mesh je Block; Zustandswechsel in
   der Simulation ändern nur Instanzfarbe bzw. tauschen die Instanz. Umrandung und Tooltip bleiben.
3. Ebenen-Ansicht: nur die sichtbare Ebene neu zeichnen.

## Abnahme

- A: Tests grün; Screenshot beider Reiter an den Nutzer.
- B: gedruckte Vorschau (PDF aus Chrome) von `xor` und `adder2` an den Nutzer.
- C: `seg7` dreht mit mindestens 30 Bildern je Sekunde; Messwerte vorher/nachher in `docs/history.md`.
- `uv run pytest tests/gui tests/unit -q` grün.

## Fallstricke

- three.js wird per Import-Map geladen (keine Build-Stufe); nichts einführen, was einen Bundler braucht.
- Die Demo-Daten (`static/demo/model.json`, `scripts/gui_demo_data.py`) müssen weiter laden (`?demo=1`).
- Stil beibehalten: dunkler Grund, schwebende Karten, eine Akzentfarbe, Alltagssprache.

## Abbruch

Teil C: Bringt Instancing nach einer Session unter 30 % Gewinn, zurücknehmen und nur die Messung festhalten.
