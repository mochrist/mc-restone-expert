# Projektstatus und Übergabe

Stand: 2026-11-03, Ende Session 2 (kurz). Geschätzter Gesamtfortschritt: **ca. 50 %** (gewichtet nach Aufwand der Meilensteine).

| Meilenstein | Gewicht | Stand | Kurz |
|---|---|---|---|
| M0 Wissensbasis | 10 % | ~95 % | 258 Aussagen aus dem 26.3-Code belegt, 27 davon im Spiel verifiziert; Linter, Index (`knowledge/UNVERIFIED.md`) |
| M1 Parser + Textdump | 10 % | 100 % | `.litematic`, `.schem` (v1–3), `.nbt` lesen und schreiben; `rsx dump`, `rsx convert` |
| M2 Oracle + Simulator | 35 % | ~75 % | Oracle läuft; Simulator stimmt mit allen 22 Golden Traces tick-genau überein |
| M3 Analyse + Erklärung | 20 % | ~30 % | erster Entwurf `rsx explain` (Experimente, Klassifikation, Wahrheitstabelle, Signalweg, Sonderfälle) |
| M4 Redesign | 25 % | 0 % | noch nicht begonnen |
| M5 Export-Mod, Screenshot | optional | 0 % | — |

## Wichtige Fakten und Entscheidungen

- Ziel: Java **26.3**, DataVersion 5023. Der Server ist unobfuskiert (Mojang-Namen). Dekompilierter Code (Vineflower) liegt in `.cache/mcsrc/`, `.cache/tmp-pis/` und `.cache/bas-*`. `.cache/` ist nicht im Repo und lässt sich neu erzeugen (siehe unten).
- Oracle: Fabric-Mod in `oracle/` (Loom 1.19, Loader 0.20.1, Fabric API 0.165.0+26.3). Er platziert Szenarien bei (0, 200, 0) mit Flags 818 (wie `/setblock … strict`) und läuft eingefroren, mit `stepGameIfPaused(1)` pro Tick. EULA für den lokalen Testserver vom Nutzer akzeptiert.
- **Der Simulator läuft an derselben absoluten Position (0, 200, 0)**, weil die Update-Reihenfolge von Redstone-Staub koordinatenabhängig ist (Java-HashSet-Reihenfolge, DUST-018). Siehe `sim/runner.py: ORACLE_ORIGIN`.
- Blockeigenschaften (Leiter, stabile Flächen FULL/RIGID/CENTER, Push-Reaktion …) stammen aus einem Dump des echten Spiels: `src/redstone/sim/data/blocks_26.3.json`, neu erzeugen mit `uv run rsx oracle --dump-blocks`. Überraschungen: Redstone-Block, Observer, TNT und Kupferbirnen sind **keine** Leiter.
- Quasi-Connectivity gibt es in 26.3 nur bei Kolben, Dispenser und Dropper. Die Liste in `idea.md` war falsch.
- Szenario- und Trace-Format: `docs/scenario-format.md` (verbindlicher Vertrag zwischen Simulator und Oracle).

## Befehle

```
uv run pytest -q                                   # 108 Tests, alle grün
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

1. **Wissensbasis-Aussagen zu den 8 neuen Szenarien markieren.** Die Golden Traces für `dust-network`, `dust-powering`,
   `dust-steps`, `piston-push-limit`, `piston-redstone-block`, `slime-structure`, `sticky-pulse-lengths` und
   `zero-tick-piston` sind aufgezeichnet (Session 2). Die Rohdaten entsprechen jeweils der Szenario-Beschreibung, und der Simulator
   stimmt ohne Änderungen überein. Offen ist noch, die passenden Aussagen-IDs (DUST-…, PISTON-…) in `knowledge/` zu suchen
   und mit `knowledge mark scenarios/<x>.yaml ID...` zu markieren. Hinweis: Das Timing-Diagramm von `rsx sim --diff`
   zeigt Kolben nur binär, deshalb für die Prüfung die Rohdaten in `tests/golden/*.trace.json` ansehen.
2. **Simulator-Lücken (M2):**
   - Dropper/Dispenser (Auslösung, QC) und Hopper (Sperre, Transfer, Cooldown) fehlen; nur das Fass ist als Container für den Comparator modelliert.
   - Es fehlen außerdem Kupferbirne, Notenblock, Zielblock, Druckplatten, Türen/Falltüren/Schienen, Tageslichtsensor, Lesepult und Sculk.
   - Unit-Tests für die HashSet-Reihenfolge der Leitung (DUST-018) und für Kolben fehlen (`tests/sim/test_wire.py`, `test_piston.py`).
   - Container rechnen mit maximaler Stapelgröße 64 für alle Items (ASSUMPTION in `sim/blocks/container.py`).
   - Danach weitere Aussagen der Wissensbasis per Szenario verifizieren (`knowledge mark`).
3. **M3 fertigstellen:**
   - Analyse mit echten Schematics testen (`tests/fixtures/licensed`, `tests/fixtures/external` nach dem Fetch).
   - Clock-Erkennung prüfen; Zwei-Observer-Clocks starten nicht von selbst, dafür gibt es den Anstoß-Modus.
   - Mehr Muster erkennen: RS-Latch, Pulsverkürzer, Decoder.
   - Sonderfall-Notizen für Kolben einbauen (`quasi_connectivity`, `bud`, `piston_spit`, `zero_tick` in `sim/notes.py` vorgesehen, aber noch nicht im Kolben-Code aufgerufen).
   - Optional ein SVG-Timing-Diagramm.
4. **M4 Redesign:** Vorher **`docs/m4-search-and-performance.md`** lesen. Kurz: keine Rust-Neuschreibung, sondern zweistufige Bewertung, Topologie per SAT/SMT, gezielte Suche und Symmetrien. Zuerst die Simulator-Geschwindigkeit messen; Rust erst später und nur für den Simulator-Kern (PyO3), falls er der Engpass ist.
   - Spezifikation (Wahrheitstabelle oder Timing) aus `analysis` ableiten.
   - Constraints (Bounding Box, erlaubte Blöcke, QC ja/nein).
   - Kandidaten aus Templates und Suche erzeugen, simulieren, ranken und als `.litematic` exportieren.
5. `plan.md` ist noch auf dem Stand vom Projektstart. Bei Gelegenheit die Erkenntnisse aus diesem Dokument einarbeiten (Versionen, QC-Liste, Origin).

## Struktur (Kurzfassung)

```
src/redstone/
  model/        BlockState, Grid, Pos, Direction
  io/           litematic.py, schem.py, structure_nbt.py
  render/       textdump.py
  verify/       scenario.py, trace.py (Diff, Timing-Diagramm)
  sim/          world.py (Level#setBlock, NeighborUpdater, LevelTicks, Block-Events), block.py, blockdata.py,
                notes.py, runner.py, blocks/{basic,diode,torch_observer,container,wire,piston}.py, data/
  analysis/     ports.py, experiment.py, analyze.py, explain.py
  knowledge.py  Linter, Index, mark
  oracle.py     Start des Fabric-Servers
oracle/         Fabric-Mod (Java)
knowledge/      Wissensbasis (Markdown)
scenarios/      Validierungsszenarien (YAML)
tests/golden/   im echten Spiel aufgezeichnete Traces
```
