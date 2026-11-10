# Projektstatus und Übergabe

Stand: 2026-11-10, Session 6 (Rust-Kern begonnen, siehe Übergabe unten). Geschätzter Gesamtfortschritt: **ca. 84 %** (gewichtet nach Aufwand der Meilensteine).

| Meilenstein | Gewicht | Stand | Kurz |
|---|---|---|---|
| M0 Wissensbasis | 10 % | ~95 % | 264 Aussagen aus dem 26.3-Code belegt, 83 davon im Spiel verifiziert; Linter, Index (`knowledge/UNVERIFIED.md`) |
| M1 Parser + Textdump | 10 % | 100 % | `.litematic`, `.schem` (v1–3), `.nbt` lesen und schreiben; `rsx dump`, `rsx convert` |
| M2 Oracle + Simulator | 35 % | ~90 % | Oracle läuft; Simulator stimmt mit allen 84 Golden Traces tick-genau überein |
| M3 Analyse + Erklärung | 20 % | ~80 % | `rsx explain`: Experimente, Klassifikation, Wahrheitstabelle, Pulsantwort, RS-Latch, Decoder, Sonderfall-Notizen |
| M4 Redesign | 25 % | ~65 % | Vorlagen (Logik inkl. Volladdierer, Zeitverhalten/Speicher), Fackel-PLA, Komposition mit Router (Logik vor Speicher, Zerlegung, Ausgänge nebeneinander), Kompaktieren; alles im Spiel geprüft |
| M5 Export-Mod, Screenshot | optional | 0 % | — |

## Übergabe: Rust-Kern in Arbeit (Session 6, 2026-11-10, abgebrochen wegen Sitzungslimit)

**Zuerst diesen Abschnitt lesen.** Auftrag: `sim/world.py` + `sim/blocks/*` als Rust-Erweiterung (PyO3/maturin),
Schnittstelle 1:1, umschaltbar, Python bleibt Referenz. Abnahme: alle Golden Traces und die ganze Testsuite grün
mit dem Rust-Kern, tick-genau. Danach messen (`scripts/bench_sim.py`, `rsx redesign examples/specs/composed/xor4.yaml`,
Python gegen Rust) und in `docs/m4-search-and-performance.md` eintragen. `azazo1/redstone-rs` nur ansehen.

Stand auf `master`:
- `rust/rsx-core/` (Modul `rsx_core`): `common.rs`, `data.rs` (Blocktabelle, Heuristiken), `state.rs` (Zustände
  interniert pro Welt, `Kind` je Block), `world.rs` (Port von `world.py`), `dispatch.rs` (Verteilung nach `Kind`),
  `basic.rs`, `wire.rs`, `diode.rs`, `torch.rs` (fertig), `lib.rs` (Python-Bindung).
- **Stubs:** `piston.rs`, `container.rs`, `outputs.rs`. Deshalb laufen erst 65 von 92 Golden Traces auf Rust.
- `src/redstone/sim/core.py`: Umschalter (`RSX_SIM_CORE=python|rust|auto`, `core.use()`, `rsx --sim-core`).
  `redstone.sim.World` ist eine Fassade. `sim/rust_world.py`: `RustWorld` mit Sichten für `blocks`,
  `block_entities`, `dirty`, `block_events`, `registry`, `block()`.
- Für beide Kerne neu: `World.is_idle()`, `World.neighbor_update_count`. `Circuit` nutzt beim Rust-Kern
  `snapshot`/`probe_values`/`comparator_positions` (gleiche Reihenfolge wie der Python-Weg).
- Python-Kern: 709 Tests grün nach dem ersten Commit; nach den Änderungen an `cli.py`/`tests/conftest.py` nicht
  erneut gelaufen.

Ungeprüfte Zwischenstände der abgebrochenen Agents (nur je eine Datei geändert, Basis `a0d4c05`):
- Branch `wip/rust-piston` (`b49c0fa`): `piston.rs`, ca. 750 Zeilen.
- Branch `wip/rust-outputs` (`0718be6`): `outputs.rs`, ca. 700 Zeilen.
- Container/Hopper/Dispenser (`container.rs`): nichts erhalten, neu portieren.
- Worktrees liegen noch unter `.claude/worktrees/` (löschen mit `git worktree remove`, wenn übernommen).

Nächste Schritte:
1. `git merge wip/rust-piston wip/rust-outputs` (getrennte Dateien), bauen, Golden Traces auf Rust laufen lassen,
   Code gegen `blocks/piston.py` und `blocks/outputs.py` gegenlesen. Unklar, ob die Stände kompilieren.
