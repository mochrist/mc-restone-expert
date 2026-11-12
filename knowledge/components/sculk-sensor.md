---
topic: Sculk-Sensor und kalibrierter Sculk-Sensor
prefix: SCULK
---

# Sculk-Sensor und kalibrierter Sculk-Sensor

Der Sculk-Sensor (`SculkSensorBlock`, `SculkSensorBlockEntity`) und der kalibrierte Sculk-Sensor
(`CalibratedSculkSensorBlock`, `CalibratedSculkSensorBlockEntity`) hören Spielereignisse („Vibrationen") in ihrer
Umgebung und geben dafür ein Redstone-Signal aus. Die Logik steckt im `VibrationSystem` (Listener, Selector, Ticker).
Zeitangaben in Game-Ticks (gt). Der Simulator (`sim/blocks/sculk.py`, `sculk.rs` im Rust-Kern) kennt nur Vibrationen,
die Blöcke auslösen (Hebel, Knöpfe, Platten, Notenblöcke, Türen, Falltüren, Zauntore, Kolben, Spender, Tageslicht-
sensor, abfallende Blöcke); Entities (Schritte, Items, Projektile), Geräusche, Wasser, der Shrieker und der Warden
fehlen. Bekannte Stolperfalle im Oracle: Item-Entities, die ein Szenario erzeugt (z. B. ein Spender mit Item, ein
abfallender Hebel), landen später als `hit_ground` (Frequenz 2) und bleiben bis ins nächste Szenario desselben
Serverlaufs bestehen; solche Szenarien gehören in einen eigenen Lauf.

### SCULK-001: Jedes Spielereignis hat eine feste Frequenz 1–15; Ereignisse ohne Frequenz werden ignoriert
- Aussage: `VibrationSystem#VIBRATION_FREQUENCY_FOR_EVENT` ordnet Ereignissen eine Frequenz zu. Für Blöcke wichtig: `block_close`, `block_deactivate`, `block_detach` = 9; `block_open`, `block_activate`, `block_attach`, `note_block_play`, `container_open` = 10; `block_change` = 11; `block_destroy` = 12; `block_place` = 13; die 15 Resonanzereignisse `resonate_N` = N. Ein Ereignis ohne Eintrag (Frequenz 0) wird nicht empfangen (`canReceiveVibration`), auch `sculk_sensor_tendrils_clicking`, das ein Sensor bei der eigenen Aktivierung auslöst.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `VibrationSystem#VIBRATION_FREQUENCY_FOR_EVENT`, `SculkSensorBlockEntity.VibrationUser#canReceiveVibration`, `SculkSensorBlock#activate`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-sources.yaml)
- Hinweise: Im Spiel gemessen über den Komparator hinter dem Sensor (SCULK-008): Hebel an 10, aus 9, Notenblock 10, Kolben aus/ein 10/9, Holzknopf (Loslassen) 9, leerer Spender 10, Tür, Falltür und Zauntor je 10 auf und 9 zu, Tageslichtsensor-Rechtsklick 11, abfallender Hebel 12. Dass die eigene Aktivierung des Sensors keine Kettenreaktion auslöst, zeigen alle Szenarien (kein Sensor aktiviert sich selbst).

### SCULK-002: Reichweite 8 (kalibriert 16), gemessen als euklidischer Abstand der Blockmitten
- Aussage: Ein Sensor empfängt ein Ereignis nur, wenn das Abstandsquadrat zwischen Quelle und Sensor höchstens `radius²` beträgt (Sensor 8, kalibrierter Sensor 16). Das Ereignis des eigenen Blocks (`block_destroy`, `block_place` an der Sensorposition) wird ignoriert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SculkSensorBlockEntity.VibrationUser#getListenerRadius`, `CalibratedSculkSensorBlockEntity.VibrationUser#getListenerRadius`, `EuclideanGameEventListenerRegistry`, `SculkSensorBlockEntity.VibrationUser#canReceiveVibration`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-lever-distance.yaml)
- Hinweise: Im Spiel: Sensoren bei Abstand 1–8 und Abstandsquadrat 64 reagieren, Abstand 9 und Abstandsquadrat 65 nicht. Der kalibrierte Sensor nimmt auch eine Quelle aus Abstand 12 an, der normale daneben nicht (scenarios/sculk-calibrated.yaml).

