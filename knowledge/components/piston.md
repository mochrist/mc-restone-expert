---
topic: Piston und Sticky Piston
prefix: PIS
---

# Piston und Sticky Piston

Piston (`minecraft:piston`) und Sticky Piston (`minecraft:sticky_piston`) sind beide `PistonBaseBlock`
(Feld `isSticky`). Ein Piston reagiert nicht sofort, sondern stellt bei einer Zustandsänderung einen
**Block-Event** in die Warteschlange (`Level#blockEvent`); die eigentliche Bewegung passiert in der
Block-Event-Phase (`PistonBaseBlock#triggerEvent`). Bewegte Blöcke werden für die Dauer der Bewegung zu
`minecraft:moving_piston` mit einem `PistonMovingBlockEntity`, das in der Block-Entity-Phase fortschreitet.
Alle Zeitangaben in Game-Ticks (gt). „Tick T" bezeichnet den Tick, in dessen Block-Event-Phase der Event
ausgeführt wird. Phasenreihenfolge siehe `mechanics/tick-phases-and-order.md`.

### PIS-001: Pistons prüfen ihre Aktivierung nur bei neighborChanged, onPlace und setPlacedBy
- Aussage: `PistonBaseBlock#checkIfExtend` wird nur aus `neighborChanged`, `onPlace` (nur wenn vorher ein anderer Block dort stand und kein Block Entity existiert) und `setPlacedBy` aufgerufen; ohne Block-Update bemerkt ein Piston eine Leistungsänderung nicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#neighborChanged`, `PistonBaseBlock#onPlace`, `PistonBaseBlock#setPlacedBy`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-piston-qc.yaml)
- Hinweise: Grundlage für BUD-Verhalten, siehe `mechanics/bud.md`.

### PIS-002: Leistungsprüfung ignoriert die Front und schließt Quasi-Connectivity ein
- Aussage: `PistonBaseBlock#getNeighborSignal` ist wahr, wenn einer der fünf Nachbarn außer dem in `facing`-Richtung ein Signal in Richtung Piston liefert, oder wenn einer der fünf Nachbarn des Blocks direkt über dem Piston (ohne den Piston selbst) ein Signal in Richtung dieses oberen Blocks liefert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#getNeighborSignal`, `SignalGetter#hasSignal`; [SRC-M-WIKI-QC]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-piston-qc.yaml)
- Hinweise: Für die obere Position wird auch die `facing`-Richtung geprüft; ein nach oben zeigender Piston kann also über seinen Kopf-Block QC-aktiviert werden (vgl. [SRC-M-WIKI-PISTON]). Der zusätzliche Aufruf `hasSignal(pos, DOWN)` auf die eigene Position ist praktisch wirkungslos, da Pistons laut `Blocks#pistonProperties` nie Redstone-Leiter sind und kein Signal abgeben.

### PIS-003: Ausfahren wird nur angestoßen, wenn die Struktur schiebbar ist
- Aussage: Ist der Piston bestromt und nicht ausgefahren, wird nur dann ein Block-Event mit `b0=0` (TRIGGER_EXTEND) eingereiht, wenn `PistonStructureResolver#resolve` für Ausfahren erfolgreich ist; sonst passiert nichts und erst ein späteres Update prüft erneut.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#checkIfExtend`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/piston-push-limit.yaml)

### PIS-004: Einfahren erzeugt Event 1 (ziehen) oder 2 (fallen lassen)
- Aussage: Ist der Piston unbestromt und ausgefahren, wird ein Block-Event mit `b0=1` (TRIGGER_CONTRACT) eingereiht; `b0=2` (TRIGGER_DROP) wird gewählt, wenn zwei Blöcke vor dem Piston ein `moving_piston` in gleicher Richtung mit noch ausfahrendem `PistonMovingBlockEntity` steht und (dessen `getProgress(0)` < 0,5 ist oder es in diesem Game-Tick schon getickt wurde oder `ServerLevel#isHandlingTick` wahr ist).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#checkIfExtend`, `PistonMovingBlockEntity#getProgress`, `PistonMovingBlockEntity#getLastTicked`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sticky-pulse-lengths.yaml)
- Hinweise: `isHandlingTick` ist von Beginn von `ServerLevel#tick` bis einschließlich der Block-Event-Phase wahr, also z. B. bei Abschaltung durch geplante Ticks (Repeater, Torch) oder durch andere Block-Events.

### PIS-005: Beim Ausführen des Events wird die Leistung erneut geprüft
- Aussage: In `triggerEvent` wird auf dem Server die Leistung erneut berechnet: Ein Extend-Event (`b0=0`) ohne Leistung wird verworfen; ein Contract/Drop-Event (`b0=1/2`) bei wieder vorhandener Leistung setzt nur `extended=true` (Flag 2, ohne Nachbar-Updates) und verwirft die Bewegung.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-pistons-ticks.yaml)
- Hinweise: Entscheidend ist also der Leistungszustand zur Block-Event-Phase, nicht nur der zum Zeitpunkt des Einreihens.