2. `container.rs` portieren (`blocks/container.py`, `blocks/dispenser_hopper.py`). `items` muss die
   Einfügereihenfolge des Python-Dicts behalten (Float-Summe in `redstone_signal`).
3. Ganze Suite auf Rust: `RSX_SIM_CORE=rust uv run pytest -q`. Zu erwarten sind Anpassungen an Tests, die
   Python-Interna nutzen: `tests/sim/test_world.py` (eigene `Block`-Unterklassen in `REGISTRY`),
   `test_wire.py` (`JavaHashSet`; `rsx_core.update_order`/`block_pos_hash` gibt es), `test_dispenser_hopper.py`
   (`add_item`, `isinstance(..., HopperBlockEntity)`; `world._c.add_item` und `RustBlockEntity.kind` gibt es),
   `test_outputs.py` (`_instrument`; `world._c.instrument` gibt es), `scripts/bench_sim.py` (patcht
   `_execute_update`; stattdessen `neighbor_update_count`).
4. `pytest --sim-core rust` geht nur mit Pfad (`pytest tests --sim-core rust`), weil die Option in
   `tests/conftest.py` steht; nach `conftest.py` im Repo-Root verschieben.
5. Sinnvoll: Differenztest beider Kerne über alle Szenarien und Vorlagen (`Recording` muss exakt gleich sein),
   Abgleich `state_facts` gegen `blockdata` für alle Zustände der Tabelle.
6. Messen, Designnotiz und diese Datei aktualisieren.

### Aufgabenverteilung für die nächste Session (Opus 5.5 als Hauptsession, Sonnet 5.5 als Agents)

Die Hauptsession läuft mit Opus 5.5 und startet Sonnet-Agents über das Agent-Tool mit `model: "sonnet"` und
`isolation: "worktree"`. Jeder Agent ändert nur die genannten Dateien, committet in seinem Worktree und meldet
Branch und Commit. Opus prüft und merged.

| Nr. | Aufgabe | Modell | Abhängig von |
|---|---|---|---|
| 1 | `wip/rust-piston` und `wip/rust-outputs` nach `master` mergen, zum Kompilieren bringen | Opus | – |
| 2 | `piston.rs` gegen `blocks/piston.py` gegenlesen und fertigstellen (Resolver, `PosHashMap`, Block-Events, BUD-Notizen); Kolben-Traces und `tests/sim/test_piston.py` grün | Opus | 1 |
| 3 | `container.rs` neu portieren (`blocks/container.py`, `blocks/dispenser_hopper.py`); Traces comparator-container, dispenser-trigger, dropper-hopper, hopper-chain, hopper-lock, hopper-stack-sizes | Sonnet | 1 |
| 4 | `outputs.rs` fertigstellen und gegenlesen; Traces copper-bulb, doors, lectern, note-block, powered-rails, target-block, seq-*-copper-bulb*, cmp-t-flip-flop-and; Zufallsvergleich für Schienen gegen den Python-Kern | Sonnet | 1 |
| 5 | Differenztest beider Kerne (`tests/sim/test_core_equivalence.py`): alle Szenarien, Vorlagen und Fixtures, `Recording` und Notizen exakt gleich; Abgleich `state_facts` gegen `blockdata` | Opus | 1 |
| 6 | Tests auf beide Kerne umstellen, die Python-Interna nutzen (`test_world.py`, `test_wire.py`, `test_dispenser_hopper.py`, `test_outputs.py`); `--sim-core` nach `conftest.py` im Repo-Root; `scripts/bench_sim.py` auf `neighbor_update_count` | Sonnet | 3, 4 |
| 7 | Abweichungen aus 5 und 6 suchen und beheben, bis `RSX_SIM_CORE=rust uv run pytest -q` und `RSX_SIM_CORE=python uv run pytest -q` grün sind | Opus | 2–6 |
| 8 | Messen (`bench_sim.py`, `rsx redesign examples/specs/composed/xor4.yaml`, beide Kerne), Profil ansehen, bei Bedarf Hot Paths im Wrapper/Kern beschleunigen | Opus | 7 |
| 9 | Ergebnis in `docs/m4-search-and-performance.md`, `STATUS.md` und Befehlsliste eintragen; Worktrees und WIP-Branches aufräumen | Sonnet | 8 |

