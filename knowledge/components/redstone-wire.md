---
topic: Redstone-Staub (Redstone Wire)
prefix: DUST
---

# Redstone-Staub

Redstone-Staub (`RedstoneWireBlock`, Block-ID `redstone_wire`) überträgt Signale ohne Verzögerung und verliert
pro Block eine Stufe. Sein Blockstate hat vier Seiten-Properties `north/east/south/west` mit den Werten
`none`, `side`, `up` und `power` (0–15). In 26.3 berechnet ohne Experimente der
`DefaultRedstoneWireEvaluator` die Stärke: Jeder Staubblock rechnet nur sich selbst neu und stößt bei einer
Änderung Neighbor-Updates an, sodass sich Änderungen als Update-Kaskade (Tiefensuche, siehe UPD-012)
durch den Strang ausbreiten. Die Reihenfolge dieser Updates hängt über ein `HashSet` von den Koordinaten ab
(„locational"). Mit dem Feature-Flag „Redstone Experiments" (seit 1.21.2, 24w33a) wird stattdessen der
`ExperimentalRedstoneWireEvaluator` benutzt.

### DUST-001: Staub braucht eine stabile Oberseite oder einen Trichter darunter
- Aussage: Staub kann nur existieren, wenn der Block darunter eine stabile volle Oberseite hat (`isFaceSturdy(UP)`) oder ein Trichter ist; sonst wird er bei Shape-Update von unten zu Luft bzw. bei einem Neighbor-Update mit Drops entfernt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#canSurviveOn`, `RedstoneWireBlock#canSurvive`, `RedstoneWireBlock#updateShape`, `RedstoneWireBlock#neighborChanged`; [SRC-WIKI-REDSTONE-DUST]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-dust-structure.yaml)
- Hinweise: Damit trägt z. B. Glas, Glowstone, obere Stufe und umgedrehte Treppe Staub, untere Stufe nicht.

### DUST-002: Aufwärtsverbindung zu Staub diagonal oben
- Aussage: Eine Seite bekommt eine Aufwärtsverbindung, wenn der Block über dem Staub kein Leiter ist, der Nachbarblock auf dieser Seite Staub tragen kann (oder eine Falltür ist) und auf dem Nachbarblock Staub liegt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getConnectingSide`, `RedstoneWireBlock#getMissingConnections`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-steps.yaml)
- Hinweise: Die Prüfung „Block darüber ist kein Leiter" ruft `isRedstoneConductor` mit der Staubposition statt der Position darüber auf; das ist nur für positionsabhängige Leiter-Prädikate relevant (in Vanilla praktisch nicht).

### DUST-003: up und side unterscheiden sich nur in der Darstellung
- Aussage: Bei einer Aufwärtsverbindung wird der Wert `up` gesetzt, wenn die zum Staub zeigende Seitenfläche des Nachbarblocks stabil ist, sonst `side`; die Signallogik fragt nur „verbunden ja/nein" ab.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getConnectingSide`, `RedstoneSide#isConnected`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-dust-shapes.yaml)

### DUST-004: Seitliche Verbindung zu Komponenten und Staub diagonal unten
- Aussage: Ohne Aufwärtsverbindung ist eine Seite `side`, wenn der Nachbar sich mit Staub aus dieser Richtung verbinden will (`shouldRedstoneWireConnectTo`), oder wenn der Nachbar kein Leiter ist und unter ihm Staub liegt; sonst `none`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getConnectingSide`, `BlockBehaviour#shouldRedstoneWireConnectTo`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-dust-structure.yaml)
- Hinweise: Ob eine Komponente (Repeater nur vorne/hinten, Observer nur hinten, …) verbindet, regelt deren `shouldRedstoneWireConnectTo`.

### DUST-005: Ein Leiter über dem unteren Staub trennt die Diagonale nach oben
- Aussage: Liegt über einem Staub ein Leiterblock, verbindet er sich mit keinem diagonal höher liegenden Staub und liest von dort auch kein Signal.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getConnectingSide`, `RedstoneWireEvaluator#getIncomingWireSignal`; [SRC-WIKI-REDSTONE-DUST]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-steps.yaml)
- Hinweise: Nicht-Leiter wie Glas, Stufen oder Redstone-Blöcke trennen nicht.

### DUST-006: Ein Leiter neben dem oberen Staub trennt die Diagonale nach unten
- Aussage: Staub verbindet sich nur dann mit Staub diagonal darunter, wenn der Block zwischen ihnen (neben dem oberen Staub, über dem unteren) kein Leiter ist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getConnectingSide`, `RedstoneWireEvaluator#getIncomingWireSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-dust-structure.yaml)

### DUST-007: Form aus Verbindungen: Linie wird verlängert, keine Verbindung ergibt Kreuz
- Aussage: Nach dem Berechnen der echten Verbindungen ergänzt `getConnectionState`: Sind Nord und Süd beide frei, werden West und Ost auf `side` gesetzt; sind West und Ost beide frei, werden Nord und Süd auf `side` gesetzt; eine einzelne Verbindung wird so zur geraden Linie, null Verbindungen zum Kreuz, zwei Verbindungen über Eck bleiben ein L.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getConnectionState`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-steps.yaml)
- Hinweise: Ausnahme Punkt-Form (DUST-008).

### DUST-008: Isolierter Staub kann Punkt oder Kreuz sein
- Aussage: Hat Staub keine echten Verbindungen, bleibt er ein Punkt, wenn er vorher ein Punkt war, sonst wird er ein Kreuz; Rechtsklick schaltet nur bei Punkt oder Kreuz zwischen beiden um und nur, wenn sich dadurch der Zustand ändert.
- Version: 26.3 (seit 1.16, 20w21a)
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getConnectionState`, `RedstoneWireBlock#useWithoutItem`; [SRC-WIKI-REDSTONE-DUST]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-powering.yaml)
- Hinweise: Neu platzierter isolierter Staub ist ein Kreuz (`getStateForPlacement` startet mit dem Kreuz-Zustand; seit 1.16, 20w18a).

