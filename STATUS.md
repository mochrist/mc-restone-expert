# Projektstatus und Übergabe

Stand: 2026-11-10, Session 8. Geschätzter Gesamtfortschritt: **ca. 88 %** (gewichtet nach Aufwand der Meilensteine).

| Meilenstein | Gewicht | Stand | Kurz |
|---|---|---|---|
| M0 Wissensbasis | 10 % | ~95 % | 272 Aussagen aus dem 26.3-Code belegt, 90 davon im Spiel verifiziert; Linter, Index (`knowledge/UNVERIFIED.md`) |
| M1 Parser + Textdump | 10 % | 100 % | `.litematic`, `.schem` (v1–3), `.nbt` lesen und schreiben; `rsx dump`, `rsx convert` |
| M2 Oracle + Simulator | 35 % | ~93 % | Oracle läuft; Simulator (Python-Referenz und Rust-Kern, ~150× schneller) stimmt mit allen 98 Golden Traces tick-genau überein; Truhen neu |
| M3 Analyse + Erklärung | 20 % | ~85 % | `rsx explain`: Experimente, Klassifikation, Wahrheitstabelle, Pulsantwort, RS-Latch, Decoder, Logik vor T-FF/Pulsgeber, Sonderfall-Notizen |
| M4 Redesign | 25 % | ~70 % | Vorlagen (Logik inkl. Volladdierer, Zeitverhalten/Speicher), Fackel-PLA (auch mit ansteuerbaren Eingängen), Komposition mit Router (Logik vor Speicher, Zerlegung, Ausgänge nebeneinander), Kompaktieren; alles im Spiel geprüft |
| M5 Export-Mod, Screenshot | optional | 0 % | — |

## Verlauf

### Session 8 (2026-11-10): parallel M2/M3/M4 (Opus-Hauptsession, 1 Opus- und 2 Sonnet-Agents)

- M4 Komposition (Hauptsession):
  - Ansteuerbarkeit aller Vorlagen-Eingänge gemessen: fast alle gehen (auch `xor2-comparator`); nicht ansteuerbar
    sind `mux2 s`, `halfadder b`, `fulladder b/c`, `a-and-not-b-torch a` und die Repeater-XOR/XNOR bei `a`.
  - PLA mit ansteuerbaren Eingängen: `synth.pla(drivable=True)`. Der Eingang ist ein Wandhebel an einem Block P
    am Westende der Leitungen; P speist die wahre Leitung, eine Fackel an P die invertierte direkt. Der Block
    über der Inverter-Fackel lag beim normalen PLA neben dem Eingang und koppelte zurück. Kostet 10–30 % mehr
    Blöcke, wird in der Zerlegung als letzte Wahl für den angesteuerten Teil h probiert.
  - Zerlegung: Versuchsbudget pro Bausteinpaar statt pro Zerlegung. Zufällige zerlegbare Funktionen mit 5 Eingängen:
    7 statt 5 von 15 gelöst. Neues Beispiel `examples/specs/composed/drivable-pla.yaml` (Mehrheit als Auswahl eines
    Multiplexers, 130 Blöcke), im Spiel identisch (`cmp-drivable-pla`).
  - Abstand zwischen nebeneinander gesetzten Bausteinen 1–3 Blöcke statt fest 3 (`compose.SPACINGS`):
    and-or-shared 34 → 22 Blöcke, im Spiel identisch.
  - Kompaktieren der Kompositionen bringt nichts (keine einzelne Entfernung/Ebene geht); größere Züge nötig.
- M3 (Opus-Agent): `rsx explain` erkennt Logik vor T-Flip-Flop bzw. Pulsgeber (2–3 Hebel, Experiment 5:
  jeder Hebel 4× umgeschaltet bei jeder Kombination der anderen; `patterns.gate_from_edges`, `Analysis.gated`).
  Grenzen: nur flankengesteuerte Bausteine, Logik bei „alle aus“ aus.
- M4 Vorlagen (Sonnet-Agent): `monostable-piston-button` (genau 3 gt, nur Knopf; ungerade Verzögerung über
  Kolben, PIS-019), `pulse-extender-comparator-fade` (L 10–26) und `-long` (L 34–50),
  `monostable-comparator-fade` (Hebel, 10–40 gt, nicht jede gerade Länge). Alle im Spiel identisch.
- M2 (Sonnet-Agent): Truhen, Redstone-Truhen, Kupfertruhen in beiden Kernen (Doppeltruhe, Sperre durch Block
  darüber gilt nicht für Trichter); Szenario `chest-container` im Spiel identisch; `knowledge/components/chests.md`.

### Session 7 (2026-11-10): Rust-Kern fertig

- `rust/rsx-core` (PyO3, Modul `rsx_core`) ersetzt `sim/world.py` und alle Block-Komponenten (Staub, Dioden,
  Fackeln/Observer, Kolben, Container/Dispenser/Trichter, Ausgänge). Umschalten: `RSX_SIM_CORE=python|rust|auto`
  (Standard `auto` = Rust, wenn gebaut), `rsx --sim-core …`, `pytest --sim-core …` (Option jetzt in `conftest.py`
  im Repo-Root). Python-Kern bleibt Referenz.
