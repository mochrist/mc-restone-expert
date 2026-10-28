---
topic: Dropper, Dispenser und Hopper
prefix: DDH
---

# Dropper, Dispenser und Hopper

Dispenser (`DispenserBlock`) und Dropper (`DropperBlock extends DispenserBlock`) reagieren auf eine
steigende Flanke ihres (QC-erweiterten) Leistungszustands mit einem geplanten Tick nach 4 gt und geben dann
genau ein Item aus. Der Hopper (`HopperBlock`, `HopperBlockEntity`) arbeitet in der Block-Entity-Phase mit
einem Transfer-Cooldown und wird durch Redstone gesperrt. Alle drei sind Container mit Comparator-Ausgabe;
Details zur Comparator-Berechnung stehen in der Comparator-Datei. Zeitangaben in Game-Ticks (gt).

### DDH-001: Dispenser und Dropper werten Leistung inklusive Quasi-Connectivity aus
- Aussage: `DispenserBlock#neighborChanged` gilt als „soll auslösen", wenn `hasNeighborSignal(pos)` oder `hasNeighborSignal(pos.above())` wahr ist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DispenserBlock#neighborChanged`; [SRC-M-WIKI-DISPENSER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: `DropperBlock` überschreibt `neighborChanged` nicht und verhält sich identisch. Siehe `mechanics/quasi-connectivity.md`.

### DDH-002: Auslösung nur bei steigender Flanke über die Eigenschaft triggered
- Aussage: Ist der Dispenser bestromt und `triggered=false`, wird ein geplanter Tick mit Verzögerung 4 gt (Priorität NORMAL) eingereiht und `triggered=true` gesetzt; ist er unbestromt und `triggered=true`, wird nur `triggered=false` gesetzt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DispenserBlock#neighborChanged`; [SRC-M-WIKI-DISPENSER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Beide Zustandswechsel nutzen Flag 2, lösen also keine Nachbar-Updates aus.

### DDH-003: Die Ausgabe passiert im geplanten Tick unabhängig von der aktuellen Leistung
- Aussage: `DispenserBlock#tick` ruft `dispenseFrom` ohne erneute Leistungsprüfung auf; auch ein Puls, der vor Ablauf der 4 gt endet, führt zu genau einer Ausgabe.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DispenserBlock#tick`, `DispenserBlock#dispenseFrom`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Das Wiki macht zu Pulsen kürzer als 4 gt keine Aussage.

### DDH-004: Weitere Pulse innerhalb der 4 gt gehen verloren
- Aussage: Wird der Dispenser innerhalb der 4 gt aus-, wieder eingeschaltet, wird der zweite geplante Tick verworfen, weil `LevelChunkTicks#schedule` einen bereits ausstehenden Tick für dieselbe Position und denselben Block nicht erneut aufnimmt; es gibt nur eine Ausgabe.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelChunkTicks#schedule`, `DispenserBlock#neighborChanged`; [SRC-M-WIKI-DISPENSER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Wiki: „additional inputs are ignored".

### DDH-005: Ein bestromt platzierter Dispenser löst erst bei einem Update aus
- Aussage: `DispenserBlock` überschreibt weder `onPlace` noch `setPlacedBy` mit einer Leistungsprüfung; ein in eine bestromte Position gesetzter Dispenser/Dropper wird erst beim nächsten `neighborChanged` ausgelöst.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DispenserBlock`
- Konfidenz: mittel
- Status: belegt
- Hinweise: Nicht im Spiel geprüft. Dispenser und Dropper sind nicht schiebbar (DDH-014), ein Ankunfts-Update wie bei Pistons (PIS-008) gibt es also nicht.

### DDH-006: Dropper legt Items in einen Container vor sich, sonst wirft er sie aus
- Aussage: `DropperBlock#dispenseFrom` wählt einen zufälligen belegten Slot und überträgt genau ein Item in einen Container vor der Front (über `HopperBlockEntity#addItem`), sonst wird das Item mit dem Standardverhalten ausgeworfen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DropperBlock#dispenseFrom`, `DispenserBlockEntity#getRandomSlot`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Die Slotwahl nutzt den Level-Zufall; ein Simulator kann sie nicht deterministisch nachbilden, für reine Füllstands-Logik ist das bei gleichen Items egal.

### DDH-007: Hopper wird ohne QC und ohne Verzögerung gesperrt
- Aussage: `HopperBlock#checkPoweredState` setzt `enabled = !hasNeighborSignal(pos)` sofort (Flag 2) bei `neighborChanged` und `onPlace`; die Position über dem Hopper wird nicht geprüft.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlock#checkPoweredState`, `HopperBlock#neighborChanged`, `HopperBlock#onPlace`; [SRC-M-WIKI-HOPPER]
- Konfidenz: hoch
- Status: belegt