### DUST-009: Umschalten Punkt/Kreuz aktualisiert nur Leiter, deren Verbindung sich ändert
- Aussage: Nach dem Umschalten per Rechtsklick ruft Staub für jede horizontale Seite, deren Verbunden-Status sich geändert hat und deren Nachbar ein Leiter ist, `updateNeighborsAtExceptFromFacing` am Leiter auf (ohne Rückrichtung zum Staub), in der Reihenfolge NORTH, EAST, SOUTH, WEST.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#updatesOnShapeChange`; [SRC-WIKI-BLOCK-UPDATE]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb3-dust-toggle.yaml)
- Hinweise: Der Zustand selbst wird per `setBlockAndUpdate` (Flag 3) gesetzt, das liefert zusätzlich die normalen Neighbor-Updates um den Staub. Im Spiel geprüft (kb3-dust-toggle, Punkt zu Kreuz und zurück): ein Detektor hinter einem Stein neben dem Staub bekommt ein Update, einer hinter Glas nicht. Die Reihenfolge N, O, S, W ist nicht beobachtbar geprüft.

### DUST-010: Staub powert den Block darunter und die Blöcke, in die er zeigt
- Aussage: Staub liefert seine Stärke nach unten immer, nie nach oben, und horizontal nur an Empfänger auf einer Seite, auf der die aus der aktuellen Umgebung neu berechnete Form (`getConnectionState`) verbunden ist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getSignal`, `RedstoneWireBlock#getDirectSignal`; [SRC-WIKI-REDSTONE-DUST]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-powering.yaml)
- Hinweise: Ein Punkt powert daher nur den Block darunter, ein Kreuz alle vier Seiten, eine Linie nur ihre beiden Enden.

