# Projektstatus

Stand: 2026-11-16, Session 22 (Planung). Ablauf für „weiter“: `CLAUDE.md`. Aufträge: `docs/tasks/`.
Vorgeschichte: `docs/history.md`. Zurückgestelltes: `docs/backlog.md`.

## Wo das Projekt steht

Werkzeug für Redstone in Minecraft Java 26.3: Schaltungen lesen, tick-genau simulieren (Python-Referenz und
Rust-Kern, 154 Golden Traces aus dem echten Spiel identisch), erklären (`rsx explain`), neu entwerfen
(`rsx redesign`: Vorlagen, Fackel-PLA bis 8 Eingänge, Zerlegung bis 11 Eingänge, Kompaktieren) und eine lokale
Web-Oberfläche mit Assistent (`rsx gui`). Suite: ~1600 Tests grün. Wissensbasis: 296 Aussagen, keine offen.

Was dem eigentlichen Ziel (ein Laie bekommt einen Bauplan, der in seiner Welt funktioniert) noch fehlt:

1. Entwürfe sind nur an einer Position und in einer Drehung geprüft (Auftrag 01).
2. Ausgänge wie Tür und Kolben sind ungetestet und nie im Spiel aufgenommen (02).
3. Große Funktionen brauchen bis zu einer halben Stunde (03).
4. Druckplatten, Sensoren und fertige Bauwerke (Kolbentür, Itemsortierer) gehen nicht (04, 05).
5. Berichte sind fachsprachlich, die Bauanleitung ist nur Text (06).

## Aufträge

Reihenfolge = Priorität. Jeder Auftrag steht vollständig in seiner Datei; Regeln in `docs/tasks/README.md`.

| Nr. | Auftrag | Modell | Hängt ab von | Datei |
|---|---|---|---|---|
| 01 | Ortsfestigkeit messen und absichern | Opus | – | `docs/tasks/01-position-robustness.md` |
| 02 | Aktoren testen und im Spiel aufnehmen | Sonnet | – | `docs/tasks/02-actuator-tests.md` |
| 03 | Entwurfssuche für große Funktionen beschleunigen | Opus | – | `docs/tasks/03-search-speed.md` |
| 04 | Druckplatte als Auslöser, danach Tageslichtsensor | Sonnet, Teil 2 Opus | – | `docs/tasks/04-trigger-inputs.md` |
| 05 | Katalog fertiger Bauwerke | Opus | 01 (Prüfung), nach 04 | `docs/tasks/05-catalog.md` |
| 06 | Berichte in Alltagssprache, Bauanleitung als Bild, große Entwürfe | Sonnet | – | `docs/tasks/06-plain-reports.md` |
| 07 | Kleinere Grundbausteine per Offline-Suche | Opus | – (besser nach 01, 03) | `docs/tasks/07-smaller-gates.md` |
| 08 | Zerlegung: mehrere Ausgänge mit gemeinsamen Eingängen | Opus | 03 | `docs/tasks/08-multi-output-common-inputs.md` |
| 09 | Assistent im Browser durchklicken | Sonnet | Nutzer | `docs/tasks/09-assistant-walkthrough.md` |
| 10 | Aufräumen (alter Worktree, `.cache`) | Sonnet | – | `docs/tasks/10-cleanup.md` |

Gleichzeitig möglich (getrennte Dateibereiche): 01 + 02 + 06 + 10; danach 03 + 04; dann 05, 07, 08.
Nicht gleichzeitig: 01/02/04 ändern alle `cli.run_redesign` (nacheinander zusammenführen), 04 und 05 beide
`gui/assistant.py`, 03 und 07/08 beide `design/evaluate.py` bzw. `design/decompose.py`.

Stand der Arbeitskopie: alles committet; API-Schlüssel des Nutzers in `.env` (gitignored), Rechtefreigaben in
`.claude/settings.local.json` (nicht im Repo); Oracle-Sperre frei.

## Wichtige Fakten und Entscheidungen

- Ziel: Java **26.3**, DataVersion 5023. Der Server ist unobfuskiert (Mojang-Namen). Dekompilierter Code (Vineflower) liegt in `.cache/mcsrc/`, `.cache/tmp-pis/` und `.cache/bas-*`. `.cache/` ist nicht im Repo und lässt sich neu erzeugen (siehe unten).
- Oracle: Fabric-Mod in `oracle/` (Loom 1.19, Loader 0.20.1, Fabric API 0.165.0+26.3). Er platziert Szenarien bei (0, 200, 0) mit Flags 818 (wie `/setblock … strict`) und läuft eingefroren, mit `stepGameIfPaused(1)` pro Tick. EULA für den lokalen Testserver vom Nutzer akzeptiert.
- **Der Simulator läuft an derselben absoluten Position (0, 200, 0)**, weil die Update-Reihenfolge von Redstone-Staub koordinatenabhängig ist (Java-HashSet-Reihenfolge, DUST-018). Siehe `sim/runner.py: ORACLE_ORIGIN`.
- Blockeigenschaften (Leiter, stabile Flächen FULL/RIGID/CENTER, Push-Reaktion …) stammen aus einem Dump des echten Spiels: `src/redstone/sim/data/blocks_26.3.json`, neu erzeugen mit `uv run rsx oracle --dump-blocks`. Überraschungen: Redstone-Block, Observer, TNT und Kupferbirnen sind **keine** Leiter.
- Quasi-Connectivity gibt es in 26.3 nur bei Kolben, Dispenser und Dropper. Die Liste in `idea.md` war falsch.
- Rust-Kern bauen: `uv sync` (Gruppe `rust`, Standard); ohne Rust `uv sync --no-group rust` (dann Python-Kern).
  Schneller Check: `cd rust/rsx-core && PYO3_PYTHON=../../.venv/Scripts/python.exe cargo check`; in Git Bash vorher
  `export PATH="$HOME/.cargo/bin:$PATH"`. Toolchain auf diesem Rechner: rustup `stable-x86_64-pc-windows-gnu`
  (keine MSVC-Build-Tools), Komponente `llvm-tools`; `~/.cargo/config.toml` setzt
  `-C dlltool=~/.cargo/tools/llvm-dlltool.exe` (Kopie von `llvm-ar`, übersteht Toolchain-Updates).
