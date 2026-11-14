# GUI (M6): Aufbau und JSON-Schnittstelle

`uv run rsx gui [datei]` startet einen lokalen Server (nur `127.0.0.1`, Standardport 8737, Python-Standardbibliothek)
und öffnet den Browser (`--port N`, `--no-browser`). Mit Datei öffnet der Browser `/?path=<pfad>`, die
Oberfläche lädt diese Datei dann gleich. Die Oberfläche ist eine statische Web-App ohne Build-Schritt.

Pfade in Anfragen sind relativ zum Repository; Dateien außerhalb (außer der beim Start angegebenen) lehnt der
Server mit 403 ab. Jede Simulation läuft in einem eigenen Thread (Rust-Welten sind an ihren Thread gebunden),
höchstens 16 gleichzeitig (die älteste fällt weg).

| Teil | Ort | Inhalt |
|---|---|---|
| Server | `src/redstone/gui/server.py` | HTTP-Server, Sitzungen (Simulation, Entwurfssuche), JSON-API unten |
| Modell | `src/redstone/gui/model.py` | Grid → Modell-JSON (Blöcke, Ein-/Ausgänge, Material, Bau-Reihenfolge) |
| Material, Bauen | `src/redstone/gui/materials.py` | `materials(grid)`, `build_order(grid)` |
| Aufzeichnung | `src/redstone/design/observe.py` | Einzelbilder aus Komposition und Kompaktieren |
| Übrige Befehle | `src/redstone/gui/tools.py` | Analyse, Text-Ansicht, Szenario-Lauf, Export als Funktionen für den Server |
| Oberfläche | `src/redstone/gui/static/` | `index.html`, `app.js`, `style.css`, weitere ES-Module (`docs.js` Berichte, `speceditor.js` Editor) |

Die Oberfläche lädt three.js als ES-Modul per Import-Map von `https://unpkg.com/three@0.160.0/` (inkl.
`examples/jsm/controls/OrbitControls.js`); weitere Bibliotheken gibt es nicht. Texte der Oberfläche auf Deutsch.

## Grundformate

- **Position** `p`: `[x, y, z]`, ganzzahlig, relativ zur Min-Ecke des Modells (0 … size−1). y ist oben,
  x Osten, z Süden (wie im Spiel).
- **Blockzustand** `s`: Zustandsstring wie im Szenarioformat, ohne `minecraft:`, z. B. `stone`,
  `redstone_wire[east=side,north=none,power=15,south=side,west=none]`, `repeater[delay=2,facing=north,locked=false,powered=true]`.
  Luft kommt in Blocklisten nicht vor; `air` in einer Änderungsliste heißt „Block entfernt“.
- **Block** `{"p": [x, y, z], "s": "<zustand>"}`.

## Modell

```json
{
  "name": "cmp4",
  "size": [18, 8, 22],
  "blocks": [{"p": [0, 2, 8], "s": "stone"}, ...],
  "inputs":  [{"name": "a3", "p": [2, 3, 10]}],
  "outputs": [{"name": "gt", "p": [16, 3, 4]}],
  "materials": [{"item": "redstone", "label": "Redstone-Staub", "count": 120}, ...],
  "build_order": [[0, 2, 8], [0, 3, 8], ...],
  "notes": ["…"]
}
```

`materials`: benötigte Gegenstände (nicht Blockzustände), absteigend nach Anzahl; z. B. Wandfackel →
`redstone_torch`, Staub → `redstone`, Doppelstufe → 2× Stufe, Kolbenkopf zählt nicht. `build_order`: alle
Blockpositionen in einer Reihenfolge, in der man sie im Spiel setzen kann (Stützblock vor Staub, Fackel, Diode,
Hebel; unten nach oben). Positionen ohne Gegenstand (Kolbenkopf, obere Türhälfte …) fehlen. `inputs`/`outputs`: Hebel/Knöpfe bzw. Lampen (bei Szenarien die Probes, bei Entwürfen
die Ports des Kandidaten). `notes`: optionale Hinweise (deutsch).

## Endpunkte

Alle Antworten sind JSON; Fehler als HTTP 4xx/5xx mit `{"error": "<deutscher Text>"}`.

