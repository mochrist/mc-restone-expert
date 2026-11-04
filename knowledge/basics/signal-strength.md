---
topic: Signalstärke
prefix: SIG
---

# Signalstärke

Redstone-Signale sind ganze Zahlen von 0 bis 15. Quellen (Hebel, Fackel, Redstone-Block, Repeater, …) liefern
über `getSignal`/`getDirectSignal` einen Wert pro Richtung; Empfänger fragen ihre Nachbarn ab und nehmen
meistens das Maximum. Nur Redstone-Staub verliert pro Block eine Stufe, alle anderen Übertragungen
(Quelle → Block → Komponente) sind verlustfrei. Richtungskonvention im Code: Der `direction`-Parameter von
`getSignal`/`getDirectSignal` ist die Richtung **vom Empfänger zur Quelle** (der Empfänger fragt
`pos.relative(dir)` mit `dir` ab).

### SIG-001: Signalstärken liegen im Bereich 0 bis 15
- Aussage: Der Code definiert Signalstärken als 4-Bit-Werte mit `Redstone.SIGNAL_MIN` = 0, `SIGNAL_MAX` = 15 und `SIGNAL_NONE` = 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `net.minecraft.world.level.redstone.Redstone`
- Konfidenz: hoch
- Status: belegt

### SIG-002: Die Richtung im Signal-Aufruf zeigt vom Empfänger zur Quelle
- Aussage: `SignalGetter#getSignal(pos, direction)` wird vom Empfänger mit `pos = empfänger.relative(direction)` aufgerufen; die Quelle bekommt also die Richtung, in der sie vom Empfänger aus liegt (z. B. fragt ein Block die Fackel über sich mit `UP` ab).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#getBestNeighborSignal`, `SignalGetter#getDirectSignalTo`, `DiodeBlock#getSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Wichtig für jede Simulator-Implementierung von `getSignal`: z. B. gibt eine Bodenfackel bei `direction == UP` 0 zurück (sie powert den Block unter sich nicht).

### SIG-003: getBestNeighborSignal ist das Maximum über alle sechs Nachbarn
- Aussage: `SignalGetter#getBestNeighborSignal` fragt die Nachbarn in der Reihenfolge von `Direction.values()` (DOWN, UP, NORTH, SOUTH, WEST, EAST) per `getSignal` ab, liefert das Maximum und bricht beim ersten Wert ≥ 15 sofort mit 15 ab.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#getBestNeighborSignal`; `Direction` (Enum-Reihenfolge)
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Abbruch ist nur bei Seiteneffekten relevant (in Vanilla keine), für das Ergebnis also reine Optimierung.

### SIG-004: Redstone-Staub speichert seine Stärke im Blockstate POWER
- Aussage: Redstone-Staub hat die Property `power` (0–15); `ownSignal` liefert genau diesen Wert, ohne Abzug.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#ownSignal`, `RedstoneWireBlock#createBlockStateDefinition`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Komponenten neben Staub der Stärke n sehen also n, nicht n−1.

### SIG-005: Staub verliert pro Staub-zu-Staub-Schritt genau eine Stufe
- Aussage: Der Staub-Eingang aus benachbartem Staub ist das Maximum der `power`-Werte aller relevanten Nachbar-Staubblöcke minus 1, mindestens 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireEvaluator#getIncomingWireSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-network.yaml)
- Hinweise: Welche Nachbarn „relevant" sind (horizontal, diagonal hoch/runter), steht in DUST-Einträgen.

### SIG-006: Zielstärke von Staub ist das Maximum aus Blocksignal und Staubsignal
- Aussage: Die neue Stärke eines Staubblocks ist 15, wenn das Signal von Nicht-Staub-Quellen (`getBlockSignal`) 15 ist, sonst das Maximum aus diesem Blocksignal und dem um 1 verringerten Staub-Eingang.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DefaultRedstoneWireEvaluator#calculateTargetStrength`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-network.yaml)

### SIG-007: Ein Staubstrang von einer 15er-Quelle versorgt höchstens 15 Staubblöcke
- Aussage: Direkt neben einer Quelle der Stärke 15 hat Staub 15; jeder weitere Staubblock hat eine Stufe weniger, der 15. Staub hat Stärke 1, der 16. hat 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireEvaluator#getIncomingWireSignal`; [SRC-WIKI-REDSTONE-DUST]
- Konfidenz: hoch
- Status: belegt