### PIS-006: Ausfahren setzt sofort extended=true und erzeugt moving_piston-Blöcke
- Aussage: Beim Extend-Event werden alle zu schiebenden Blöcke an ihrer Zielposition durch `moving_piston` mit Block Entity (Fortschritt 0) ersetzt, der Kopf wird als `moving_piston` (source) davor gesetzt, und danach wird die Piston-Basis mit Flags 67 (inkl. Nachbar-Updates) auf `extended=true` gesetzt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`, `PistonBaseBlock#moveBlocks`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/piston-push-limit.yaml)
- Hinweise: `moveBlocks` setzt die Blöcke ohne Nachbar-Updates (Flags 324/82) und löst danach explizit `updateNeighborsAt` in dieser Reihenfolge aus: zerstörte Blöcke, alte Positionen der geschobenen Blöcke (in umgekehrter Listenreihenfolge), dann die Kopfposition.

### PIS-007: Ein bewegter Block erreicht sein Ziel 2 gt nach dem Event
- Aussage: Ein in Tick T erzeugtes `PistonMovingBlockEntity` wird noch in der Block-Entity-Phase von T getickt (Fortschritt 0 → 0,5), in T+1 auf 1,0 gesetzt und in der Block-Entity-Phase von T+2 durch den Endblock ersetzt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonMovingBlockEntity#tick`, `Level#addBlockEntityTicker`, `Level#tickBlockEntities`, `ServerLevel#tick`; [SRC-M-WIKI-PISTON]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/piston-push-limit.yaml)
- Hinweise: Gilt für Aus- und Einfahren gleich. Das Wiki nennt „2 game ticks" für Aus- und Einfahren. Neue Ticker werden direkt in die Ticker-Liste eingefügt, wenn gerade keine Block Entities getickt werden (Block-Event-Phase liegt davor), daher läuft der erste Schritt im selben Tick.

### PIS-008: Der ankommende Block bekommt ein eigenes neighborChanged
- Aussage: Beim Abschluss setzt `PistonMovingBlockEntity#tick` den Endblock mit Flags 67 (Nachbar-Updates) und ruft zusätzlich `neighborChanged` auf der Zielposition selbst auf, sodass z. B. ein geschobener (nicht ausgefahrener) Piston seine Leistung sofort neu prüft.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonMovingBlockEntity#tick`, `PistonMovingBlockEntity#finalTick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-pistons-ticks.yaml)
- Hinweise: Würde der Endblock an der Position nicht überleben (`updateFromNeighbourShapes` liefert Luft), wird er stattdessen platziert und über `Block#updateOrDestroy` entfernt.

### PIS-009: Eine eingefahrene Basis kann frühestens in T+3 wieder ausfahren
- Aussage: Beim Einfahren wird die Basis selbst zu `moving_piston`; sie wird erst in der Block-Entity-Phase von T+2 wieder ein Piston und prüft dann per `neighborChanged` ihre Leistung, ein dabei eingereihtes Extend-Event läuft daher frühestens in der Block-Event-Phase von T+3.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`, `PistonMovingBlockEntity#tick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-timing.yaml)
- Hinweise: Leistungsänderungen während des Einfahrens werden nicht gesehen, weil `MovingPistonBlock` kein `checkIfExtend` hat.

### PIS-010: Ein neues Event beendet laufende Bewegungen sofort (finalTick)
- Aussage: Ein Contract/Drop-Event ruft zuerst `finalTick` auf dem `PistonMovingBlockEntity` direkt vor der Basis auf; bei einem Sticky Piston wird zusätzlich ein noch ausfahrender bewegter Block zwei Positionen vor der Basis per `finalTick` sofort an seiner Zielposition platziert und dann nicht zurückgezogen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`, `PistonMovingBlockEntity#finalTick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sticky-pulse-lengths.yaml)
- Hinweise: Das ist das „Ausspucken" (Block-Dropping) des Sticky Pistons. `finalTick` setzt den Block mit `setBlockAndUpdate` und ruft `neighborChanged` auf der Position auf.

### PIS-011: Sticky Piston zieht nur bei Event 1 und ziehbarem Block
- Aussage: Ein Sticky Piston zieht beim Einfahren den Block zwei Positionen vor der Basis nur, wenn das Event `b0=1` ist, der Block nicht Luft ist, `isPushable` gilt und seine Push-Reaktion `PUSH_PULL` (normal) ist oder er ein Piston ist; sonst wird nur der Kopf entfernt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`, `PistonBaseBlock#isPushable`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/piston-redstone-block.yaml)
- Hinweise: Glasierte Terrakotta (`PUSH`) wird daher geschoben, aber nicht gezogen.

