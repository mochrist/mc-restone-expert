---
topic: Block Update Detector (BUD)
prefix: BUD
---

# Block Update Detector (BUD)

Ein BUD ist eine Schaltung, die einen Block in einem „veralteten" Zustand hält: Nach den Regeln müsste er
anders stehen (z. B. ein QC-bestromter Piston, der nicht ausgefahren ist), er rechnet aber erst neu, wenn er
ein Block-Update erhält. Jedes Update an seiner Position löst ihn dann aus. Im Code ist das Block-Update
(„NC-Update") der Aufruf von `neighborChanged` über den `NeighborUpdater` des Levels; davon getrennt sind
Shape-Updates (`updateShape`, „PP-Updates") und Comparator-Updates (`updateNeighbourForOutputSignal`).
Die genaue Reihenfolge der Update-Ausbreitung beschreibt die Basics-Datei zu Updates; hier nur das, was für
BUDs relevant ist.

### BUD-001: Block-Updates erreichen nur die sechs direkten Nachbarn
- Aussage: `Level#updateNeighborsAt(pos, …)` ruft `neighborChanged` auf den sechs Nachbarn von `pos` in der Reihenfolge West, Ost, Unten, Oben, Nord, Süd auf, nicht auf `pos` selbst.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#updateNeighborsAt`, `NeighborUpdater#UPDATE_ORDER`, `NeighborUpdater#updateNeighborsAtExceptFromFacing`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb3-bud-reach.yaml)
- Hinweise: Im Spiel geprüft: Detektoren an den vier Seiten und darüber reagieren, Diagonale, diagonal darüber und Abstand 2/3 nicht. Dass `pos` selbst nicht aktualisiert wird, ist nicht getrennt geprüft.

### BUD-002: Eine Zustandsänderung mit Flag UPDATE_NEIGHBORS updatet die Nachbarn
- Aussage: `Level#setBlock` löst nur bei gesetztem Flag 1 (`UPDATE_NEIGHBORS`) `updateNeighborsAt` an der geänderten Position aus; zusätzlich ein Comparator-Update, wenn der neue Block ein Analogsignal hat.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#setBlock`, `Block#UPDATE_NEIGHBORS`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-neighbor-updates.yaml)
- Hinweise: Viele Redstone-Zustandswechsel nutzen nur Flag 2 (z. B. `triggered` beim Dispenser, `enabled` beim Hopper) und erzeugen daher keine Block-Updates.

### BUD-003: Auch Flag-2-Änderungen erzeugen Shape-Updates
- Aussage: Solange Flag 16 (`UPDATE_KNOWN_SHAPE`) nicht gesetzt ist, sendet `Level#setBlock` Shape-Updates an die Nachbarn, auch wenn Flag 1 fehlt; ein Observer bemerkt daher z. B. das Setzen von `triggered` am Dispenser oder `enabled` am Hopper.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#setBlock`, `DispenserBlock#neighborChanged`, `HopperBlock#checkPoweredState`
- Konfidenz: mittel
- Status: im-Spiel-verifiziert (scenarios/kb-neighbor-updates.yaml)
- Hinweise: Das Observer-Verhalten selbst ist Thema der Observer-Datei. Im Spiel bestätigt (kb-neighbor-updates z=4: Lampe mit Flag 2, der Observer daneben pulst).

### BUD-004: Der QC-Piston-BUD
- Aussage: Ein Piston, der nur über QC bestromt ist, aber noch kein Update erhalten hat, fährt beim nächsten `neighborChanged` an seiner Position aus (Block-Event in derselben Tick-Phase-Logik wie in PIS-019).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#neighborChanged`, `PistonBaseBlock#checkIfExtend`; [SRC-M-WIKI-BUD]; [SRC-M-WIKI-QC]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-qc-updates.yaml)

### BUD-005: Der Dispenser/Dropper-BUD
- Aussage: Ein über QC bestromter Dispenser oder Dropper mit `triggered=false` löst beim nächsten `neighborChanged` aus und gibt 4 gt später aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DispenserBlock#neighborChanged`; [SRC-M-WIKI-DISPENSER]; [SRC-M-WIKI-BUD]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-qc-updates.yaml)

### BUD-006: Observer reagieren nicht auf Block-Updates
- Aussage: In der Java Edition erkennt der Observer keine NC-Updates (`neighborChanged`), sondern Zustandsänderungen des beobachteten Blocks über Shape-Updates.
- Version: 26.3
- Quelle: [SRC-M-WIKI-BUD]
- Konfidenz: mittel
- Status: im-Spiel-verifiziert (scenarios/kb-observer.yaml)
- Hinweise: Details in der Observer-Datei; dort sollte der Code (`ObserverBlock#updateShape`) zitiert werden.

### BUD-007: Updates erreichen QC-Blöcke oft über Quellen mit Zwei-Block-Reichweite
- Aussage: Ein QC-Block erhält ein Update von einer zwei Blöcke entfernten Änderung nur, wenn die Quelle über `updateNeighborsAt` an einer Zwischenposition auch deren Nachbarn updatet (z. B. Redstone-Staub, Diode über den Block vor ihr, Hebel/Knopf über den Trägerblock).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `NeighborUpdater#updateNeighborsAtExceptFromFacing`; [SRC-M-WIKI-QC]
- Konfidenz: mittel
- Status: im-Spiel-verifiziert (scenarios/kb2-qc-updates.yaml)
- Hinweise: Welche Komponente welche Positionen updatet, steht in den jeweiligen Komponenten-Dateien; das Wiki fasst es als „Redstone-Änderungen innerhalb von zwei Blöcken" zusammen.

### BUD-008: Ankommende Piston-Blöcke updaten sich selbst
- Aussage: Ein Block, den ein Piston an seine Zielposition bewegt hat, erhält dort beim Abschluss ein eigenes `neighborChanged`; ein geschobener QC-bestromter Piston reagiert also ohne fremdes Update.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonMovingBlockEntity#tick`, `PistonMovingBlockEntity#finalTick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-pistons-ticks.yaml)

### BUD-009: Ein bestromt platzierter Piston prüft sofort
- Aussage: Anders als Dispenser/Dropper prüft ein frisch platzierter Piston seine Leistung über `onPlace`/`setPlacedBy` sofort; ein BUD-Zustand entsteht beim Piston daher nur durch spätere Leistungsänderungen ohne Update.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#onPlace`, `PistonBaseBlock#setPlacedBy`, `DispenserBlock`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-piston-qc.yaml)
- Hinweise: `onPlace` prüft nur, wenn an der Position kein Block Entity existiert und vorher ein anderer Block stand.

### BUD-010: Updates sind auf eine Kettenlänge begrenzt
- Aussage: Der `CollectingNeighborUpdater` zählt verschachtelte Updates und verwirft weitere, sobald `maxChainedNeighborUpdates` erreicht ist (falls dieser Wert ≥ 0 ist).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CollectingNeighborUpdater#addAndRun`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Standardwert ist in der Updates-Datei bzw. der Gamerule-Doku nachzuschlagen; für normale Redstone-Schaltungen ist das Limit nicht relevant.