| Methode, Pfad | Anfrage | Antwort |
|---|---|---|
| `GET /` | – | `static/index.html` (weitere Dateien unter `/static/…`) |
| `GET /api/files` | – | `{"schematics": [...], "scenarios": [...], "specs": [...]}`: Pfade relativ zum Repo (Beispiele, Szenarien, Spezifikationen) |
| `GET /api/model?path=P` | Schaltplan (`.litematic`, `.schem`, `.nbt`) oder Szenario (`.yaml` mit `build`) | Modell |
| `POST /api/sim` | `{"path": P}` oder `{"job": J}` (Ergebnis einer Suche) | `{"sim": id, "tick": 0, "model": Modell}` |
| `POST /api/sim/<id>/use` | `{"p": [x, y, z]}` (Hebel umlegen, Knopf drücken) | `{"tick": t, "changed": [Block, ...]}` |
| `POST /api/sim/<id>/tick` | `{"n": 1}` (1 … 1000 Ticks) | `{"tick": t, "changed": [Block, ...]}` |
| `POST /api/redesign` | `{"path": P, "compact": 100, …}` (Spezifikation `.yaml` oder Schaltplan; Optionen unten) | `{"job": id}` |
| `GET /api/job/<id>?since=k` | – | Job (unten), nur Einzelbilder ab Nummer `k` |
| `GET /api/info` | – | `{"core": "rust", "rust": true, "rust_error": null, "formats": [...]}` |
| `POST /api/core` | `{"core": "rust"\|"python"\|"auto"}` | `{"core": name}`; gilt für neue Welten |
| `GET /api/text?path=P` | Textdatei (`.yaml`, `.md`, `.txt`, `.json`) | `{"path": P, "text": "…"}` |
| `POST /api/upload?name=N` | Dateiinhalt als Körper (bis 64 MiB; `.litematic`, `.schem`, `.nbt`, `.yaml`) | `{"path": P, "group": "schematics"\|"scenarios"\|"specs"}` |
| `POST /api/spec` | `{"name": N, "text": YAML}` (Spezifikation aus dem Editor) | wie Upload |
| `POST /api/explain` | Quelle | `{"markdown": "…", "svgs": {"in1.svg": "<svg…"}}` (`rsx explain`) |
| `POST /api/dump` | Quelle plus `layers` (Liste), `components` (Standard an), `states` | `{"name": N, "text": "…"}` (`rsx dump`) |
| `POST /api/scenario` | `{"path": P}` | Szenario-Lauf (unten; `rsx sim --diff`) |
| `POST /api/oracle` | `{"path": P, "golden": false}` | `{"job": id}`; Aufnahme im Spiel, höchstens eine zugleich (sonst 409) |
| `GET /api/export?path=P\|job=J&format=F` | – | Datei (`Content-Disposition: attachment`) |

`changed` enthält alle Positionen, deren Zustand sich gegenüber der letzten Antwort dieser Sitzung geändert hat
(Staubstärke, `powered`, `lit`, Kolben …), mit dem neuen Zustand. Ein Comparator bekommt im Zustand zusätzlich
`|output=<0…15>` (wie die Probe-Werte im Trace-Format).

**Quelle** heißt `{"path": P}` (Datei) oder `{"job": J}` (bester Entwurf einer fertigen Suche).

Hochgeladene Dateien und Spezifikationen aus dem Editor liegen in `.cache/gui/uploads/` bzw. `.cache/gui/specs/`
(nicht in Git) und erscheinen in `/api/files` in ihrer Gruppe vorn.

Optionen von `/api/redesign` (alle optional, wie die Schalter von `rsx redesign`): `compact` (Versuche, 0 = aus),
`time` (Sekunden), `top`, `max_size` (`[x, y, z]` oder `"X,Y,Z"`), `max_delay` (gt), `allow` und `forbid`
(Block-IDs als Liste oder mit Komma getrennt; Wandfackel zählt als Fackel), `no_qc`, `outputs` (`"out1,out3"`
oder `"all"`).

Formate von `/api/export`: `litematic`, `schem`, `nbt` (`rsx convert`), `materials`, `dump`, `guide` (Material
plus Ebenen als Text), `scenario` (kompiliertes Szenario-JSON, `rsx compile`; nur Szenario-Dateien), `report`
(Markdown-Bericht einer Suche; nur `job`).

Szenario-Lauf: `{"name", "description", "ticks", "diagram": ASCII, "svg", "warnings": [...], "golden": null |
{"matches": bool, "count": n, "mismatches": [Text, ...]}}`. Ein Oracle-Job hat keine Einzelbilder; sein `result` ist
`{"name", "ticks", "diagram", "svg", "simulator": Vergleich wie golden, "written": Pfad des Golden Trace oder null}`.
Jeder Job nennt seine Art in `kind` (`redesign` oder `oracle`).

### Job (Entwurfssuche)

```json
{
  "done": false,
  "error": null,
  "frames": [{"i": 0, "phase": "compose", "label": "cmp1-comparator → cmp-stage-comparator",
              "accepted": true, "size": [12, 6, 9], "blocks": [Block, ...]}, ...],
  "log": ["Ebene x=3 entfernt", ...],
  "result": null
}
```

