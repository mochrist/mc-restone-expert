---
topic: Ticks und Scheduled Ticks
prefix: TCK
---

# Ticks, Tick-Phasen und die Scheduled-Tick-Liste

Ein Spieltick (Game Tick) ist ein Durchlauf der Server-Schleife, normal 20 pro Sekunde. Innerhalb eines
Ticks bearbeitet jede Dimension (`ServerLevel#tick`) feste Phasen nacheinander. Für Redstone sind vor allem
die **Scheduled Block Ticks** (verzögerte Aktionen von Repeatern, Komparatoren, Fackeln, Observern, …),
die **Block Events** (Kolben) und die **Block Entities** (bewegte Kolbenblöcke, Hopper) relevant.
Neighbor-Updates laufen nicht in einer eigenen Phase, sondern synchron innerhalb der Phase, die sie
auslöst (siehe UPD).

### TCK-001: Ein Spieltick dauert normal 50 ms, ein Redstone-Tick sind 2 Spielticks
- Aussage: Java Edition läuft mit 20 Spielticks pro Sekunde; „Redstone-Tick" ist in Java nur ein Community-Begriff für 2 Spielticks, keine Einheit der Engine.
- Version: 26.3
- Quelle: [SRC-WIKI-TICK]; [SRC-MC-CODE] `RepeaterBlock#getDelay`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Im Code arbeitet alles in Spielticks; ein Repeater mit `delay=n` plant seinen Tick mit `n * 2` Spielticks Verzögerung.

### TCK-002: Reihenfolge der Phasen in ServerLevel#tick
- Aussage: `ServerLevel#tick` arbeitet in dieser Reihenfolge: Weltgrenze und Wetter, Schlaf-Prüfung, Himmelshelligkeit, `tickTime` (Spielzeit +1, geplante Funktionen), Scheduled Block Ticks, Scheduled Fluid Ticks, Raids, `ChunkSource#tick` (u. a. Random Ticks und Mob-Spawning), Block Events, Entities (inkl. Drachenkampf), Block Entities, Entity-Management.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`, `ServerChunkCache#tickChunks`; [SRC-WIKI-TICK]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Entities und Block Entities laufen nur, solange die Dimension nicht seit 300 Ticks leer ist (`emptyTime < 300`).

### TCK-003: Die Spielzeit wird vor den Scheduled Ticks erhöht
- Aussage: `tickTime` erhöht `gameTime` um 1, bevor `blockTicks.tick(gameTime, …)` aufgerufen wird; die Block-Tick-Phase arbeitet also mit der neuen Zeit.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`, `ServerLevel#tickTime`
- Konfidenz: hoch
- Status: belegt

### TCK-004: Ein geplanter Tick fällt auf gameTime + delay
- Aussage: `scheduleTick(pos, block, delay[, priority])` erzeugt einen `ScheduledTick` mit `triggerTick = getGameTime() + delay` und einer fortlaufenden `subTickOrder` aus dem pro Level globalen Zähler `Level#nextSubTickCount`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ScheduledTickAccess#scheduleTick`, `LevelAccessor#createTick`, `Level#nextSubTickCount`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Zähler wird auch dann erhöht, wenn der Tick anschließend als Duplikat verworfen wird (TCK-009); das ändert nur Lücken, nicht die relative Reihenfolge.

### TCK-005: Fällige Ticks werden zu Phasenbeginn gesammelt, neue laufen frühestens im nächsten Tick
- Aussage: `LevelTicks#tick` sammelt zuerst alle Ticks mit `triggerTick <= gameTime` (höchstens 65536) in eine Liste und führt dann nur diese aus; Ticks, die während der Ausführung geplant werden, laufen auch mit `delay=0` frühestens im nächsten Spieltick.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelTicks#tick`, `LevelTicks#collectTicks`, `LevelTicks#runCollectedTicks`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ein Tick mit Verzögerung d, geplant irgendwo im Spieltick T (egal ob in Block-Tick-, Block-Event- oder Entity-Phase), läuft in der Block-Tick-Phase von Spieltick T+d (bei d ≥ 1); d = 0 wirkt wie d = 1.

### TCK-006: Reihenfolge innerhalb eines Spielticks: Priorität, dann Planungsreihenfolge
- Aussage: Gesammelte Block-Ticks laufen aufsteigend nach `TickPriority` (kleinerer Wert zuerst) und bei gleicher Priorität nach `subTickOrder`, also in der Reihenfolge, in der sie geplant wurden, über alle Chunks hinweg.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ScheduledTick#INTRA_TICK_DRAIN_ORDER`, `LevelTicks#drainContainers`, `LevelTicks#drainFromCurrentContainer`; [SRC-WIKI-TICK]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Die Position spielt für die Reihenfolge keine Rolle.

### TCK-007: TickPriority hat sieben Stufen von -3 bis 3
- Aussage: `TickPriority` kennt EXTREMELY_HIGH (-3), VERY_HIGH (-2), HIGH (-1), NORMAL (0), LOW (1), VERY_LOW (2), EXTREMELY_LOW (3); ohne Angabe wird NORMAL verwendet.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `TickPriority`, `ScheduledTick` (Konstruktor ohne Priorität)
- Konfidenz: hoch
- Status: belegt
- Hinweise: Laut Wiki nutzen Repeater -3/-2/-1, Komparatoren -1/0, alles andere 0; die genauen Bedingungen gehören in die Komponenten-Dateien.