Reihenfolge: 1 zuerst (kurz). Dann 3 und 4 parallel als Sonnet-Agents, währenddessen 2 und 5 in der
Hauptsession. Danach 6 (Sonnet), 7, 8 (Opus), 9 (Sonnet). Für die Agent-Aufträge taugen die Prompts dieser
Session als Vorlage: Referenzdatei nennen, nur eine Rust-Datei ändern, Signaturen behalten, Abnahme über die
genannten Golden Traces, Build-Befehle mitgeben.

Build: `uv sync` baut die Erweiterung (Gruppe `rust`, Standard). Nach Rust-Änderungen
`uv pip install --reinstall-package rsx-core ./rust/rsx-core`, schneller Check mit
`cd rust/rsx-core && PYO3_PYTHON=../../.venv/Scripts/python.exe cargo check`. In Git Bash vorher
`export PATH="$HOME/.cargo/bin:$PATH"`. Ohne Rust: `uv sync --no-group rust` (dann Python-Kern).
Toolchain auf diesem Rechner: rustup, `stable-x86_64-pc-windows-gnu` (keine MSVC-Build-Tools), Komponente
`llvm-tools`; `~/.cargo/config.toml` setzt `-C dlltool=~/.cargo/tools/llvm-dlltool.exe` (Kopie von `llvm-ar`,
geht bei einem Toolchain-Update nicht verloren).

### Session 5 (2026-11-10)

- Komposition (`design/compose.py`): Ausgang eines Bausteins treibt den Eingang eines anderen.
  - Lampe wird zu Verstärker, Staub oder Block plus Verstärker; der Hebel wird zu Staub oder Verstärker.
  - Gerade Leitungen oder BFS-Router (Staub auf Stein, Stufen hoch/runter, Abstand zu allem, Verstärker
    nach 15 Blöcken); Bausteine werden in 4 Richtungen gedreht (`rotate`).
  - `wire`: Leitung innerhalb eines Kandidaten, auch durch Abgreifen eines Hebels.
- Logik vor Speicher: YAML `inputs`/`gate` (`behaviour.gated`), z. B. `examples/behaviour/t-flip-flop-and.yaml`.
  Aus aufgezeichnetem Verhalten wird das Gatter erraten (`search.gate_guesses`, zweistufig).
  Bei Verhaltensaufnahmen gelten nur Lampen als Ausgänge, wenn es welche gibt.
- Zerlegung von Wahrheitstabellen (`design/decompose.py`, Ashenhurst): and5 (5 Eingänge, über der
  PLA-Grenze) 27 Blöcke; xor4 199 statt 470. Mehrere Ausgänge nebeneinander mit abgegriffenen Hebeln
  (`decompose.parallel`).
- T-Flip-Flop-Spezifikation hat einen zweiten Flankenabstand (ein 30-gt-Monoflop galt sonst als T-FF).
- Agent: Volladdierer-Vorlage `fulladder-comparator` (108 statt 270 Blöcke), Observer-Monoflop 2 gt.
  Kompaktere XOR nicht gefunden (28 Blöcke bleibt Minimum der geprüften Bauweisen).
- 5 Kompositions-Szenarien `scenarios/cmp-*.yaml` im Spiel aufgezeichnet, alle identisch
  (`scripts/compose_scenarios.py`).
- **Rust-Messung:** >90 % der Redesign-Zeit liegen im Simulator-Kern (volle Bewertung PLA xor4: 8,9 s).
  Bedingung für den Rust-Kern ist erfüllt; Details in `docs/m4-search-and-performance.md`.
  Entscheidung steht beim Nutzer (will dafür Fable 5.2 ausprobieren).

### Session 4 (2026-11-05)

- Clock-Erkennung an echten Bauformen geprüft (`tests/fixtures/analysis/clocks/`, `tests/analysis/test_clocks.py`):
  Observer-Paar, Repeater-Ring, Fackel-Repeater-Clock (läuft bzw. brennt durch).
  - Der Anstoß schickt jetzt auch Shape-Updates (sonst starten Observer-Clocks nicht).
  - Periode aus dem ersten regelmäßigen Abschnitt; ein späteres Ende (Burnout) wird mit Tick gemeldet.
  - Die Ausschaltverzögerung der Lampe wird von der An-Zeit abgezogen. Schwingen ohne feste Periode wird gemeldet.
  - Fehler behoben: Trichter ohne Cooldown galten als „beschäftigt“, die Welt kam nie zur Ruhe (2TickFiveLanternPrize).
