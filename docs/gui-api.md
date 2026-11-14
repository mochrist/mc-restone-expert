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
| Oberfläche | `src/redstone/gui/static/` | `index.html`, `app.js`, `style.css`, weitere ES-Module |

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
| `POST /api/redesign` | `{"path": P, "compact": 100}` (Spezifikation `.yaml` oder Schaltplan) | `{"job": id}` |
| `GET /api/job/<id>?since=k` | – | Job (unten), nur Einzelbilder ab Nummer `k` |

`changed` enthält alle Positionen, deren Zustand sich gegenüber der letzten Antwort dieser Sitzung geändert hat
(Staubstärke, `powered`, `lit`, Kolben …), mit dem neuen Zustand. Ein Comparator bekommt im Zustand zusätzlich
`|output=<0…15>` (wie die Probe-Werte im Trace-Format).

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

## Ansichten der Oberfläche

- **3D**: Blöcke als vereinfachte Formen (Vollblock, Staub als flache Linie mit Stärke-Farbe und Verbindungen,
  Fackel, Verstärker/Comparator als Platte mit Richtungspfeil, Hebel, Lampe leuchtend wenn `lit=true`, Kolben),
  Orbit-Steuerung, Klick auf Hebel/Knopf in der Simulation = `use`. Ebenen über der gewählten ausblendbar.
- **2D / Ebenen**: Draufsicht einer y-Ebene (Schieberegler), Kacheln mit Symbol je Blockart, darunter die Ebene
  darunter blass; Tooltip mit Zustand.
- **Material**: Tabelle aus `materials`, Summe, Stapel (64er) und Kisten.
- **Abspielen**: Bau-Reihenfolge (`build_order`) Block für Block, Einzelbilder einer Entwurfssuche, Simulation
  (Ticks); jeweils Start/Pause/Schritt und Tempo-Regler.

### URL-Parameter (zum Testen und für Screenshots)

`/?path=<Datei>&layout=3d|2d|split&y=<Ebene>&cam=px,py,pz,tx,ty,tz` – `path` wählt eine Datei vor, `layout` die Ansicht,
`y` die Ebene der 2D-Ansicht, `cam` Kameraposition und Blickziel der 3D-Ansicht.
