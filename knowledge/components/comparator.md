---
topic: Redstone Comparator
prefix: CMP
---

# Redstone Comparator

Der Comparator (`minecraft:comparator`, Klasse `ComparatorBlock`, Oberklasse `DiodeBlock`) hat eine feste
Verzögerung von 2 Game-Ticks, zwei Modi (`mode=compare|subtract`) und speichert seine aktuelle
Ausgangsstärke im Block-Entity (`ComparatorBlockEntity`, NBT `OutputSignal`). Er kann Blöcke mit
analogem Ausgang (Container, Kuchen, Item-Rahmen, ...) direkt oder durch einen Leiterblock hindurch lesen.
Ein- und Ausgangsseite sind wie beim Repeater (siehe REP-001/REP-002), da beide `DiodeBlock` erben.

### CMP-001: Eingang auf der `facing`-Seite, Ausgang auf der Gegenseite
- Aussage: Ein Comparator liest seinen Haupteingang vom Nachbarn in Richtung `facing` und gibt an den Nachbarn in Richtung `facing.getOpposite()` aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#getInputSignal`, `DiodeBlock#getInputSignal`, `DiodeBlock#getSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Gleiche Semantik wie beim Repeater; bestätigt die Annahme in `src/redstone/render/textdump.py`.

### CMP-002: Die Verzögerung ist immer 2 Game-Ticks
- Aussage: Comparator-Ticks werden immer mit Verzögerung 2 gt geplant, unabhängig vom Modus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#getDelay`, `ComparatorBlock#checkTickOnNeighbor`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt

### CMP-003: Tick-Priorität HIGH bei priorisierter Diode vorne, sonst NORMAL
- Aussage: Steht am Ausgang eine Diode, die nicht frontal zurück in den Comparator zeigt (`shouldPrioritize`), plant der Comparator mit `TickPriority.HIGH` (-1), sonst mit `NORMAL` (0).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#checkTickOnNeighbor`, `DiodeBlock#shouldPrioritize`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Anders als beim Repeater gibt es kein EXTREMELY_HIGH/VERY_HIGH.

### CMP-004: Ein Tick wird nur geplant, wenn sich Ausgangsstärke oder `powered` ändern würden
- Aussage: `checkTickOnNeighbor` plant einen Tick, wenn die neu berechnete Ausgangsstärke vom gespeicherten `OutputSignal` abweicht oder `powered` nicht zu `shouldTurnOn` passt, und nur, wenn für diese Position in diesem Tick nicht bereits ein Comparator-Tick ausgeführt wird.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#checkTickOnNeighbor`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Werte werden erst beim Tick neu berechnet, nicht beim Planen; Schwankungen kürzer als 2 gt können daher verloren gehen ([SRC-WIKI-COMPARATOR]).

### CMP-005: Im Compare-Modus ist die Ausgabe der Eingang oder 0
- Aussage: Im Modus `compare` ist die Ausgangsstärke gleich dem Haupteingang, wenn die stärkere Seiteneingabe ≤ Haupteingang ist, sonst 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#calculateOutputSignal`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt

### CMP-006: Im Subtract-Modus ist die Ausgabe Eingang minus stärkste Seite
- Aussage: Im Modus `subtract` ist die Ausgangsstärke `max(Eingang − max(links, rechts), 0)`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#calculateOutputSignal`, `ComparatorBlock#shouldTurnOn`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt
- Hinweise: `powered` ist im Subtract-Modus nur bei Eingang > Seite wahr; bei Gleichstand ist der Comparator aus.

### CMP-007: Seiteneingänge akzeptieren Staub, Redstone-Blöcke und gerichtete Quellen
- Aussage: Ein Seiteneingang liefert 15 für einen Redstone-Block, den `power`-Wert für Redstone-Staub und für andere Signalquellen deren `getDirectSignal` in Richtung des Comparators; geladene Leiterblöcke an der Seite zählen nicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getAlternateSignal`, `SignalGetter#getControlInputSignal`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Praktisch zählen Repeater/Comparatoren/Observer, die auf die Seite zeigen. Eine daneben stehende Redstone-Fackel zählt nicht (ihr `getDirectSignal` ist nur nach oben ungleich 0). Wiki: „Seiteneingänge zählen nur, wenn sie den Comparator stark laden" – entspricht dem Code bis auf die Sonderfälle Staub/Redstone-Block.

### CMP-008: Ein Block mit analogem Ausgang ersetzt das normale Eingangssignal
- Aussage: Hat der Block direkt am Eingang `hasAnalogOutputSignal`, ist der Haupteingang genau dessen `getAnalogOutputSignal` (auch wenn ein normales Redstone-Signal stärker wäre).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#getInputSignal`
- Konfidenz: hoch
- Status: belegt

