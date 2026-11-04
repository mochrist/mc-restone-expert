# Projektstatus und Übergabe

Stand: 2026-11-04, Ende Session 3. Geschätzter Gesamtfortschritt: **ca. 65 %** (gewichtet nach Aufwand der Meilensteine).

| Meilenstein | Gewicht | Stand | Kurz |
|---|---|---|---|
| M0 Wissensbasis | 10 % | ~95 % | 264 Aussagen aus dem 26.3-Code belegt, 81 davon im Spiel verifiziert; Linter, Index (`knowledge/UNVERIFIED.md`) |
| M1 Parser + Textdump | 10 % | 100 % | `.litematic`, `.schem` (v1–3), `.nbt` lesen und schreiben; `rsx dump`, `rsx convert` |
| M2 Oracle + Simulator | 35 % | ~90 % | Oracle läuft; Simulator stimmt mit allen 33 Golden Traces tick-genau überein |
| M3 Analyse + Erklärung | 20 % | ~70 % | `rsx explain`: Experimente, Klassifikation, Wahrheitstabelle, Pulsantwort, RS-Latch, Decoder, Sonderfall-Notizen |
| M4 Redesign | 25 % | 0 % | noch nicht begonnen |
| M5 Export-Mod, Screenshot | optional | 0 % | — |

### Session 3 (2026-11-04)

- 28 Aussagen zu den 8 Dust/Piston-Szenarien markiert. Korrektur: Teppich ist in 26.3 `PUSH_PULL` und wird geschoben (Beschreibung von `piston-push-limit` angepasst).
- Simulator (drei parallele Agents, je eigene Dateien):
  - `sim/blocks/dispenser_hopper.py`: Dispenser/Dropper (QC, 4 gt, triggered), Hopper (Sperre, 8-gt-Cooldown, 7 gt bei leerem Hopper). `container.py` rechnet mit echten Stapelgrößen (`sim/data/item_stack_sizes_26.3.json`).
  - `sim/blocks/outputs.py`: Kupferbirne, Notenblock, Zielblock, Türen/Falltüren/Zauntore, Antriebs-/Aktivierungsschiene, Lesepult.
  - 11 neue Szenarien mit Golden Traces, alle beim ersten Lauf identisch zum Spiel. Erkenntnis: Antriebsschiene versorgt sich selbst plus 8 weitere (OUT-011).
  - Unit-Tests `tests/sim/test_wire.py` (inkl. HashSet-Reihenfolge DUST-018) und `test_piston.py`; keine Simulator-Fehler gefunden.
  - Kolben melden jetzt Notizen `quasi_connectivity`, `bud`, `piston_spit`, `zero_tick` (`notes.register_state_check` für BUD im Ruhezustand).
- M3: `analysis/patterns.py` – Pulsantwort (Hebel 1…20 gt an; Pulsfilter, Pulsverkürzer, Monoflop, Mindestpulslänge, Lampen-Ausschaltverzögerung wird herausgerechnet), RS-Latch über Eingabe-Sequenzen, Decoder aus der Wahrheitstabelle. `rsx explain` zeigt „Erkannte Bausteine“ und „Pulsantwort“. `tests/fixtures/analysis/rs-latch.yaml`.
- Test mit echten Schematics: `mux3-8` wird als 3→8-Decoder erkannt. `observer-clock-100.schem` ist nur ein Parser-Stresstest (500 000 Observer im Schachbrett), keine Schaltung.
- `plan.md` mit den Erkenntnissen aktualisiert. Projekt-`.claude/settings.json` erlaubt ein paar lesende Befehle.

## Wichtige Fakten und Entscheidungen

- Ziel: Java **26.3**, DataVersion 5023. Der Server ist unobfuskiert (Mojang-Namen). Dekompilierter Code (Vineflower) liegt in `.cache/mcsrc/`, `.cache/tmp-pis/` und `.cache/bas-*`. `.cache/` ist nicht im Repo und lässt sich neu erzeugen (siehe unten).
- Oracle: Fabric-Mod in `oracle/` (Loom 1.19, Loader 0.20.1, Fabric API 0.165.0+26.3). Er platziert Szenarien bei (0, 200, 0) mit Flags 818 (wie `/setblock … strict`) und läuft eingefroren, mit `stepGameIfPaused(1)` pro Tick. EULA für den lokalen Testserver vom Nutzer akzeptiert.
- **Der Simulator läuft an derselben absoluten Position (0, 200, 0)**, weil die Update-Reihenfolge von Redstone-Staub koordinatenabhängig ist (Java-HashSet-Reihenfolge, DUST-018). Siehe `sim/runner.py: ORACLE_ORIGIN`.
- Blockeigenschaften (Leiter, stabile Flächen FULL/RIGID/CENTER, Push-Reaktion …) stammen aus einem Dump des echten Spiels: `src/redstone/sim/data/blocks_26.3.json`, neu erzeugen mit `uv run rsx oracle --dump-blocks`. Überraschungen: Redstone-Block, Observer, TNT und Kupferbirnen sind **keine** Leiter.
- Quasi-Connectivity gibt es in 26.3 nur bei Kolben, Dispenser und Dropper. Die Liste in `idea.md` war falsch.
- Szenario- und Trace-Format: `docs/scenario-format.md` (verbindlicher Vertrag zwischen Simulator und Oracle).

