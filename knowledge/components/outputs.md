---
topic: Ausgabe-Komponenten
prefix: OUT
---

# Ausgabe-Komponenten

Blöcke, die auf Redstone reagieren, ohne selbst ein Signal zu erzeugen: Redstone-Lampe, Notenblock,
Kupferbirne, Türen, Falltüren und angetriebene Schienen. Alle prüfen ihren Eingang mit
`SignalGetter#hasNeighborSignal` (Signal > 0 aus irgendeiner der sechs Richtungen, inkl. Ladung benachbarter
Leiter), reagieren also auf schwache und starke Ladung. Zeiten in Game-Ticks (gt).

### OUT-001: Redstone-Lampe geht sofort an
- Aussage: Bekommt eine ausgeschaltete Redstone-Lampe bei einem Neighbor-Update ein Signal, setzt sie `lit=true` sofort im selben Update (Flag 2, keine Nachbar-Updates).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneLampBlock#neighborChanged`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/repeater-delay-2.yaml)

### OUT-002: Redstone-Lampe geht erst 4 gt verzögert aus
- Aussage: Verliert eine leuchtende Lampe ihr Signal, plant sie einen Tick nach 4 gt (Priorität NORMAL) und schaltet nur aus, wenn dann immer noch kein Signal anliegt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneLampBlock#neighborChanged`, `RedstoneLampBlock#tick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/torch-inverter.yaml)
- Hinweise: Aus-Pulse kürzer als 4 gt sind daher an der Lampe nicht sichtbar (sofern kein weiteres Update dazwischen kommt; doppelte Planung wird dedupliziert).

### OUT-003: Lampen-Zustandswechsel lösen keine Neighbor-Updates aus
- Aussage: Die Lampe setzt `lit` mit Flag 2; sie löst damit Shape-Updates (z. B. für Observer), aber keine Neighbor-Updates an ihren Nachbarn aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `RedstoneLampBlock#neighborChanged`, `RedstoneLampBlock#tick`, `Level#setBlock`
- Konfidenz: hoch
- Status: belegt

### OUT-004: Notenblock spielt nur bei steigender Flanke
- Aussage: Ein Notenblock speichert den Eingang in `powered` und spielt einen Ton (Block-Event) nur, wenn `powered` von false auf true wechselt; der Wechsel wird sofort mit `setBlockAndUpdate` gesetzt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `NoteBlock#neighborChanged`, `NoteBlock#playNote`
- Konfidenz: hoch
- Status: belegt
- Hinweise: Der Ton wird nur gespielt, wenn das Instrument über Notenblöcken funktioniert oder der Block darüber Luft ist.

### OUT-005: Kupferbirne wechselt `lit` bei steigender Flanke sofort
- Aussage: Eine Kupferbirne invertiert `lit`, wenn ihr Eingang von aus auf an wechselt (`powered` false→true), sofort im Neighbor-Update ohne geplanten Tick; bei fallender Flanke wird nur `powered` aktualisiert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CopperBulbBlock#checkAndFlip`, `CopperBulbBlock#neighborChanged`; [SRC-WIKI-COPPER-BULB]
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/copper-bulb.yaml)
- Hinweise: Wiki: Snapshot 23w43a hatte 1 gt Verzögerung, in 23w46a entfernt. In 26.3 keine Verzögerung.

### OUT-006: Kupferbirne löst volle Updates und Comparator-Updates aus
- Aussage: Die Kupferbirne setzt ihren neuen Zustand mit `setBlockAndUpdate` (Flags 3), also mit Neighbor-Updates und, da sie `hasAnalogOutputSignal` hat, Comparator-Updates.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CopperBulbBlock#checkAndFlip`, `Level#setBlock`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/copper-bulb.yaml)

### OUT-007: Kupferbirne liefert Comparator-Wert 15 oder 0
- Aussage: Ein Comparator liest an einer Kupferbirne 15, wenn `lit=true`, sonst 0, unabhängig von der Oxidationsstufe.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CopperBulbBlock#getAnalogOutputSignal`; [SRC-WIKI-COPPER-BULB]
- Konfidenz: hoch
- Status: belegt
- Hinweise: Die Kupferbirne selbst ist keine Signalquelle.

### OUT-008: Kupferbirne prüft beim Platzieren ihren Eingang
- Aussage: Wird eine Kupferbirne neu gesetzt (vorher anderer Block), führt `onPlace` dieselbe Flanken-Prüfung wie bei einem Neighbor-Update aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CopperBulbBlock#onPlace`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/copper-bulb.yaml)
- Hinweise: Relevant für per Kolben bewegte Birnen.

