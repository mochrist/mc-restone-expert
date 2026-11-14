---
topic: Tick-Phasen und Reihenfolge innerhalb eines Game-Ticks
prefix: ORD
---

# Tick-Phasen und Reihenfolge innerhalb eines Game-Ticks

Ein Game-Tick (gt, nominal 50 ms) besteht in `MinecraftServer#tickServer` → `tickChildren` aus dem Ticken aller
Dimensionen nacheinander; jede Dimension läuft `ServerLevel#tick` mit fester Phasenreihenfolge. Für Redstone
relevant sind vor allem: geplante Block-Ticks → Fluid-Ticks → (Raids, Chunks inkl. Random Ticks) →
Block-Events → Entities → Block Entities. Der Simulator sollte genau diese Phasen nachbilden.

### ORD-001: Phasenreihenfolge in ServerLevel#tick
- Aussage: `ServerLevel#tick` führt (bei normal laufender Tickrate) in dieser Reihenfolge aus: World Border, Wetter, Schlaflogik, Spielzeit erhöhen (`tickTime`, inkl. geplanter Funktionen), geplante Block-Ticks, geplante Fluid-Ticks, Raids, Chunk-Source (`ServerChunkCache#tick`, u. a. Random Ticks und Spawning), Block-Events, Entities (inkl. Drachenkampf), Block Entities, Entity-Management.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`; [SRC-M-WIKI-TICK]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Entities und Block Entities werden nur getickt, solange die Dimension nicht länger als 300 Ticks leer war (`emptyTime < 300`).

### ORD-002: Die Spielzeit wird vor den geplanten Ticks erhöht
- Aussage: `ServerLevel#tickTime` erhöht `gameTime` vor der Phase der geplanten Ticks; ein in Tick T (beliebige Phase) mit Verzögerung d geplanter Tick hat `triggerTick = T + d` und läuft in der Block-Tick-Phase von Tick T+d.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`, `ServerLevel#tickTime`, `LevelAccessor#createTick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-pistons-ticks.yaml)

### ORD-003: Reihenfolge geplanter Block-Ticks
- Aussage: Fällige geplante Ticks werden nach Priorität (niedrigerer Wert zuerst, `EXTREMELY_HIGH = -3` bis `EXTREMELY_LOW = 3`) und bei gleicher Priorität nach `subTickOrder` (globaler Zähler in Planungsreihenfolge) ausgeführt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ScheduledTick#INTRA_TICK_DRAIN_ORDER`, `ScheduledTick#DRAIN_ORDER`, `TickPriority`, `Level#nextSubTickCount`; [SRC-M-WIKI-TICK]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-priorities.yaml)
- Hinweise: Welche Komponente welche Priorität nutzt, steht in den Komponenten-Dateien (Wiki: Repeater -3/-2/-1, Comparator -1/0, sonst 0).

### ORD-004: In der Tick-Phase neu geplante Ticks laufen nicht mehr im selben Tick
- Aussage: `LevelTicks#tick` sammelt zu Beginn alle fälligen Ticks (max. 65536) in eine Liste und arbeitet nur diese ab; während der Abarbeitung neu geplante Ticks laufen frühestens im nächsten Game-Tick.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelTicks#tick`, `LevelTicks#collectTicks`, `LevelTicks#runCollectedTicks`; [SRC-M-WIKI-TICK]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Überzählige fällige Ticks (> 65536) bleiben für den nächsten Tick liegen.

### ORD-005: Ein Tick pro Position und Block gleichzeitig
- Aussage: Ein geplanter Tick für dieselbe Position und denselben Blocktyp wird nicht erneut aufgenommen, solange einer aussteht (`LevelChunkTicks#schedule` mit `ticksPerPosition`); erst nachdem er zur Ausführung entnommen wurde, kann neu geplant werden.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelChunkTicks#schedule`, `ScheduledTick#UNIQUE_TICK_HASH`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-pistons-ticks.yaml)
- Hinweise: Der verworfene Tick behält also nicht seine eigene Verzögerung oder Priorität; es gilt der bereits ausstehende.