### PIS-012: Sticky Piston lässt den Block bei kurzen Pulsen fallen
- Aussage: Wird ein Sticky Piston abgeschaltet, während der geschobene Block noch als ausfahrender `moving_piston` existiert (bei Abschaltung durch geplante Ticks oder Block-Events also in T+1 oder T+2), bleibt der Block an der ausgefahrenen Position liegen, statt zurückgezogen zu werden.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#checkIfExtend`, `PistonBaseBlock#triggerEvent`; [SRC-M-WIKI-STICKY-PISTON]
- Konfidenz: mittel
- Status: im-Spiel-verifiziert (scenarios/sticky-pulse-lengths.yaml)
- Hinweise: Aus dem Code abgeleitet (Kombination PIS-004, PIS-007, PIS-010). Das Wiki beschreibt nur qualitativ „verliert Leistung, bevor das Ausfahren fertig ist", ohne Tickzahl. Bei Abschaltung in der Entity-/Block-Entity-Phase oder durch Spieleraktion hängt das Ergebnis vom Fortschritt ab (siehe PIS-004).

### PIS-013: Push-Limit 12 Blöcke
- Aussage: Eine Piston-Struktur darf höchstens 12 zu bewegende Blöcke enthalten (`MAX_PUSH_DEPTH = 12`), zerstörbare Blöcke (`POPPED`) zählen nicht dazu; sonst schlägt `resolve` fehl.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonStructureResolver#addBlockLine`, `PistonStructureResolver#resolve`; [SRC-M-WIKI-PISTON]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/piston-push-limit.yaml)

### PIS-014: Unbewegliche Blöcke
- Aussage: `isPushable` ist falsch für Positionen außerhalb der Bauhöhe oder der World Border, für Blöcke mit Härte -1, Push-Reaktion `IMMOVEABLE` (z. B. Obsidian, Piston-Kopf, `moving_piston`), ausgefahrene Pistons und für jeden Block mit Block Entity (mit Ausnahme von Blöcken mit Push-Reaktion `PUSH` oder `POPPED`, die vorher entschieden werden).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#isPushable`, `Blocks#pistonProperties`; [SRC-M-WIKI-PISTON]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/piston-push-limit.yaml)
- Hinweise: Damit sind Dispenser, Dropper, Hopper, Truhen usw. unbeweglich. Nicht ausgefahrene Pistons sind trotz `IMMOVEABLE` in den Properties schiebbar, weil sie vor der Push-Reaktion gesondert behandelt werden.

### PIS-015: Blöcke mit Push-Reaktion POPPED werden beim Schieben zerstört
- Aussage: Trifft die Schiebelinie auf einen Block mit Push-Reaktion `POPPED` (z. B. Redstone-Staub, Hebel, Fackeln), wird er in `toDestroy` aufgenommen, beim Ausführen mit Drops abgebaut und begrenzt die Linie; beim Einfahren werden solche Blöcke nicht zerstört.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonStructureResolver#resolve`, `PistonStructureResolver#addBlockLine`, `PistonBaseBlock#moveBlocks`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-timing.yaml)

### PIS-016: Slime- und Honigblöcke ziehen seitliche Blöcke mit, aber nicht einander
- Aussage: Slime- und Honigblöcke nehmen bei der Strukturauflösung angrenzende schiebbare Blöcke quer zur Schieberichtung (und hinter sich) mit; Slime und Honig haften nicht aneinander.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonStructureResolver#isSticky`, `PistonStructureResolver#canStickToEachOther`, `PistonStructureResolver#addBranchingBlocks`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/slime-structure.yaml)
- Hinweise: Mitgezogene Blöcke zählen zum 12er-Limit. Blöcke mit Push-Reaktion `PUSH` (z. B. glasierte Terrakotta) haften nur in Schieberichtung (`isPushable` mit `connectionDirection`).

### PIS-017: Einfahrender Piston aktualisiert seine Nachbarn sofort
- Aussage: Beim Contract/Drop-Event wird die Basis mit Flags 276 (ohne automatische Nachbar-Updates) zu `moving_piston` und danach explizit `updateNeighborsAt` an der Basisposition aufgerufen, bevor der Kopf entfernt bzw. der Block gezogen wird.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb3-piston-retract.yaml)
- Hinweise: Im Spiel geprüft (kb3-piston-retract): ein Detektor neben der Basis geht 2 gt nach dem Einfahr-Event aus, nicht erst nach dem Ende des beweglichen Kolbens (2 gt später).

### PIS-018: Normale Pistons lassen keine Blöcke fallen, schieben aber zu Ende
- Aussage: Ein normaler Piston entfernt beim Einfahren nur die Kopfposition; ein noch ausfahrender geschobener Block läuft als `moving_piston` weiter und kommt regulär an.
- Version: 26.3 (seit 1.13.1, 18w30b)
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`; [SRC-M-WIKI-PISTON]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sticky-pulse-lengths.yaml)
- Hinweise: In 1.13-pre7 bis 18w30b ließen auch normale Pistons Blöcke fallen.

### PIS-019: Start-Verzögerung 0 oder 1 gt je nach Phase der Aktivierung
- Aussage: Wird ein Piston während der Phasen geplante Ticks, Random Ticks oder Block-Events bestromt, bewegt er sich in der Block-Event-Phase desselben Ticks; bei Bestromung in der Entity- oder Block-Entity-Phase oder durch Spieleraktion erst in der Block-Event-Phase des nächsten Ticks.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#tick`, `ServerLevel#runBlockEvents`; [SRC-M-WIKI-PISTON]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/piston-push-limit.yaml)