### DUST-011: Für das Powern zählt die neu berechnete, nicht die gespeicherte Form
- Aussage: `getSignal` berechnet die Verbindungsform bei jeder Abfrage aus der Umgebung neu; nur die Punkt/Kreuz-Unterscheidung bei isoliertem Staub kommt aus dem gespeicherten Zustand.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getSignal`, `RedstoneWireBlock#getConnectionState`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-powering.yaml)
- Hinweise: Ein veralteter gespeicherter Zustand (z. B. nach unterdrückten Shape-Updates) ändert das Powering also nicht.

### DUST-012: Dioden lesen die Staubstärke an ihrem Eingang direkt
- Aussage: Repeater und Komparatoren nehmen als Eingang das Maximum aus `getSignal` des Eingangsblocks und, falls dort Staub liegt, dessen `power`-Wert, unabhängig von der Verbindungsform des Staubs.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getInputSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb-sources.yaml)

### DUST-013: Staub liest Staubsignale horizontal und diagonal
- Aussage: Der Staub-Eingang berücksichtigt den Staub in jedem der vier horizontalen Nachbarn, zusätzlich den Staub über einem Nachbarn, wenn der Nachbar ein Leiter und der Block über dem Staub kein Leiter ist, sowie den Staub unter einem Nachbarn, wenn der Nachbar kein Leiter ist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireEvaluator#getIncomingWireSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-steps.yaml)
- Hinweise: Die gespeicherten Seiten-Properties werden dabei nicht abgefragt, nur die Geometrie.

### DUST-014: Signal läuft über nicht-leitende Träger nur nach oben
- Aussage: Liegt Staub auf einem Nicht-Leiter, der ihn tragen kann (Glas, Glowstone, obere Stufe, umgedrehte Treppe, Trichter), empfängt er Signal vom Staub diagonal darunter, gibt aber selbst keines an diesen ab, weil der untere Staub nur über Leiter nach oben liest.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireEvaluator#getIncomingWireSignal`; [SRC-WIKI-REDSTONE-DUST]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-dust-structure.yaml)
- Hinweise: Grundlage für Einweg-Treppen aus Glas/Stufen. Wiki: in Bedrock kann Signal durch Glas nach unten laufen (out of scope).

### DUST-015: Blocksignal wird ohne Staub-Beiträge gelesen
- Aussage: Das Blocksignal eines Staubs ist `getBestNeighborSignal` seiner Position, während alle Staubblöcke 0 liefern; Staub wird also nie über einen nur von Staub gepowerten Block gespeist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#getBlockSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-dust-structure.yaml)
- Hinweise: Siehe PWR-010/PWR-011.

### DUST-016: Der Standard-Evaluator berechnet nur den aktualisierten Staub neu
- Aussage: `DefaultRedstoneWireEvaluator#updatePowerStrength` berechnet nur die Zielstärke der eigenen Position; ist sie gleich der gespeicherten, passiert nichts, sonst wird `power` mit Flag 2 gesetzt (sofern der Blockstate noch der übergebene ist) und danach werden Neighbor-Updates ausgelöst.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DefaultRedstoneWireEvaluator#updatePowerStrength`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Flag 2 bedeutet: keine Neighbor-Updates aus `setBlock`, aber Shape-Updates an die Nachbarn (UPD-004).

### DUST-017: Bei Stärkeänderung aktualisiert Staub die Nachbarn von sieben Positionen
- Aussage: Nach einer Stärkeänderung ruft Staub `updateNeighborsAt` für seine eigene Position und für jede seiner sechs Nachbarpositionen auf (insgesamt 42 Neighbor-Updates, Positionen mehrfach).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DefaultRedstoneWireEvaluator#updatePowerStrength`; [SRC-WIKI-BLOCK-UPDATE]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-comparator-updates.yaml)
- Hinweise: Dadurch werden auch Komponenten zwei Blöcke entfernt (über einen Leiter) aktualisiert.