- Abnahme: 92/92 Golden Traces und die ganze Suite auf beiden Kernen grün. Differenztest
  `tests/sim/test_core_equivalence.py`: ganze Welt jeden Tick über Szenarien, Vorlagen, Fixtures und 150 zufällige
  Block-Soups, dazu statische Fakten aller 35 723 Blockzustände. Einzige Abweichung (leeres Lesepult `page`) behoben.
- Tests mit Python-Interna: `test_dispenser_hopper.py` läuft auf beiden Kernen; drei Tests in `test_world.py`
  (eigene `Block`-Klassen) und einer in `test_wire.py` (Monkeypatch) nur auf Python, dafür Rust-eigene Gegenstücke
  (`update_order`/`block_pos_hash`, `neighbor_update_count`). `scripts/bench_sim.py --sim-core …`.
- Messung (Details `docs/m4-search-and-performance.md`): Kern ~150× schneller, `rsx explain` 50×, Testsuite 80 s → 25 s.
  `rsx redesign …/xor4.yaml`: 70 s (Python) → 8,7 s (Rust) → **3,3 s** nach Router-Optimierung (`compose._halo`
  statt 27 Abfragen pro BFS-Zelle; Ergebnis identisch). Engpass ist jetzt der BFS-Router in Python, nicht mehr der Simulator.
- Ablauf: Merge der WIP-Stände (Kolben, Ausgänge) kompilierte sofort und bestand alle zugehörigen Traces;
  Container-Port und Testumstellung als Sonnet-Agents, Differenztest und Messung in der Hauptsession.

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
- Rust-Kern bauen: `uv sync` (Gruppe `rust`, Standard); ohne Rust `uv sync --no-group rust` (dann Python-Kern).
  Schneller Check: `cd rust/rsx-core && PYO3_PYTHON=../../.venv/Scripts/python.exe cargo check`; in Git Bash vorher
  `export PATH="$HOME/.cargo/bin:$PATH"`. Toolchain auf diesem Rechner: rustup `stable-x86_64-pc-windows-gnu`
  (keine MSVC-Build-Tools), Komponente `llvm-tools`; `~/.cargo/config.toml` setzt
  `-C dlltool=~/.cargo/tools/llvm-dlltool.exe` (Kopie von `llvm-ar`, übersteht Toolchain-Updates).
- Szenario- und Trace-Format: `docs/scenario-format.md` (verbindlicher Vertrag zwischen Simulator und Oracle).

## Befehle

```
uv run pytest -q [--sim-core python|rust]         # ~1100 Tests, alle grün (Rust ~30 s, Python ~105 s)
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
2. **Rust-Kern: erledigt** (Session 7). Bei Änderungen am Simulator beide Kerne pflegen; der Differenztest
   `tests/sim/test_core_equivalence.py` deckt Abweichungen auf. Mögliche Folgearbeit: BFS-Router
   (`design/compose.py: _route`) beschleunigen, Lauf-Schleife samt Aufzeichnung (`Circuit.run`) nach Rust.
3. **M4 weiter:** Leitlinie bleibt `docs/m4-search-and-performance.md`.
   - Lücken der Vorlagen: Monoflop 3 gt nur mit Knopf (Hebel unmöglich, siehe Session 8); Hebel-Comparator-Monoflop nicht für jede gerade Länge; XOR-Vorlagen groß (28–33 Blöcke).
   - Komposition: nicht ansteuerbare Vorlagen-Eingänge siehe Session 8 (`mux2 s`, Addierer b/c …); 8 von 15 zufälligen 5-Eingänge-Funktionen bleiben ungelöst (Zerlegung nur g(3)+h(3); andere Aufteilungen, tiefere Ketten prüfen). Kompaktieren braucht größere Züge (Route neu legen, Bausteine zusammenschieben). Geteilte Teilfunktionen zwischen Ausgängen werden nicht genutzt (Volladdierer per `parallel` nicht gefunden; Vorlage gewinnt).
   - Verhalten aus Bestandsschaltungen nur bis 3 Eingänge; Ausgänge, die schneller schwingen als die Lampe, werden falsch gelesen.
   - M3-Analyse erkennt Logik vor T-FF/Pulsgeber (Session 8), nicht aber vor Set-only-Speicher oder Pulsverlängerer.
   - Danach: Topologie per SAT/SMT, gezielte Suche (Mutation, Kompaktieren) – der schnellere Kern ist jetzt da.
   - Achtung: Ergebnisse gelten zunächst nur an der Oracle-Position (DUST-018).
4. **Restliche Simulator-Lücken (M2):**
   - Tageslichtsensor (Block-Entity alle 20 gt, Himmelslicht/Tageszeit), Druckplatten, Detektorschiene, Sculk, Crafter. Truhen erledigt (Session 8; ohne Katzen/Spieler).
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
rust/rsx-core/  Rust-Kern (PyO3): world.rs, wire/diode/torch/piston/container/outputs.rs; sim/rust_world.py ist die Python-Seite
oracle/         Fabric-Mod (Java)
knowledge/      Wissensbasis (Markdown)
scenarios/      Validierungsszenarien (YAML)
tests/golden/   im echten Spiel aufgezeichnete Traces
```
