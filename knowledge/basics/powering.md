---
topic: Powering (stark/schwach, Leiter)
prefix: PWR
---

# Powering: stark und schwach, Leiterblöcke

Im Code gibt es zwei Signalwege:

- `getSignal` („schwach"): das Signal, das eine Quelle **direkt an einen angrenzenden Empfänger** gibt
  (Komponente, Staub, oder ein Leiterblock, der es aber nicht weiterreicht).
- `getDirectSignal` („stark"): das Signal, das eine Quelle **in einen angrenzenden Leiterblock** drückt.
  Ein Leiterblock gibt das Maximum dieser starken Eingänge an alle seine Nachbarn als `getSignal` weiter.

Die Community-Begriffe „stark gepowert" und „schwach gepowert" für Blöcke entstehen daraus, dass Staub
technisch zwar ein `getDirectSignal` liefert, Staub beim Lesen aber alle Staub-Beiträge ausblendet
(`shouldSignal`-Trick). „Schwach gepowert" heißt also: Der Leiter wird nur von Staub gespeist und powert
deshalb Komponenten, aber keinen Staub.

### PWR-001: Ob ein Block leitet, entscheidet isRedstoneConductor
- Aussage: Ein Block ist Redstone-Leiter genau dann, wenn `BlockState#isRedstoneConductor` wahr ist; der Default-Prädikat ist `isCollisionShapeFullBlock` (Kollisionsbox ist ein voller Würfel).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BlockBehaviour.Properties` (Feld `isRedstoneConductor`), `BlockBehaviour.BlockStateBase#isRedstoneConductor`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-conductors-plates.yaml)

### PWR-002: Bestimmte volle Blöcke sind explizit keine Leiter
- Aussage: In 26.3 sind per `isRedstoneConductor(Blocks::never)` keine Leiter: Glas, gefärbtes Glas, getöntes Glas, Eis, Brüchiges Eis, Glowstone, Seelaterne, Redstone-Block, Observer, TNT, Leuchtfeuer, alle Laubarten, Kolben/Klebrige Kolben (alle Zustände), `moving_piston`, Gerüst, Kupfergitter, Kupferbirne, Chorusblüte, Pulverschnee, Bambus, Tropfstein (pointed dripstone) und `sulfur_spike`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Blocks` (Block-Registrierungen, `leavesProperties`, `pistonProperties`)
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-conductors.yaml)
- Hinweise: Liste durch Suche nach `isRedstoneConductor` in `Blocks` erstellt; Blockarten, deren Kollisionsbox ohnehin kein voller Würfel ist (Slabs, Treppen, …), fallen über den Default heraus und sind hier nicht aufgezählt. Im Spiel nur stichprobenartig geprüft (Glas, getöntes Glas, Glowstone, Eis, Laub, Observer sind keine Leiter); die übrigen Blöcke der Liste sind nur aus dem Code belegt.

### PWR-003: Seelensand und Schlamm sind Leiter trotz niedrigerer Kollisionsbox
- Aussage: Seelensand und Schlamm (`mud`) sind per `isRedstoneConductor(Blocks::always)` immer Leiter, obwohl ihre Kollisionsbox kein voller Würfel ist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Blocks#SOUL_SAND`, `Blocks#MUD`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-conductors.yaml)

### PWR-004: Halbe Stufen und Treppen sind keine Leiter, Doppelstufen schon
- Aussage: Obere/untere Stufen und Treppen haben keine Vollblock-Kollisionsbox und sind daher keine Leiter; eine Doppelstufe (`type=double`) hat einen vollen Würfel und leitet.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SlabBlock`, `StairBlock` (keine Überschreibung von `isRedstoneConductor`), Default `isCollisionShapeFullBlock`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-conductors.yaml)

### PWR-005: Ein Leiterblock gibt nur starke Eingänge weiter
- Aussage: `SignalGetter#getSignal` liefert für einen Leiterblock das Maximum aus seinem eigenen `getSignal` und `getDirectSignalTo(pos)` (Maximum der `getDirectSignal` seiner sechs Nachbarn); für Nicht-Leiter nur das eigene `getSignal`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#getSignal`, `SignalGetter#getDirectSignalTo`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-conductors.yaml)
- Hinweise: Nicht-Leiter (z. B. Glas) können also nie gepowert werden und leiten nichts weiter.

### PWR-006: Standard-Quellen liefern kein starkes Signal
- Aussage: `BlockBehaviour#getDirectSignal` ist per Default 0; nur Blöcke, die es überschreiben (u. a. Hebel, Knopf, Fackel, Druckplatten, Repeater/Komparator, Staub), können einen Leiterblock powern.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BlockBehaviour#getDirectSignal`, `LeverBlock#getDirectSignal`, `ButtonBlock#getDirectSignal`, `RedstoneTorchBlock#getDirectSignal`, `BasePressurePlateBlock#getDirectSignal`, `DiodeBlock#getDirectSignal`, `RedstoneWireBlock#getDirectSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-conductors.yaml)
- Hinweise: Beispiele ohne starkes Signal: Redstone-Block, Zielblock, Tageslichtsensor.

### PWR-007: Repeater und Komparatoren powern den Block vor sich stark
- Aussage: Für Dioden ist `getDirectSignal` gleich `getSignal`; der Leiterblock in Ausgaberichtung wird also mit der vollen Ausgangsstärke gepowert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getDirectSignal`, `DiodeBlock#getSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-conductors.yaml)

### PWR-008: Druckplatten powern nur den Block unter sich stark
- Aussage: Druckplatten liefern ein starkes Signal nur bei `direction == UP`, also an den Block direkt darunter.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BasePressurePlateBlock#getDirectSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-conductors-plates.yaml)

### PWR-009: Staub liefert als starkes Signal dasselbe wie als schwaches
- Aussage: `RedstoneWireBlock#getDirectSignal` gibt (solange `shouldSignal` wahr ist) denselben Wert wie `getSignal` zurück: den Block darunter und den Block, in den der Staub zeigt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getDirectSignal`, `RedstoneWireBlock#getSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-powering.yaml)
- Hinweise: Dass der so gepowerte Block trotzdem keinen anderen Staub speist, erledigt PWR-010.

### PWR-010: Beim Lesen der Blockeingänge blendet Staub sämtlichen Staub aus
- Aussage: `RedstoneWireBlock#getBlockSignal` setzt das Instanzfeld `shouldSignal` auf false, ruft `getBestNeighborSignal` auf und setzt es danach zurück; während dieser Zeit liefern alle Staubblöcke (geteilte Block-Instanz) 0 für `getSignal`/`getDirectSignal` und `isSignalSource` ist false.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getBlockSignal`, `RedstoneWireBlock#getSignal`, `RedstoneWireBlock#getDirectSignal`, `RedstoneWireBlock#isSignalSource`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-dust-structure.yaml)
- Hinweise: Das ist die eigentliche Implementierung von „schwach gepowert": Ein nur von Staub gepowerter Leiter trägt zum Blocksignal eines Staubs 0 bei, powert aber Lampen, Kolben, Repeater usw.

### PWR-011: Schwach gepowerte Blöcke aktivieren Komponenten, aber keinen Staub
- Aussage: Ein Leiterblock, der nur durch Staub gepowert ist, powert angrenzende Repeater, Komparatoren und Mechanismen, aber keinen angrenzenden Staub.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getBlockSignal`, `SignalGetter#getSignal`; [SRC-WIKI-REDSTONE-DUST]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-dust-structure.yaml)

### PWR-012: hasNeighborSignal prüft sechs Nachbarn in fester Reihenfolge
- Aussage: `SignalGetter#hasNeighborSignal` liefert true, sobald `getSignal` eines Nachbarn > 0 ist, geprüft in der Reihenfolge DOWN, UP, NORTH, SOUTH, WEST, EAST.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#hasNeighborSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb3-signal-dirs.yaml)
- Hinweise: Wird z. B. von Lampen, Kolben und Türen benutzt (Quasi-Connectivity prüft zusätzlich die Position darüber, siehe Mechanik-Dateien).

### PWR-013: getBestOwnOrNeighbourSignal berücksichtigt das Eigensignal einer Quelle
- Aussage: `SignalGetter#getBestOwnOrNeighbourSignal` ist das Maximum aus `getBestNeighborSignal(pos)` und, falls der Block selbst Signalquelle ist, seinem `ownSignal`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#getBestOwnOrNeighbourSignal`
- Konfidenz: hoch
- Status: belegt

### PWR-014: Seiteneingänge von Dioden lesen nur starke Signale, Staub und Redstone-Blöcke
- Aussage: `SignalGetter#getControlInputSignal` liefert für einen Redstone-Block 15, für Staub dessen `power`, für andere Signalquellen deren `getDirectSignal` und für alle anderen Blöcke (auch gepowerte Leiter) 0; mit `onlyDiodes=true` zählen nur Dioden (über `getDirectSignal`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#getControlInputSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb3-diode-side-inputs.yaml)
- Hinweise: Repeater (Locking) nutzen `onlyDiodes=true`, Komparator-Seiteneingänge `false`; Details in den Komponenten-Dateien. Im Spiel geprüft (kb3-diode-side-inputs): Repeater sperren nur ein gespeister Repeater, nicht Redstone-Block, Staub, Hebel oder angetriebener Stein; Comparatoren ziehen Redstone-Block, Staub und Diode ab, nicht einen angetriebenen Stein und nicht einen Bodenhebel (dessen starkes Signal geht nur in den Block darunter, `getDirectSignal` mit anderer Richtung ist 0). Ein Hebel mit passender Richtung am Comparator ist nicht gebaut.

### PWR-015: Standard-Signalquellen verbinden sich mit Staub nur bei bekannter Richtung
- Aussage: Der Default von `shouldRedstoneWireConnectTo` ist `isSignalSource() && direction != null`; bei Abfragen ohne Richtung (diagonal hoch/runter) verbindet sich Staub daher nur mit Blöcken, die die Methode überschreiben (vor allem Staub selbst).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BlockBehaviour#shouldRedstoneWireConnectTo`, `RedstoneWireBlock#shouldRedstoneWireConnectTo`, `RedstoneWireBlock#getConnectingSide`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-dust-shapes.yaml)
