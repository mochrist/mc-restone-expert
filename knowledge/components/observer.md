---
topic: Observer
prefix: OBS
---

# Observer

Der Observer (`minecraft:observer`, Klasse `ObserverBlock`, Zustände `facing`, `powered`) erkennt Shape-Updates
des Blocks, auf den sein Gesicht zeigt, und gibt daraufhin hinten einen Puls von 2 Game-Ticks aus.

### OBS-001: `facing` zeigt auf den beobachteten Block
- Aussage: Ein Observer reagiert auf Shape-Updates, die aus Richtung `facing` kommen (`directionToNeighbour == facing`), d. h. er beobachtet den Nachbarn in Richtung `facing`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#updateShape`; [SRC-WIKI-OBSERVER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-pulse-extend.yaml)
- Hinweise: Bestätigt die Annahme in `src/redstone/render/textdump.py`.

### OBS-002: Der Ausgang liegt auf der Rückseite
- Aussage: Ein Observer liefert Signal nur an den Nachbarn in Richtung `facing.getOpposite()` (Abfrage-Richtung gleich `facing`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#getSignal`, `ObserverBlock#updateNeighborsInFront`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-pulse-extend.yaml)

### OBS-003: Der Observer lädt den Block hinter sich stark mit 15
- Aussage: Ein Observer mit `powered=true` liefert Stärke 15, und `getDirectSignal` ist gleich `getSignal`, der Block an der Rückseite wird also stark geladen.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#ownSignal`, `ObserverBlock#getDirectSignal`; [SRC-WIKI-OBSERVER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-sources.yaml)

### OBS-004: Erkannt werden Shape-Updates, nicht Neighbor-Updates
- Aussage: Der Observer reagiert nur über `updateShape`; er überschreibt `neighborChanged` nicht und reagiert daher nicht auf reine Neighbor-Updates (Block-Updates).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#updateShape`; [SRC-WIKI-OBSERVER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Shape-Updates entstehen u. a. bei jedem `setBlock` ohne Flag 16 an den sechs Nachbarn (`Level#setBlock` → `updateNeighbourShapes`), also bei jeder Blockstate-Änderung des beobachteten Blocks, auch mit Flag 2 (z. B. Repeater-Umschalten).

### OBS-005: Nur ein unbetriebener Observer startet einen Puls
- Aussage: Ein Shape-Update von vorne plant nur dann einen Tick, wenn `powered=false` ist und für diesen Observer noch kein Tick geplant ist.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#updateShape`, `ObserverBlock#startSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/verify-sources.yaml)
- Hinweise: Änderungen während des Pulses werden ignoriert.

### OBS-006: Verzögerung bis zum Einschalten: 2 Game-Ticks, Priorität NORMAL
- Aussage: Der Einschalt-Tick wird 2 gt nach dem Shape-Update mit Standardpriorität `NORMAL` geplant.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#startSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-pulse-extend.yaml)
- Hinweise: Wiki nennt keine explizite Zahl; seit 1.12 (16w44a) nicht mehr sofort.

### OBS-007: Pulsdauer 2 Game-Ticks
- Aussage: Beim Einschalt-Tick setzt der Observer `powered=true` und plant den Ausschalt-Tick 2 gt später (Priorität `NORMAL`), der Ausgangspuls dauert also 2 gt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#tick`; [SRC-WIKI-OBSERVER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-pulse-extend.yaml)

### OBS-008: Zustandswechsel mit Flag 2 und Update nur vorne
- Aussage: Der Observer setzt `powered` mit Flag 2 und ruft danach `updateNeighborsInFront` auf: `neighborChanged` am Block hinter ihm, dann Updates an dessen Nachbarn außer dem Observer selbst.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#tick`, `ObserverBlock#updateNeighborsInFront`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Flag 2 löst trotzdem Shape-Updates an den Nachbarn aus; ein Observer, der einen anderen Observer beobachtet, sieht also dessen Zustandswechsel (Observer-Uhren).

### OBS-009: Neu platzierter eingeschalteter Observer ohne Tick wird ausgeschaltet
- Aussage: Wird ein Observer mit `powered=true` neu an eine Position gesetzt (anderer Block vorher) und hat dort keinen geplanten Tick, setzt `onPlace` ihn auf `powered=false` (Flags 18) und aktualisiert vorne.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#onPlace`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Relevant für per Kolben bewegte Observer. Laut Wiki erzeugt ein unbetriebener, per Kolben bewegter Observer einen Puls; der Mechanismus (Shape-Updates beim Absetzen) ist hier nicht im Code nachverfolgt.

### OBS-010: Entfernen während eines Pulses aktualisiert vorne
- Aussage: Wird ein eingeschalteter Observer mit geplantem Tick entfernt, ruft `affectNeighborsAfterRemoval` `updateNeighborsInFront` auf (auch bei Kolbenbewegung).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#affectNeighborsAfterRemoval`
- Konfidenz: hoch
- Status: belegt

### OBS-011: Redstone-Staub verbindet sich nur mit der Rückseite
- Aussage: `shouldRedstoneWireConnectTo` ist nur für die Richtung gleich `facing` wahr, d. h. Staub hinter dem Observer verbindet sich optisch mit dessen Ausgang.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ObserverBlock#shouldRedstoneWireConnectTo`
- Konfidenz: mittel
- Status: im-Spiel-verifiziert (scenarios/verify-sources.yaml)
- Hinweise: Richtungskonvention der Staub-Abfrage nicht separat geprüft; siehe Staub-Dokumentation.
