# Szenario- und Trace-Format

Simulator (`src/redstone/sim`) und Oracle (`oracle/`, Fabric-Server) führen **dasselbe** Szenario aus
und erzeugen **dasselbe** Trace-Format. Ein Diff der Traces ist der Validierungstest.

## 1. Szenario (YAML, von Menschen geschrieben)

```yaml
name: repeater-delay-2          # eindeutig, [a-z0-9-]+
description: Repeater mit Delay 2 zwischen Hebel und Lampe
# Entweder eine Schematic-Datei (relativ zur YAML-Datei) ...
schematic: repeater.litematic
# ... oder ein Inline-Aufbau:
build:
  size: [4, 2, 1]               # x, y, z
  fill:                         # optional, Quader [x1,y1,z1, x2,y2,z2, state], vor "blocks" angewendet
    - [0, 0, 0, 3, 0, 0, "stone"]
  block_entities:               # optional, [x,y,z, SNBT]
    - [3, 1, 0, '{id:"minecraft:barrel",Items:[{Slot:0b,id:"minecraft:stone",count:64}]}']
  blocks:
    - [0, 0, 0, "stone"]
    - [0, 1, 0, "lever[face=floor,facing=east,powered=false]"]
    - [1, 1, 0, "repeater[delay=2,facing=west,locked=false,powered=false]"]
ticks: 20                       # Anzahl simulierter Game-Ticks
inputs:
  - {tick: 2, pos: [0, 1, 0], action: use}
  - {tick: 12, pos: [0, 1, 0], action: use}
  - {tick: 15, pos: [3, 0, 0], action: setblock, state: "redstone_block"}
probes:                         # name -> Position; aufgezeichnet wird der volle Blockzustand
  lever: [0, 1, 0]
  lamp: [3, 1, 0]
```

Koordinaten sind relativ zur Schematic (Min-Ecke = `(0,0,0)`).

### Aktionen

| `action` | Bedeutung | Oracle-Implementierung |
|---|---|---|
| `use` | Rechtsklick eines Spielers ohne Item auf den Block (Hebel umlegen, Knopf drücken, Repeater-Delay weiterschalten, Comparator-Modus wechseln) | `BlockState#useWithoutItem` mit einem Fake-Player, Trefferpunkt Blockmitte, Seite `up` |
| `step` | **nur Simulator** (kein Oracle: dort fehlen Entities): ein Entity betritt eine Druckplatte und verlässt sie sofort wieder (löst die Platte aus, der geplante Tick löst sie wieder). `use` auf einer Druckplatte tut wie im Spiel nichts. Die Analyse (`Experiment.run`) setzt für Platten automatisch `step` statt `use` ein | – |
| `setblock` | wie `/setblock <pos> <state>` (ersetzt den Block, Flags `UPDATE_ALL` = 3) | `ServerLevel#setBlock(pos, state, 3)` |

## 2. Ablauf (für Simulator und Oracle identisch)

1. **Aufbau**: Alle Blöcke werden exakt im gespeicherten Zustand gesetzt, **ohne** Block- oder
   Shape-Updates und ohne `onPlace` (Flags 818 = `UPDATE_CLIENTS | UPDATE_KNOWN_SHAPE |
   UPDATE_SUPPRESS_DROPS | UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS | UPDATE_SKIP_ON_PLACE`, wie
   `/setblock … strict`). Vorhandene
   geplante Ticks werden verworfen. Block-Entities werden aus den Schematic-Daten geladen.
   Die Umgebung ist Luft (Void-Welt); im Oracle liegt die Min-Ecke an einer festen, chunk-ausgerichteten
   Position, die Chunks sind geladen (force-loaded) und das Spiel ist eingefroren.
2. Für `t = 0, 1, ..., ticks`:
   1. alle Eingaben mit `tick == t` in Dateireihenfolge ausführen (inklusive aller sofortigen Updates),
   2. alle Sonden lesen → Sample für Tick `t`,
   3. falls `t < ticks`: genau **einen** Game-Tick ausführen.

Ein Sample bei Tick `t` zeigt also den Zustand nach `t` ausgeführten Game-Ticks und nach den Eingaben
von Tick `t`. Eingaben liegen damit „zwischen" zwei Game-Ticks, genau wie Spieleraktionen im echten Spiel.