### ORD-006: Ein geplanter Tick wird nur ausgeführt, wenn der Block noch passt
- Aussage: `ServerLevel#tickBlock` ruft `BlockState#tick` nur auf, wenn an der Position noch ein Block des geplanten Typs steht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tickBlock`, `ServerLevel#tickFluid`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-priorities.yaml)

### ORD-007: Fluid-Ticks laufen nach allen Block-Ticks
- Aussage: Die Fluid-Tick-Liste (`fluidTicks`) wird erst nach vollständiger Abarbeitung der Block-Tick-Liste verarbeitet, mit demselben Ordnungsschema.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`; [SRC-M-WIKI-TICK]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Das Wiki sagt „keine Priorität, in Planungsreihenfolge"; laut Code nutzt `LevelTicks` auch hier Priorität und `subTickOrder`, Fluid-Ticks werden aber in der Regel mit Standardpriorität geplant.

### ORD-008: Block-Events: FIFO, inklusive während der Phase neu hinzugefügter Events
- Aussage: `ServerLevel#runBlockEvents` entnimmt Events in Einfügereihenfolge, bis die Warteschlange leer ist; Events, die während der Abarbeitung eingereiht werden, werden noch in derselben Phase ausgeführt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#runBlockEvents`, `ServerLevel#blockEvent`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Grundlage für 0-Tick-Verhalten und Piston-Ketten (siehe `zero-tick.md`).

### ORD-009: Identische Block-Events werden zusammengefasst
- Aussage: Die Block-Event-Warteschlange ist ein `ObjectLinkedOpenHashSet` von `BlockEventData(pos, block, b0, b1)`; ein Event, das identisch noch aussteht, wird nicht ein zweites Mal eingereiht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#blockEvents`, `ServerLevel#blockEvent`, `BlockEventData`
- Konfidenz: hoch
- Status: belegt

### ORD-010: Block-Events prüfen den Blocktyp und werden in nicht tickenden Chunks verschoben
- Aussage: Ein Block-Event wird nur ausgeführt, wenn an der Position noch der Block des Events steht (sonst still verworfen); liegt die Position nicht im Block-Ticking-Bereich, wird es auf den nächsten Tick verschoben.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#doBlockEvent`, `ServerLevel#runBlockEvents`, `ServerLevel#shouldTickBlocksAt`
- Konfidenz: hoch
- Status: belegt

### ORD-011: isHandlingTick umfasst geplante Ticks bis Block-Events
- Aussage: `ServerLevel#isHandlingTick` ist vom Beginn von `ServerLevel#tick` bis nach der Block-Event-Phase wahr und in Entity- und Block-Entity-Phase sowie außerhalb des Level-Ticks (Spieleraktionen) falsch.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`, `ServerLevel#isHandlingTick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Wird von Pistons ausgewertet (PIS-004).

### ORD-012: Block Entities ticken in Listenreihenfolge, neue werden angehängt
- Aussage: `Level#tickBlockEntities` tickt die Ticker in der Reihenfolge der Liste `blockEntityTickers`; Ticker, die außerhalb dieser Phase entstehen (z. B. `moving_piston` aus Block-Events), werden direkt angehängt und noch im selben Tick getickt, während der Phase entstehende Ticker erst im nächsten Tick.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#addBlockEntityTicker`, `Level#tickBlockEntities`, `LevelChunk#updateBlockEntityTicker`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Wird an einer Position ein Block Entity ersetzt, für die schon ein Ticker existiert, wird dieser neu gebunden und behält seinen Listenplatz (`RebindableTickingBlockEntityWrapper`).

