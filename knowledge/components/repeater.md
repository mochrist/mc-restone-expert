---
topic: Redstone Repeater
prefix: REP
---

# Redstone Repeater

Der Repeater (`minecraft:repeater`, Klasse `RepeaterBlock`, Oberklasse `DiodeBlock`) ist eine Diode mit
einstellbarer Verzögerung von 1 bis 4 Redstone-Ticks (2 bis 8 Game-Ticks). Er lässt sich nur von der Seite
durch andere Dioden (Repeater, Comparator) sperren. Alle Zeitangaben unten sind in Game-Ticks (gt).

Konvention zur Signalrichtung im Code: `SignalGetter#getSignal(pos, dir)` fragt den Block an `pos` ab, wobei
`dir` die Richtung vom abfragenden Block zum abgefragten Block ist. Ein Block gibt also an den Nachbarn
`pos.relative(dir.getOpposite())` aus, wenn er für `dir` ein Signal liefert.

### REP-001: Der Eingang liegt auf der Seite, auf die `facing` zeigt
- Aussage: Ein Repeater liest sein Eingangssignal vom Block in Richtung `facing` (bei `facing=north` vom nördlichen Nachbarn).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getInputSignal`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-delay-2.yaml)
- Hinweise: Bestätigt die Annahme in `src/redstone/render/textdump.py`. Beim Platzieren wird `facing` auf die Gegenrichtung der Blickrichtung des Spielers gesetzt (`DiodeBlock#getStateForPlacement`), d. h. der Ausgang zeigt vom Spieler weg.

### REP-002: Der Ausgang liegt auf der `facing` entgegengesetzten Seite
- Aussage: Ein Repeater liefert Signal nur an den Nachbarn in Richtung `facing.getOpposite()` (bei `facing=north` nach Süden); `getSignal` ist nur für die abgefragte Richtung gleich `facing` ungleich 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getSignal`, `DiodeBlock#updateNeighborsInFront`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-delay-2.yaml)

### REP-003: Der Eingang liest Signalstärke inklusive Redstone-Staub-Level
- Aussage: Das Eingangssignal ist das Maximum aus `level.getSignal` des Eingangsblocks (inklusive starker Ladung, falls er ein Leiter ist) und dem `power`-Wert von Redstone-Staub an dieser Position.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getInputSignal`, `SignalGetter#getSignal`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Staub-Sonderfall ist nötig, weil Staub über `getSignal` ggf. nicht in diese Richtung liefert (Verbindungsform). Ein Repeater schaltet bei jedem Eingang > 0 (`shouldTurnOn`).

### REP-004: Die Verzögerung beträgt `delay` × 2 Game-Ticks
- Aussage: Ein Repeater mit Blockstate `delay` (1–4) plant seine Ticks mit `delay * 2` Game-Ticks, also 2, 4, 6 oder 8 gt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RepeaterBlock#getDelay`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-delays.yaml)
- Hinweise: Rechtsklick zyklisiert `delay` über `setBlockAndUpdate` (Flags 3, volle Nachbar-Updates).

### REP-005: Der Repeater gibt bei eingeschaltetem Zustand immer Stärke 15 aus
- Aussage: Ein Repeater mit `powered=true` liefert an seinem Ausgang Signalstärke 15, unabhängig von der Eingangsstärke.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getOutputSignal`, `DiodeBlock#ownSignal`
- Konfidenz: hoch
- Status: belegt

### REP-006: Der Repeater lädt den Block vor sich stark
- Aussage: `getDirectSignal` gibt denselben Wert wie `getSignal` zurück, daher wird ein Leiterblock am Ausgang stark geladen (Stärke 15), nicht nur schwach.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getDirectSignal`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: belegt

### REP-007: Bei Zustandswechsel werden nur der Ausgangsblock und dessen Nachbarn aktualisiert
- Aussage: Bei jedem Setzen des Repeater-Zustands (über `onPlace`) erhält der Block am Ausgang ein `neighborChanged` und danach alle Nachbarn des Ausgangsblocks außer dem Repeater selbst (`updateNeighborsAtExceptFromFacing`); der Repeater setzt seinen Zustand selbst mit Flag 2 (ohne allgemeine Nachbar-Updates).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#tick`, `DiodeBlock#onPlace`, `DiodeBlock#updateNeighborsInFront`, `LevelChunk#setBlockState`
- Konfidenz: hoch
- Status: belegt
- Hinweise: `onPlace` wird von `LevelChunk#setBlockState` bei jeder Zustandsänderung aufgerufen, solange Flag 512 nicht gesetzt ist. Die Reihenfolge innerhalb von `updateNeighborsAtExceptFromFacing` gehört in die Update-Reihenfolge-Dokumentation (mechanics).

