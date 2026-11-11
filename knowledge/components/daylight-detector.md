---
topic: Tageslichtsensor
prefix: DAY
---

# Tageslichtsensor

Der Tageslichtsensor (`DaylightDetectorBlock`, `DaylightDetectorBlockEntity`, auch `inverted=true`) ist eine
Signalquelle mit schwachem Signal `power` (0–15). Die Stärke wird aus dem Himmelslicht und dem Sonnenwinkel
berechnet. Der Block-Entity-Ticker läuft nur serverseitig in Dimensionen mit Himmelslicht (`hasSkyLight`).
Zeitangaben in Game-Ticks (gt). Die Simulation (`sim/blocks/daylight.py`, `outputs.rs`/`daylight` im Rust-Kern)
modelliert die Oracle-Welt: Weltuhr bei 0 eingefroren, klares Wetter.

### DAY-001: Der Sensor aktualisiert seine Stärke nur, wenn `gameTime % 20 == 0`
- Aussage: `DaylightDetectorBlock#tickEntity` ruft im Block-Entity-Tick `updateSignalStrength` nur auf, wenn `level.getGameTime() % 20 == 0`; dazwischen bleibt `power` stehen (auch wenn der Sensor mit einer veralteten Stärke gesetzt wurde). Die Spielzeit gilt nach dem Hochzählen im selben Tick (wie bei allen Block-Entity-Tickern).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DaylightDetectorBlock#tickEntity`, `DaylightDetectorBlock#getTicker`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/daylight-detector.yaml)
- Hinweise: Die Phase hängt von der absoluten Spielzeit ab, die das Oracle nicht setzen kann (docs/scenario-format.md, „Spielzeit“). Ein Sensor, dessen `power` schon dem Ziel entspricht, ändert beim Takt nichts.

### DAY-002: Normaler Sensor: `round(Himmelslicht * cos(korrigierter Sonnenwinkel))`, invertiert: `15 - Himmelslicht`
- Aussage: `updateSignalStrength` nimmt `Level#getEffectiveSkyBrightness` (Himmelslicht am Block minus `skyDarken`) als Ziel. Invertiert wird `15 - Ziel`, sonst bei Ziel > 0 `Math.round(Ziel * Mth.cos(w))` mit `w = a + ((a < π ? 0 : 2π) - a) * 0.2` und `a` = `SUN_ANGLE` im Bogenmaß; das Ergebnis wird auf 0–15 begrenzt. `power` wird nur gesetzt (`setBlockAndUpdate`, Flags 3), wenn es vom Ziel abweicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DaylightDetectorBlock#updateSignalStrength`, `LevelReader#getEffectiveSkyBrightness`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/daylight-detector.yaml)
- Hinweise: Bei Nacht oder Regen sinkt das Himmelslicht (`skyDarken` > 0) und damit das Ziel; das ist im Simulator nicht modelliert (feste Tageszeit der Oracle-Welt).

### DAY-003: Rechtsklick schaltet `inverted` um und aktualisiert sofort
- Aussage: `useWithoutItem` (nur für Spieler mit `mayBuild`) setzt `inverted` umgekehrt (Flags 2, keine Nachbar-Updates), erzeugt ein `BLOCK_CHANGE`-Spielereignis und ruft sofort `updateSignalStrength` mit dem neuen Zustand auf. Die Phase des 20-gt-Takts spielt dabei keine Rolle.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DaylightDetectorBlock#useWithoutItem`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/daylight-detector.yaml)
- Hinweise: Ändert sich `power` dabei, folgen die Nachbar-Updates der Flags 3 von `setBlockAndUpdate`.

### DAY-004: Das Signal ist schwach und von Staub, Komparator und Lampe lesbar
- Aussage: `isSignalSource` ist wahr, `ownSignal` liefert `power`, `getDirectSignal` ist nicht überschrieben (0). Redstone-Staub verbindet sich seitlich (Standard `shouldRedstoneWireConnectTo` der Signalquellen), ein Komparator hinter dem Sensor liest `power` als Eingang, eine anliegende Lampe leuchtet bei `power > 0`.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DaylightDetectorBlock#isSignalSource`, `DaylightDetectorBlock#ownSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/daylight-detector.yaml)
- Hinweise: Die Stärke wird nicht über einen Leiterblock weitergegeben (schwach).

### DAY-005: In der Oracle-Welt (Weltuhr 0, klares Wetter, freier Himmel) liest ein normaler Sensor 7, ein invertierter 0
- Aussage: Das Oracle schaltet `advance_time` ab; die Weltuhr `minecraft:overworld` steht in der frischen Welt bei `total_ticks = 0`. Die Timeline `minecraft:day` (`Timelines#bootstrap`) liefert dort `SUN_ANGLE` ≈ 282,37° (Keyframe-Ostwert 6000 ↔ 0°/360° mit symmetrischer kubischer Bézier-Glättung, Zeitanteil 0,75) und `SKY_LIGHT_LEVEL` = 15 · 0,945 = 14,2, also `skyDarken` = 0. Normaler Sensor: `round(15 · cos(w))` = `round(7,02)` = 7; invertiert 0.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Timelines#bootstrap`, `Level#updateSkyBrightness`, `DaylightDetectorBlock#updateSignalStrength`; Weltuhr aus `world_clocks.dat` des Oracle-Servers
- Konfidenz: mittel
- Status: im-Spiel-verifiziert (scenarios/daylight-detector.yaml)
- Hinweise: Im Spiel gemessen: 7 (normal) und 0 (invertiert); die Glättungskurve ist daraus nur grob bestätigt (Sonnenwinkel zwischen 279,6° und 285° ergeben 7). Der Simulator rechnet mit Doppelwerten und dem festen Winkel 282,3711°. Andere Tageszeiten sind nicht modelliert.

### DAY-006: Himmelslicht am Sensor: 15 minus Abstand zur nächsten Zelle mit offenem Himmel
- Aussage: Himmelslicht ist 15 in Zellen ohne lichtdichten Block darüber und verliert 1 pro Schritt durch durchlässige Zellen. Ein Sensor unter einem Stein neben offenen Spalten liest daher Himmelslicht 14 (normal 7, invertiert 1); 3 Blöcke tief unter einer Platte 12 (normal 6, invertiert 3).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelReader#getEffectiveSkyBrightness`
- Konfidenz: mittel
- Status: ungeprüft
- Hinweise: ASSUMPTION: Lichtdichte Blöcke werden durch Redstone-Leiter angenähert (volle Würfel); Platten, Treppen, Blätter, Wasser und so weiter sind nicht modelliert. Im Spiel gemessen (Messläufe, nicht als Szenario aufgezeichnet): Sensor unter einem Stein 7 (Himmelslicht 14); Sensor 3 Blöcke tief unter einer Platte 6 (Himmelslicht 12). Der Stein-Fall ist in `scenarios/daylight-detector.yaml` (Zeile C) enthalten.