### ORD-013: Entities ticken vor Block Entities
- Aussage: Innerhalb eines Dimension-Ticks werden alle Entities (inkl. Spieler-Entities) vor den Block Entities getickt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`; [SRC-M-WIKI-TICK]
- Konfidenz: hoch
- Status: belegt

### ORD-014: Spieleraktionen passieren zwischen zwei Game-Ticks
- Aussage: Eingehende Spielerpakete (z. B. Knopf drücken, Block setzen) werden in `MinecraftServer#processPacketsAndTick` vor `tickServer` bzw. während der Wartezeit zwischen Ticks abgearbeitet, also nach der Block-Entity-Phase des vorigen und vor den geplanten Ticks des nächsten Ticks.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `MinecraftServer#processPacketsAndTick`, `MinecraftServer#waitUntilNextTick`, `MinecraftServer#tickChildren`; [SRC-M-WIKI-TICK]
- Konfidenz: mittel
- Status: belegt
- Hinweise: Kein echter Widerspruch, nur unterschiedliche Zählweise (aufgelöst, Code als Beleg). Das Oracle führt Eingaben im `END_SERVER_TICK` aus (`OracleMod#onEndTick`), also nach der Block-Entity-Phase und vor den geplanten Ticks des nächsten Ticks; alle Golden Traces mit Eingaben stimmen mit dem Simulator überein, der dieselbe Konvention nutzt. Der echte Paketweg (Netzwerk-Thread, `processPacketsAndTick`) wird damit nicht getestet. Das Wiki ordnet die Paketverarbeitung als Schritt nach dem Ticken aller Dimensionen ein (innerhalb desselben Ticks). Für Redstone ist das gleichwertig: In beiden Darstellungen liegt die Aktion zwischen der Block-Entity-Phase eines Ticks und der Block-Tick-Phase des nächsten. Die Zuordnung „Tick-Nummer" einer Aktion ist daher Konvention; ein in der Aktion geplanter Tick nutzt die bereits erhöhte bzw. noch nicht erhöhte `gameTime`.

### ORD-015: Dimensionen werden nacheinander getickt
- Aussage: `MinecraftServer#tickChildren` tickt zuerst die Tick-Funktionen (`commandFunctions`), dann jede Dimension vollständig nacheinander (Overworld, Nether, End, weitere).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `MinecraftServer#tickChildren`; [SRC-M-WIKI-TICK]
- Konfidenz: hoch
- Status: belegt

### ORD-016: Redstone ruht in nicht tickenden Chunks
- Aussage: Geplante Ticks laufen nur in Chunks mit `isPositionTickingWithEntitiesLoaded`, Block-Events nur im Block-Ticking-Bereich (`shouldTickBlocksAt`) und Block Entities nur in tickenden Chunks; ausstehende Ticks und Events bleiben erhalten und laufen nach, sobald der Chunk wieder tickt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelTicks#sortContainersToTick`, `ServerLevel#runBlockEvents`, `Level#tickBlockEntities`
- Konfidenz: mittel
- Status: belegt
- Hinweise: An Chunk-Grenzen zum nicht tickenden Bereich können Schaltungen daher „einfrieren"; nachgeholte Ticks werden nur nach Priorität und `subTickOrder` sortiert. Für den Simulator ist das nur relevant, wenn Schaltungen über geladene Bereichsgrenzen reichen.

### ORD-017: Die Verarbeitung ist deterministisch bis auf Zufall und Listenreihenfolgen
- Aussage: Geplante Ticks (Priorität, `subTickOrder`), Block-Events (FIFO) und Nachbar-Updates (feste Richtungsreihenfolge) sind deterministisch; nicht aus einer Schematic ableitbar sind die Block-Entity-Ticker-Reihenfolge (Lade-/Platzierungsreihenfolge) und zufallsabhängige Teile wie die Slotwahl von Dispenser/Dropper.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ScheduledTick#INTRA_TICK_DRAIN_ORDER`, `ServerLevel#runBlockEvents`, `NeighborUpdater#UPDATE_ORDER`, `Level#tickBlockEntities`, `DispenserBlockEntity#getRandomSlot`
- Konfidenz: mittel
- Status: belegt
- Hinweise: Die `subTickOrder` hängt ebenfalls von der Vorgeschichte ab (globaler Zähler); relativ zueinander ist sie aber durch die Planungsreihenfolge bestimmt.
