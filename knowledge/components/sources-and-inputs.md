---
topic: Signalquellen und Eingaben
prefix: SRCB
---

# Signalquellen und Eingaben

Überblick über Blöcke, die selbst ein Redstone-Signal erzeugen: Hebel, Knöpfe, Druckplatten, Redstone-Block,
Zielblock, Tageslichtsensor, Lesepult, Redstone-Falle (Truhe) und Sculk-Sensoren. Für den Simulator zählen
vor allem: Dauer des Signals, Stärke, welcher Nachbar stark geladen wird und welche Positionen ein Update
bekommen. Zeiten in Game-Ticks (gt).

### SRCB-001: Hebel schaltet sofort und lädt den Befestigungsblock stark
- Aussage: Ein Hebel schaltet beim Benutzen sofort um (`setBlockAndUpdate`), liefert dann an alle Nachbarn schwach 15 und lädt den Block, an dem er befestigt ist, stark mit 15.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LeverBlock#pull`, `LeverBlock#getDirectSignal`, `BlockBehaviour#getSignal`, `FaceAttachedHorizontalDirectionalBlock#getConnectedDirection`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-inverter.yaml)

### SRCB-002: Hebel und Knopf aktualisieren eigene Position und Befestigungsblock
- Aussage: Hebel und Knöpfe rufen nach dem Umschalten `updateNeighborsAt` für ihre eigene Position und dann für den Befestigungsblock auf (zusätzlich zu den Updates aus `setBlockAndUpdate`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LeverBlock#updateNeighbours`, `ButtonBlock#updateNeighbours`
- Konfidenz: hoch
- Status: belegt

### SRCB-003: Steinknöpfe bleiben 20 gt gedrückt
- Aussage: Stein- und Polierter-Schwarzstein-Knöpfe planen beim Drücken einen Tick nach 20 gt, nach dem sie wieder loslassen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Blocks` (`STONE_BUTTON`, `POLISHED_BLACKSTONE_BUTTON`: `ticksToStayPressed`=20), `ButtonBlock#press`, `ButtonBlock#checkPressed`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-pulse-extend.yaml)

### SRCB-004: Holzknöpfe bleiben 30 gt gedrückt und reagieren auf Pfeile
- Aussage: Alle Holzknöpfe (inkl. Bambus, Karmesin, Wirr) bleiben 30 gt gedrückt; solange ein Pfeil im Knopf steckt, wird der Tick erneut geplant und der Knopf bleibt gedrückt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Blocks` (`*_BUTTON`: `ticksToStayPressed`=30), `ButtonBlock#checkPressed`, `ButtonBlock#entityInside`
- Konfidenz: hoch
- Status: belegt

### SRCB-005: Knöpfe laden den Befestigungsblock stark
- Aussage: Ein gedrückter Knopf liefert schwach 15 an alle Nachbarn und stark 15 an den Befestigungsblock.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ButtonBlock#getDirectSignal`, `ButtonBlock#ownSignal`
- Konfidenz: hoch
- Status: belegt

### SRCB-006: Druckplatten laden den Block darunter stark
- Aussage: Druckplatten liefern ihr Signal schwach an alle Nachbarn und stark an den Block darunter; bei Änderung werden die eigene Position und der Block darunter aktualisiert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BasePressurePlateBlock#getDirectSignal`, `BasePressurePlateBlock#updateNeighbours`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Zustandsänderung mit Flag 2 plus explizite Updates (`BasePressurePlateBlock#checkPressed`).

### SRCB-007: Nachprüfintervall der Druckplatten
- Aussage: Solange eine Druckplatte gedrückt ist, prüft sie sich nach 20 gt (Holz/Stein) bzw. 10 gt (gewichtete Platten) erneut.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `BasePressurePlateBlock#getPressedTime`, `WeightedPressurePlateBlock#getPressedTime`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Holz: alle Entities, Stein: nur `LivingEntity` (`PressurePlateBlock#getSignalStrength`). Gewichtet: `ceil(min(n, max)/max * 15)` mit max 15 (Gold) bzw. 150 (Eisen).

### SRCB-008: Redstone-Block liefert nur schwaches Signal und ist kein Leiter
- Aussage: Ein Redstone-Block liefert an alle Nachbarn ein (schwaches) Signal 15, aber kein starkes (`getDirectSignal`=0) und ist selbst kein Redstone-Leiter.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PoweredBlock`, `Blocks#REDSTONE_BLOCK` (`isRedstoneConductor(never)`)
- Konfidenz: hoch
- Status: belegt
- Hinweise: Als Seiteneingang von Comparatoren zählt er dennoch mit 15 (`SignalGetter#getControlInputSignal`), für Repeater-Sperre nicht.

### SRCB-009: Zielblock: Stärke nach Trefferposition, Dauer 20 gt (Pfeil) bzw. 8 gt
- Aussage: Ein Zielblock setzt bei Projektiltreffer `power` auf 1–15 je nach Abstand zur Flächenmitte und fällt nach 20 gt (Pfeile) bzw. 8 gt (andere Projektile) auf 0 zurück; während ein Tick geplant ist, wird ein neuer Treffer ignoriert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `TargetBlock#updateRedstoneOutput`, `TargetBlock#getRedstoneStrength`, `TargetBlock#tick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Zielblock liefert nur schwaches Signal (kein `getDirectSignal`). In `Blocks#TARGET` ist `isRedstoneConductor` nicht überschrieben (Standard: voller Block = Leiter); nicht separat geprüft.

### SRCB-010: Tageslichtsensor aktualisiert nur alle 20 gt
- Aussage: Ein Tageslichtsensor berechnet seine Stärke im Block-Entity-Tick nur, wenn `gameTime % 20 == 0`, bzw. sofort beim Umschalten von `inverted`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DaylightDetectorBlock#tickEntity`, `DaylightDetectorBlock#updateSignalStrength`, `DaylightDetectorBlock#useWithoutItem`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Nur schwaches Signal (`ownSignal`=`power`). Für tick-genaue Simulation reicht meist ein fester `power`-Wert.

### SRCB-011: Lesepult gibt beim Blättern einen 2-gt-Puls und lädt den Block darunter stark
- Aussage: Beim Seitenwechsel setzt das Lesepult `powered=true` und plant einen Tick nach 2 gt, der es wieder ausschaltet; es lädt den Block darunter stark mit 15.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LecternBlock#signalPageChange`, `LecternBlock#tick`, `LecternBlock#getDirectSignal`
- Konfidenz: hoch
- Status: belegt

### SRCB-012: Comparator-Wert des Lesepults
- Aussage: Ein Lesepult mit Buch liefert `floor(p * 14) + 1` mit `p = Seite / (Seitenzahl − 1)` (bzw. `p = 1` bei höchstens einer Seite), ohne Buch 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LecternBlockEntity#getRedstoneSignal`, `LecternBlock#getAnalogOutputSignal`
- Konfidenz: hoch
- Status: belegt

### SRCB-013: Redstone-Falle liefert die Anzahl der Betrachter
- Aussage: Eine Redstone-Falle (trapped chest) liefert `min(Anzahl Spieler mit geöffneter Truhe, 15)` schwach an alle Nachbarn und stark an den Block darunter.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `TrappedChestBlock#ownSignal`, `TrappedChestBlock#getDirectSignal`, `TrappedChestBlockEntity#signalOpenCount`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Bei Änderung werden eigene Position und Block darunter aktualisiert.

### SRCB-014: Sculk-Sensor: 30 gt aktiv, dann 10 gt Abklingzeit
- Aussage: Ein Sculk-Sensor bleibt nach Aktivierung 30 gt aktiv (kalibrierter Sculk-Sensor 10 gt) und geht danach für 10 gt in die Phase `cooldown`, bevor er wieder `inactive` wird.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SculkSensorBlock#getActiveTicks`, `CalibratedSculkSensorBlock#getActiveTicks`, `SculkSensorBlock#deactivate`, `SculkSensorBlock#tick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Stärke hängt von der Entfernung der Vibration ab; Comparator liest die Vibrationsfrequenz (nur in Phase `active`).

### SRCB-015: Sculk-Sensoren laden den Block darunter stark
- Aussage: Sculk-Sensoren liefern `power` schwach an Nachbarn und stark an den Block darunter; der kalibrierte Sensor liefert an den Nachbarn in Richtung `facing.getOpposite()` kein Signal (Abfrage-Richtung gleich `facing`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SculkSensorBlock#getDirectSignal`, `CalibratedSculkSensorBlock#getSignal`
- Konfidenz: hoch
- Status: belegt