### Spielzeit und Tageslichtsensor

- Das Oracle läuft in einer eingefrorenen Welt (`advance_time` aus, Weltuhr `minecraft:overworld` bei
  `total_ticks = 0`, klares Wetter). Der Tageslichtsensor sieht daher immer denselben Himmel: Sonnenwinkel
  282,37 Grad, `skyDarken` 0 (normaler Sensor unter freiem Himmel 7, invertierter 0). Der Simulator nimmt
  genau diese Welt an (`sim/blocks/daylight.py`); andere Tageszeiten sind nicht modelliert.
- Die Spielzeit (`gameTime`) läuft im Oracle über Szenarien hinweg weiter. Das Oracle setzt sie beim Aufbau
  deterministisch: nur die Phase `gameTime % 20` des Szenarios zählt (der 20-gt-Takt des Sensors), die Uhr springt
  dafür um mindestens 100 Ticks **vorwärts** (nie zurück, damit Fackel-Ausbrenn-Buchführung früherer Szenarien
  abgelaufen ist) auf die nächste Zeit mit dieser Phase. Das optionale Szenariofeld `game_time` (ganze Zahl,
  Standard 0) gibt die Anfangs-Spielzeit des Simulators vor und wird als `game_time` ins kompilierte JSON
  geschrieben; das Oracle nutzt davon `game_time mod 20`. Wetter wird beim Aufbau auf klar gesetzt (zusätzlich
  zu `advance_weather` aus). Aktionen `use` am Sensor sind phasenunabhängig (sofortige Aktualisierung).

### Ursprung

Simulator und Oracle setzen die Min-Ecke des Aufbaus standardmäßig auf (0, 200, 0). Das optionale Feld
`origin: [x, y, z]` verschiebt sie für dieses Szenario (beide Seiten; wird als `origin` ins kompilierte JSON
geschrieben). Gebraucht wird es, weil die Update-Reihenfolge von Redstone-Staub von den absoluten Koordinaten
abhängt (DUST-018, `docs/robustness.md`). Das Oracle lädt und forciert die Chunks um den Ursprung; in der Nähe
bleiben (wenige Chunks vom Weltursprung). Die System-Properties `rsx.originX/Y/Z` verschieben den Standard für
einen ganzen Lauf.

## 3. Kompiliertes Szenario (JSON, Eingabe für das Oracle)

`rsx compile <szenario.yaml>` löst Schematic-Datei bzw. Inline-Aufbau auf. Das Oracle muss nur dieses
Format lesen:

```json
{
  "format": 1,
  "name": "repeater-delay-2",
  "size": [4, 2, 1],
  "blocks": [{"pos": [0, 0, 0], "state": "minecraft:stone"}],
  "block_entities": [{"pos": [2, 1, 0], "snbt": "{id:\"minecraft:comparator\",OutputSignal:0}"}],
  "ticks": 20,
  "inputs": [{"tick": 2, "pos": [0, 1, 0], "action": "use"},
             {"tick": 15, "pos": [3, 0, 0], "action": "setblock", "state": "minecraft:redstone_block"}],
  "probes": [{"name": "lamp", "pos": [3, 1, 0]}]
}
```

Blockzustände sind im Format `namespace:id[key=value,...]` mit alphabetisch sortierten Properties.
Luft wird nicht aufgeführt.

## 4. Trace (JSON, Ausgabe von Oracle und Simulator)

```json
{
  "format": 1,
  "scenario": "repeater-delay-2",
  "source": "oracle",
  "version": "26.3",
  "ticks": 20,
  "probes": {"lamp": [3, 1, 0]},
  "samples": {
    "lamp": [[0, "minecraft:redstone_lamp[lit=false]"], [6, "minecraft:redstone_lamp[lit=true]"]]
  }
}
```

- `samples[probe]` ist eine Liste von **Änderungspunkten** `[tick, wert]`: Der erste Eintrag ist immer
  Tick 0, danach nur Ticks, an denen sich der Wert geändert hat.
- `wert` ist der Blockzustand (sortierte Properties). Bei einem Comparator wird die Ausgangsstärke aus
  dem Block-Entity angehängt: `minecraft:comparator[...]|output=7`.
- `source` ist `oracle` oder `sim`.

Golden Traces aus dem Oracle liegen unter `tests/golden/<name>.trace.json`.
