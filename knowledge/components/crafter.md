---
topic: Crafter
prefix: CRAFTER
---

# Crafter

Der Crafter (`CrafterBlock`, `CrafterBlockEntity`) ist ein 3x3-Container, der bei einer steigenden Flanke ein
Rezept ausführt und das Ergebnis in den Container vor seiner Vorderseite (`orientation`) schiebt. Er hat
Comparator-Ausgabe und einen Block-Entity-Ticker. Zeitangaben in Game-Ticks (gt).

### CRAFTER-001: Steigende Flanke löst nach 4 gt das Craften aus, das Ergebnis hängt nicht mehr von der Eingangsleistung ab
- Aussage: `CrafterBlock#neighborChanged` setzt bei Leistung (`hasNeighborSignal`, ohne Quasi-Konnektivität) und `triggered=false` sofort `triggered=true` (Flag 2) und plant einen Tick nach 4 gt. `CrafterBlock#tick` craftet ohne erneute Prüfung der Leistung; ein 1-gt-Puls (Hebel an und gleich wieder aus) craftet also trotzdem.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlock#neighborChanged`, `CrafterBlock#tick`, `CrafterBlock#dispenseFrom`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/crafter.yaml)
- Hinweise: Fällt die Leistung weg, setzt `neighborChanged` `triggered=false` und `crafting=false`.

### CRAFTER-002: Nach erfolgreichem Craften ist `crafting` 6 gt lang wahr
- Aussage: `CrafterBlock#dispenseFrom` setzt `craftingTicksRemaining=6` und `crafting=true`; `CrafterBlockEntity#serverTick` zählt herunter und setzt bei 0 `crafting=false` (`setBlockAndUpdate`). Mit Auslösung bei Tick 2 ist `crafting` ab Tick 6 wahr und ab Tick 11 wieder falsch.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlock#dispenseFrom`, `CrafterBlockEntity#serverTick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/crafter.yaml)
- Hinweise: Ohne gültiges Rezept bleibt `crafting` falsch.

### CRAFTER-003: Der Comparator liest die belegten plus die gesperrten Slots
- Aussage: `CrafterBlockEntity#getRedstoneSignal` zählt jeden Slot, der ein Item enthält oder in `disabled_slots` steht (Maximum 9, unabhängig von der Stapelgröße).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlock#getAnalogOutputSignal`, `CrafterBlockEntity#getRedstoneSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/crafter.yaml)
- Hinweise: Ein Slot kann nur gesperrt werden, wenn er leer ist (`slotCanBeDisabled`).

### CRAFTER-004: Craften verbraucht aus jedem belegten Slot genau ein Item
- Aussage: Nach dem Ausgeben des Ergebnisses ruft `dispenseFrom` für jeden nicht leeren Slot `shrink(1)` auf, unabhängig davon, wie oft die Zutat im Rezept vorkommt; Reste (Eimer, Flaschen) werden zusätzlich ausgegeben.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlock#dispenseFrom`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/crafter.yaml)
- Hinweise: Der Simulator kennt nur wenige Rezepte (`crafter.py`, `RECIPES`) und keine Reste.

### CRAFTER-005: Das Rezept wird wie bei der Werkbank aus dem beschnittenen Raster gewählt
- Aussage: `CrafterBlockEntity#asCraftInput` baut ein `CraftingInput` aus 3x3 Slots; `CraftingInput#of` schneidet leere Randzeilen und -spalten ab, so dass ein Rezept an jeder Stelle des Rasters passt (zwei verschiedene Bretter in Slot 1 und 4 ergeben Stöcke). Zwei Steine nebeneinander ergeben eine Steindruckplatte; kein passendes Rezept bewirkt nichts.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlock#dispenseFrom`, `CrafterBlock#getPotentialResults`, `CrafterBlockEntity#asCraftInput`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/crafter.yaml)
- Hinweise: Ein gesperrter Slot bleibt leer und fehlt deshalb im Raster (8 Barren plus ein gesperrter Slot ergeben keinen Eisenblock).

### CRAFTER-006: Trichter füllen den Crafter gleichmäßig und nie in gesperrte Slots
- Aussage: `CrafterBlockEntity#canPlaceItem` verweigert gesperrte Slots und einen Slot, wenn ein späterer freier Slot leer ist oder einen kleineren Stapel desselben Items enthält. Ein Trichter verteilt Items deshalb reihum auf die Slots.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlockEntity#canPlaceItem`, `CrafterBlockEntity#smallerStackExist`, `HopperBlockEntity#tryMoveInItem`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/crafter.yaml)
- Hinweise: Jede eingefügte Menge ändert den Comparator-Ausgang nach 2 gt.

### CRAFTER-007: Das Ergebnis geht in den Container davor, auch in einen gesperrten Trichter
- Aussage: `CrafterBlock#dispenseItem` fügt das Ergebnis über `HopperBlockEntity#addItem` in den Container an der Vorderseite ein (ein Item nach dem anderen, wenn das Ziel ein Crafter ist oder die Menge die Stapelgröße übersteigt). Ein gesperrter Trichter (`enabled=false`) nimmt das Item an und gibt es erst nach dem Entsperren weiter.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CrafterBlock#dispenseItem`, `HopperBlockEntity#addItem`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/crafter.yaml)
- Hinweise: Passt das Ergebnis nicht hinein, wird der Rest als Item-Entity ausgeworfen; Entities simuliert der Simulator nicht.