### CMP-009: Durch einen Leiterblock wird der Block dahinter gelesen
- Aussage: Ist der Eingangsblock ein Redstone-Leiter ohne analogen Ausgang und sein Signal < 15, liest der Comparator den Block zwei Felder in `facing`-Richtung (bzw. einen Item-Rahmen dort) und verwendet dessen Analogwert anstelle des Leitersignals, falls vorhanden.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#getInputSignal`, `ComparatorBlock#getItemFrame`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ist der Leiter mit 15 geladen, gewinnt die 15. Bei mehreren Item-Rahmen im Feld wird keiner gelesen (genau einer, mit `getDirection()==facing`). Gibt es Rahmen und Block, zählt das Maximum.

### CMP-010: Container-Signalstärke
- Aussage: Für Container ist die Stärke `floor(f * 14) + (f > 0 ? 1 : 0)`, wobei `f` der Mittelwert über alle Slots von `Anzahl / maxStackSize(Item)` ist (leer = 0).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `AbstractContainerMenu#getRedstoneSignalFromContainer`, `Mth#lerpDiscrete`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Berechnung in `float`. Ein einziges Item in irgendeinem Slot ergibt bereits 1.

### CMP-011: Item-Rahmen liefert 1–8 nach Drehung
- Aussage: Ein Item-Rahmen liefert 0 wenn leer, sonst `rotation % 8 + 1`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ItemFrame#getAnalogOutput`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt

### CMP-012: Kuchen liefert (7 − bites) × 2
- Aussage: Ein Kuchen liefert `(7 - bites) * 2`, also 14 für einen vollen Kuchen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CakeBlock#getOutputSignal`; [SRC-WIKI-COMPARATOR]
- Konfidenz: hoch
- Status: belegt

### CMP-013: Die Ausgabe ist das gespeicherte `OutputSignal`, nur wenn `powered`
- Aussage: Ein Comparator liefert an seinem Ausgang den im Block-Entity gespeicherten Wert `OutputSignal`, aber nur wenn `powered=true`, sonst 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#getOutputSignal`, `DiodeBlock#ownSignal`, `ComparatorBlockEntity`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Für den Simulator muss das Block-Entity (`OutputSignal`) aus der Schematic mitgelesen werden.

### CMP-014: Der Comparator lädt den Block vor sich stark
- Aussage: Wie beim Repeater ist `getDirectSignal` gleich `getSignal`, ein Leiter am Ausgang wird also stark mit der Ausgangsstärke geladen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getDirectSignal`
- Konfidenz: hoch
- Status: belegt

### CMP-015: Beim Tick werden Ausgangswert und `powered` neu gesetzt
- Aussage: Im Tick berechnet der Comparator die Ausgabe neu, speichert sie im Block-Entity, setzt `powered` gemäß `shouldTurnOn` (Flag 2) und ruft `updateNeighborsInFront` auf, falls sich der Wert geändert hat oder der Modus `compare` ist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#tick`, `ComparatorBlock#refreshOutputState`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Im Compare-Modus wird also auch ohne Änderung ein Update nach vorne ausgelöst. Ändert sich `powered`, kommt über `DiodeBlock#onPlace` ein weiteres `updateNeighborsInFront` hinzu.

### CMP-016: Moduswechsel wirkt sofort ohne Verzögerung
- Aussage: Ein Rechtsklick ändert `mode` (Flag 2) und ruft sofort `refreshOutputState` auf, also ohne 2-gt-Verzögerung.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ComparatorBlock#useWithoutItem`
- Konfidenz: hoch
- Status: belegt

### CMP-017: Comparator-Updates gehen an horizontale Nachbar-Comparatoren, auch durch einen Leiter
- Aussage: `updateNeighbourForOutputSignal` ruft für jede horizontale Richtung (Reihenfolge N, O, S, W) `neighborChanged` an einem dort stehenden Comparator auf; ist dort stattdessen ein Leiterblock, an einem Comparator ein Feld weiter.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#updateNeighbourForOutputSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Reihenfolge aus `Direction.Plane.HORIZONTAL`.

### CMP-018: Auslöser für Comparator-Updates
- Aussage: Comparator-Updates werden ausgelöst bei `setBlock` mit Flag 1, wenn der neue Zustand `hasAnalogOutputSignal` hat, sowie bei jedem `BlockEntity#setChanged` (für jeden Block-Entity-Block, nicht nur analoge).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Level#setBlock`, `BlockEntity#setChanged`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Damit reagieren Comparatoren auf Inventaränderungen von Truhen, Trichtern usw.