### DUST-018: Die Reihenfolge der sieben Positionen ist ortsabhängig (HashSet)
- Aussage: Die sieben Positionen werden in einem `HashSet<BlockPos>` gesammelt und in dessen Iterationsreihenfolge abgearbeitet; sie ergibt sich aus `BlockPos#hashCode` = `(y + 31·z)·31 + x`, gespreizt mit `h ^ (h >>> 16)` und auf 16 Buckets abgebildet (`& 15`), bei gleichem Bucket in Einfügereihenfolge (eigene Position, dann DOWN, UP, NORTH, SOUTH, WEST, EAST).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DefaultRedstoneWireEvaluator#updatePowerStrength`, `Vec3i#hashCode`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Berechnete Beispiele (Java-`HashMap`-Logik nachgerechnet): Staub bei (0,64,0): selbst, unten, Süd, Ost, oben, Nord, West; bei (1,64,0): oben, Nord, West, selbst, unten, Süd, Ost. Ein Simulator muss genau diese Java-Hash-Reihenfolge nachbilden, um ortsabhängiges Verhalten (z. B. welcher Kolben zuerst schaltet) zu treffen.

### DUST-019: Wiki nennt die Update-Reihenfolge von Staub „zufällig", der Code ist deterministisch
- Aussage: Die Reihenfolge, in der Staub bei Stärkeänderung Nachbarn aktualisiert, ist deterministisch und nur von den Koordinaten abhängig, nicht zufällig.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DefaultRedstoneWireEvaluator#updatePowerStrength`; [SRC-WIKI-BLOCK-UPDATE]
- Konfidenz: hoch
- Status: widersprüchlich
- Hinweise: Das Wiki (Block update) schreibt „in random order". Der Code nutzt ein `HashSet` ohne Zufall; „zufällig" meint vermutlich „ohne erkennbares Muster/ortsabhängig". Für 26.3 gilt der Code.

### DUST-020: Signaländerungen breiten sich ohne Verzögerung im selben Spieltick aus
- Aussage: Staub plant keine Ticks; die gesamte Kaskade von Stärkeänderungen läuft innerhalb der Neighbor-Update-Kette, die sie ausgelöst hat.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#neighborChanged`, `DefaultRedstoneWireEvaluator#updatePowerStrength`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/dust-network.yaml)

### DUST-021: Beim Abschalten durchläuft Staub Zwischenwerte
- Aussage: Weil jeder Staub nur sich selbst aus den aktuellen Nachbarwerten neu berechnet, kann ein Staub beim Abschalten eines Strangs vorübergehend einen Wert größer 0 von noch nicht aktualisierten Nachbarn übernehmen, bevor er im Lauf derselben Kaskade auf 0 fällt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DefaultRedstoneWireEvaluator#calculateTargetStrength`, `RedstoneWireEvaluator#getIncomingWireSignal`
- Konfidenz: mittel
- Status: belegt
- Hinweise: Aus dem Code abgeleitet; Ursache für die bekannte Lag-Anfälligkeit von Staub. Komponenten, die während der Kaskade auslesen, können solche Zwischenwerte sehen; im Oracle prüfen.

### DUST-022: Reihenfolge der Updates beim Platzieren von Staub
- Aussage: `onPlace` eines neuen Staubs (vor den Neighbor-Updates aus `setBlock`) führt aus: Stärke berechnen, `updateNeighborsAt` über und unter dem Staub (erst oben, dann unten), dann für jeden horizontalen Nachbarn (N, O, S, W) falls dort Staub liegt Updates um diesen Staub, dann für jede horizontale Richtung (N, O, S, W) dasselbe für Staub über dem Nachbarn (wenn der Nachbar ein Leiter ist) bzw. unter ihm (sonst).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#onPlace`, `RedstoneWireBlock#updateNeighborsOfNeighboringWires`, `RedstoneWireBlock#checkCornerChangeAt`, `LevelChunk#setBlockState`; [SRC-WIKI-BLOCK-UPDATE]
- Konfidenz: hoch
- Status: belegt
- Hinweise: „Updates um diesen Staub" heißt: `updateNeighborsAt` an seiner Position und an jeder seiner sechs Nachbarpositionen (Reihenfolge DOWN, UP, NORTH, SOUTH, WEST, EAST).

