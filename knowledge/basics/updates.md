---
topic: Block-Updates
prefix: UPD
---

# Block-Updates: Neighbor-, Shape- und Komparator-Updates

Blöcke reagieren auf Änderungen in ihrer Umgebung über drei Update-Arten:

- **Neighbor-Update** (`neighborChanged`, Community: „NC-Update"/„Block-Update"): „in deiner Nähe hat sich
  etwas geändert". Komponenten prüfen dann ihre Eingänge neu.
- **Shape-Update** (`updateShape`, Community: „PP-Update"/„Post-Placement"): Ein Nachbar teilt seinen neuen
  Zustand mit; der Empfänger kann daraufhin seinen eigenen Zustand anpassen (Staub-Verbindungen, Zäune) oder
  abfallen.
- **Komparator-Update** (`updateNeighbourForOutputSignal`): nur an Komparatoren, wenn sich ein analog
  auslesbarer Block ändert.

Alle Neighbor- und Shape-Updates einer Dimension laufen durch einen `CollectingNeighborUpdater`, der seit 1.19
iterativ statt rekursiv arbeitet. Die neue Klasse `Orientation` (seit 1.21.2, 24w33a) ist nur für das
experimentelle Redstone relevant.

### UPD-001: Neighbor-Updates gehen in der Reihenfolge West, Ost, Unten, Oben, Nord, Süd
- Aussage: `updateNeighborsAt(pos, block)` schickt ein Neighbor-Update an die sechs Nachbarn von `pos` in der Reihenfolge `NeighborUpdater.UPDATE_ORDER` = WEST, EAST, DOWN, UP, NORTH, SOUTH.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `NeighborUpdater#UPDATE_ORDER`, `CollectingNeighborUpdater.MultiNeighborUpdate#runNext`, `ServerLevel#updateNeighborsAt`; [SRC-WIKI-BLOCK-UPDATE]
- Konfidenz: hoch
- Status: belegt

### UPD-002: updateNeighborsAtExceptFromFacing lässt genau eine Richtung aus
- Aussage: `updateNeighborsAtExceptFromFacing(pos, block, skip, …)` aktualisiert die Nachbarn in `UPDATE_ORDER`, überspringt aber den Nachbarn in Richtung `skip`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CollectingNeighborUpdater.MultiNeighborUpdate`, `NeighborUpdater#updateNeighborsAtExceptFromFacing`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-neighbor-updates.yaml)
- Hinweise: Wird z. B. von Dioden und Observern genutzt, um den Block vor sich und dessen Nachbarn (außer sich selbst) zu aktualisieren.

### UPD-003: Shape-Updates gehen in der Reihenfolge West, Ost, Nord, Süd, Unten, Oben
- Aussage: `BlockState#updateNeighbourShapes` schickt Shape-Updates an die sechs Nachbarn in der Reihenfolge `UPDATE_SHAPE_ORDER` = WEST, EAST, NORTH, SOUTH, DOWN, UP.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BlockBehaviour#UPDATE_SHAPE_ORDER`, `BlockBehaviour.BlockStateBase#updateNeighbourShapes`; [SRC-WIKI-BLOCK-UPDATE]
- Konfidenz: hoch
- Status: belegt

### UPD-004: Bedeutung der setBlock-Flags
- Aussage: Die Flags von `Level#setBlock` sind Bitmasken: 1 `UPDATE_NEIGHBORS`, 2 `UPDATE_CLIENTS`, 4 `UPDATE_INVISIBLE`, 8 `UPDATE_IMMEDIATE`, 16 `UPDATE_KNOWN_SHAPE` (keine Shape-Updates), 32 `UPDATE_SUPPRESS_DROPS`, 64 `UPDATE_MOVE_BY_PISTON`, 128 `UPDATE_SKIP_SHAPE_UPDATE_ON_WIRE`, 256 `UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS`, 512 `UPDATE_SKIP_ON_PLACE`; `UPDATE_ALL` = 3.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Block` (Konstanten `UPDATE_*`), `Level#setBlock`, `LevelChunk#setBlockState`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Flag 2 allein (häufig bei Komponenten-Zustandswechseln, z. B. Staub-Stärke) löst also keine Neighbor-Updates, aber Shape-Updates aus.

### UPD-005: setBlock ohne tatsächliche Zustandsänderung löst nichts aus
- Aussage: Ist der neue Blockstate identisch mit dem alten, gibt `LevelChunk#setBlockState` null zurück und `Level#setBlock` löst weder `onPlace`, Neighbor-, Komparator- noch Shape-Updates aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelChunk#setBlockState`, `Level#setBlock`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-neighbor-updates.yaml)