### SCULK-003: Laufzeit `floor(Abstand)` Ticks, Stärke `max(1, 15 - floor(15 / Radius * Abstand))`
- Aussage: Die Vibration läuft `Mth.floor(distance)` Ticks (`calculateTravelTimeInTicks`; der Abstand ist ein Float, `(float) sqrt(distSqr)`). Danach aktiviert der Sensor mit `power = max(1, 15 - floor(15 / Radius * Abstand))`. Bei Abstand 1 und Radius 8 ist das 14, bei Abstand 8 gleich 1.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SculkSensorBlockEntity.VibrationUser#calculateTravelTimeInTicks`, `VibrationSystem#getRedstoneStrengthForDistance`, `VibrationSystem.Listener#distanceBetweenInBlocks`, `VibrationSystem.Ticker#tick`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-lever-distance.yaml)
- Hinweise: 13 Sensoren in Abstand 1–9, auch diagonal. Ein Ereignis in Tick T erreicht den Sensor, der in Tick T selbst nicht zuerst tickt, in Tick `T + floor(Abstand)`: der Ticker wählt die Vibration im Tick nach dem Ereignis und zählt im selben Tick herunter (Block-Entity-Tick am Ende des Ticks, nach Block-Ticks und Block-Events).

### SCULK-004: Phasen aktiv (30 gt) → Abkühlung (10 gt) → inaktiv; der kalibrierte Sensor ist nur 10 gt aktiv
- Aussage: `activate` setzt `sculk_sensor_phase=active` und `power`, plant einen Tick in `getActiveTicks()` (Sensor 30, kalibriert 10) und benachrichtigt die Nachbarn des Sensors und des Blocks darunter. Dieser Tick ruft `deactivate`: Phase `cooldown`, `power=0`, neuer Tick in 10 gt, danach `inactive`. Nur in der Phase `inactive` empfängt der Sensor Vibrationen (`canActivate`).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SculkSensorBlock#activate`, `SculkSensorBlock#deactivate`, `SculkSensorBlock#tick`, `SculkSensorBlock#getActiveTicks`, `CalibratedSculkSensorBlock#getActiveTicks`, `SculkSensorBlock#canActivate`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-lever-distance.yaml)
- Hinweise: Beim Platzieren (`onPlace`) setzt ein Sensor mit `power > 0` und ohne geplanten Tick die Stärke mit Flags 18 auf 0 zurück; beim Entfernen im aktiven Zustand folgen Nachbar-Updates (`affectNeighborsAfterRemoval`). Die 10 gt Aktivzeit des kalibrierten Sensors zeigt scenarios/sculk-calibrated.yaml. Das Zurücksetzen beim Platzieren und das Entfernen im aktiven Zustand sind nur im Differenztest geprüft (Python- und Rust-Kern identisch), nicht im Spiel.

### SCULK-005: Eine Vibration unterwegs oder ein aktiver Sensor schluckt weitere; im selben Tick gewinnt die nächste, bei Gleichstand die höhere Frequenz
- Aussage: Solange `currentVibration` gesetzt ist, ignoriert der Listener neue Ereignisse. In der Phase `inactive` sammelt der `VibrationSelector` die Kandidaten desselben Game-Ticks und behält den mit dem kleineren Abstand, bei gleichem Abstand den mit der höheren Frequenz; ein Kandidat aus einem früheren Tick wird nicht mehr ersetzt und im nächsten Tick als Vibration eingeplant (`chosenCandidate`). Die Reihenfolge der Ereignisse im Tick spielt keine Rolle.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `VibrationSystem.Listener#handleGameEvent`, `VibrationSelector#addCandidate`, `VibrationSelector#chosenCandidate`, `VibrationSystem.Ticker#trySelectAndScheduleVibration`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-simultaneous.yaml)
- Hinweise: Im Spiel: Hebel in Abstand 2 und 5 im selben Tick, die nähere gewinnt (beide Reihenfolgen); Hebel aus (9) und an (10) im selben Tick in gleichem Abstand 3: 10 gewinnt (beide Reihenfolgen); eine Vibration aus Abstand 7 ist unterwegs, die nähere bei Tick 5 und eine bei Tick 12 (Sensor aktiv) werden ignoriert.

### SCULK-006: Wolle verdeckt Vibrationen, Teppich nicht; entscheidend ist die Sichtlinie von sechs leicht verschobenen Startpunkten
- Aussage: `Listener#isOccluded` prüft sechs Linien von der Blockmitte der Quelle, jeweils um `1.0E-5` in eine der sechs Richtungen verschoben, zur Blockmitte des Sensors. Die Vibration ist nur verdeckt, wenn jede der sechs Linien einen Block des Tags `occludes_vibration_signals` (alle Wolle) trifft (`isBlockInLine`, Voxel-Traversierung). Wolle neben der Linie verdeckt nichts, Teppich (nur im Tag `dampens_vibrations`) verdeckt nicht. Schneidet die Linie genau eine Blockkante (Diagonale), reicht Wolle auf nur einer der beiden Seiten nicht; auf beiden Seiten verdeckt sie.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `VibrationSystem.Listener#isOccluded`, `BlockGetter#isBlockInLine`, `BlockTags#OCCLUDES_VIBRATION_SIGNALS`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-wool.yaml)
- Hinweise: Im Spiel gemessen mit einem Hebel und elf Sensoren (alle in Reichweite): verdeckt sind der Sensor hinter einem Wollblock auf der Geraden, der Sensor über einem Wollblock, die Diagonale mit Wolle auf beiden Seiten der Kante (zwei Fälle) und die Diagonale mit Wolle genau auf der Linie. Nicht verdeckt sind der Sensor neben der Wolle, der Sensor hinter einem Teppich, der freie Sensor und die Diagonalen mit Wolle nur auf einer Seite (drei Fälle). Der Simulator rechnet die Voxel-Traversierung in Doppelwerten nach.

