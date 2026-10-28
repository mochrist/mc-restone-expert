---
topic: Quasi-Connectivity
prefix: QC
---

# Quasi-Connectivity

Quasi-Connectivity (QC) heißt: ein Block wertet zusätzlich die Leistung an der Position **direkt über sich**
aus, als ob er zwei Blöcke hoch wäre. Das ist ein Java-Edition-Verhalten, das historisch aus dem Code der
Pistons stammt. Weil der QC-Block nur bei eigenen Block-Updates (`neighborChanged`) neu rechnet, ein
Signalwechsel an der Position darüber ihn aber oft nicht direkt updatet, entsteht ein „bestromter, aber nicht
reagierender" Zustand, die Grundlage vieler BUDs (siehe `bud.md`).

Hinweis zur Liste in `idea.md`: Dort stehen auch Lampen, Rails und Türen. Laut 26.3-Code haben Lampen und
Rails **kein** QC; Türen prüfen nur ihre eigene zweite Hälfte (siehe QC-005).

### QC-001: Pistons und Sticky Pistons haben QC
- Aussage: `PistonBaseBlock#getNeighborSignal` wertet zusätzlich die Signale der Nachbarn von `pos.above()` (alle Richtungen außer DOWN) aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#getNeighborSignal`; [SRC-M-WIKI-QC]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Details siehe PIS-002.

### QC-002: Dispenser und Dropper haben QC
- Aussage: `DispenserBlock#neighborChanged` verwendet `hasNeighborSignal(pos) || hasNeighborSignal(pos.above())`; `DropperBlock` erbt das.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DispenserBlock#neighborChanged`, `DropperBlock`; [SRC-M-WIKI-QC]; [SRC-M-WIKI-DISPENSER]
- Konfidenz: hoch
- Status: belegt

### QC-003: Der Crafter hat kein QC
- Aussage: `CrafterBlock#neighborChanged` prüft nur `hasNeighborSignal(pos)`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlock#neighborChanged`; [SRC-M-WIKI-QC]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Wiki: „crafters are not affected by quasi-connectivity".

### QC-004: Redstone-Lampen, Rails, Hopper, Trapdoors, Zauntore und Notenblöcke haben kein QC
- Aussage: `RedstoneLampBlock`, `PoweredRailBlock`, `BaseRailBlock`, `HopperBlock`, `TrapDoorBlock`, `FenceGateBlock` und `NoteBlock` prüfen ausschließlich `hasNeighborSignal(pos)` (Powered/Activator Rails zusätzlich verbundene Rails), nicht die Position darüber.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneLampBlock#neighborChanged`, `PoweredRailBlock#updateState`, `HopperBlock#checkPoweredState`, `TrapDoorBlock#neighborChanged`, `FenceGateBlock#neighborChanged`, `NoteBlock#neighborChanged`; [SRC-M-WIKI-QC]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Widerlegt die Liste in `idea.md` (Lampen, Rails). Powered Rails hatten laut Wiki nur in Beta 1.5 QC-artiges Verhalten. Im gesamten Paket `net.minecraft.world.level.block` verwenden nur `DispenserBlock` und `DoorBlock` `hasNeighborSignal` auf einer anderen als der eigenen Position, dazu kommt `PistonBaseBlock` mit eigener Schleife.

### QC-005: Türen prüfen beide Hälften, das ist kein QC im engeren Sinn
- Aussage: `DoorBlock#neighborChanged` prüft `hasNeighborSignal` an der eigenen Position und an der Position der anderen Türhälfte (oben bzw. unten); da beide Positionen zur Tür gehören, öffnet ein Signal neben einer der Hälften die Tür.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DoorBlock#neighborChanged`; [SRC-M-WIKI-QC]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Die Wiki-Seite nutzt Türen nur als Analogie für QC. Das Update einer Hälfte wird per Shape-Update an die andere weitergegeben (`DoorBlock#updateShape`), daher kein BUD-artiger Zustand wie bei Pistons zu erwarten; nicht im Spiel geprüft.

### QC-006: Die QC-Position zählt alle Signalarten wie an einer echten Blockposition
- Aussage: Für die Position über dem QC-Block wird `SignalGetter#getSignal` je Nachbar verwendet, d. h. sowohl direkte Signale von Quellen (z. B. Redstone-Block, Hebel, Fackel, Repeater, Staub) als auch Signale durch stark bestromte Leiter neben dieser Position zählen; der Block an der Position selbst muss nicht existieren.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SignalGetter#hasNeighborSignal`, `SignalGetter#getSignal`, `PistonBaseBlock#getNeighborSignal`; [SRC-M-WIKI-DISPENSER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ist die Position darüber selbst ein Leiter, wird dieser nicht als „bestromter Block" gewertet, sondern nur seine Nachbarn werden abgefragt (beim Dispenser über `hasNeighborSignal(above)`).

### QC-007: QC-Aktivierung braucht ein Block-Update am QC-Block
- Aussage: Ändert sich nur die Leistung an der Position über dem QC-Block, erhält dieser in der Regel kein `neighborChanged` und reagiert erst beim nächsten Block-Update an seiner eigenen Position.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#neighborChanged`, `DispenserBlock#neighborChanged`, `NeighborUpdater#updateNeighborsAtExceptFromFacing`; [SRC-M-WIKI-QC]; [SRC-M-WIKI-BUD]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Eine Signalquelle aktualisiert über `updateNeighborsAt` nur ihre sechs direkten Nachbarn. Ob der QC-Block trotzdem ein Update bekommt, hängt davon ab, ob die Quelle auch Nachbarn ihrer Nachbarn aktualisiert (z. B. Redstone-Staub, Repeater/Comparator über den Block vor ihnen, Hebel/Knopf über den Block, an dem sie hängen). Das Wiki nennt „Redstone-Änderungen innerhalb von zwei Blöcken" als typische Updatequelle.

### QC-008: Ein QC-bestromter Piston fährt auch nicht von selbst ein
- Aussage: Verliert ein ausgefahrener Piston seine (QC- oder direkte) Leistung, ohne ein Block-Update zu erhalten, bleibt er ausgefahren, bis ein Update an seiner Position eintrifft.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#checkIfExtend`, `PistonBaseBlock#neighborChanged`; [SRC-M-WIKI-BUD]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Grundlage für „stuck"-Zustände. Davon zu unterscheiden ist der Wiki-Fall „Redstone-Block auf nach oben zeigendem Piston: kann ausfahren, aber nicht einfahren" [SRC-M-WIKI-PISTON]: dort liegt der geschobene Redstone-Block neben der QC-Position (Kopfposition) und hält den Piston dauerhaft per QC bestromt (QC-001).

### QC-009: Kein QC beim Hopper-Sperren
- Aussage: Ein Hopper wird nur durch Leistung an seiner eigenen Position gesperrt; Leistung an der Position darüber sperrt ihn nicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `HopperBlock#checkPoweredState`
- Konfidenz: hoch
- Status: belegt