### TCK-008: Überfällige Ticks werden chunkübergreifend nicht nach triggerTick sortiert
- Aussage: Innerhalb eines Chunks sortiert die Warteschlange zuerst nach `triggerTick`, dann Priorität, dann `subTickOrder`; zwischen Chunks vergleicht `LevelTicks` nur Priorität und `subTickOrder` der jeweils vordersten Ticks.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ScheduledTick#DRAIN_ORDER`, `LevelChunkTicks` (PriorityQueue), `LevelTicks#CONTAINER_DRAIN_ORDER`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Nur relevant, wenn Ticks aus früheren Spielticks übrig sind (65536-Limit, nicht tickende Chunks, `delay=0`). In normalen Schaltungen ohne Überlauf ist das Ergebnis gleich TCK-006.

### TCK-009: Ein zweiter Tick für dieselbe Position und denselben Block wird verworfen
- Aussage: `LevelChunkTicks#schedule` ignoriert einen neuen Tick, solange für dieselbe Position und denselben Block-Typ (nicht Blockstate) noch ein Tick aussteht, egal mit welcher Verzögerung oder Priorität; der zuerst geplante gewinnt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelChunkTicks#schedule`, `ScheduledTick#UNIQUE_TICK_HASH`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Viele Komponenten prüfen vorher zusätzlich `hasScheduledTick`/`willTickThisTick`.

### TCK-010: Ein gesammelter Tick blockiert keine Neuplanung mehr
- Aussage: Beim Einsammeln für den aktuellen Spieltick wird der Tick aus der Duplikat-Menge seines Chunks entfernt; schon bevor er ausgeführt wurde, kann für dieselbe Position und denselben Block ein neuer Tick geplant werden.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelChunkTicks#poll`, `LevelTicks#drainContainers`
- Konfidenz: hoch
- Status: belegt
- Hinweise: `hasScheduledTick` liefert dann false; `willTickThisTick` erkennt solche gesammelten, noch nicht gelaufenen Ticks.

### TCK-011: Ein Tick wird übersprungen, wenn der Block nicht mehr passt
- Aussage: Beim Ausführen ruft `ServerLevel#tickBlock` `BlockState#tick` nur auf, wenn an der Position noch ein Block desselben Typs steht; sonst verfällt der Tick ohne Wirkung.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tickBlock`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-timing.yaml)
- Hinweise: Der Blockstate darf sich geändert haben (z. B. andere `delay`/`powered`), nur der Block-Typ muss gleich sein.

### TCK-012: Höchstens 65536 Block-Ticks pro Spieltick
- Aussage: Pro Spieltick werden höchstens 65536 Block-Ticks und separat höchstens 65536 Fluid-Ticks gesammelt; der Rest bleibt in der Liste und ist im nächsten Spieltick überfällig.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick` (Argument 65536), `LevelTicks#canScheduleMoreTicks`, `LevelTicks#rescheduleLeftoverContainers`
- Konfidenz: hoch
- Status: belegt

### TCK-013: Fluid-Ticks laufen nach allen Block-Ticks in einer eigenen Liste
- Aussage: Fluid-Ticks liegen in einer separaten `LevelTicks<Fluid>` und laufen vollständig nach der Block-Tick-Phase desselben Spielticks.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`, `ServerLevel#tickFluid`
- Konfidenz: hoch
- Status: belegt

### TCK-014: Ticks laufen nur in tickenden Chunks
- Aussage: Ein Chunk-Container wird nur gesammelt, wenn das Prädikat `isPositionTickingWithEntitiesLoaded` für den Chunk gilt; sonst bleiben seine Ticks liegen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelTicks#sortContainersToTick`, `ServerLevel` (Konstruktor der `blockTicks`)
- Konfidenz: hoch
- Status: belegt
- Hinweise: Für Simulator-Szenarien in geladenen Chunks irrelevant, relevant für Chunk-Grenzen-Tests.

### TCK-015: Block Events werden FIFO und dedupliziert abgearbeitet
- Aussage: Block Events liegen in einem `ObjectLinkedOpenHashSet`; identische Events (gleiche Position, Block, beide Parameter) werden zusammengefasst, und `runBlockEvents` arbeitet in Einfüge-Reihenfolge, bis die Menge leer ist, sodass während der Phase hinzugefügte Events im selben Spieltick laufen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#blockEvent`, `ServerLevel#runBlockEvents`, `BlockEventData`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ein Event wirkt nur, wenn an der Position noch derselbe Block steht (`ServerLevel#doBlockEvent`); Events in nicht tickenden Chunks werden auf den nächsten Tick verschoben. Relevant für Kolben.

### TCK-016: Block Events laufen nach Random Ticks und vor Entities
- Aussage: Die Block-Event-Phase liegt nach `ChunkSource#tick` (Random Ticks) und vor den Entities und Block Entities desselben Spielticks.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Damit gilt pro Spieltick: Scheduled Ticks → Block Events → Entities → Block Entities (z. B. Kolbenbewegung beenden, Hopper).

### TCK-017: Eingefrorene Spielzeit stoppt Ticks und Block Events
- Aussage: Wenn `TickRateManager#runsNormally` false ist (z. B. `/tick freeze`), laufen weder `tickTime`, Scheduled Ticks noch Block Events.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Für das Oracle relevant: `/tick step` lässt einzelne Ticks laufen.

### TCK-018: Aus dem Speicher geladene Ticks laufen vor neu geplanten gleicher Priorität
- Aussage: Beim Laden eines Chunks erhalten gespeicherte Ticks negative `subTickOrder`-Werte (ab `-Anzahl`), laufen bei gleicher Priorität und gleichem Spieltick also vor allen im Spiel neu geplanten Ticks; die gespeicherte Reihenfolge wird durch Sortierung nach `subTickOrder` beim Speichern erhalten.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelChunkTicks#unpack`, `LevelChunkTicks#pack`
- Konfidenz: mittel
- Status: belegt
- Hinweise: Gespeichert wird nur die Restverzögerung relativ zur Spielzeit (`SavedTick`). Für Schematic-Importe ohne Tick-Daten ohne Bedeutung.