- Szenario- und Trace-Format: `docs/scenario-format.md` (verbindlicher Vertrag zwischen Simulator und Oracle).
- GUI: Standard-Port 8737, Vertrag `docs/gui-api.md`. Headless-Screenshot ohne Erweiterung:
  `chrome.exe --headless=new --enable-unsafe-swiftshader --use-angle=swiftshader --virtual-time-budget=15000
  --screenshot=x.png <url>`; URL-Parameter `click=…` drückt Knöpfe der Reihe nach, `?demo=1` lädt Demo-Daten.
- Assistent: `gui/assistant.py`, Modell `claude-opus-5-5`, Schlüssel aus `.env` oder `~/.rsx/anthropic_api_key`;
  `scripts/assistant_eval.py` prüft 10 Wünsche gegen die echte API (kostet Aufrufe, nur gezielt laufen lassen).
- Zeitmessungen sind nur belastbar, wenn der Nutzer nicht nebenbei spielt; lange Oracle-Läufe vorher ansagen.

## Befehle

```
uv run pytest -q [--sim-core python|rust] [--slow] # ~1580 Tests, alle grün (Rust ~70 s, Python ~9 min)
uv sync                                            # baut auch den Rust-Kern; nach Rust-Änderungen:
uv pip install --reinstall-package rsx-core ./rust/rsx-core
uv run rsx --sim-core python|rust <befehl>         # Kern wählen (Standard: Rust, wenn gebaut)
uv run rsx redesign examples/specs/xor.yaml -o out.litematic   # Redesign Logik (M4)
uv run rsx redesign examples/behaviour/t-flip-flop.yaml        # Redesign Zeitverhalten/Speicher
uv run rsx redesign <schematic> [--max-size X,Y,Z] [--no-qc] [--compact N] [--time S]
uv run python scripts/template_scenarios.py        # tpl-/pla-Szenarien neu erzeugen (danach rsx oracle … --golden)
uv run python scripts/seq_template_scenarios.py    # seq-Szenarien neu erzeugen
uv run python scripts/bench_sim.py --sim-core rust # Simulator-Geschwindigkeit
uv run rsx dump <datei> [--components]             # Schematic als Text
uv run rsx sim scenarios/<x>.yaml --diff           # Simulator vs. Golden Trace
uv run rsx oracle scenarios/<x>.yaml --golden      # im echten Spiel aufzeichnen (~10 s pro Batch)
uv run rsx explain <schematic|scenario.yaml>       # Analyse (M3-Entwurf)
uv run rsx gui [datei]                             # GUI im Browser (M6), http://127.0.0.1:8737
uv run rsx materials <schematic|scenario.yaml>     # Materialliste
uv run python -m redstone.knowledge lint|index     # Wissensbasis prüfen / Index erzeugen
uv run python -m redstone.knowledge mark scenarios/<x>.yaml ID...   # Aussagen als im Spiel verifiziert markieren
uv run python scripts/fetch_external_fixtures.py   # Test-Schematics ohne Lizenz lokal laden
```

Neuaufbau von `.cache/` (nur nötig, um Spielcode zu lesen): Server-Jar 26.3 über das Mojang-Versionsmanifest laden, das innere Jar `META-INF/versions/26.3/server-26.3.jar` entpacken und Klassen mit `java -jar vineflower.jar -e=<jar> <in> <out>` dekompilieren. Vineflower 1.12.0 kommt von Maven Central.

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
  gui/          server.py, tools.py, model.py, materials.py, assistant.py, static/ (Web-Oberfläche)
  design/       observe.py, candidate.py, spec.py, behaviour.py, evaluate.py, templates.py, seq_templates.py, synth.py,
                search.py, compact.py, report.py, compose.py (Router), decompose.py, actuators.py
  knowledge.py  Linter, Index, mark
  oracle.py     Start des Fabric-Servers
rust/rsx-core/  Rust-Kern (PyO3): world.rs, wire/diode/torch/piston/container/outputs.rs; sim/rust_world.py ist die Python-Seite
oracle/         Fabric-Mod (Java)
knowledge/      Wissensbasis (Markdown)
scenarios/      Validierungsszenarien (YAML)
tests/golden/   im echten Spiel aufgezeichnete Traces
docs/           tasks/ (Aufträge), history.md, backlog.md, gui-api.md, scenario-format.md, m4-search-and-performance.md
```