- Neue Golden Traces `torch-repeater-clock` (Burnout bei Tick 60, wieder an 160 gt später) und `repeater-ring-clock`: beim ersten Lauf identisch. TRCH-008/011 verifiziert.
- Performance gemessen, Werte in `docs/m4-search-and-performance.md`: ~4 000 aktive Ticks/s, ~210 000 Neighbor-Updates/s; `rsx explain` 3 s (mux3-8) bzw. 9 s (seg7). Hot-Path-Optimierung brachte ~15–20 %.
- M4 begonnen (`src/redstone/design/`):
  - `spec.py`: Spezifikation (Wahrheitstabelle, max. Verzögerung) aus YAML (`examples/specs/*.yaml`, Ausdrücke wie `a != b`) oder aus `analyze()`.
  - `evaluate.py`: Kandidat im Simulator prüfen, und zwar jede Kombination ab dem gespeicherten Zustand und jeden Einzel-Übergang (ein Lauf pro Kombination). Constraints: Box (x/z drehbar), erlaubte/verbotene Blöcke, QC, Verzögerung.
  - `templates.py` (Agent): 24 Gatter-Vorlagen (Buffer … XOR, MUX2, Halbaddierer). Alle per `scripts/template_scenarios.py` → `scenarios/tpl-*.yaml` im echten Spiel aufgezeichnet und identisch.
  - `search.py`: Vorlagen über Permutation von Ein-/Ausgängen zuordnen, ranken (korrekt, Volumen, Blöcke, Verzögerung).
  - `compact.py`: Entwurf verkleinern (Ebenen schneiden, Blöcke entfernen, zuschneiden). Jeder Schritt wird simuliert, `normalize` lässt den gespeicherten Zustand im Simulator einschwingen.
  - `rsx redesign <spec.yaml|schematic> [--max-size X,Y,Z] [--allow/--forbid] [--no-qc] [--max-delay] [-o out.litematic]`.
  - Simulator-Fehler behoben: `is_face_sturdy`-Overrides ohne `support`-Parameter (Absturz, wenn eine Wandfackel ihren Block verliert).
  - Messung: Eine volle Bewertung von mux3-8 dauert 2,4 s, fast alles in der Staub-Neuberechnung. Geschätzter Gewinn eines Rust-Kerns: 30–100× im Kern, 20–50× pro Bewertung, wenn die Lauf-Schleife samt Aufzeichnung mit nach Rust geht.
- `synth.py`: generische Synthese als Fackel-PLA (Quine-McCluskey, eine Spalte pro Produktterm). Erste Fassung: höchstens 4 Eingänge und 7 Terme (siehe nächster Punkt). Auf Anhieb korrekt für alle Beispiele und 40 Zufallstabellen. Volladdierer, Halbaddierer, XOR und Mehrheit sind im Spiel aufgezeichnet (`scenarios/pla-*.yaml`) und identisch. Die Entwürfe sind groß (Volladdierer 15×4×15); `rsx redesign` kompaktiert sie im Zeitlimit `--time`.
- PLA kompakter (Agent): Terme werden über Ausgänge geteilt, mehr als 7 Terme sind möglich (Repeater in den Leitungen), das Layout ist dichter. Weiterhin höchstens 4 Eingänge (`MAX_INPUTS`). Volladdierer 410 → 270 Blöcke, XOR 90 → 50. 8 PLA-Szenarien sind im Spiel identisch. Der Agent wurde vor seinem Abschlussbericht gestoppt; sein Stand wurde danach geprüft (Tests, Oracle-Traces) und committet.
- Verhaltens-Spezifikationen `design/behaviour.py`: Testabläufe mit erwarteten An-Intervallen und Toleranzen. Konstruktoren für monostable, pulse-extender, delay, t-flip-flop, rs-latch und clock (YAML `behaviour: …`, Beispiele in `examples/behaviour/`). Aus Bestandsschaltungen werden Pulse je Eingang, Eingangspaare und gehaltene Hebel aufgezeichnet. Ohne angegebene Verzögerung sind Flanken 0–10 gt nach dem Eingang erlaubt. Die Lampen-Ausschaltverzögerung wird herausgerechnet.
- `rsx redesign` mit einer Schematic wählt selbst: Wahrheitstabelle, wenn das Original sie in allen Übergängen erfüllt; Clock-Spezifikation bei Clocks; sonst das aufgezeichnete Verhalten.
- `design/seq_templates.py` (Agent): 17 Vorlagen mit 60 Varianten. Delay, Monoflop (Comparator, Kupferbirne; Hebel/Knopf), Pulsverlängerer, T-Flip-Flop (Kupferbirne), RS-Latch (Fackeln), 5 Clock-Bauweisen. Die erste Variante jeder Vorlage ist im Spiel aufgezeichnet (`scenarios/seq-*.yaml`, `scripts/seq_template_scenarios.py`).
- Fehler behoben: Kupferbirnen-Ausgänge wurden über `powered` (Eingang) statt `lit` gelesen; betraf auch `rsx explain`.
- Aufzeichnung in `Circuit.run` fragt nur geänderte Blöcke ab (`World.dirty`), dadurch 15–25 % schneller.
- Rust-Kern: Der Nutzer ist offen dafür. Entscheidung: erst die M4-Pipeline in Python, dann anhand der Kandidaten/s entscheiden (siehe Designnotiz).

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
uv run pytest -q                                   # 709 Tests, alle grün (~65 s)
uv run rsx redesign examples/specs/xor.yaml -o out.litematic   # Redesign Logik (M4)
uv run rsx redesign examples/behaviour/t-flip-flop.yaml        # Redesign Zeitverhalten/Speicher
uv run rsx redesign <schematic> [--max-size X,Y,Z] [--no-qc] [--compact N] [--time S]
uv run python scripts/template_scenarios.py        # tpl-/pla-Szenarien neu erzeugen (danach rsx oracle … --golden)
uv run python scripts/seq_template_scenarios.py    # seq-Szenarien neu erzeugen
uv run python scripts/bench_sim.py                 # Simulator-Geschwindigkeit
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
   - Erledigt (Session 4): Clock-Erkennung an echten Clocks. Offen: optional SVG-Timing-Diagramm; Analyse großer Schaltungen beschleunigen (`_run_steps` spielt jede Eingabe-Sequenz von vorn ab).
   - BUD-Notiz ist eine Heuristik (Staub zwei Blöcke entfernt wird nicht gemeldet).
