# Plan: Redstone-Analyse- und Design-Assistent

Stand: 2026-10-28, aktualisiert 2026-11-04 · Grundlage: `idea.md`

> **Historisch.** Dieser Plan beschreibt den Aufbau der Meilensteine M0–M5 vom Projektstart. Rust-Kern, GUI (M6)
> und Assistent kamen später dazu. Aktueller Stand: `STATUS.md`, offene Aufträge: `docs/tasks/`.

> **Erkenntnisse seit Projektstart (Kurzfassung)**
> - Der 26.3-Server ist unobfuskiert (Mojang-Namen). Der dekompilierte Spielcode ist die Hauptquelle der Wissensbasis.
> - Die Update-Reihenfolge von Redstone-Staub hängt in 26.3 weiterhin von den Koordinaten ab (Java-HashSet, DUST-018). Oracle und Simulator platzieren Szenarien deshalb an derselben absoluten Position (0, 200, 0).
> - Quasi-Connectivity haben in 26.3 nur Kolben, Dispenser und Dropper. Die Liste in `idea.md` ist zu lang.
> - Blockeigenschaften (Leiter, stabile Flächen, Push-Reaktion) kommen aus einem Dump des echten Spiels (`src/redstone/sim/data/blocks_26.3.json`) statt aus einer handgepflegten Tabelle.
> - Für M4 gibt es eine eigene Design-Notiz: `docs/m4-search-and-performance.md` (keine Rust-Neuschreibung).

## 1. Entscheidungen