### UPD-006: Reihenfolge der Effekte in setBlock
- Aussage: Bei einer Zustandsänderung läuft auf dem Server in dieser Reihenfolge: (1) Zustand im Chunk setzen, (2) bei Wechsel des Block-Typs und Flag 1 oder Kolbenbewegung `affectNeighborsAfterRemoval` des alten Zustands, (3) `onPlace` des neuen Zustands (außer Flag 512), (4) Client-Sync (Flag 2), (5) bei Flag 1 `updateNeighborsAt(pos, alterBlock)` und danach Komparator-Updates, falls der neue Zustand analog auslesbar ist, (6) ohne Flag 16: `updateIndirectNeighbourShapes` des alten Zustands, `updateNeighbourShapes` und `updateIndirectNeighbourShapes` des neuen Zustands.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#setBlock`, `LevelChunk#setBlockState`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Als Quell-Block der Neighbor-Updates wird der **alte** Block übergeben. Für Schienen wird `affectNeighborsAfterRemoval` auch ohne Typwechsel aufgerufen.

### UPD-007: onPlace wird bei jeder Zustandsänderung aufgerufen
- Aussage: `LevelChunk#setBlockState` ruft `onPlace` bei jeder Zustandsänderung auf (nicht nur bei neuem Block-Typ); Blöcke wie Staub prüfen selbst, ob sich der Typ geändert hat.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelChunk#setBlockState`, `RedstoneWireBlock#onPlace`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-neighbor-updates.yaml)

### UPD-008: Shape-Updates an Shape-Nachbarn tragen Flags ohne 1 und 32 weiter
- Aussage: `Level#setBlock` gibt Shape-Updates die eigenen Flags ohne `UPDATE_NEIGHBORS` und `UPDATE_SUPPRESS_DROPS` weiter, und `updateLimit` um 1 verringert; bei `updateLimit` 0 gibt es keine weiteren Shape-Updates.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#setBlock` (Maske `& -34`, `updateLimit - 1`), `Block#UPDATE_LIMIT`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Startwert von `updateLimit` ist 512 (`Block.UPDATE_LIMIT`).

### UPD-009: Ein Shape-Update kann den Empfänger neu setzen oder zerstören
- Aussage: Bei einem Shape-Update berechnet der Empfänger `updateShape`; ist das Ergebnis Luft, wird der Block per `destroyBlock` zerstört (mit Drops, außer Flag 32), sonst bei Änderung per `setBlock` mit den übergebenen Flags (ohne 32) gesetzt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `NeighborUpdater#executeShapeUpdate`, `Block#updateOrDestroy`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb3-shape-update.yaml)
- Hinweise: `destroyBlock` setzt mit Flag 3, löst also Neighbor-Updates aus; ein normales Shape-Update-`setBlock` hat Flag 1 meist nicht. Im Spiel geprüft (kb3-shape-update): ein Repeater, dessen Stein darunter entfernt wird, wird zerstört und aktualisiert seine Nachbarn; ein zweites Staubstück verändert den Zustand des ersten per Shape-Update. Drops und das Weglassen von Flag 32 sind nicht geprüft.

### UPD-010: Neighbor- und Shape-Updates laufen sofort, wenn gerade keine Update-Kette läuft
- Aussage: Wird ein Update angefordert, während der `CollectingNeighborUpdater` nicht arbeitet (Zähler 0), wird es sofort synchron ausgeführt, inklusive aller dadurch ausgelösten Folge-Updates, bevor der Aufruf zurückkehrt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CollectingNeighborUpdater#addAndRun`, `CollectingNeighborUpdater#runUpdates`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Beispiel: Ein Repeater-Tick ruft `setBlock`; die komplette Update-Kaskade ist abgeschlossen, bevor der Code nach `setBlock` weiterläuft.