### OUT-009: Türen reagieren sofort und auf Signal an beiden Hälften
- Aussage: Eine Tür setzt `powered` und `open` sofort im Neighbor-Update (Flag 2), wobei ein Signal an der eigenen oder der anderen Türhälfte zählt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DoorBlock#neighborChanged`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/doors.yaml)
- Hinweise: Updates, deren auslösender Block selbst dieser Türtyp ist, werden ignoriert. Die andere Hälfte wird über Shape-Updates nachgezogen.

### OUT-010: Falltüren reagieren sofort
- Aussage: Eine Falltür setzt bei Änderung des Eingangs `powered` (und ggf. `open`) sofort im Neighbor-Update mit Flag 2.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `TrapDoorBlock#neighborChanged`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/doors.yaml)

### OUT-011: Angetriebene Schienen leiten bis zu 8 Schienen weiter
- Aussage: Eine angetriebene Schiene (bzw. Aktivierungsschiene) ist an, wenn sie selbst ein Signal hat oder über eine Kette gleichartiger Schienen in einer Richtung mit Suchtiefe < 8 eine direkt versorgte Schiene erreicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PoweredRailBlock#findPoweredRailSignal`, `PoweredRailBlock#updateState`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/powered-rails.yaml)
- Hinweise: Bei Zustandswechsel: `setBlockAndUpdate`, dann Updates am Block darunter und bei Schrägen am Block darüber. Reichweite im Spiel: die direkt versorgte Schiene plus 8 weitere (9 Schienen), die 10. bleibt aus. Die Kette läuft auch über Steigungen (`ascending_*`).

### OUT-012: Notenblock übernimmt den Eingang sofort in `powered`
- Aussage: Ein Notenblock setzt `powered` bei steigender und fallender Flanke sofort im Neighbor-Update mit `setBlockAndUpdate` (Flags 3, ohne geplanten Tick); Rechtsklick erhöht `note` um 1 (modulo 25), ohne `powered` zu ändern.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `NoteBlock#neighborChanged`, `NoteBlock#useWithoutItem`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/note-block.yaml)
- Hinweise: `instrument` wird nur bei Shape-Updates von oben/unten neu bestimmt (`NoteBlock#updateShape`). Der Ton selbst ist ein Block-Event ohne Einfluss auf den Zustand.

### OUT-013: Zauntore reagieren sofort; Rechtsklick dreht sie zum Spieler
- Aussage: Ein Zauntor setzt bei Änderung des Eingangs `powered` und `open` sofort im Neighbor-Update mit Flag 2. Beim Öffnen per Rechtsklick wird `facing` auf die Blickrichtung des Spielers gesetzt, wenn das Tor vorher zum Spieler hin zeigte.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `FenceGateBlock#neighborChanged`, `FenceGateBlock#useWithoutItem`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/doors.yaml)
- Hinweise: Rechtsklick setzt mit Flags 10 (keine Neighbor-Updates). Der Fake-Player des Oracles blickt nach Süden (yRot 0).

### OUT-014: Eisentüren und Eisenfalltüren lassen sich nicht per Hand öffnen
- Aussage: Rechtsklick ohne Item auf eine Eisentür oder Eisenfalltür ändert nichts (`BlockSetType#canOpenByHand` = false); alle anderen Türen und Falltüren (Holz, Kupfer) schalten `open` um, ohne `powered` zu ändern.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DoorBlock#useWithoutItem`, `TrapDoorBlock#useWithoutItem`, `BlockSetType`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/doors.yaml)
- Hinweise: Türen setzen beim Rechtsklick mit Flags 10, Falltüren mit Flag 2 (jeweils ohne Neighbor-Updates). Ein offenes, angetriebenes Tor/Tür bleibt nach dem Schließen per Hand `powered=true` und öffnet erst bei der nächsten steigenden Flanke wieder.

### OUT-015: Antriebs- und Aktivierungsschienen leiten nur an gleichartige Schienen weiter
- Aussage: Die Weiterleitung von `powered` läuft nur über Schienen desselben Blocktyps (`state.is(this)`): Eine Antriebsschiene unterbricht eine Kette von Aktivierungsschienen und umgekehrt.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `PoweredRailBlock#isSameRailWithPower`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/powered-rails.yaml)