`log`: Kompaktier-Protokoll, wächst während der Suche (immer vollständig). `error`: deutscher Text, auch wenn
kein funktionierender Entwurf gefunden wurde (dann `result` nur mit `summary`).
`phase`: `compose` (ein fertig zusammengesetzter Kandidat) oder `compact` (ein Kompaktier-Versuch; `accepted`
sagt, ob er funktioniert und übernommen wurde). Einzelbilder sind vollständige Blocklisten, jeweils auf ihre
eigene Min-Ecke bezogen. Höchstens 3000 Einzelbilder je Job (danach nur noch übernommene). `result` am Ende:
Modell des besten Entwurfs plus `"summary"` (deutscher Bericht von `rsx redesign`).

## Aufbau der Oberfläche

Drei Spalten als schwebende Karten (dunkel oder hell nach Systemeinstellung, Schrift Geist von Google Fonts,
Icons in `static/icons.js`), nach Aufgaben statt nach Funktionen geordnet und für Leute ohne Redstone-Vorwissen
beschriftet. Die **aktuelle Schaltung** (Name oben in der Leiste)
ist die geladene Datei oder der beste Entwurf der letzten Suche; alle Aufgaben arbeiten auf ihr.

- **Dateien (links, mit ☰ ausblendbar)**: „Öffnen“ (auch Ziehen ins Fenster), „Entwerfen“, Suchfeld über alle
  Dateien, Reiter Schaltpläne / Beispiele (= Szenarien, oben eine Auswahl „Zum Einstieg“ mit Klarnamen) /
  Vorgaben (= Spezifikationen).
- **Ansichten (Mitte)**: 3D (vereinfachte Blockformen, Orbit-Steuerung, Ebenen oberhalb ausblendbar) und Ebene
  (Draufsicht einer y-Ebene, Ebene darunter blass, Tooltip mit Zustand); oben rechts umschaltbar. Darunter die
  Abspielleiste: Bauanleitung Block für Block, Schritte einer Entwurfssuche oder die Zeit der Simulation.
  Ohne Schaltung steht dort ein Startbildschirm (öffnen, Beispiel, neu entwerfen).
- **Arbeitsbereich (rechts, Breite ziehbar)** mit einem Reiter je Aufgabe:
  - *Nachbauen*: Hinweise, Material (Summe, Stacks, Kisten), Herunterladen in allen Formaten.
  - *Ausprobieren*: startet die Simulation selbst; Ein- und Ausgänge mit Namen (Eingänge anklickbar, ebenso Hebel
    und Knöpfe in den Ansichten), „Von vorn beginnen“. Bei Szenarien: Testablauf simulieren (Zeitdiagramm, Vergleich
    mit der Spielaufnahme) und im echten Spiel prüfen.
  - *Verstehen*: Analyse (Markdown gerendert, Zeitdiagramme als SVG) und Text-Ansicht, jeweils speicherbar.
  - *Entwerfen*: 1 Ziel: Wunsch-Karten mit wenigen Reglern (`static/wizard.js`: Lampe nach Regel, Umkehrer,
    Impuls, Nachleuchten, Ein/Aus per Knopf, zwei Knöpfe, Blinker, Verzögerung, Addierer; jede schreibt das YAML
    der Spezifikation, der Texteditor darunter zeigt es und dient für „Eigene Vorgabe“), oder die geladene
    Schaltung verkleinern,
    2 Grenzen (Optionen der Suche), 3 Ergebnis (Zustand, Suchverlauf, Bericht; Knöpfe zum Nachbauen, Simulieren,
    Analysieren des Entwurfs).

Fensteraufteilung (Ansicht, Breite des Arbeitsbereichs, Dateiliste) merkt sich der Browser (`localStorage`).

### URL-Parameter (zum Testen und für Screenshots)

`/?path=<Datei>&task=build|sim|analyze|design&layout=3d|2d|split&y=<Ebene>&cam=px,py,pz,tx,ty,tz&click=…` – `path`
wählt eine Datei vor, `task` den Reiter, `layout` die Ansicht, `y` die Ebene der 2D-Ansicht, `cam` Kameraposition
und Blickziel der 3D-Ansicht. `click` drückt nacheinander Knöpfe (Element-IDs, je 1,2 s Abstand), `task:sim` usw.
wechselt den Reiter, eine Zahl wartet so viele Millisekunden, z. B. `click=wExample,800,sRun` oder
`path=examples/specs/xor.yaml&click=btnRedesign,7000`.