## Befehle

```
uv run pytest -q                                   # 219 Tests, alle grün
uv run rsx dump <datei> [--components]             # Schematic als Text
uv run rsx sim scenarios/<x>.yaml --diff           # Simulator vs. Golden Trace
uv run rsx oracle scenarios/<x>.yaml --golden      # im echten Spiel aufzeichnen (~10 s pro Batch)
uv run rsx explain <schematic|scenario.yaml>       # Analyse (M3-Entwurf)
uv run python -m redstone.knowledge lint|index     # Wissensbasis prüfen / Index erzeugen
uv run python -m redstone.knowledge mark scenarios/<x>.yaml ID...   # Aussagen als im Spiel verifiziert markieren
uv run python scripts/fetch_external_fixtures.py   # Test-Schematics ohne Lizenz lokal laden
```

Neuaufbau von `.cache/` (nur nötig, um Spielcode zu lesen): Server-Jar 26.3 über das Mojang-Versionsmanifest laden, das innere Jar `META-INF/versions/26.3/server-26.3.jar` entpacken und Klassen mit `java -jar vineflower.jar -e=<jar> <in> <out>` dekompilieren. Vineflower 1.12.0 kommt von Maven Central.

## Offene Punkte (nächste Schritte, nach Priorität)

1. **M3 fertigstellen:**
   - Erledigt (Session 3, Ende): Druckplatten als Eingang (Emulation „betreten und sofort verlassen“, `PressurePlateBlock` in `basic.py`, nicht gegen das Spiel validiert, weil der Oracle keine Entities hat); volle Wahrheitstabelle bis 6 Hebel, darüber Teiltabellen je Ausgangsgruppe (`seg7`: NAND über 4 Hebel); höchstens 64 Ausgänge; Gatternamen AND/OR/NAND/NOR für n Eingänge.
   - Teiltabellen sehen nur Abhängigkeiten, die beim einzelnen Umschalten sichtbar sind.
   - Clock-Erkennung an echten Clocks prüfen (Anstoß-Modus); optional SVG-Timing-Diagramm.
   - BUD-Notiz ist eine Heuristik (Staub zwei Blöcke entfernt wird nicht gemeldet).
2. **M4 Redesign beginnen:** Vorher **`docs/m4-search-and-performance.md`** lesen. Kurz: keine Rust-Neuschreibung, sondern zweistufige Bewertung, Topologie per SAT/SMT, gezielte Suche und Symmetrien. Zuerst die Simulator-Geschwindigkeit messen.
   - Spezifikation (Wahrheitstabelle, Timing, Pulsantwort) aus `analysis` ableiten.
   - Constraints (Bounding Box, erlaubte Blöcke, QC ja/nein).
   - Kandidaten aus Templates und Suche erzeugen, simulieren, ranken und als `.litematic` exportieren.
   - Achtung: Ergebnisse gelten zunächst nur an der Oracle-Position (DUST-018).
3. **Restliche Simulator-Lücken (M2):**
   - Tageslichtsensor (Block-Entity alle 20 gt, Himmelslicht/Tageszeit), Druckplatten, Detektorschiene, Sculk, Crafter, Truhen als Container.
   - Notenblock-Instrument nur über Blocknamen (ASSUMPTION; Feld `instrument` im Block-Dump fehlt).
   - Dispenser: item-spezifisches Verhalten, zufällige Slotwahl → erster Slot (ASSUMPTIONs in `dispenser_hopper.py`).
   - Weitere ungeprüfte Aussagen per Szenario verifizieren (`knowledge/UNVERIFIED.md`).

Hinweise für parallele Agents: Der Oracle hat festen Port und festes Verzeichnis, Sperre per `mkdir .cache/oracle.lock`. `knowledge/UNVERIFIED.md` erst am Ende einmal neu erzeugen.

## Struktur (Kurzfassung)

```
src/redstone/
  model/        BlockState, Grid, Pos, Direction
  io/           litematic.py, schem.py, structure_nbt.py
  render/       textdump.py
  verify/       scenario.py, trace.py (Diff, Timing-Diagramm)
  sim/          world.py (Level#setBlock, NeighborUpdater, LevelTicks, Block-Events), block.py, blockdata.py,
                notes.py, runner.py, blocks/{basic,diode,torch_observer,container,wire,piston,dispenser_hopper,outputs}.py, data/
  analysis/     ports.py, experiment.py, analyze.py, patterns.py, explain.py
  knowledge.py  Linter, Index, mark
  oracle.py     Start des Fabric-Servers
oracle/         Fabric-Mod (Java)
knowledge/      Wissensbasis (Markdown)
scenarios/      Validierungsszenarien (YAML)
tests/golden/   im echten Spiel aufgezeichnete Traces
```