### UPD-011: Innerhalb einer Update-Kette werden neue Updates bis zum Ende des aktuellen Handlers verzögert
- Aussage: Fordert ein Block während seines `neighborChanged`/`updateShape` neue Updates an, werden sie gesammelt und erst ausgeführt, wenn der aktuelle Handler zurückkehrt; der restliche Code des Handlers sieht also noch keine Reaktionen der Nachbarn.
- Version: 26.3 (seit 1.19)
- Quelle: [SRC-MC-CODE] `CollectingNeighborUpdater#addAndRun`; [SRC-B-MCMOD-UPDATESUPP]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Vor 1.19 liefen Neighbor-Updates rekursiv und sofort (Stack Overflow ermöglichte „Update Suppression"). Exakter Snapshot der Umstellung nicht geprüft.

### UPD-012: Die Update-Kette arbeitet als Tiefensuche
- Aussage: Nach jedem einzelnen Update werden die dabei angeforderten Updates (in Anforderungsreihenfolge) vollständig abgearbeitet, bevor das unterbrochene Mehrfach-Update (z. B. die restlichen Richtungen von `updateNeighborsAt`) fortgesetzt wird.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CollectingNeighborUpdater#runUpdates` (Stack, `addedThisLayer` in umgekehrter Reihenfolge gepusht)
- Konfidenz: hoch
- Status: belegt
- Hinweise: Damit entspricht die Reihenfolge im Wesentlichen der alten rekursiven Reihenfolge, nur mit „Handler zuerst fertig" (UPD-011).

### UPD-013: Update-Ketten sind auf max-chained-neighbor-updates begrenzt
- Aussage: Pro Kette zählt der `CollectingNeighborUpdater` jede angeforderte Update-Einheit (ein `updateNeighborsAt` zählt als 1); ab `max-chained-neighbor-updates` (Default 1000000, negativ = unbegrenzt) werden weitere Anforderungen verworfen und einmalig „Too many chained neighbor updates" geloggt; der Zähler wird nach Ende der Kette auf 0 gesetzt.
- Version: 26.3 (seit 1.19)
- Quelle: [SRC-MC-CODE] `CollectingNeighborUpdater#addAndRun`, `Level` (Konstruktor); [SRC-B-MC-DEDICATED-PROPS] `DedicatedServerProperties#maxChainedNeighborUpdates`; [SRC-B-MCMOD-UPDATESUPP]
- Konfidenz: hoch
- Status: belegt
- Hinweise: „Update Skipping". In normalen Schaltungen nie erreicht.

### UPD-014: Komparator-Updates erreichen Komparatoren direkt oder hinter einem Leiter
- Aussage: `Level#updateNeighbourForOutputSignal` prüft die vier horizontalen Nachbarn in der Reihenfolge NORTH, EAST, SOUTH, WEST; ein Komparator dort bekommt ein Neighbor-Update, und ist der Nachbar ein Leiterblock, bekommt ein Komparator einen Block weiter in derselben Richtung eines.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#updateNeighbourForOutputSignal`, `Direction.Plane.HORIZONTAL`; [SRC-WIKI-BLOCK-UPDATE]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-comparator-updates.yaml)
- Hinweise: Die Ausrichtung des Komparators wird nicht geprüft. Ausgelöst von `setBlock` (Flag 1, neuer Zustand mit `hasAnalogOutputSignal`), von `BlockEntity#setChanged` (Inventaränderung) und einigen Blöcken direkt.

### UPD-015: Komparator-Updates nach Inventaränderung laufen bei jedem setChanged
- Aussage: `BlockEntity#setChanged` löst für jeden nicht-Luft-Block ein `updateNeighbourForOutputSignal` aus, unabhängig davon, ob sich das Analogsignal tatsächlich ändert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BlockEntity#setChanged`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-comparator-updates.yaml)

### UPD-016: Nur Staub erzeugt indirekte Shape-Updates
- Aussage: `updateIndirectNeighbourShapes` ist im Default leer und wird in 26.3 nur von `RedstoneWireBlock` überschrieben (Shape-Updates an diagonal darüber/darunter liegenden Staub).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BlockBehaviour#updateIndirectNeighbourShapes`, `RedstoneWireBlock#updateIndirectNeighbourShapes`
- Konfidenz: mittel
- Status: belegt
- Hinweise: Suche nur in den lokal dekompilierten Klassen; andere Blöcke außerhalb von `.cache/mcsrc` nicht geprüft.

### UPD-017: Flag 128 unterdrückt nur Shape-Updates an Staub
- Aussage: Mit `UPDATE_SKIP_SHAPE_UPDATE_ON_WIRE` (128) wird ein Shape-Update nicht ausgeführt, wenn der Empfänger Redstone-Staub ist; andere Empfänger bekommen es normal.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `NeighborUpdater#executeShapeUpdate`, `ExperimentalRedstoneWireEvaluator#updatePowerStrength`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Gesetzt wird das Flag nur vom experimentellen Staub-Evaluator.

### UPD-018: Orientation beschreibt oben, vorne und eine Seitenpräferenz
- Aussage: Die Klasse `Orientation` (48 Instanzen) besteht aus `up`, `front` und `SideBias` (LEFT/RIGHT); `getDirections` liefert die Reihenfolge: hinten, vorne, Seite, Gegenseite, unten, oben (relativ zu front/up/side).
- Version: 26.3 (seit 1.21.2)
- Quelle: [SRC-MC-CODE] `net.minecraft.world.level.redstone.Orientation`; [SRC-WIKI-24W33A]
- Konfidenz: hoch
- Status: belegt

### UPD-019: Ohne Redstone-Experimente ist die Orientation immer null
- Aussage: Ist das Feature-Flag `REDSTONE_EXPERIMENTS` aus, liefert `ExperimentalRedstoneUtils#initialOrientation` null und `MultiNeighborUpdate` übergibt null; in Vanilla erhält `neighborChanged` daher stets `orientation = null` und die Update-Reihenfolge bleibt `UPDATE_ORDER`.
- Version: 26.3 (seit 1.21.2)
- Quelle: [SRC-MC-CODE] `ExperimentalRedstoneUtils#initialOrientation`, `CollectingNeighborUpdater.MultiNeighborUpdate#runNext`, `ServerLevel#updateNeighborsAt`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Simulator kann Orientation für Vanilla ignorieren.

### UPD-020: Mit Redstone-Experimenten startet die Orientation zufällig
- Aussage: Mit `REDSTONE_EXPERIMENTS` wird eine fehlende Orientation aus dem Level-Zufall gewählt (`Orientation.random`, SideBias LEFT), sodass Update-Reihenfolgen im Experiment vom Zufall abhängen können.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ExperimentalRedstoneUtils#initialOrientation`, `ExperimentalRedstoneWireEvaluator#getInitialOrientation`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Experimentell, außerhalb des Scopes. Updates von Staub an Staub werden im Experiment ignoriert (`RedstoneWireBlock#neighborChanged`).