### SIG-008: Redstone-Block liefert konstant 15 in alle Richtungen
- Aussage: Der Redstone-Block (`PoweredBlock`) ist Signalquelle mit `ownSignal` 15 für alle Richtungen, aber `getDirectSignal` 0 (keine starke Ladung).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PoweredBlock#ownSignal`, `PoweredBlock#isSignalSource`, `BlockBehaviour#getDirectSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ein Redstone-Block powert daher angrenzende Blöcke nicht; er ist außerdem kein Leiter (siehe PWR).

### SIG-009: Hebel und Knopf liefern 15 im aktiven Zustand
- Aussage: Hebel und Knöpfe liefern bei `powered=true` als schwaches Signal 15 in alle Richtungen und als starkes Signal 15 nur an den Block, an dem sie befestigt sind.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LeverBlock#ownSignal`, `LeverBlock#getDirectSignal`, `ButtonBlock#getDirectSignal`
- Konfidenz: hoch
- Status: belegt

### SIG-010: Redstone-Fackel liefert 15, aber nicht in Richtung ihres Trägerblocks
- Aussage: Eine brennende Redstone-Fackel liefert 15 an alle Empfänger außer an den Block, an dem sie hängt (Bodenfackel: `direction == UP` ergibt 0; Wandfackel: `direction == FACING` ergibt 0); stark powert sie nur den Block über sich.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#getSignal`, `RedstoneTorchBlock#getDirectSignal`, `RedstoneWallTorchBlock#getSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Details zur Fackel gehören in die Komponenten-Datei der Fackel.

### SIG-011: Repeater geben immer 15 aus
- Aussage: Ein eingeschalteter Repeater liefert 15 (`DiodeBlock#getOutputSignal`), unabhängig von der Eingangsstärke, und nur in Ausgaberichtung.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getOutputSignal`, `DiodeBlock#getSignal`, `DiodeBlock#ownSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Komparator überschreibt `getOutputSignal` und liest den Wert aus seinem Block-Entity.

### SIG-012: Gewichtete Druckplatten liefern ceil(Anzahl/Maximum · 15)
- Aussage: Eine gewichtete Druckplatte liefert `ceil(min(n, maxWeight) / maxWeight * 15)` für n Entities auf der Platte, 0 bei keiner Entity.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `WeightedPressurePlateBlock#getSignalStrength`
- Konfidenz: hoch
- Status: belegt
- Hinweise: `maxWeight` ist pro Plattentyp im Konstruktor gesetzt (leicht/schwer); nicht geprüft, welche Werte 26.3 verwendet.

### SIG-013: Zielblock und Tageslichtsensor liefern ihren gespeicherten Wert
- Aussage: Target-Block und Tageslichtsensor sind Signalquellen, deren `ownSignal` direkt der Blockstate-Property `power` entspricht (`TargetBlock.OUTPUT_POWER` bzw. `DaylightDetectorBlock.POWER`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `TargetBlock#ownSignal`, `DaylightDetectorBlock#ownSignal`
- Konfidenz: hoch
- Status: belegt

### SIG-014: Signalstärke eines Leiterblocks ist das Maximum seiner starken Eingänge
- Aussage: Fragt ein Empfänger einen Leiterblock ab, ist der Wert das Maximum aus dem eigenen `getSignal` des Blocks und `getDirectSignalTo`, dem Maximum der `getDirectSignal`-Werte aller sechs Nachbarn des Leiters (Reihenfolge DOWN, UP, NORTH, SOUTH, WEST, EAST, Abbruch bei 15).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#getSignal`, `SignalGetter#getDirectSignalTo`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ein gepowerter Block gibt also die Stärke der stärksten direkten Quelle verlustfrei weiter.

### SIG-015: Staub liefert nach oben kein Signal
- Aussage: `RedstoneWireBlock#getSignal` gibt 0 zurück, wenn der Empfänger über dem Staub liegt (`direction == DOWN`); nach unten (`UP`) liefert er immer seine Stärke.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getSignal`
- Konfidenz: hoch
- Status: belegt
