---
topic: 0-Tick-Pulse
prefix: ZT
---

# 0-Tick-Pulse

Ein 0-Tick-Puls ist ein Signal, das innerhalb desselben Game-Ticks an- und wieder ausgeht. Er entsteht
typischerweise, wenn eine Leitung bestromt und die Quelle in derselben Block-Event-Phase von einem Piston
wieder weggeschoben wird. Komponenten mit geplanten Ticks (Repeater, Comparator, Torch, Lampe) sehen am Ende
meist nichts; Pistons reagieren dagegen über Block-Events noch im selben Tick. Grundlage: Block-Events, die
während der Block-Event-Phase entstehen, werden in derselben Phase abgearbeitet (ORD-008).

### ZT-001: Definition
- Aussage: Ein 0-Tick-Puls ist ein Leistungszustand, der in einem Game-Tick entsteht und im selben Game-Tick wieder verschwindet; Java-Komponenten können ihn nur durch Reaktionen innerhalb desselben Ticks (Block-Updates, Block-Events) wahrnehmen.
- Version: 26.3
- Quelle: [SRC-M-WIKI-ZEROTICK]
- Konfidenz: hoch
- Status: belegt

### ZT-002: Ein Piston ignoriert einen 0-Tick-Puls, wenn die Leistung vor seinem Event wieder weg ist
- Aussage: Wird ein eingefahrener Piston bestromt und vor der Ausführung seines Extend-Events wieder unbestromt, verwirft `triggerEvent` das Event; der Piston bewegt sich nicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`, `PistonBaseBlock#checkIfExtend`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Die Abschaltung vor dem Event erzeugt kein Contract-Event, weil `extended` zu diesem Zeitpunkt noch false ist.

### ZT-003: Ein Piston reagiert, wenn die Abschaltung nach seinem Extend-Event in derselben Block-Event-Phase passiert
- Aussage: Läuft das Extend-Event und verliert der Piston danach in derselben Block-Event-Phase die Leistung (z. B. weil ein anderer Piston die Quelle wegschiebt), wird ein Contract/Drop-Event eingereiht, das noch in derselben Phase abgearbeitet wird.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerLevel#runBlockEvents`, `PistonBaseBlock#checkIfExtend`; [SRC-M-WIKI-ZEROTICK]
- Konfidenz: hoch
- Status: belegt

### ZT-004: Sticky Piston beim 0-Tick-Puls: Block wird sofort an die ausgefahrene Position gesetzt
- Aussage: Bei Ausfahren und Einfahren im selben Tick setzt das Contract/Drop-Event den noch bewegten geschobenen Block per `finalTick` sofort an seine Zielposition und zieht ihn nicht zurück; der Piston beginnt einzufahren.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`, `PistonMovingBlockEntity#finalTick`; [SRC-M-WIKI-ZEROTICK]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Da `isHandlingTick` in der Block-Event-Phase wahr ist, wird immer Event 2 (Drop) gewählt (PIS-004). Der Block „teleportiert" ohne Animation einen Block weiter, mit Block-Updates (`setBlockAndUpdate`) und eigenem `neighborChanged`.

### ZT-005: Normaler Piston beim 0-Tick-Puls: Block wird nicht teleportiert
- Aussage: Ein normaler Piston, der im selben Tick aus- und wieder einfährt, entfernt nur den Kopf sofort; der geschobene Block bewegt sich als `moving_piston` weiter und kommt nach regulärer Laufzeit an.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PistonBaseBlock#triggerEvent`; [SRC-M-WIKI-ZEROTICK]
- Konfidenz: hoch
- Status: belegt

### ZT-006: Repeater und Comparator übertragen 0-Tick-Pulse nicht
- Aussage: Komponenten, die auf Eingangsänderungen nur mit einem geplanten Tick reagieren und im Tick die aktuelle Eingangsleistung neu prüfen, geben einen 0-Tick-Puls nicht weiter.
- Version: 26.3
- Quelle: [SRC-M-WIKI-ZEROTICK]
- Konfidenz: mittel
- Status: belegt
- Hinweise: Das Wiki nennt Comparatoren („reagieren nicht") und Repeater („verlieren den Puls"). Code-Details in den Dateien zu Repeater und Comparator. Als Workaround nennt das Wiki „0-Tick-Repeater" auf Basis von Block-Events (Pistons).

### ZT-007: Dispenser und Dropper werden durch einen 0-Tick-Puls ausgelöst
- Aussage: Erhält ein Dispenser/Dropper während eines 0-Tick-Pulses ein `neighborChanged` im bestromten Zustand, wird der 4-gt-Tick geplant und die Ausgabe erfolgt unabhängig davon, dass die Leistung im selben Tick wieder wegfällt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DispenserBlock#neighborChanged`, `DispenserBlock#tick`
- Konfidenz: mittel
- Status: belegt
- Hinweise: Aus dem Code abgeleitet, nicht im Spiel geprüft.

### ZT-008: Zero-Tick-Pflanzenfarmen funktionieren nicht mehr
- Aussage: Kaktus und Zuckerrohr wachsen nur im Random Tick; der geplante Tick (`tick`) prüft nur das Überleben und zerstört den Block, sodass ein durch 0-Tick-Pistons ausgelöster geplanter Tick kein Wachstum mehr erzwingt.
- Version: 26.3 (seit 20w12a / 1.16)
- Quelle: [SRC-MC-CODE] `CactusBlock#tick`, `CactusBlock#randomTick`, `SugarCaneBlock#tick`, `SugarCaneBlock#randomTick`; [SRC-M-WIKI-ZEROTICK]; [SRC-M-MOJIRA-MC-113809]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Laut Wiki versehentlich schon in 18w06a, offiziell in 20w12a behoben. Die 0-Tick-Piston-Mechanik selbst (ZT-003 bis ZT-005) existiert in 26.3 weiterhin laut Code.

### ZT-009: 0-Tick-Pulse werden oft nicht gerendert
- Aussage: Weil Zustand und Rückkehr im selben Tick passieren, sieht der Client viele 0-Tick-Pulse nicht; ein Simulator muss Zwischenzustände innerhalb eines Ticks protokollieren, um sie darzustellen.
- Version: 26.3
- Quelle: [SRC-M-WIKI-ZEROTICK]
- Konfidenz: mittel
- Status: belegt
