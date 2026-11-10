---
topic: Redstone-Fackel
prefix: TRCH
---

# Redstone-Fackel

Die Redstone-Fackel gibt es als stehende Fackel (`minecraft:redstone_torch`, `RedstoneTorchBlock`, Zustand
`lit`) und als Wandfackel (`minecraft:redstone_wall_torch`, `RedstoneWallTorchBlock`, Zustände `facing`, `lit`).
Sie invertiert das Signal des Blocks, an dem sie hängt, mit 2 Game-Ticks Verzögerung und kann bei zu
häufigem Schalten durchbrennen.

### TRCH-001: Stehende Fackel liest den Block darunter
- Aussage: Eine stehende Redstone-Fackel gilt als „angesteuert", wenn `level.hasSignal(pos.below(), DOWN)` wahr ist, also der Block darunter ein Signal > 0 nach oben liefert (inkl. Ladung, falls er ein Leiter ist).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#hasNeighborSignal`, `SignalGetter#getSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-sources.yaml)

### TRCH-002: Wandfackel liest den Block hinter sich
- Aussage: Eine Wandfackel liest den Block in Richtung `facing.getOpposite()` (den Block, an dem sie hängt); `facing` zeigt von der Wand weg.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWallTorchBlock#hasNeighborSignal`, `RedstoneWallTorchBlock#canSurvive`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-inverter.yaml)

### TRCH-003: Die Fackel invertiert: an genau dann, wenn kein Eingang
- Aussage: Im Endzustand ist `lit=true` genau dann, wenn der Befestigungsblock kein Signal liefert (Ausgang 15 bzw. 0).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#tick`, `RedstoneTorchBlock#ownSignal`; [SRC-WIKI-TORCH]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-inverter.yaml)

### TRCH-004: Die Schaltverzögerung beträgt 2 Game-Ticks mit Priorität NORMAL
- Aussage: Bei einem Neighbor-Update, bei dem `lit` gleich dem Eingangszustand ist (also umgeschaltet werden muss), plant die Fackel einen Tick nach 2 gt mit Standardpriorität `NORMAL`, sofern nicht bereits in diesem Tick ein Fackel-Tick an dieser Position ausgeführt wird.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#neighborChanged`; [SRC-WIKI-TORCH]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-inverter.yaml)
- Hinweise: Der Zustand wird erst im Tick erneut geprüft; ist der Eingang dann wieder wie vorher, schaltet die Fackel nicht. Kurze Pulse (< 2 gt) können daher verschluckt werden.

### TRCH-005: Fackel-Zustandswechsel benutzen volle Nachbar-Updates
- Aussage: Die Fackel setzt `lit` mit `setBlockAndUpdate` (Flags 3) und aktualisiert zusätzlich über `onPlace` die Nachbarn aller sechs angrenzenden Blöcke (`updateNeighborsAt` für jede Richtung, Reihenfolge `Direction.values()`: unten, oben, N, S, W, O).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#tick`, `RedstoneTorchBlock#onPlace`, `RedstoneTorchBlock#notifyNeighbors`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Also Updates bis Abstand 2 (Taxicab). Beim Entfernen ebenso (`affectNeighborsAfterRemoval`, außer durch Kolben).

### TRCH-006: Die Fackel lädt den Block darüber stark
- Aussage: `getDirectSignal` ist nur für die Abfrage-Richtung `DOWN` (Abfrager liegt über der Fackel) ungleich 0; der Block über einer leuchtenden Fackel (stehend oder an der Wand) wird stark mit 15 geladen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#getDirectSignal`; [SRC-WIKI-TORCH]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-burnout.yaml)
- Hinweise: `RedstoneWallTorchBlock` überschreibt `getDirectSignal` nicht.

### TRCH-007: Stehende Fackel versorgt alle Nachbarn außer dem Block darunter schwach
- Aussage: `getSignal` einer stehenden Fackel liefert 15 für jede Abfrage außer aus Richtung des Blocks darunter (Abfrage-Richtung `UP`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#getSignal`; [SRC-WIKI-TORCH]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-sources.yaml)

### TRCH-008: Wandfackel versorgt alle Nachbarn außer dem Befestigungsblock
- Aussage: `getSignal` einer Wandfackel liefert 15 für jede Abfrage-Richtung außer `facing`, d. h. nicht an den Block, an dem sie hängt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWallTorchBlock#getSignal`; [SRC-WIKI-TORCH]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-repeater-clock.yaml)

### TRCH-009: Burnout ab dem 8. Ausschalten innerhalb des Zeitfensters
- Aussage: Bei jedem Ausschalten wegen Eingang wird ein Eintrag (Position, Spielzeit) in eine pro Level geführte Liste geschrieben; sind danach für diese Position ≥ 8 Einträge vorhanden, brennt die Fackel durch.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#tick`, `RedstoneTorchBlock#isToggledTooFrequently` (`MAX_RECENT_TOGGLES`=8); [SRC-WIKI-TORCH]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-burnout.yaml)
- Hinweise: Wiki: „mehr als 8 Mal innerhalb von 60 gt". Code: das 8. aufgezeichnete Ausschalten löst aus. Nur Ausschalten (lit→unlit) wird gezählt. Im Spiel bestätigt: In `torch-burnout` geht die Fackel bei Tick 4, 8, …, 32 aus und bleibt nach dem 8. Ausschalten aus. Der Code hat recht, die Wiki-Formulierung ist ungenau.

### TRCH-010: Einträge älter als 60 Game-Ticks werden nur beim Fackel-Tick entfernt
- Aussage: Vor jeder Auswertung entfernt `tick` Einträge vom Listenanfang, deren Alter (`gameTime - when`) größer als 60 ist (`RECENT_TOGGLE_TIMER`); Einträge mit Alter genau 60 zählen noch.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#tick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Die Liste ist global pro Level (alle Fackeln) und wird nur vom Anfang her bereinigt; `RECENT_TOGGLES` ist eine `WeakHashMap` im Speicher und wird nicht gespeichert.

### TRCH-011: Eine durchgebrannte Fackel plant einen Wiederversuch nach 160 Game-Ticks
- Aussage: Beim Durchbrennen plant die Fackel einen Tick nach 160 gt (`RESTART_DELAY`) und löst Level-Event 1502 (Rauch/Zischen) aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#tick`; [SRC-WIKI-TORCH]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-repeater-clock.yaml)

### TRCH-012: Eine aus-geschaltete Fackel geht nur an, wenn nicht zu häufig geschaltet
- Aussage: Eine Fackel mit `lit=false` und ohne Eingang schaltet im Tick nur ein, wenn für ihre Position weniger als 8 Einträge in der Toggle-Liste stehen; sonst bleibt sie aus, ohne neuen Tick zu planen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneTorchBlock#tick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ein späteres Neighbor-Update plant erneut (TRCH-004); laut Wiki geht eine durchgebrannte Fackel nach einem Block-Update wieder an.
