---
topic: Truhen, Redstone-Truhen und Kupfertruhen
prefix: CHEST
---

# Truhen, Redstone-Truhen und Kupfertruhen

Truhe (`ChestBlock`), Redstone-Truhe (`TrappedChestBlock extends ChestBlock`) und die acht Kupfertruhen
(`CopperChestBlock extends ChestBlock`) sind Container mit 27 Slots und Comparator-Ausgabe. Zwei Truhen mit
gleicher Blockart und `facing` bilden über `type=left/right` eine Doppeltruhe mit gemeinsamem Inventar.
Truhen haben keinen Block-Entity-Ticker auf dem Server; ohne Spieler (Öffnungszähler 0) gibt es keine
Zeitabläufe. Zeitangaben in Game-Ticks (gt).

### CHEST-001: Eine Einzeltruhe gibt wie ein Fass ihren Füllstand an den Comparator aus
- Aussage: `ChestBlock#getAnalogOutputSignal` liefert `AbstractContainerMenu#getRedstoneSignalFromContainer` des Truhen-Inventars (27 Slots); 10 volle Stacks Stein ergeben 6.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ChestBlock#getAnalogOutputSignal`, `AbstractContainerMenu#getRedstoneSignalFromContainer`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/chest-container.yaml)
- Hinweise: Die Formel steht in `comparator.md`.

### CHEST-002: Eine Doppeltruhe ist ein gemeinsames Inventar aus 54 Slots
- Aussage: `ChestBlock#getContainer` verbindet beide Hälften über `DoubleBlockCombiner` zu einem `CompoundContainer` (erst die rechte Hälfte `type=right`, dann die linke); der Comparator liest an beiden Hälften denselben Füllstand über alle 54 Slots (27 volle Stacks nur in der linken Hälfte ergeben an beiden Hälften 8).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ChestBlock#getContainer`, `ChestBlock#getBlockType`, `DoubleBlockCombiner#combineWithNeigbour`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/chest-container.yaml)
- Hinweise: `type=right` ist der erste Teil (`BlockType.FIRST`), `type=left` der zweite. Der `CompoundContainer` zählt die Slots der rechten Hälfte zuerst.

### CHEST-003: Ein Block oder eine sitzende Katze über der Truhe sperrt nur die Comparator-Ausgabe
- Aussage: `ChestBlock#getAnalogOutputSignal` ruft `getContainer` mit `ignoreBeingBlocked=false` auf; ist über der Truhe ein Block, der Redstone leitet (`isRedstoneConductor`), oder sitzt dort eine Katze, wird der Combiner leer und die Ausgabe ist 0. Bei einer Doppeltruhe zählt die Sperre jeder der beiden Hälften für beide.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ChestBlock#isChestBlockedAt`, `ChestBlock#getContainer`, `DoubleBlockCombiner#combineWithNeigbour`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/chest-container.yaml)
- Hinweise: Katzen (Entities) simuliert der Simulator nicht. Der Comparator liest den neuen Wert erst bei seinem nächsten Update, wenn der Block entfernt wird (der Block darüber ist kein Nachbar des Comparators).

### CHEST-004: Trichter ignorieren die Sperre durch einen Block über der Truhe
- Aussage: `HopperBlockEntity#getBlockContainer` ruft für Truhen `ChestBlock.getContainer(..., true)` (`ignoreBeingBlocked`) auf; Trichter füllen und leeren also auch eine blockierte Truhe.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlockEntity#getBlockContainer`, `ChestBlock#getContainer`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/chest-container.yaml)
- Hinweise: Gilt für Einzel- und Doppeltruhen. Eine Doppeltruhe ist für den Trichter immer ein 54-Slot-Container, auch wenn eine Hälfte blockiert ist.

### CHEST-005: Trichter behandeln eine Doppeltruhe als einen Container
- Aussage: Ein Trichter, der eine Hälfte einer Doppeltruhe füllt oder von unten leert, arbeitet auf dem `CompoundContainer`: das Einfügen belegt zuerst Slots der rechten Hälfte, das Absaugen nimmt aus dem ersten belegten Slot der Gesamtliste (rechte Hälfte zuerst); jede Änderung benachrichtigt die Comparator an beiden Hälften.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlockEntity#addItem`, `HopperBlockEntity#suckInItems`, `HopperBlockEntity#getBlockContainer`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/chest-container.yaml)
- Hinweise: `CompoundContainer` ist im dekompilierten Baum nicht enthalten; das Verhalten (Slots hintereinander, `setChanged` auf beide) folgt dem Spielcode der Klasse.

### CHEST-006: Die Redstone-Truhe ist Signalquelle, gibt aber ohne Spieler kein Signal aus
- Aussage: `TrappedChestBlock#isSignalSource` ist wahr, `ownSignal` ist die auf 0..15 begrenzte Anzahl der Spieler, die die Truhe geöffnet haben, und `getDirectSignal` gibt dieses Signal nur nach oben aus. Redstone-Staub neben der Truhe verbindet sich deshalb mit ihr, bleibt aber bei `power=0`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `TrappedChestBlock#isSignalSource`, `TrappedChestBlock#ownSignal`, `TrappedChestBlock#getDirectSignal`, `ChestBlockEntity#getOpenCount`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/chest-container.yaml)
- Hinweise: Beim Öffnen und Schließen aktualisiert `TrappedChestBlockEntity#signalOpenCount` die Nachbarn der Truhe und des Blocks darunter. Spieler (Öffnungszähler) simuliert der Simulator nicht.

### CHEST-007: Truhen bilden Doppeltruhen über Shape-Updates, ohne Nachbar-Updates auszulösen
- Aussage: `ChestBlock#updateShape` setzt eine `type=single`-Truhe auf `left/right`, wenn ein horizontaler Nachbar dieselbe Blockart mit gleichem `facing` und passendem `type` ist, und eine Hälfte auf `single`, wenn der Partner in `getConnectedDirection` ersetzt wird. Die Änderung läuft ohne `UPDATE_NEIGHBORS`; ein anliegender Comparator liest den Füllstand der neuen Form erst bei seinem nächsten Update.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ChestBlock#updateShape`, `ChestBlock#getConnectedDirection`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/chest-container.yaml)
- Hinweise: `facing=north` mit `type=left` verbindet nach Osten (`getClockWise`), mit `type=right` nach Westen. Wasserspiegel (`waterlogged`-Ticks) sind nicht modelliert.

### CHEST-008: Kupfertruhen verhalten sich wie Truhen
- Aussage: Alle acht Kupfertruhen (normal, `exposed_`, `weathered_`, `oxidized_`, jeweils `waxed_`) nutzen das Block-Entity `BlockEntityTypes.CHEST` und die Logik von `ChestBlock`; ihre Comparator-Ausgabe entspricht der einer Truhe. Eine Doppeltruhe entsteht nur aus derselben Blockart, Shape-Updates verbinden dagegen beliebige Kupfertruhen miteinander.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CopperChestBlock`, `BlockEntityTypes#CHEST`
- Konfidenz: hoch
- Status: belegt
- Hinweise: `CopperChestBlock#updateShape` gleicht die Blockart einer verbundenen Hälfte an (Oxidation, Wachs); der Simulator bildet das nicht nach.
