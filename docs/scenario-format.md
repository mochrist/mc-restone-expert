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
| `setblock` | wie `/setblock <pos> <state>` (ersetzt den Block, Flags `UPDATE_ALL` = 3) | `ServerLevel#setBlock(pos, state, 3)` |

## 2. Ablauf (für Simulator und Oracle identisch)

1. **Aufbau**: Alle Blöcke werden exakt im gespeicherten Zustand gesetzt, **ohne** Block- oder
   Shape-Updates (Flags `UPDATE_CLIENTS | UPDATE_KNOWN_SHAPE`, keine Neighbor-Updates). Vorhandene
   geplante Ticks werden verworfen. Block-Entities werden aus den Schematic-Daten geladen.
   Die Umgebung ist Luft (Void-Welt); im Oracle liegt die Min-Ecke an einer festen, chunk-ausgerichteten
   Position, die Chunks sind geladen (force-loaded) und das Spiel ist eingefroren.
2. Für `t = 0, 1, ..., ticks`:
   1. alle Eingaben mit `tick == t` in Dateireihenfolge ausführen (inklusive aller sofortigen Updates),
   2. alle Sonden lesen → Sample für Tick `t`,
   3. falls `t < ticks`: genau **einen** Game-Tick ausführen.

Ein Sample bei Tick `t` zeigt also den Zustand nach `t` ausgeführten Game-Ticks und nach den Eingaben
von Tick `t`. Eingaben liegen damit „zwischen" zwei Game-Ticks, genau wie Spieleraktionen im echten Spiel.

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