### DDH-008: Ein gesperrter Hopper überträgt nichts
- Aussage: `HopperBlockEntity#tryMoveItems` schiebt und saugt nur, wenn der Cooldown abgelaufen ist und `enabled=true` gilt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlockEntity#tryMoveItems`; [SRC-M-WIKI-HOPPER]
- Konfidenz: hoch
- Status: belegt

### DDH-009: Der Cooldown läuft auch im gesperrten Zustand ab
- Aussage: `HopperBlockEntity#pushItemsTick` verringert `cooldownTime` in jedem Block-Entity-Tick und setzt ihn bei Ablauf auf 0, unabhängig von `enabled`; ein entsperrter Hopper mit abgelaufenem Cooldown kann im nächsten eigenen Block-Entity-Tick sofort übertragen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlockEntity#pushItemsTick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Das Wiki sagt nur, dass das Entfernen der Leistung den Cooldown nicht ändert.

### DDH-010: Erfolgreicher Transfer setzt 8 gt Cooldown
- Aussage: Hat ein Hopper in seinem Tick erfolgreich ausgegeben oder angesaugt, wird `cooldownTime` auf 8 (`MOVE_ITEM_SPEED`) gesetzt; er arbeitet dann wieder im 8. Block-Entity-Tick danach.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlockEntity#tryMoveItems`, `HopperBlockEntity#pushItemsTick`; [SRC-M-WIKI-HOPPER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Pro Tick erst Ausgeben (ein Item), dann Ansaugen (ein Item), beides kann im selben Tick passieren.

### DDH-011: Ein leerer Hopper, der von einem Hopper ein Item erhält, arbeitet 7 gt später wieder
- Aussage: Erhält ein leerer Hopper ein Item und hat keinen Cooldown über 8, wird sein Cooldown auf 8 gesetzt, bzw. auf 7, wenn die Quelle ein Hopper ist und der Empfänger in diesem Game-Tick bereits getickt hat; bei Quelle Hopper führt der Empfänger dadurch in beiden Tick-Reihenfolgen seinen nächsten Transfer 7 gt nach dem Empfang aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlockEntity#tryMoveInItem`, `HopperBlockEntity#pushItemsTick`; [SRC-M-WIKI-HOPPER]
- Konfidenz: mittel
- Status: belegt
- Hinweise: Das Wiki sagt vereinfacht „Cooldown 7 gt beim Schieben in einen leeren Hopper". Laut Code ist der gesetzte Wert 8 oder 7 je nach Ticker-Reihenfolge (`tickedGameTime` des Empfängers ≥ dem der Quelle → 7); ist der Empfänger noch nicht getickt, zählt er im selben Tick noch auf 7 herunter. Die 7-gt-Folgerung ist aus dem Code abgeleitet, nicht im Spiel geprüft. Schieben in einen nicht leeren Hopper ändert dessen Cooldown nicht.

### DDH-012: Hopper arbeiten in der Block-Entity-Phase in Ticker-Reihenfolge
- Aussage: Hopper-Transfers laufen in `pushItemsTick`, also in der Block-Entity-Phase von `ServerLevel#tick`, in der Reihenfolge der Liste `Level#blockEntityTickers` (Einfügereihenfolge der Block Entities).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#tickBlockEntities`, `LevelChunk#updateBlockEntityTicker`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Die Einfügereihenfolge hängt von Lade-/Platzierungsreihenfolge ab und ist aus einer Schematic allein nicht eindeutig ableitbar.

### DDH-013: Inventaränderungen lösen Comparator-Updates aus
- Aussage: Nach einem erfolgreichen Hopper-Transfer ruft `BlockEntity#setChanged` `Level#updateNeighbourForOutputSignal` auf, sodass benachbarte Comparatoren neu auslesen; Dispenser, Dropper und Hopper liefern ihr Analogsignal über `AbstractContainerMenu#getRedstoneSignalFromBlockEntity`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlockEntity#tryMoveItems`, `BlockEntity#setChanged`, `HopperBlock#getAnalogOutputSignal`, `DispenserBlock#getAnalogOutputSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Formel und Comparator-Timing siehe Comparator-Datei.

### DDH-014: Dispenser, Dropper und Hopper sind nicht schiebbar
- Aussage: Alle drei besitzen ein Block Entity und sind daher für Pistons unbeweglich.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#isPushable`
- Konfidenz: hoch
- Status: belegt