### DUST-023: Reihenfolge der Updates beim Entfernen von Staub
- Aussage: Wird Staub nicht durch einen Kolben entfernt, ruft er `updateNeighborsAt` an allen sechs Nachbarpositionen (DOWN, UP, NORTH, SOUTH, WEST, EAST), führt dann die Stärkeberechnung für seine alte Position aus (nur Updates, falls die alte Stärke vom neu berechneten Wert abweicht) und aktualisiert zuletzt benachbarte und diagonale Staubblöcke wie beim Platzieren.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#affectNeighborsAfterRemoval`, `DefaultRedstoneWireEvaluator#updatePowerStrength`
- Konfidenz: hoch
- Status: belegt

### DUST-024: Staub schickt indirekte Shape-Updates an diagonalen Staub
- Aussage: Für jede verbundene Seite, auf der kein Staub direkt daneben liegt, schickt Staub ein Shape-Update an Staub diagonal darunter und diagonal darüber auf dieser Seite, damit dieser seine Verbindung anpasst.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#updateIndirectNeighbourShapes`, `Level#setBlock`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-dust-shapes.yaml)

### DUST-025: Shape-Update von oben berechnet alle Seiten neu
- Aussage: Ein Shape-Update von oben führt zur kompletten Neuberechnung der Form (ein Leiter darüber kann Aufwärtsverbindungen trennen); ein Shape-Update von einer Seite ändert nur diese Seite, außer der Verbunden-Status kippt oder der Staub ist ein Kreuz, dann wird die gesamte Form neu bestimmt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#updateShape`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-dust-shapes.yaml)

### DUST-026: Staub reagiert auf jedes Neighbor-Update mit Neuberechnung
- Aussage: Jedes Neighbor-Update an Staub prüft zuerst, ob er noch stehen kann (sonst Drop und Entfernen), und ruft dann die Stärkeberechnung auf; der übergebene Quell-Block und die Orientation spielen im Standard-Evaluator keine Rolle.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#neighborChanged`, `DefaultRedstoneWireEvaluator#updatePowerStrength`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/kb2-dust-shapes.yaml)

### DUST-027: Experimenteller Evaluator rechnet das ganze Netz vor den Updates
- Aussage: Mit „Redstone Experiments" berechnet `ExperimentalRedstoneWireEvaluator` erst alle betroffenen Staubstärken (zuerst Abschalten, dann Einschalten per Warteschlange), setzt sie alle und löst erst danach Neighbor-Updates aus, nur in verbundene Richtungen und durch Leiter hindurch, in Orientation-Reihenfolge.
- Version: 26.3 (seit 1.21.2, 24w33a; nur mit Feature-Flag)
- Quelle: [SRC-MC-CODE] `ExperimentalRedstoneWireEvaluator#updatePowerStrength`, `ExperimentalRedstoneWireEvaluator#calculateCurrentChanges`, `ExperimentalRedstoneWireEvaluator#causeNeighborUpdates`; [SRC-WIKI-24W33A]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Außerhalb des Scopes. Im Experiment werden Neighbor-Updates von Staub an Staub ignoriert und Staub-Shape-Updates mit Flag 128 unterdrückt.

### DUST-028: Die Standard-Staublogik ist seit 1.21.2 unverändert locational
- Aussage: Ohne Experimente nutzt 26.3 weiterhin die ortsabhängige `HashSet`-Update-Reihenfolge; die Änderungen aus 24w33a (Netzberechnung, weniger Updates, neue Reihenfolge) gelten nur mit „Redstone Experiments".
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneWireBlock#updatePowerStrength`, `DefaultRedstoneWireEvaluator`; [SRC-WIKI-24W33A]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Ob die HashSet-Variante seit älteren Versionen bitgleich ist, wurde nicht gegen alten Code geprüft.