### REP-008: Ein Neighbor-Update plant einen Tick nur bei Abweichung zwischen Zustand und Eingang
- Aussage: `checkTickOnNeighbor` plant genau dann einen Tick mit `getDelay`, wenn der Repeater nicht gesperrt ist, `powered` von `shouldTurnOn` abweicht und für diese Position in diesem Tick nicht schon ein Tick dieses Blocks ausgeführt wird (`willTickThisTick`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#checkTickOnNeighbor`, `LevelTicks#willTickThisTick`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Zusätzlich ignoriert `LevelChunkTicks#schedule` einen neuen Tick, wenn für dieselbe Position und denselben Block schon einer geplant ist (Deduplizierung nur nach Position+Blocktyp, nicht nach Zeitpunkt).

### REP-009: Tick-Priorität EXTREMELY_HIGH, wenn vor dem Repeater eine nicht zurückzeigende Diode steht
- Aussage: Steht am Ausgang eine Diode (Repeater/Comparator), deren `facing` nicht gleich der Ausgangsrichtung des Repeaters ist (d. h. die nicht frontal zurück in ihn ausgibt), plant `checkTickOnNeighbor` mit `TickPriority.EXTREMELY_HIGH` (-3).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#shouldPrioritize`, `DiodeBlock#checkTickOnNeighbor`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Gilt für in Reihe geschaltete Dioden und für Dioden, die seitlich gespeist (gesperrt) werden.

### REP-010: Tick-Priorität VERY_HIGH beim Ausschalten, sonst HIGH
- Aussage: Ohne Priorisierung nach REP-009 plant ein eingeschalteter Repeater (Ausschalten) mit `VERY_HIGH` (-2) und ein ausgeschalteter (Einschalten) mit `HIGH` (-1).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#checkTickOnNeighbor`; `TickPriority`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Kleinerer Zahlenwert = früher innerhalb desselben Game-Ticks (`ScheduledTick#DRAIN_ORDER`).

### REP-011: Der Tick schaltet ein, auch wenn der Eingang wieder weg ist (Pulsverlängerung)
- Aussage: Ist der Repeater beim Tick aus, schaltet er immer ein; ist der Eingang dabei bereits wieder 0, plant er sofort einen Ausschalt-Tick mit `getDelay` und Priorität `VERY_HIGH`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#tick`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-pulse-extend.yaml)
- Hinweise: Folge: Ein Eingangspuls kürzer als die Verzögerung (auch 0- oder 1-gt-Pulse) erzeugt einen Ausgangspuls von genau `delay*2` gt.

### REP-012: Der Tick schaltet nur aus, wenn der Eingang dann noch fehlt
- Aussage: Ist der Repeater beim Tick an und `shouldTurnOn` ist weiterhin wahr, passiert nichts; nur bei fehlendem Eingang wird `powered=false` gesetzt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#tick`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Zusammen mit der Tick-Deduplizierung werden Aus-Pulse, die kürzer als die Verzögerung sind, unterdrückt; Randfälle (Puls fällt mit bereits geplantem Tick zusammen) laut Wiki möglich.

### REP-013: Gesperrt wird nur durch seitliche Dioden
- Aussage: Ein Repeater ist gesperrt, wenn ein Repeater oder Comparator links oder rechts von ihm (relativ zu `facing`) ein Signal > 0 in seine Richtung liefert; Staub, Redstone-Blöcke, Fackeln oder geladene Blöcke an der Seite sperren nicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RepeaterBlock#isLocked`, `RepeaterBlock#sideInputDiodesOnly`, `DiodeBlock#getAlternateSignal`, `SignalGetter#getControlInputSignal`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-lock.yaml)
- Hinweise: Die seitliche Diode muss mit ihrem Ausgang auf den Repeater zeigen (`getDirectSignal` einer Diode ist nur in Ausgangsrichtung ungleich 0).

### REP-014: Ein gesperrter Repeater ignoriert Ticks und Neighbor-Updates
- Aussage: Ist `isLocked` wahr, tun sowohl `tick` als auch `checkTickOnNeighbor` nichts; der Ausgang bleibt im letzten Zustand.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#tick`, `DiodeBlock#checkTickOnNeighbor`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-lock.yaml)
- Hinweise: Ein bereits geplanter Tick, der während der Sperre fällig wird, verfällt wirkungslos und wird nicht nachgeholt.

### REP-015: Der Blockstate `locked` wird per Shape-Update von den Seiten aktualisiert
- Aussage: `locked` wird in `updateShape` neu berechnet, wenn sich ein Nachbar auf der Achse quer zu `facing` ändert, sowie beim Platzieren; die eigentliche Logik verwendet aber stets `isLocked` (Live-Berechnung), nicht den Blockstate.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RepeaterBlock#updateShape`, `RepeaterBlock#getStateForPlacement`, `RepeaterBlock#isLocked`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Für den Simulator: `locked` im Blockstate ist ein Anzeigewert; entscheidend ist die aktuelle Seitenleistung beim Tick/Update.

### REP-016: Beim Platzieren mit anliegendem Eingang wird ein Tick nach 1 gt geplant
- Aussage: Wird ein Repeater von einem Spieler/Entity platziert und hat bereits Eingang, plant `setPlacedBy` einen Tick mit Verzögerung 1 gt (Priorität NORMAL) statt `delay*2`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#setPlacedBy`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Für aus Schematics geladene Schaltungen irrelevant, solange der Blockstate konsistent ist.

### REP-017: Der Repeater fällt ab, wenn der Block darunter keine stabile Oberseite hat
- Aussage: Ein Repeater benötigt darunter einen Block mit stabiler (`RIGID`) Oberseite; sonst wird er bei Shape-Update von unten zu Luft bzw. bei Neighbor-Update entfernt und aktualisiert alle sechs Nachbarn.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#canSurviveOn`, `RepeaterBlock#updateShape`, `DiodeBlock#neighborChanged`
- Konfidenz: hoch
- Status: belegt