### SCULK-007: Wolle und Wollteppich als betroffener Block dämpfen die Vibration
- Aussage: Trägt das Ereignis einen betroffenen Blockzustand (`Context#affectedState`) aus dem Tag `dampens_vibrations` (Wolle, Wollteppiche), ist die Vibration ungültig (`User#isValidVibration`) und kein Sensor reagiert.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `VibrationSystem.User#isValidVibration`, `BlockTags#DAMPENS_VIBRATIONS`
- Konfidenz: mittel
- Status: belegt
- Hinweise: Im Simulator abgebildet, aber ohne Szenario: die Quellen im Szenarien-Satz tragen keinen betroffenen Blockzustand aus Wolle (Spender, Kolben und Tageslichtsensor setzen ihn, sind aber nie Wolle). Nur Blöcke, die ein Kolben zerstört, hätten Wolle als betroffenen Zustand (`block_destroy`).

### SCULK-008: Das Signal ist schwach, der Komparator liest die zuletzt empfangene Frequenz, solange der Sensor aktiv ist
- Aussage: `isSignalSource` ist wahr, `ownSignal` liefert `power`, `getDirectSignal` nur nach oben (`Direction.UP`). `hasAnalogOutputSignal` ist wahr: `getAnalogOutputSignal` liefert `lastVibrationFrequency` in der Phase `active`, sonst 0. Ein Komparator hinter dem Sensor zeigt so die Frequenz (nicht die Stärke).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SculkSensorBlock#isSignalSource`, `SculkSensorBlock#ownSignal`, `SculkSensorBlock#getDirectSignal`, `SculkSensorBlock#getAnalogOutputSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-sources.yaml)
- Hinweise: Der Komparator im Szenario zeigt 10 für Hebel an, 9 für Hebel aus usw. (SCULK-001); die Frequenz bleibt nur in der Phase `active` sichtbar. Redstone-Staub und Lampen am Sensor sind in sculk-calibrated.yaml geprüft; das Hochleiten über einen Leiterblock (direktes Signal nach oben) ist nur im Differenztest abgedeckt.

### SCULK-009: Kalibrierter Sensor: kein Ausgang zur Eingangsseite, Frequenzfilter vom Eingang
- Aussage: `getSignal` des kalibrierten Sensors liefert `power` in jede Richtung außer der, in die `facing` zeigt. Der Eingang liegt hinter dem Sensor (`facing` entgegengesetzt): `getSignal` an dieser Position. Ist es 0, nimmt der Sensor jede Vibration an; sonst nur Vibrationen genau dieser Frequenz (`comparisonType != 0 && Frequenz != comparisonType` lehnt ab).
- Version: 26.3
- Quelle: [SRC-MC-CODE] `CalibratedSculkSensorBlock#getSignal`, `CalibratedSculkSensorBlockEntity.VibrationUser#canReceiveVibration`, `CalibratedSculkSensorBlockEntity.VibrationUser#getBackSignal`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-calibrated.yaml)
- Hinweise: Im Spiel: Gruppe ohne Eingang nimmt alles an, drei Lampen leuchten, die auf der Eingangsseite nicht; Eingang 10 (Staub): Hebel an (10) angenommen, aus (9) nicht; Eingang 9 umgekehrt; Eingang 15: nichts (keine Frequenz 15 vom Hebel).

### SCULK-010: Amethystblöcke neben einem aktivierten Sensor wiederholen die Vibration als Resonanz
- Aussage: Beim Aktivieren (`tryResonateVibration`) sendet jeder angrenzende Block des Tags `vibration_resonators` (Amethystblock) das Ereignis `resonate_<Frequenz>` an seiner Position. Andere Sensoren in Reichweite empfangen es mit der Frequenz der Resonanz und dem Abstand zum Amethystblock; die Resonanz kann so von Sensor zu Sensor weiterlaufen. Der Sensor selbst ist während dessen aktiv und hört nicht.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `SculkSensorBlock#tryResonateVibration`, `VibrationSystem#getResonanceEventByFrequency`, `BlockTags#VIBRATION_RESONATORS`
- Konfidenz: hoch
- Status: im-Spiel-verifiziert (scenarios/sculk-resonance.yaml)
- Hinweise: Im Spiel: Hebel → Sensor A → Amethyst neben A → Sensor B (außer Reichweite des Hebels, 6 vom Amethyst) → Amethyst neben B → Sensor C; Komparatoren zeigen die Frequenz 10.
