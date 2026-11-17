---
topic: Tageslichtsensor
prefix: DAY
---

# Tageslichtsensor

Der Tageslichtsensor (`DaylightDetectorBlock`, `DaylightDetectorBlockEntity`, auch `inverted=true`) ist eine
Signalquelle mit schwachem Signal `power` (0–15). Die Stärke wird aus dem Himmelslicht und dem Sonnenwinkel
berechnet. Der Block-Entity-Ticker läuft nur serverseitig in Dimensionen mit Himmelslicht (`hasSkyLight`).
Zeitangaben in Game-Ticks (gt). Die Simulation (`sim/blocks/daylight.py`, `outputs.rs`/`daylight` im Rust-Kern)
modelliert die Oracle-Welt: Weltuhr eingefroren (Start 0, verstellbar mit der Szenario-Aktion `time`), klares
Wetter.

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
- Hinweise: Bei Nacht oder Regen sinkt das Himmelslicht (`skyDarken` > 0) und damit das Ziel. Die Tageszeit ist modelliert (DAY-007, DAY-008), Regen nicht (das Oracle hält das Wetter klar).

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
- Hinweise: Im Spiel gemessen: 7 (normal) und 0 (invertiert); die Glättungskurve ist daraus nur grob bestätigt (Sonnenwinkel zwischen 279,6° und 285° ergeben 7). Der Simulator rechnet den Winkel wie das Spiel in float (282,37433°, DAY-007); andere Tageszeiten siehe DAY-007/DAY-008.

### DAY-006: Himmelslicht am Sensor: 15 minus Abstand zur nächsten Zelle mit offenem Himmel
- Aussage: Himmelslicht ist 15 in Zellen ohne lichtdichten Block darüber und verliert 1 pro Schritt durch durchlässige Zellen. Ein Sensor unter einem Stein neben offenen Spalten liest daher Himmelslicht 14 (normal 7, invertiert 1); 3 Blöcke tief unter einer Platte 12 (normal 6, invertiert 3).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `LevelReader#getEffectiveSkyBrightness`
- Konfidenz: mittel
- Status: im-Spiel-verifiziert (scenarios/daylight-skylight-distance.yaml)
- Hinweise: Im Spiel bestätigt für volle Würfel als lichtdichte Blöcke: `scenarios/daylight-skylight-distance.yaml` (zwei lange Räume mit Steindach, nur an den Enden offen; invertierte Sensoren bei x=1..12 lesen 1,2,3,4,5,6,6,5,4,3,2,1, also Himmelslicht 15 minus Abstand durch Luftzellen zur nächsten offenen Zelle; gleich bei Dach in 3 und in 6 Blöcken Höhe, Simulator in beiden Kernen identisch). Der Stein-Fall ist zusätzlich in `scenarios/daylight-detector.yaml` (Zeile C) enthalten. ASSUMPTION (bleibt): Lichtdichte Blöcke werden durch Redstone-Leiter angenähert (volle Würfel); Platten, Treppen, Blätter, Wasser und so weiter sind nicht modelliert.

### DAY-007: Sonnenwinkel und Himmelslicht folgen der Weltuhr über die Timeline `minecraft:day`
- Aussage: `SUN_ANGLE` und `SKY_LIGHT_LEVEL` kommen aus `data/minecraft/timeline/day.json` (Uhr `minecraft:overworld`, Periode 24000). Sonnenwinkel: Keyframes 6000 → 360° und 6000 → 0°, also 0° bei 6000 und linear über die Zeit mit kubischer Bézier-Glättung `[0.362, 0.241, 0.638, 0.759]` bis 360° bei 30000 (= 6000 des nächsten Tags). Himmelslicht: 15 · Spur (linear; 1,0 von 133 bis 11867, fällt bis 13670 auf 0,26666668, bleibt bis 22330, steigt bis 24133 wieder auf 1,0); `skyDarken = (int)(15 − Himmelslicht)`. Alle Rechnungen in float (`KeyframeTrackSampler#sample`, `EasingType.CubicBezier`, `Mth.lerp`), der Kosinus ist `Mth.cos` (Tabelle mit 65536 Werten). Unter freiem Himmel ergibt das: Zeit 0 → normal 7 / invertiert 0, 6000 → 15/0, 12000 → 7/0, 12500 → 4/3, 13000 → 2/6, 13500 → 1/9, 18000 → 0/11, 22500 → 1/9, 23000 → 2/6, 23500 → 4/3; unter einem Stein (Himmelslicht 14) normal 14 bei 6000, invertiert 12 bei 18000.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `Timeline`, `KeyframeTrackSampler`, `EasingType.CubicBezier`, `AttributeTrackSampler`, `Level#updateSkyBrightness`, `Mth#cos`; Daten `data/minecraft/timeline/day.json` aus dem 26.3-Server-Jar
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/daylight-time.yaml)
- Hinweise: „An bei Nacht“: ein invertierter Sensor unter freiem Himmel gibt von 12031 bis 23969 ein Signal (`skyDarken` ≥ 1; 13000: 6, Mitternacht 11), sichtbar beim nächsten 20-gt-Takt, ein normaler ist dann fast oder ganz aus. Regen und Gewitter senken das Himmelslicht zusätzlich (`WeatherAttributes`), im Simulator nicht modelliert.

### DAY-008: `/time set` wirkt auf den Sonnenwinkel sofort, auf `skyDarken` erst ab dem nächsten Tick
- Aussage: `/time set <t>` setzt `totalTicks` der Weltuhr (`ServerClockManager#setTotalTicks`) und leert den Tick-Cache der Umgebungsattribute, der Sonnenwinkel gilt also sofort. `Level#skyDarken` wird nur am Anfang jedes Server-Ticks neu berechnet (`ServerLevel#tick` → `updateSkyBrightness`). Der Sensor selbst übernimmt die neue Zeit beim nächsten 20-gt-Takt (DAY-001); ein Rechtsklick im selben Tick wie `/time set` (DAY-003) rechnet mit dem neuen Sonnenwinkel und der alten Helligkeit.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `ServerClockManager#setTotalTicks`, `ServerClockManager#modifyClock`, `ServerLevel#tick`, `EnvironmentAttributeSystem#invalidateTickCache`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/daylight-time.yaml)
- Hinweise: Im Szenario die Sensoren U/V bei Tick 205: Zeit 23500 → 6000 und Rechtsklick; normal geschaltet 12 statt 15, invertiert geschaltet 3 statt 0. Das Oracle setzt die Uhr beim Aufbau jedes Szenarios auf 0 und ruft `updateSkyBrightness` sofort auf, damit kein Szenario die Helligkeit des vorigen sieht.
