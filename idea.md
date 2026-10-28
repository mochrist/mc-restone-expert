# Idee: Redstone-Analyse- und Design-Assistent

## Ziel
Ein Toolkit, das kompakte Minecraft-Redstone-Schaltungen
1. **einliest** (Schematic-Dateien, optional per Export-Mod, Screenshots nur als Fallback),
2. **simuliert und erklärt** (was macht die Schaltung, mit Timing-Diagramm),
3. **neu designt** (gleiche Funktion, kompakter oder mit geänderten Randbedingungen)
und das Ergebnis wieder als importierbare Schematic ausgibt.

## Leitprinzip
Wissensdateien allein reichen nicht. Redstone ist 3D, tick-genau und voller Sonderfälle. Jede Erklärung und jedes Design muss deshalb **durch einen Simulator verifiziert** werden, der gegen das echte Spiel validiert ist. Das LLM schlägt vor, der Simulator entscheidet.

## Randbedingungen (vor dem Planen klären)
- Edition und Version: Java Edition, feste Zielversion (z. B. aktuellste stabile). Bedrock hat andere Mechaniken und ist zunächst out of scope.
- Primärer Input: `.litematic` (Litematica) und `.schem` (WorldEdit). Beide Mods exportieren Bereichsauswahlen bereits, ein eigener Export-Mod ist daher nur eine spätere Option.
- Sprache für den Prototyp: Python (Parsing und Simulation schnell iterierbar). Performance-kritische Teile später ggf. portieren.

## Bausteine

### 1. Wissensbasis (`knowledge/`)
- Markdown-Dateien pro Thema: Signalstärke, Strong/Weak Powering, Repeater (Delay, Locking), Comparator (Compare/Subtract, Container-Ausgabe), Torches (Burnout), Observer, Piston (Update-Reihenfolge, BUD, 0-Tick-Pulse), Hopper, Dropper/Dispenser, Daylight Sensor, Target Block, Lectern, Sculk-Sensoren, Redstone Dust (Verbindungslogik, Slabs/Stufen).
- Sonderfälle: **Quasi-Connectivity** (Pistons, Dropper, Dispenser, Lampen, Rails, Türen), Update-Reihenfolge (Neighbor Updates, Shape Updates, Comparator Updates), Block-Updates vs. Zustandsänderung, Chunk-Grenzen, Tick-Prioritäten.
- Der Agent recherchiert selbst online (Minecraft Wiki, technische Community-Dokumentation, Quellcode-Mappings) und persistiert. **Jede Aussage mit Quelle, Spielversion und Konfidenz**. Widersprüche und Versionsunterschiede explizit markieren statt glätten.
- Wissen, das sich nicht belegen lässt, wird als "ungeprüft" geführt und per Testfall im echten Spiel verifiziert.

### 2. Import/Export
- Parser für `.litematic`, `.schem`, `.nbt` in ein internes 3D-Grid (Block + Blockstate-Properties).
- Optionaler Phase-2-Export-Mod (Fabric): Bereich auswählen, als JSON/Schematic exportieren, optional direkt an das Tool schicken.
- Screenshot-Input: nur als Best-Effort-Fallback, immer mit Rückfrage und niedriger Konfidenz, da Redstone-Zustände (Facing, Delay, Powered) auf Bildern mehrdeutig sind.

### 3. Simulator
- Tick-genaue Java-Redstone-Simulation: Power-Propagation, Strong/Weak Power, Quasi-Connectivity, Repeater/Comparator/Torch/Observer/Piston-Verhalten, Update-Reihenfolge.
- **Validierung gegen die Realität**: Referenz ist ein echter Server (headless Fabric/Paper) oder ein etablierter Redstone-Simulator (z. B. MCHPRS als Vergleich). Testsuite aus bekannten Schaltungen (Clocks, Flip-Flops, 0-Tick-Farmen, BUD-Beispiele) mit erwarteten Signalverläufen aus dem echten Spiel.
- Ausgabe: Signalverlauf pro Tick für definierte Ein-/Ausgänge.

### 4. Analyse und Erklärung
- Aus dem Grid einen Signalgraphen extrahieren, Teilschaltungen erkennen (Clock, T-Flip-Flop, Pulse-Extender, Decoder, ...).
- Erklärung in natürlicher Sprache plus Timing-Diagramm plus Liste der genutzten Sonderfälle (z. B. "nutzt Quasi-Connectivity bei Block X").
- Aussagen werden durch Simulation belegt, nicht nur aus dem Layout "geraten".

### 5. Redesign
- Eingabe: Spezifikation (Wahrheitstabelle oder Timing-Diagramm), abgeleitet aus einer Bestandsschaltung oder direkt vom Nutzer.
- Constraints: maximale Bounding Box, erlaubte Blöcke, Quasi-Connectivity ja/nein, Version, Delay-Toleranz, Rahmenbedingungen wie "muss in 1x1-Wand passen".
- Vorgehen: Kandidaten erzeugen (LLM-Vorschläge, Templates bekannter Kompakt-Bauweisen, ggf. Suche/Optimierung), jeden Kandidaten simulieren, gegen die Spezifikation prüfen, nach Kompaktheit ranken.
- Ausgabe: `.litematic`/`.schem` plus Erklärung und Begründung, was geändert wurde.

### 6. Verifikation
- Jedes Design durchläuft: Simulator → Vergleich mit Spezifikation → (optional) Lauf im echten Server.
- Nichts wird als "funktioniert" ausgegeben, was nicht simuliert wurde.

## Meilensteine
- **M0**: Wissensbasis aufbauen (Recherche, Quellen, Versionen).
- **M1**: Parser plus einfacher 3D-Viewer/Textdump des Grids.
- **M2**: Simulator plus Validierungs-Testsuite gegen das echte Spiel.
- **M3**: Analyse und Erklärung bestehender Schaltungen.
- **M4**: Redesign mit Constraints.
- **M5 (optional)**: Eigener Fabric-Export-Mod, Screenshot-Fallback.

## Anweisung an Claude Code
1. Lies diese idea.md und stelle zuerst Rückfragen zu offenen Punkten (Version, Referenz-Oracle, Sprache).
2. Erstelle daraus eine `plan.md` mit konkreter Architektur, Ordnerstruktur, Testsfrategie und Reihenfolge der Meilensteine. Warte auf mein OK.
3. Implementiere danach meilensteinweise, beginnend mit M0 und M1. Nach jedem Meilenstein Tests laufen lassen und kurz berichten.
4. Halte Annahmen und ungeprüftes Wissen immer sichtbar fest (z. B. `knowledge/UNVERIFIED.md`).