2. **Rust-Kern (Entscheidung beim Nutzer, Bedingung erfüllt):** nur `sim/world.py` + Blöcke als PyO3-Modul,
   Python bleibt Referenz, alle Golden Traces (`tests/sim/test_golden.py`) müssen bestehen. Messwerte in
   `docs/m4-search-and-performance.md` (Abschnitt Session 5). Als Messlatte `azazo1/redstone-rs` nur ansehen.
3. **M4 weiter:** Leitlinie bleibt `docs/m4-search-and-performance.md`.
   - Lücken der Vorlagen: kein Monoflop mit 3 gt (2 gt per Observer, sonst ab 4 gt); Comparator-Monoflop mit Hebel nur bis 8 gt; kein Pulsverlängerer max(p, L) per Comparator-Fade-out (nur konzipiert); XOR-Vorlagen groß (28–33 Blöcke).
   - Komposition: XOR-Vorlagen lassen sich nicht als zweiter Baustein ansteuern (Hebel eingebaut; Agent meint, freie Nachbarn lägen außerhalb des zugeschnittenen Rasters – prüfen). PLA-Eingänge vertragen keinen Staub an Hebelstelle (Block über der Inverter-Fackel liegt daneben) – PLA-Variante mit ansteuerbaren Eingängen wäre nützlich. Geteilte Teilfunktionen zwischen Ausgängen werden nicht genutzt (Volladdierer per `parallel` nicht gefunden; Vorlage gewinnt).
   - Verhalten aus Bestandsschaltungen nur bis 3 Eingänge; Ausgänge, die schneller schwingen als die Lampe, werden falsch gelesen.
   - M3-Analyse erkennt „Logik vor Speicher“ nicht (Wahrheitstabelle meldet AND für das T-FF hinter AND); nur `rsx redesign` errät es.
   - Danach: Topologie per SAT/SMT, gezielte Suche (Mutation, Kompaktieren) – lohnt erst mit schnellerem Kern.
   - Achtung: Ergebnisse gelten zunächst nur an der Oracle-Position (DUST-018).
4. **Restliche Simulator-Lücken (M2):**
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
  design/       candidate.py, spec.py, behaviour.py, evaluate.py, templates.py, seq_templates.py, synth.py,
                search.py, compact.py, report.py, compose.py (Router), decompose.py
  knowledge.py  Linter, Index, mark
  oracle.py     Start des Fabric-Servers
oracle/         Fabric-Mod (Java)
knowledge/      Wissensbasis (Markdown)
scenarios/      Validierungsszenarien (YAML)
tests/golden/   im echten Spiel aufgezeichnete Traces
```