| Punkt | Entscheidung |
|---|---|
| Edition / Version | Java Edition **26.3** (aktuellste Release laut Mojang-Versionsmanifest, 2026-09-15). Fabric unterstützt 26.3. |
| Redstone-Variante | Vanilla-Standardverhalten. Das experimentelle Redstone (Feature-Flag „Redstone Experiments") ist out of scope, wird aber in der Wissensbasis als Abweichung markiert. |
| Referenz-Oracle | **Headless Fabric-Server** (eigener Test-Harness-Mod; Loom 1.19, Loader 0.20.1, Fabric API 0.165.0+26.3). Kein MCHPRS (zusätzliche Reimplementierung, Rust nicht installiert). |
| Sprache | **Python 3.12** mit `uv`, `pytest`. Oracle-Mod in **Java 25** (Gradle + Fabric Loom), da er im Server läuft. |
| Versionskontrolle | Lokales Git-Repo, ein Commit pro Meilenstein, kein Push. |

## 2. Architektur

```
 .litematic / .schem / .nbt
            │
            ▼
   io/ (Parser, Writer) ──► model/ Grid (Blöcke + Blockstates, Block-Entities)
                                   │
            ┌──────────────────────┼─────────────────────────┐
            ▼                      ▼                         ▼
   sim/ Tick-Simulator     analysis/ Signalgraph       design/ Redesign
   (Scheduler, Updates,    + Mustererkennung           (Kandidaten erzeugen,
    Komponenten)           + Erklärung                  simulieren, ranken)
            │                      │                         │
            └──────────► verify/ Szenario + Trace-Vergleich ◄┘
                                   │
                                   ▼
                     oracle/ Fabric-Server (Ground Truth)
```

**Kernidee:** Alles läuft über ein gemeinsames *Szenario*-Format. Ein Szenario = Schematic + Eingaben (z. B. „Hebel bei (2,0,0) an in Tick 5, aus in Tick 40") + Sonden (welche Positionen/Properties pro Tick aufzeichnen) + Dauer. Simulator und Oracle führen **dasselbe** Szenario aus und erzeugen **dasselbe** Trace-Format (JSON, ein Eintrag pro Tick und Sonde). Ein Diff der beiden Traces ist der Validierungstest.

### Module

- **`model/`**: `BlockState` (Name + Properties, unveränderlich, gehasht), `Grid` (sparse oder dichtes 3D-Array mit Palette), `Pos`, `Direction`. Dazu ein Blockregister mit Redstone-relevanten Eigenschaften (fest/transparent, Leiter, Komponente).
- **`io/`**: eigene Decoder für `.litematic` (bitgepackte Long-Arrays, mehrere Regionen), `.schem` (Sponge v2/v3, VarInt-Palette) und Vanilla-`.nbt` (Structure-Block). NBT-Grundlage über `nbtlib`. Writer für `.litematic` und `.schem`. `litemapy` nur als Dev-Abhängigkeit zum Gegentesten.
- **`sim/`**: tick-genaue Nachbildung der Vanilla-Logik: Scheduled-Tick-Liste mit Prioritäten, Block-Events (Pistons), Neighbor-Updates in Vanilla-Reihenfolge, Shape-Updates, Comparator-Updates, Quasi-Connectivity. Pro Blocktyp eine Komponente mit klarer Schnittstelle (`on_neighbor_update`, `on_scheduled_tick`, `get_power`, ...). Der Aufbau orientiert sich an den Klassen- und Methodennamen des Spiels, damit Abweichungen auffindbar sind.
- **`verify/`**: Szenario-Format, Trace-Format, Trace-Diff mit lesbarer Ausgabe („Tick 14, Lampe (3,1,0): Sim=aus, Spiel=an").
- **`analysis/`** (M3): Signalgraph, Teilschaltungserkennung, Timing-Diagramm (Text und SVG), Erklärung.
- **`design/`** (M4): Spezifikation, Constraints, Kandidatengenerierung, Ranking.
- **`cli.py`**: `rsx dump <datei>`, `rsx sim <szenario>`, `rsx oracle <szenario>`, `rsx diff`, später `rsx explain`, `rsx redesign`.

### Oracle (Fabric-Mod)

- Serverseitiger Mod für 26.3, startet einen headless Dedicated Server mit flacher Void-Welt.
- Liest Szenario-Dateien aus einem Eingangsordner, platziert die Schematic bei (0, 200, 0) mit Flags 818 (wie `/setblock … strict`), friert die Welt ein, schaltet Eingaben exakt zum geplanten Tick (Spieleraktion zwischen zwei Ticks) und schreibt Sonden-Zustände pro Tick als JSON.
- Pro Tick wird mit `stepGameIfPaused(1)` genau ein Game-Tick ausgeführt. Damit sind die Ticks deterministisch, unabhängig von der Serverlast.
- Der Server-Jar wird von Loom geladen und nicht ins Repo eingecheckt.
- Eingespielte Traces landen als **Golden Traces** in `tests/golden/`. Damit laufen die Simulator-Tests später auch ohne Server.

## 3. Ordnerstruktur

```
minecraft-redstone-expert/
├── idea.md, plan.md, README.md
├── pyproject.toml                # uv, Python 3.12, Einstiegspunkt "rsx"
├── src/redstone/
│   ├── model/                    # BlockState, Grid, Pos, Blockregister
│   ├── io/                       # litematic.py, schem.py, structure_nbt.py, writer
│   ├── sim/                      # world.py, block.py, blockdata.py, notes.py, runner.py, blocks/*.py, data/
│   ├── verify/                   # scenario.py, trace.py, diff.py
│   ├── analysis/                 # (M3)
│   ├── design/                   # (M4)
│   ├── render/                   # Textdump pro Ebene, später SVG/Timing-Diagramm
│   └── cli.py
├── knowledge/
│   ├── README.md                 # Format der Aussagen, Konfidenzskala
│   ├── SOURCES.md                # alle Quellen mit Abrufdatum
│   ├── UNVERIFIED.md             # Index aller ungeprüften oder widersprüchlichen Aussagen
│   ├── basics/                   # signal-strength.md, powering.md, updates.md, ticks.md
│   ├── components/               # dust, repeater, comparator, torch, observer, piston, ...
│   └── mechanics/                # quasi-connectivity.md, update-order.md, 0-tick.md, bud.md
├── oracle/                       # Fabric-Mod (Gradle, Java 25)
├── scenarios/                    # Testszenarien (YAML) + zugehörige Schematics
└── tests/
    ├── unit/                     # Model, Parser, Komponenten einzeln
    ├── io/fixtures/              # Beispiel-Schematics (generiert + echte Exporte)
    ├── golden/                   # vom Oracle aufgezeichnete Traces
    └── oracle/                   # Live-Tests gegen den Server (Marker "oracle")
```

## 4. Wissensbasis: Format

Jede Aussage ist ein eigener Eintrag mit stabiler ID:

```markdown
### REP-002: Ein gesperrter Repeater ändert seinen Ausgang nicht
- Aussage: ...
- Version: 26.3 (Verhalten seit 1.4.2)
- Quelle: [Minecraft Wiki: Redstone Repeater](https://minecraft.wiki/w/Redstone_Repeater), abgerufen 2026-10-28
- Konfidenz: hoch | mittel | niedrig
- Status: belegt | ungeprüft | widersprüchlich | im-Spiel-verifiziert (Szenario: scenarios/repeater_lock.yaml)
- Hinweise: Versionsunterschiede, Gegenquellen
```

- Quellen: Minecraft Wiki, technische Community-Dokumentation, Bug-Tracker (MC-xxxx), Spiel-Quellcode. Laut Mojang wird Java ab 26.1 nicht mehr obfuskiert, das wird in M0 geprüft. Code wird nur zitiert und nach Klasse/Methode referenziert, nicht ins Repo kopiert.
- Widersprüche werden mit beiden Quellen festgehalten, nicht aufgelöst.
- `UNVERIFIED.md` wird per Skript aus den Einträgen erzeugt, damit der Index nicht veraltet. Sobald ein Szenario eine Aussage im Oracle bestätigt, wechselt ihr Status auf „im-Spiel-verifiziert".

## 5. Teststrategie

| Ebene | Was | Läuft |
|---|---|---|
| Unit | BlockState-Parsing, Bit-Packing, Grid-Operationen, einzelne Komponenten | immer (`pytest`) |
| Round-Trip | Schematic schreiben → lesen → identisch; mit `hypothesis` über zufällige Grids und Palettengrößen | immer |
| Gegentest | eigene Parser gegen `litemapy` bzw. echte Exporte aus Litematica/WorldEdit | immer |
| Golden Trace | Simulator-Trace == aufgezeichneter Oracle-Trace für jedes Szenario | immer (ab M2) |
| Oracle live | Szenario frisch im Fabric-Server ausführen, Golden Trace neu erzeugen/prüfen | manuell, `pytest -m oracle` |
| Wissensbasis | Linter: jede Aussage hat ID, Version, Quelle, Konfidenz und Status; Links auf Szenarien existieren | immer |

Validierungs-Testsuite für M2 (Auswahl): Leitung mit Signalabfall, Repeater-Delays 1–4, Repeater-Lock, Comparator Compare/Subtract, Comparator an Containern, Torch-Inverter und Burnout, Observer-Pulse, Piston- und Sticky-Piston-Timing, Quasi-Connectivity-BUD, Repeater- und Observer-Clocks, T-Flip-Flop, Pulse-Extender, 0-Tick-Puls.

## 6. Meilensteine

**M0: Wissensbasis** (parallel zu M1 möglich)
- Format, Linter und `UNVERIFIED.md`-Generator.
- Recherche und Einträge für alle Themen aus `idea.md`, zuerst die Komponenten aus M2 (Dust, Repeater, Comparator, Torch, Observer, Piston, Update-Reihenfolge, QC).
- Prüfen, ob der 26.x-Server-Code ohne Obfuskation vorliegt, und wenn ja, Klassenreferenzen für jede Kernmechanik ergänzen.
- Fertig, wenn: jedes Thema eine Datei hat, der Linter grün ist und `UNVERIFIED.md` existiert.

**M1: Parser + Textdump**
- `model/`, `io/` (Lesen von `.litematic`, `.schem` und `.nbt`, Schreiben von `.litematic` und `.schem`), `render/` Textdump pro Y-Ebene mit Legende, `rsx dump`.
- Fixtures: programmatisch erzeugte Schematics, dazu nach Möglichkeit 2–3 echte Exporte von dir.
- Fertig, wenn: Round-Trip- und Gegentests grün sind und `rsx dump` eine lesbare Ansicht liefert.

**M2: Oracle + Simulator**
- M2a: Fabric-Oracle-Mod, Szenario- und Trace-Format, erste Golden Traces.
- M2b: Simulator, Komponente für Komponente, jeweils gegen die Golden Traces getestet.
- Fertig, wenn: die gesamte Validierungs-Testsuite trace-identisch zum Spiel ist.

**M3: Analyse + Erklärung.** Signalgraph, Mustererkennung, Timing-Diagramm, Erklärung mit Liste der genutzten Sonderfälle, jede Aussage simulationsbelegt.

**M4: Redesign mit Constraints.** Spezifikation aus Bestandsschaltung oder Nutzereingabe, Kandidaten (Templates, LLM-Vorschläge, Suche), Simulation, Ranking, Export als Schematic plus Begründung.

**M5 (optional):** eigener Export-Mod, Screenshot-Fallback.

Nach jedem Meilenstein: Tests laufen lassen, kurzer Bericht, Git-Commit.

## 7. Risiken und offene Punkte

- **Litematica für 26.3:** Der neueste gefundene Build zielt auf 26.2 (Litematica 0.28.3). Das Dateiformat ist versionsunabhängig (`DataVersion` wird gespeichert). Exporte aus 26.2 sollten also lesbar sein. Blockzustände können sich zwischen Versionen leicht unterscheiden, deshalb gibt der Parser eine Warnung aus, wenn die `DataVersion` von der von 26.3 abweicht.
- **Update-Reihenfolge und Sonderfälle** sind der schwierigste Teil des Simulators. Der Plan setzt deshalb früh auf Golden Traces statt auf reine Dokumentation.
- **Lokalitätsabhängiges Verhalten:** Die HashSet-Reihenfolge bei Redstone-Staub gibt es in 26.3 weiterhin (DUST-018). Gelöst, indem Simulator und Oracle an derselben absoluten Position laufen. Für Redesign-Kandidaten (M4) heißt das: Ergebnisse gelten zunächst nur für diese Position; ortsunabhängiges Verhalten muss gesondert geprüft werden.
- **Simulator-Umfang:** Zunächst nur die Blöcke aus der Validierungs-Testsuite. Unbekannte Blöcke in einer Schematic führen zu einer expliziten Warnung, nicht zu stillem Fehlverhalten.
