# Verlauf der Sessions

Neueste zuerst. Neue Sessions tragen hier 3–6 Zeilen ein (was geändert wurde, Befunde, Messwerte).
Der aktuelle Stand und die offenen Aufträge stehen in `STATUS.md` und `docs/tasks/`.

## Session 23 (2026-11-16): Aufträge 02, 06, 10 (Sonnet-Agents), 01 (Opus), 03 (Opus-Agent)

- 04 Teil 1 Druckplatte (Sonnet-Agent): `design/sensors.py`, `rsx redesign --input stone_pressure_plate`, API,
  Assistent (Absage für Platten entfällt), Wunsch-Karten; Plattenentwürfe ortsfest (48 × 4). Nur im Simulator
  geprüft. `assistant_eval --only druckplatte` gelungen (Pulsverlängerer + Platte + Eisentür, 61 Blöcke).
- 03 Suche (Opus-Agent): Übergänge nur noch je Richtung einmal (`evaluate.TRANSITIONS="half"`), Aufzeichnungsschleife
  im Rust-Kern (`World.run_recording`). Volle Prüfung mux8 78 s → 8,8 s; mux8 ohne Zeitlimit ~34 → 12–13 min
  (Rechner belastet), mit `--time 60` 3:44 → 2:16 und jetzt kompaktiert; cmp5 ~15 → 6 min. Kein Beispielentwurf
  geändert. Neuer Engpass: `compact.relocations`/`_dust_path` (prüft das Zeitlimit nicht), im Backlog.
- 01 Ortsfestigkeit: `design/robust.py` (`origins`, `check`, `robust`, `plan`), `evaluate*`/`observe` mit
  `origin`. Messung (`docs/robustness.md`): 125 Entwürfe × 48 Ursprünge × 4 Drehungen, **0 ortsabhängig**.
  Szenariofeld `origin` (Simulator und Oracle); `piston_race` an x=5/x=7 im Spiel aufgenommen: Gewinner wechselt
  wie vorhergesagt, Hash-Nachbildung bestätigt. `rsx redesign` prüft den besten Entwurf (~5 s Budget, XOR +0,9 s)
  und hat einen Abschnitt „Ortsfestigkeit“. Suite: Rust 1690, Python 1675 grün.
- 02 Aktoren: `tests/design/test_actuators.py` (32 Tests, 7 Aktoren × 4 Entwürfe; Fackel-AND geht nur mit
  Notenblock und Eisenfalltür), `scripts/actuator_scenarios.py`, sieben Szenarien `act-*` mit XOR im Spiel
  aufgenommen, alle identisch zum Simulator. Wunsch-Karten haben das Feld „Was soll geschaltet werden?“.
- Oracle aus einem Worktree: `oracle/build` fehlt dort; `redstone.oracle.ORACLE_DIR` auf den Hauptordner setzen.
- 06 Alltagssprache: `render/plain.py` (`plain_design`, `plain_analysis`), Feld `plain` in `/api/explain` und
  `/api/redesign`, Reiter zeigen „Kurz erklärt“ oben; Bauanleitung als druckbare HTML-Seite (`gui/guide_html.py`,
  `/api/export?format=guide-html`); 3D-Ansicht zeichnet Sonderformen instanziert: Zeichenaufrufe seg7 677 → 62,
  cmp5 459 → 75 (Bilder je Sekunde headless nicht aussagekräftig, ~50 vorher wie nachher).
- 10 Aufräumen: alter Agent-Worktree entfernt; `.cache`-Zwischenstände (~9 MB, bas-/dec-/ge-/mcsrc-in*, Logs) nach Freigabe gelöscht.

## Session 22 (2026-11-16): Umplanung (Fable-5.2-Hauptsession, kein Programmcode)

- Übergabe neu gegliedert: `STATUS.md` nur noch Stand, Auftragstabelle, Fakten, Befehle (595 → ~115 Zeilen); der
  Verlauf liegt in dieser Datei, Zurückgestelltes in `docs/backlog.md`, je Aufgabe ein Auftrag in `docs/tasks/`
  (Ziel, Einstieg, Schritte, Abnahme, Fallstricke, Abbruch), Regeln in `docs/tasks/README.md`.
- Neue Reihenfolge: zuerst Ortsfestigkeit (Entwürfe sind nur bei (0, 200, 0) und in einer Drehung geprüft; der
  Oracle kann nur `originY` verschieben), dann Tests und Spielaufnahmen der Aktoren, dann Suchgeschwindigkeit.
- Befund zur Suchzeit: `evaluate._check_transitions` prüft jeden Übergang zweimal (Hin- und Rückweg von beiden
  Enden): halbe Laufzahl möglich (Auftrag 03, noch nicht umgesetzt und nicht gemessen).
- Entscheidung: Topologie per SAT/SMT wird nicht verfolgt (Begründung in `docs/backlog.md`); stattdessen
  Offline-Suche nach kleineren Grundbausteinen (Auftrag 07). Fortschritt in Prozent entfällt.

## Session 21 (2026-11-15): Assistent mit echtem Schlüssel, Shannon-Zerlegung (Opus-Hauptsession, 1 Opus-Agent)

- Assistent (`gui/assistant.py`): Antworten werden gestreamt (`client.beta.messages.stream`, Ereignis `delta` je
  Textblock mit `key`, `text` ersetzt die Stücke), Runde abbrechen (`POST /api/chat/<id>/cancel`, Knopf „Stopp“;
  abgebrochene Antwort bleibt nicht in der Historie, offene `tool_use` bekommen ein Fehler-Ergebnis), Chat übersteht
  Neuladen der Seite (Ereignis `user`, Chat-ID in localStorage, Wiedergabe ab since=0 ohne neue Suchen), Knopf
  „Neue Unterhaltung“. Schlüssel auch aus `.env` im Projektordner. Systemprompt: nur beschreiben, was im Bericht steht.
- `scripts/assistant_eval.py`: 10 Wünsche in Alltagssprache gegen die echte API (Codeschloss, Türklingel,
  Alarmanlage, Leuchtturm, Treppenlicht, Wechselschalter, Mehrheit, Kolben-Umschalter, Druckplatte → ehrlicher
  Ersatz, Itemsortierer → ehrlich abgelehnt). Alle 10 richtig übersetzt, Entwürfe gefunden, je 7–15 s;
  Bericht in `.cache/assistant-eval/report.md`.
- M4 (Agent): Shannon-Zerlegung f = mux2(s, f|s=0, f|s=1) in `design/decompose.py`, neue Teil-Vorlage
  `mux2-comparator-select` (s per Leitung ansteuerbar, Markierung `part`: nur in Zerlegungen), `wire` auch mit
  Verstärker vor Staub, Router: Wege, die ihre eigenen Stufen unterbrechen, werden streng neu gesucht (Python und
  Rust, `strict`). mux4 111 statt 190 Blöcke, mux8 354 statt 782 (im Spiel geprüft, `cmp-mux8`). Durch den
  Router änderte sich `cmp-cmp5` (vorher 533 Blöcke, Weg unterbrach sich selbst, lief aber): neu erzeugt, im Spiel aufgenommen, Wahrheitstabelle und Simulator = Spiel. Ganze Suite: 1609 grün, 11 übersprungen.

## Session 20 (2026-11-15): Assistent in der GUI (Opus-Agent im Worktree)

- `src/redstone/gui/assistant.py`: Chat mit Claude (`claude-opus-5-5`, Beta-Endpunkt mit `fallbacks="default"`,
  Effort medium, eigene Werkzeug-Schleife, höchstens 12 Modellaufrufe je Runde). Werkzeuge: `design_circuit`
  (YAML-Vorgabe + Höchstmaße/verbotene Blöcke + `output`, über `server.Job`, Vorgabe landet in `.cache/gui/specs`),
  `explain_circuit` (`tools.explain`), `shrink_circuit` (auch für Suchergebnisse, als `.litematic` zwischengespeichert),
  `find_examples`/`load_example`. Systemprompt: Laie, Deutsch, Vorgabeformat, nur baubare Werte (wie `wizard.js`),
  ehrlich sagen, was nicht geht.
- Server: `GET /api/assistant`, `POST /api/assistant/key` (nach `~/.rsx/anthropic_api_key`), `POST /api/chat`,
  `GET /api/chat/<id>?since=k` (Ereignisse status/job/load/text/error; `docs/gui-api.md`).
- Oberfläche: Reiter „Assistent“ mit Schlüsselfeld (nur ohne Schlüssel sichtbar), Ideen-Knöpfen, Chat; vom
  Assistenten gestartete Suchen laufen wie im Reiter „Entwerfen“ live in der Ansicht (`followJob`).
- Tests: `tests/gui/test_assistant.py` (ohne Schlüssel klare Meldung, Schlüsselablage, ganze Schleife mit gemocktem
  Client inkl. echter Entwurfssuche). `tests/gui` und `tests/design` grün. Mit echtem Schlüssel noch nicht gelaufen.

## Session 20b (2026-11-15): M4-Agent (Opus, Worktree), auf Wunsch des Nutzers vorzeitig beendet

- Keine Code-Änderung, nur Analyse. Befund zu `mux2-comparator`: als G verbindet er sich doch
  (`chains(mux2, 0, buffer-dust, 0)`: 32 von 40 Layouts korrekt, Lampe → Staub nach Süden), als H an den
  Dateneingängen a/b ebenfalls (23 bzw. 24 von 40), am Auswahleingang s nie (0 von 40).
- Plan für kleinere Multiplexer (offen): Shannon-Zerlegung f = mux2(s, f|s=0, f|s=1) mit zwei G-Teilen, wenn
  die Kofaktoren höchstens `MAX_COMMON` gemeinsame Eingänge haben: G0 → mux2.a (`chains`), G1 → Eingang b der
  Komposition (`chains` mit `in_index`), gemeinsame Hebel per `_tapped`. mux8 wäre dann 7 × mux2 (je 19 Blöcke)
  plus Leitungen statt 782 Blöcke; Tiefe 2 reicht (mux8 → mux4 → mux2-Vorlage).
- Plan für mehrere Ausgänge mit gemeinsamen Eingängen (offen): `shared_splits` mit C wie in `_common_split`
  (je Belegung von C höchstens zwei Mehrausgangs-Spalten), Verbindung wie `_nondisjoint`. Gutes Beispiel:
  Addierer/Subtrahierer (op, a0..a3, b0..b3; 9 Eingänge), op ist in jeder Stufe gemeinsam. Carry-Lookahead ist
  als Funktion ohnehin Ripple-zerlegbar und braucht das nicht.

## Session 19 (2026-11-14): Oberfläche, „alle Funktionen auch in der GUI“ (Fable-5.2-Hauptsession, keine Agents)

- Server (`gui/server.py`, neu `gui/tools.py`): Endpunkte für Analyse (`/api/explain`, Markdown plus SVGs),
  Text-Ansicht (`/api/dump`), Szenario-Lauf mit Golden-Vergleich (`/api/scenario`), Aufnahme im Spiel als Job
  (`/api/oracle`, höchstens eine zugleich, Vergleich Spiel ↔ Simulator, optional Golden schreiben), Download
  (`/api/export`: litematic/schem/nbt, Material, Bauanleitung als Text, Ebenen, kompiliertes Szenario, Bericht),
  Upload (`/api/upload`) und Spezifikationen aus dem Editor (`/api/spec`), beide nach `.cache/gui/`; Kernwahl
  (`/api/info`, `/api/core`). `/api/redesign` nimmt alle Schalter von `rsx redesign`. Vertrag: `docs/gui-api.md`.
- Oberfläche: Berichtsspalte mit Reitern (`static/docs.js`, eigener kleiner Markdown-Renderer),
  Spezifikations-Editor mit Vorlagen (`static/speceditor.js`), Aktionen und Suchoptionen in der Seitenleiste,
  Ein-/Ausgänge mit Namen in der Simulation (Eingänge anklickbar), Ziehen von Dateien ins Fenster, „Ergebnis
  zeigen“ macht den besten Entwurf zur aktuellen Schaltung (analysieren, simulieren, herunterladen).
  URL-Parameter `click=…` drückt Knöpfe der Reihe nach (für Screenshots ohne Erweiterung).
- Auf Rückmeldung des Nutzers („noch nicht übersichtlich“) Oberfläche nach Aufgaben neu gegliedert: links nur
  Dateien (Reiter je Dateiart, Suche), Mitte Ansichten mit Abspielleiste und Startbildschirm, rechts
  Arbeitsbereich mit Reitern Bauen / Simulieren / Analysieren / Entwerfen (Bedienelemente und Ergebnisse je
  Aufgabe zusammen; Entwerfen in drei Schritten). „Aktuelle Schaltung“ = Datei oder Entwurf der Suche; der
  Reiter Simulieren startet die Simulation selbst. Berichtsspalte, Modus-Schalter und Quellenauswahl entfallen.
- Auf weiteren Wunsch („moderneres Design wie Watermelon UI / Cult UI, bin kein Schaltkreis-Profi“): neues
  Aussehen (fast schwarzer Grund, schwebende Karten, Pillen-Knöpfe, Akzent Redstone-Rot, Schrift Geist, Icons
  `static/icons.js`), Reiter heißen Nachbauen / Ausprobieren / Verstehen / Entwerfen, Startbildschirm, Beispiele
  mit Klarnamen („Zum Einstieg“), Bedienhinweise in den Ansichten. Entwerfen über Wunsch-Karten statt YAML
  (`static/wizard.js`). Die Regler bieten nur Werte an, für die `rsx redesign` einen Entwurf findet (gemessen:
  Impuls 2–8, 12, 16, 20, 30, 40 gt; Blinker nur zehn Paare aus Periode/An-Zeit; andere Längen haben keine Vorlage).
- `design/actuators.py`, `rsx redesign --output BLOCK` (auch `/api/redesign` mit `output`): Notenblock, Spender, Werfer, Eisenfalltür, Eisentür, Kolben oder klebriger Kolben statt Lampe am Ausgang, erst an Stelle der Lampe, sonst daneben hinter einem Verstärker; jede Fassung wird im Simulator gegen die Lampen-Fassung geprüft (Endzustand und Zahl der Einschaltungen je Eingabe), der beste passende Entwurf wird genommen. Stichprobe: bei sechs Entwürfen gehen fast alle Kombinationen, nur das Fackel-AND geht mit Tür/Kolben/Spender nicht. Nicht im Spiel aufgenommen, keine eigenen Tests. Simulation in der GUI läuft von selbst; Umrandung in 3D folgt der Blockform.
- `design/evaluate.py`: bei `--allow`/`--forbid` zählt die Wandfackel als Fackel (vorher umging
  `--forbid redstone_torch` die Wandfackel).
- `tests/sim/test_core_equivalence.py`: Kerne laufen Tick für Tick nebeneinander (vorher alle Welt-Dumps im
  Speicher: `cmp-mux8` mit 81 922 Ticks brauchte über 11 GB und hing), Szenarien dort bis 6000 Ticks.
- Im Browser geprüft (Chrome-Erweiterung): Suche für `xor.yaml` mit `forbid: comparator`, Ergebnis simuliert,
  Upload einer `.schem`, Analyse, Text-Ansicht, Editor; Oracle-Lauf über die GUI (`tpl-xor2-comparator`): identisch.

## Session 18 (2026-11-14): Übergabe aus Session 17 (Opus-Hauptsession, 2 Sonnet-Agents)

- M4: `cmp5` (5-Bit-Komparator, reine Vorlagen-Kaskade, kompaktiert 533 Blöcke, 31×5×19) nach `composed/`, im
  Spiel aufgenommen (`cmp-cmp5`, 1024 Kombinationen, Oracle nur wenige Minuten statt geschätzter 45): identisch,
  Wahrheitstabelle stimmt. Suche ~15 min (slow-Test).
- M4: nicht-disjunkte Zerlegung f = h(g(S ∪ C), C, F) (`decompose.nondisjoint_splits`, `CommonSplit`,
  `_nondisjoint`): bis zu zwei gemeinsame Eingänge C, je Belegung von C höchstens zwei Spalten. H's gemeinsame
  Hebel werden über angezapfte Leitungen von G's Hebeln gespeist (`compose.wire`, `_tapped`; am Wandhebel einer
  ansteuerbaren PLA meist Repeater). Vor dem Anzapfen wird die Verkettung mit getrennten Hebeln geprüft
  (`_apart`, Stichprobe von 128 Kombinationen) – die meisten Layouts scheitern schon dort (PLA-Lampe von Staub
  darüber gespeist: nur Modus „stone“ geht). Nur für einen Ausgang, nur ohne disjunkte Zerlegung und nur über
  dem PLA-Limit (innerhalb der Teile vervielfachte sie die Suchzeit: mux8 17 min → 1 min, gleiches Ergebnis).
  Beispiel `examples/specs/composed/mux8.yaml` (8:1-Multiplexer, 11 Eingänge): kompaktiert 782 Blöcke,
  14×10×23, ~5 min; `cmp-mux8` im Spiel identisch (2048 Kombinationen). Spaltenvergleich über
  `operator.itemgetter` auf der umsortierten Wahrheitstabelle (11 Eingänge: ~2 s).
- M2 (Sonnet): Notenblock-Instrument im Spiel (`note-block-instrument`, 7 Fälle, OUT-016): Wandkopf oben wirkt
  nicht (der Block darunter zählt; harp nur bei Luft darunter), Teppich → harp, Wolltreppe → guitar,
  Eichentreppe → bass. Block-Dump identisch, `gen_note_block_instruments.py --check` ok.
- M0 (Sonnet): alle 4 offenen Aussagen aufgelöst. DAY-006 im Spiel (`daylight-skylight-distance`: 15 minus
  Abstand bestätigt), ZT-006 im Spiel (Wiki widerlegt), DUST-019 per Code (HashSet, deterministisch), ORD-014
  nur Zählweise. `UNVERIFIED.md`: 0 offen.

## Session 17 (2026-11-14): Fortsetzung der abgebrochenen Session 16 (Opus-Hauptsession, 9 Agents)

- M6 GUI (Entscheidung des Nutzers in Session 16: lokale Web-App, alle drei Live-Ansichten). Vertrag
  `docs/gui-api.md`. Server `gui/server.py` (Standardbibliothek, 127.0.0.1:8737; jede Simulation in eigenem
  Thread, Suche als Job mit Einzelbildern aus `design/observe.py`), `gui/model.py`, `rsx gui [datei]`.
  `cli.run_redesign()` ausgelagert. Sonnet-Agents: Oberfläche `gui/static/` (three.js 0.160 per Import-Map,
  `?demo=1` mit `static/demo/model.json`), `gui/materials.py` + `rsx materials`.
- `RustWorld.block_entities` hält die Welt nur noch schwach: der Zyklus ließ den Garbage Collector Rust-Welten
  (unsendable) in fremden Threads freigeben (Fehlermeldungen, Speicherleck).
- GUI im Browser (Chrome-Erweiterung) geprüft: Bauanleitung, Simulation (Hebel per Klick in der Ebenen-Ansicht,
  Lampe geht an), Entwurfssuche (`adder2`: 32 Einzelbilder, Ergebnis simulierbar). Tooltip folgt jetzt
  Simulationsänderungen. Standard-Port 8737; unter Windows exklusiv gebunden (SO_REUSEADDR ließ mehrere Server
  denselben Port teilen; auf 127.0.0.1:8765 lag zudem ein Service Worker einer anderen App). `gui.bat` startet die
  GUI. Material-Wörterbuch (Sonnet-Agent): Farben × Nomen mit Adjektivendung, Holzarten, Steinvarianten, Kupfer.
- Headless-Screenshot ohne Erweiterung: `chrome.exe --headless=new --enable-unsafe-swiftshader
  --use-angle=swiftshader --virtual-time-budget=15000 --screenshot=x.png <url>`.

- M4: 5-Bit-Komparator als reine Vorlagen-Kaskade cmp1 → 4 Stufen: 545 Blöcke, 36×8×19 (vorher PLA → PLA 1401
  Blöcke, 42×8×45). Teilspezifikationen (Rest einer Kaskade) bekommen kleine Zwei-Signal-Schnitte jetzt auch über
  `MAX_CASCADE_INPUTS`; Paare von Teilentwürfen werden nach geschätztem Volumen probiert (`decompose._pairs`).
  Beispiel `examples/specs/large/cmp5.yaml` (ohne Spielaufnahme, Suche mehrere Minuten). Zeiten dieser Session
  nicht belastbar (Rechner nebenbei ausgelastet), Größen schon.
- M4 Kompaktieren: `relocations` versetzt auch zusammenhängende Gruppen von Bausteinen (`compact._units`: Kopf
  oder Ende einer Kaskade). Wichtiger: `MAX_PLACES` zählte Platzierungen mit, die mit dem Rest überlappen – bei
  Kaskaden waren das alle 4000 besten, es wurde nie ein Umzug versucht. Jetzt zählen nur freie Plätze.
  `bench_compact.py` (Budget 100): Summe Volumen 8100 → 8012, `adder3` 1056 → 968. Der Benchmark baut nur die mit
  `--only` gewählten Entwürfe (Cache wird ergänzt).

- Drei Agents parallel: M4 (Opus) Umzüge bei Komparator-Kaskaden: `_dust_path` schnitt sich selbst ab (Treppe
  auf der Stelle, Boden über eigenem Staub; `_clashes`), lange Leitungen verloren Signalstärke (`_strength_limits`,
  `_boosts` setzen Verstärker auf gerade Zellen). `bench_compact`: cmp3 1632 → 1260, cmp4 3344 → 2346, Summe
  8012 → 6954. M6 (Sonnet) Blockformen: Wandhebel/-knöpfe, Treppen, Holzfarben, Truhe, Trichter, Sculk-Sensor,
  Tageslichtsensor (`daylight_detector`), Komparator-Modus; URL-Parameter `?layout`, `?y`, `?cam`. M3 (Sonnet)
  `analyze._refine_dependencies` (s. Offene Punkte 1), Teiltabellen bis 8 Hebel.

- Nachtrag: `cmp3` (jetzt 9×8×10) und `cmp4` (17×6×23) neu im Spiel aufgenommen, identisch – die von
  `_boosts` gesetzten Verstärker sind damit im Spiel bestätigt. M6 (Sonnet): Treppenecken (`shape=inner/outer_*`,
  gegen `StairBlock.java` geprüft), deutlichere Hebel/Knöpfe/Wandfackeln in der Ebenen-Ansicht. M2 (Sonnet):
  Notenblock-Instrument aus Feld `instrument` in `blocks_26.3.json` (abgeleitet aus `Blocks.java` mit
  `scripts/gen_note_block_instruments.py`, `BlockDump.java` schreibt es künftig), beide Kerne, OUT-016; alte
  Namensheuristik war bei Teppich, Wandköpfen und Wolltreppen falsch. Demo-GIF der GUI erstellt (nicht im Repo).

## Session 16 (2026-11-13, abgebrochen durch Login-Fehler, nicht in STATUS eingetragen)

- `cmp4` als Beispiel, im Spiel aufgenommen (362 Blöcke). Fehler bei 5 Bit in `decompose._shared_split`
  (Spalten mit „egal“) behoben. BFS-Router in Rust (`rust/rsx-core/src/route.rs`, Differenztest
  `tests/design/test_route.py`).


## Session 15 (2026-11-12): Übergabe aus Session 14 (Opus-Hauptsession, 1 Sonnet-Agent), vorzeitig beendet

- M4: Zerlegung mit gemeinsamen Signalen auch für Teilspezifikationen (`decompose._merged`: verträgliche Spalten
  werden zu Klassen zusammengefasst, G wird partiell, wo keine Kombination zählt). Teilspezifikationen (das H
  eines Zwei-Signal-Schnitts) nur mit Zwei-Signal-Schnitten mit kleinem H, und nicht weiter zerlegt, wenn eine
  Vorlage passt; Durchreiche-Schnitte (so viele Klassen wie Belegungen) entfallen. 4-Bit-Komparator jetzt reine
  Kaskade cmp1 → Stufe → Stufe → Stufe: 370 Blöcke in 34 s (vorher PLA-Komposition 937 Blöcke, 74 s). Noch nicht
  im Spiel aufgenommen; 5 Bit nicht neu gemessen.
- Oracle (Sonnet-Agent): Abweichung von `daylight-detector`/`kb-unmodeled` lag an der weiterlaufenden Spielzeit
  (`gameTime`, Messung bei `gameTime % 20 == 0`), nicht an der Tageszeit. `ScenarioRun.build` springt jetzt um
  mindestens 100 Ticks vor auf die Phase `game_time mod 20` (Szenariofeld `game_time` geht ins kompilierte JSON)
  und setzt klares Wetter. Rücksprung der Uhr ließ 20 Fackel-Goldens abweichen (Ausbrenn-Einträge), daher nur
  vorwärts. Alle 149 Szenarien identisch.

## Session 14 (2026-11-12): Übergabe aus Session 13 (Opus-Hauptsession, 1 Sonnet-Agent)

- M4: Komparator-Stufe v2 (`cmp-stage-comparator`, 66 Blöcke): gi bzw. li laufen mit a−b bzw. b−a auf einem
  Staub am Rückeingang des letzten Komparators zusammen, nur dieser speist die Lampe (stark). go/lo weichen von v1
  nur bei gi = li = 1 ab (kommt in einer Kaskade nie vor). Im Spiel neu aufgenommen, identisch.
- `compose.wire`: Ausgangsmodus „top“ (Lampe → Stein, Leitung beginnt obendrauf; nur bei stark gespeisten
  Lampen sinnvoll), tight-Routen dürfen ihren Boden auf andere Blöcke legen (Brücke über fremde Leitungen) und
  schon am Start steigen. Zwei-Signal-Schnitte mit kleinem H (≥ 2 freie Eingänge) zuerst, bis 6 Eingänge
  (`MAX_CASCADE_INPUTS`), danach die billigsten.
- Ergebnis 3-Bit-Komparator: reine Kaskade cmp1 → Stufe → Stufe (242 Blöcke, Volumen 1728) in 14 s; nach Volumen
  am besten cmp1 → Stufe → PLA, kompaktiert 1496 (Session 13: 1750, Session 12: 6032; PLA allein 2700).
  `cmp-cmp3` neu aufgenommen, identisch. Test `test_comparator_cascade_of_templates` (slow).
- Oracle (Sonnet-Agent): `kb3-bud-reach`-Abweichung nicht reproduzierbar (> 10 frische Läufe, Batch aller 149,
  neue Welt, CPU-Last), Golden unverändert. Einziger gefundener Mechanismus für „ein Tick daneben“:
  `LevelTicks` überspringt Chunks außerhalb der Block-Tick-Reichweite. Der Oracle wartet jetzt 5 Ticks nach
  „Chunks bereit“ (`SETTLE_TICKS`) und bricht mit `<name>.error.txt` ab, wenn die Szenario-Chunks nicht mehr
  block-ticken. Die Spielzeit-Phase (`gameTime % 20`) und das Wetter setzt das Oracle jetzt beim Aufbau fest
  (`game_time` im kompilierten JSON, Uhr nur vorwärts); alle 149 Goldens identisch.

## Session 13 (2026-11-12): Übergabe aus Session 12 (Opus-Hauptsession, 1 Sonnet-Agent)

- M4: Vorlagen `cmp1-comparator` (1-Bit-Vergleich gt/lt, zwei Subtraktions-Komparatoren, 14 Blöcke) und
  `cmp-stage-comparator` (Kaskadenstufe gi, li, a, b → go, lo; 58 Blöcke), beide im Spiel identisch
  (`tpl-cmp1-comparator`, `tpl-cmp-stage-comparator`). 2-Bit-Komparator jetzt cmp1 → Stufe: 118 Blöcke,
  Volumen 264 (PLA 276/748). 3-Bit: PLA → Stufe, kompaktiert Volumen 1750 (PLA allein 2700), `cmp-cmp3` neu
  aufgenommen und identisch. Eine reine Kaskade (cmp1 → Stufe → Stufe) entsteht nicht: in der Stufe liegen
  go/lo auf entgegengesetzten Seiten und gi/li in entgegengesetzten Ecken, beim Verketten umschließt die zweite
  Leitung einen Ausgang (beide Verbindungsreihenfolgen geprobt, verworfen). `compose.wire` hat eine
  tight-Rückfallstufe (Leitungen dürfen nur nicht berühren), `_route(tight=True)`.
- Verworfen: unbenutzten Code der Zwei-Signal-Zerlegung auffüllen, damit H weiter zerlegbar wird – 15× langsamer,
  keine kleineren Entwürfe (Kaskaden aus Fackel-PLAs sind nicht kleiner als ein PLA).
- M2 (Sonnet-Agent): `sculk-placement` (SCULK-004) und `sculk-signal-up` (SCULK-008) im Spiel; Befund: das starke
  Signal eines aktiven Sensors geht in den Block **darunter**. SCULK-007 ohne Entities nicht prüfbar. Druckplatte:
  `use` tut jetzt nichts (wie im Spiel), neue Simulator-Aktion `step` (betreten und verlassen, nur Simulator,
  `docs/scenario-format.md`); `Experiment.run` nimmt für Platten automatisch `step`. Oracle-Mod entfernt vor jedem
  Szenario Nicht-Spieler-Entities im Szenariobereich (`ScenarioRun.build`).

## Session 12 (2026-11-12): Übergabe aus Session 11 (Opus-Hauptsession, 2 Sonnet-Agents)

- M4: Zerlegung mit zwei gemeinsamen Signalen (`decompose.shared_splits(width=2)`): Sehen die Ausgänge über
  einer gebundenen Menge 3–4 verschiedene Spalten, liefert G zwei Signale g0, g1 (Code mit den wenigsten Termen
  für G und H; bei drei Spalten ist der vierte Code für H egal, H wird eine partielle Spezifikation). Schnitte,
  bei denen G nur seine Hebel weiterreicht, entfallen. Nur versucht, wenn kein Schnitt mit einem Signal geht
  (`MAX_WIDE_SPLITS = 2`). Verbindung: g0 über `chains`, g1 über `compose.wire` in der fertigen Komposition.
  `wire` dazu erweitert: Ausgangsmodus „stone“, Staub-Modus darf neben eng stehenden Lampen beginnen (PLA-Lampen
  werden von der Fackel darüber gespeist: Verstärker und Stein lesen das nicht), Wandhebel (ansteuerbarer PLA)
  werden geradeaus angefahren; `_route` läuft nie unter seinem Startfeld durch. Neues Beispiel
  `examples/specs/composed/cmp3.yaml` (3-Bit-Komparator gt/lt), `cmp-cmp3` im Spiel identisch. 5-Bit-Komparator
  (10 Eingänge, über dem PLA-Limit) jetzt entwerfbar (~2000 Blöcke, ~80 s); bei 6 Eingängen bleibt der PLA kleiner.
- M4: Kompaktier-Budget: Messung (`scripts/bench_compact.py`) zeigt, dass fast alle Beispiele schon mit 100
  Bewertungen konvergieren (400 bringen nichts); die Einzelblöcke bekamen nur den Rest. Großen Entwürfen fehlte
  das Neuverlegen von Leitungen, das erst nach Schnitten/Verschiebungen kam: jetzt im Strukturdurchgang, nur
  angenommen, wenn kleiner. Ebenen mit wenig Blöcken zuerst, höchstens `CUT_SHARE` = 20 % je Durchgang.
  cmp3-Komposition 6032 → 3480 (vorher 4704), Rest unverändert.
- M0 (Sonnet-Agent): 12 weitere Aussagen im Spiel verifiziert, keine widerlegt (`scenarios/kb3-*`, Generator
  `scripts/gen_kb3_scenarios.py`). TRCH-012 praktisch nur beim Burnout selbst erreichbar (aus dem Code).
- M2 (Sonnet-Agent): Sculk- und kalibrierter Sculk-Sensor im Rust-Kern (`rust/rsx-core/src/sculk.rs`, Auslöser
  in basic/outputs/piston/container/world), registriert, Differenztest mit Sculk-Soup (120 Seeds); sechs
  Szenarien `sculk-*` im Spiel identisch; `knowledge/components/sculk-sensor.md` (SCULK-001…010). Befunde:
  `use` auf einer Druckplatte tut im Spiel nichts (Simulator löst aus; Platte aus dem Szenario entfernt);
  **der Oracle löscht Entities zwischen Läufen nicht** – ein geworfenes Item löste im nächsten Szenario Sensoren
  aus. Abhilfe: `oracle/run/rsx-world/dimensions/minecraft/overworld/entities/*.mca` unter der Sperre löschen,
  Szenarien mit Item-Entities einzeln laufen lassen. Teppich ist inert (Warnung „not modeled“ harmlos).

## Session 11 (2026-11-11): M3 und M4 (Fable-5.2-/Opus-Hauptsession; ab „Agents parallel“: 3 Sonnet-, 1 Opus-Agent)

- Logik vor Zeitglied (Pulsverlängerer, Pulsverkürzer, Monoflop hinter einem Gatter): Folgt ein Ausgang einem
  Hebel laut Wahrheitstabelle nur, wenn andere Hebel an sind, wird die Pulsantwort mit diesen Hebeln gehalten
  wiederholt (`pulse_response(held=…)`, `analyze._held_pulse_responses`, höchstens 24 Gruppen). Ändern alle
  Pulsantworten eines Ausgangs mit mehreren Hebeln die Pulslänge gleich, meldet `rsx explain`
  „AND, dahinter ein Zeitglied: …“ (`Analysis.timing`). Bloße Gatter (Pulsfilter, „unverändert durchgereicht“)
  werden nicht als Baustein gemeldet; 50 Vorlagen/PLA/Kompositionen ohne Falschmeldung.
  Fixtures `tests/fixtures/analysis/gated/pulse-extender-{and,or}.yaml` (Kupferbirnen-Verlängerer hinter
  and2-torch/or2-direct, mit `compose.chains` gebaut; nur Analyse, nicht im Spiel aufgezeichnet).
- M4: Gegatterte Verhaltens-Spezifikationen lassen Hebelpulse unter 2 gt weg, wo andere Hebel gehalten werden
  (`behaviour.MIN_HELD_PULSE`; die AND-Fackel schluckt sie, vorher fand `rsx redesign` für einen
  Pulsverlängerer hinter AND nichts). Bestehende Szenarien unverändert. Neues Beispiel
  `examples/behaviour/pulse-extender-and.yaml` (49 Blöcke, 1 s), `cmp-pulse-extender-and` im Spiel identisch;
  `rsx explain` erkennt den Entwurf als „AND, dahinter ein Zeitglied“ wieder.
- M4: PLA bis 8 Eingänge (`synth.MAX_INPUTS`, vorher 6). Engpass war `_primes` (Quine-McCluskey verglich alle
  Paare); jetzt Partnersuche per Hash, gleiche Entwürfe, 9 Eingänge 47 s → 1,7 s. Zufallsfunktionen mit 7–10
  Eingängen und bis 3 Ausgängen alle korrekt; Bewertung dauert dann 1–25 s (2^n Kombinationen plus Übergänge),
  deshalb Grenze 8. Ganzer `rsx redesign` mit 7 Eingängen 5–25 s. Neues Beispiel `examples/specs/lock7.yaml`
  (Codeschloss, 7 Hebel, zwei komplementäre Codes, nicht einfach zerlegbar, vorher kein Entwurf; 182 Blöcke),
  `pla-lock7` im Spiel identisch (alle 128 Kombinationen, offen genau bei den zwei Codes).
- M4: Redesign aus Bestandsschaltungen mit aufgezeichnetem Verhalten bis 6 Eingänge (`cli.MAX_RECORDED_INPUTS`,
  vorher 3). Die Analyse liefert das Gatter vor dem Baustein (`BehaviourSpec.gate_hints` aus `analysis.gated`
  bzw. `analysis.timing`); `search.gate_guesses` probiert diese zuerst, über 3 Hebeln nur sie. Logik vor
  Bausteinen erkennt die Analyse jetzt bis 4 Hebel (32 Läufe). Aufgezeichnete Spezifikationen pulsen jeden Hebel
  zusätzlich, während andere Hebel an sind (bis 4 Hebel alle Kombinationen, darüber bis 2 gehaltene): vorher
  sah die Spezifikation ein Gatter wie (a and b) or (c and d) nur mit allen Hebeln an, und das Kompaktieren
  durfte die halbe Logik weglassen (24 statt 48 Blöcke, falsch). Ausgänge mit Zeitglied oder Baustein hinter
  Logik werden nicht mehr als Wahrheitstabelle neu entworfen (ein Pulsverlängerer hinter AND erfüllt die
  Tabelle samt Übergängen; vorher kam ein bloßes AND heraus). Fixture
  `tests/fixtures/analysis/gated/t-flip-flop-and-or4.yaml`.
- M0 (Sonnet-Agent): 30 weitere Aussagen im Spiel verifiziert (167 von 285 inkl. DAY-*), keine widerlegt.
  Szenarien `kb-neighbor-updates`, `kb-observer`, `kb-piston-qc`, `kb-comparator-values`, `kb-comparator-stored`,
  `kb-sources`, `kb-unmodeled` (+ Regressionen `kb-cmp-timing`, `kb-cmp-timing2`). Trick: ein Repeater
  `powered=true`, Delay 1, ohne Eingang geht bei jedem Neighbor-Update aus und macht Updates sichtbar.
  Danach in der Hauptsession: Kuchen als Comparator-Quelle in beiden Kernen ((7 − Bissen)·2, fällt ohne
  `solid`-Block darunter; Rust liest dafür jetzt das `solid`-Flag), `kb-unmodeled` damit identisch zum Spiel.
  Beobachtung eines Agents (drei von 36 Comparator-Spuren im Spiel einen Tick später) ließ sich nicht
  nachstellen: 8 Nachbauten (Abstand 1–3, Staub dazwischen, gespeicherte Ausgänge, `use`, Zufallsmixe) alle
  identisch auf beiden Kernen; drei bleiben als Regression (`diag-cmp-lanes2`, `-lanes3`, `-lanes-rnd1`,
  Generator `scripts/gen_diag_cmp_lanes.py`). Vermutlich der Effekt „erste Aufnahme nach Serverstart“ (Session 10).
- M2 (Sonnet-Agent, unvollständig): Sculk- und kalibrierter Sculk-Sensor im **Python-Kern**
  (`sim/blocks/sculk.py`: Frequenzen, Radius 8/16, Laufzeit, Auswahl, Phasen 30/10 gt, Stärke nach Abstand,
  Frequenzfilter, Wolle-Verdeckung, Resonanz; `World.game_event` mit Auslösern für Hebel, Knopf, Platte,
  Notenblock, Tür/Falltür/Zauntor, Kolben, Spender, Tageslichtsensor). Noch **nicht registriert** (Rust fehlt,
  sonst schlägt der Differenztest fehl). `sculk-lever-distance` im Spiel aufgenommen, stimmt mit dem Python-Kern
  (13 Sensoren, Abstand 1–9); übrige Szenarien nur entworfen, in `scenarios/pending-sculk/`, Generator
  `scripts/gen_sculk_scenarios.py`.
- M4 (zweiter Opus-Agent): Kompositionen halten fest, welcher Block zu welchem Teil gehört
  (`Candidate.assembly`: Labels „0“, „1/0“ …, Leitungen „~0“, `ends`), gesetzt in `connect`, `routed`,
  `place_beside`, `wire`, `rotate` und durch alle Kompaktier-Schritte mitgeführt. `compact.parts` nutzt sie, so
  lassen sich auch sich berührende Teile umsetzen; direkte Verbindungen werden neu verlegt (mit Repeater davor,
  wenn der Eingang vorher volle Stärke bekam). Volumen: xor4 270 → 243, and5 140 → 128, drivable-pla 540 → 500,
  adder2 624 → 560, adder3 1056 → 960 (Blockzahl teils leicht höher); die fünf `cmp-*` neu aufgenommen, identisch.
  Tests `tests/design/test_assembly.py`. Danach in der Hauptsession: Teile-Cache `decompose._BEST` auch nach
  Eingangsnamen geschlüsselt (Beschreibungen übernahmen sonst Namen eines anderen Teils; `cmp-adder3` hing von
  der Testreihenfolge ab).
- M0 (zweiter Sonnet-Agent): 31 weitere Aussagen verifiziert (jetzt 203 von 285), keine widerlegt, keine
  Simulator-Unterschiede; Szenarien `kb2-*` (7). Einschränkungen in den Hinweisen von CMP-015 (nur Compare-Modus)
  und SRCB-006 (nur Stärken). Beobachtungen: Seelensand leitet; eine per setblock mit `powered=true` gesetzte
  Druckplatte bleibt an (SRCB-007 so nicht prüfbar); ein Staub, der seine Stärke ändert, weckt auch einen
  Comparator zwei Felder daneben.
- M4 (Opus-Agent): Kompaktieren setzt ganze Bausteine um und dreht sie (`compact.parts`, `relocations`, Leitungen
  per BFS neu, höchstens 12 Staub). Nur drivable-pla wird kleiner (Volumen 660 → 540, `cmp-drivable-pla` neu
  aufgenommen, identisch); bei den übrigen Kompositionen berühren sich die Teile, `parts` findet nur eine Gruppe.
  Dafür müsste die Komposition festhalten, welcher Block zu welchem Teil gehört (xor4: geschätzt ~7 %).
- M2 (Sonnet-Agent): Tageslichtsensor (normal/invertiert) in beiden Kernen (`sim/blocks/daylight.py`, Rust
  `outputs.rs`), `scenarios/daylight-detector.yaml` im Spiel identisch, `knowledge/components/daylight-detector.md`
  (DAY-001..005 verifiziert). Die Oracle-Welt hat Weltuhr 0 (Sensor liest 7 unter freiem Himmel). Die 20-gt-Phase
  hängt von der absoluten Spielzeit ab: neues Szenariofeld `game_time` (nur Simulator; bei Neuaufnahme den Wert aus
  dem Oracle-Log `built at …, game time N` nachtragen). Himmelslicht nur über Leiter angenähert (ASSUMPTION,
  DAY-006 ungeprüft); Nacht/Wetter nicht modelliert.
- M3 (Sonnet-Agent): SVG-Zeitdiagramme. `rsx explain <datei> --svg DIR` schreibt ein SVG pro Eingang und
  verlinkt es im Markdown (ASCII-Diagramme bleiben); `rsx sim <szenario> --svg DATEI`; Modul
  `render/svg_timing.py`. Nicht für Pulsantwort und Logik-vor-Baustein-Abschnitte.
- Teiltabellen: zusätzlich Einzel-Umschaltungen an zufälligen Hebelstellungen (fester Seed, ~600 Läufe,
  `analyze._sampled_dependencies`). Ein AND aus drei in Ruhe ausgeschalteten Hebeln bekommt so eine Tabelle.
  seg7 unverändert (die 15 Ausgänge ohne Tabelle hängen wirklich von mehr als 6 Hebeln ab), 1,7 s.

## Session 10 (2026-11-11): Übergabe aus Session 9 abgearbeitet (Opus-Hauptsession, 1 Sonnet-Agent)

- M4 (dritter Teil der Session): Zerlegung mit gemeinsamem Teil mehrerer Ausgänge (`decompose.shared_splits`,
  `shared`): G berechnet g und die Ausgänge, die nur von der gebundenen Menge abhängen, H die übrigen aus g und
  den freien Eingängen (Mehrausgangs-Zerlegungstabelle mit höchstens zwei Spalten). Addierer: 2 Bit 151 statt
  562 Blöcke, 3 Bit 274 statt 2438, 4 Bit (8 Eingänge, vorher unmöglich) 392 Blöcke, 36 gt, ~140 s.
  - Angetriebene Teile (`_best(..., driven=True)`): alle Belegungen des ersten Eingangs einer Vorlage
    (`template_candidates(first_inputs=True)`), die per `drivable_first` (Puffer `buffer-dust` davor)
    ansteuerbaren zuerst. Teile behalten zusätzlich den Entwurf mit den wenigsten Blöcken (vorher nur Volumen).
  - `compose.chains`: findet die normale Suche nichts, Leitungen, die die Teile nur nicht berühren
    (`connect(tight=True)`, `_touches`); nötig für die eingeschlossenen Lampen des Volladdierers.
  - Übergangsprüfung: Abstand zwischen Hebelwechseln mindestens doppelte Verzögerung + 12 gt (lange Ketten).
  - Szenarien `cmp-adder2`, `cmp-adder3` (Schritt 30/40 gt je nach Verzögerung), neu aufgenommen `cmp-xor4`
    (jetzt drei Repeater-XOR, 10×3×9) und `cmp-drivable-pla`; alle im Spiel identisch.
  - Zufällige zerlegbare Funktionen (5–8 Eingänge, |S| = 2–4) werden alle gelöst, meist deutlich kleiner als das PLA.
  - Test-Option `--slow` (Marker `slow`): der Neuentwurf von adder3 (~50 s) läuft nur damit.
- M3 (zweiter Teil der Session):
  - Teiltabellen (mehr als 6 Hebel) nutzen jetzt auch Paar-Umschaltungen ab dem gespeicherten Hebelzustand
    (`analyze._pair_dependencies`, bis 20 Hebel, 1 + n + n(n-1)/2 Läufe). Ein AND aus zwei in Ruhe ausgeschalteten
    Hebeln bekommt so eine Tabelle. seg7: neue Tabelle für out13/15/17; 15 Ausgänge hängen von mehr als 6 Hebeln
    ab und werden als „ohne Tabelle“ gemeldet (vorher fälschlich nur von in1 abhängig).
  - Logik vor Set-only-Speicher (`patterns.memory_gate_from_edges`): der Speicher reagiert nur, wo die Logik
    von aus auf an wechselt; Kombinationen, bei denen er schon beim Einstellen der übrigen Hebel gesetzt wird,
    gelten als „an“ und werden gemeldet (OR und XOR sind so nicht unterscheidbar). Fixtures
    `tests/fixtures/analysis/gated/memory-{and,or}.yaml` (RS-Latch ohne Reset hinter AND/OR).
  - Analysegeschwindigkeit ist mit dem Rust-Kern kein Thema mehr: `rsx explain` seg7/mux3-8 je ~0,6 s.

- Kompaktieren mit größeren Zügen (`design/compact.py`, Branch `wip/compact-moves` geprüft, mit `master` zusammengeführt):
  Teile eines Entwurfs verschieben (Halbräume um 1–3 Blöcke, gleiche Blöcke verschmelzen, gerade Leitungen werden
  kürzer), Staubleitungen kürzer neu verlegen (`lines`, `rerouted`), Züge mit schon gescheiterter Umgebung
  überspringen (`_local_key`). `redesign` kompaktiert auch die zwei besten Kompositionen (`COMPACT_COMPOSED`).
  Volumen: and-or-shared 72 → 45, monoflop-or 48 → 30, t-flip-flop-and 84 → 72, xor4 760 → 504,
  drivable-pla 1176 → 660; Laufzeit +0,1–1,5 s. Alle `cmp-*` im Spiel neu aufgezeichnet, identisch.
- Crafter in beiden Kernen (Sonnet-Agent): Auslösen per Flanke, 4-gt-Tick, 6-gt-Crafting, gesperrte Slots,
  Comparator, Trichter; `scenarios/crafter.yaml` im Spiel identisch, `knowledge/components/crafter.md`
  (CRAFTER-001..007). Grenzen: nur wenige Rezepte (u. a. fehlt die Steindruckplatte), keine Reste/Items als Entities.
  Beobachtung: die erste Oracle-Aufnahme nach Serverstart lag bei Comparator-/Trichter-Timing einen Tick daneben,
  die Wiederholungen waren identisch zueinander und zum Simulator (unbestätigt; bei 1 Tick Versatz neu aufnehmen).
- PLA: gleiche Ausgangsfunktionen teilen eine Leitung, eine Lampe pro Ausgang (`synth.pla`, `lamp_count`).
  Lampen zwischen den Fackeln und jenseits davon auf beiden Seiten; dort fließt der Strom nur in eine Richtung,
  also dürfen Repeater zwischen den Lampen stehen. Eine Fackel in der Leitung (Südfackel) schneidet die Seite
  dahinter ab. Mit Verzögerungsgrenze gewinnen Layouts mit weniger Repeatern. seg7: 195 Blöcke, 10 gt (vorher
  ~990). 80 Zufallsfälle mit bis zu 20 gleichen Ausgängen alle korrekt. Neues Beispiel
  `examples/specs/shared-lines.yaml` (23 Ausgänge, 3 Funktionen), im Spiel identisch.

## Session 9 (2026-11-10)

- PLA bis 6 Eingänge (vorher 4; Zufallsfunktionen mit 5–6 Eingängen, auch mehrere Ausgänge und ansteuerbar, alle korrekt).
- Zerlegung: alle 55 zufälligen g(3)+h(3)-Funktionen gelöst (Budget pro Bausteinpaar).
- `rsx redesign --outputs out1,out3|all`: Ausgänge einer Bestandsschaltung wählen (Kolben-Extender: Lampe war nur Anzeige).
- Teil-Wahrheitstabellen (`others: dont_care` in YAML, `Spec.care`): Bewertung und Übergänge nur über relevante
  Kombinationen, Minimierung per Expand (`synth.minimize_partial`), PLA bis 16 Eingänge bei Teiltabellen.
  Bestandsschaltungen mit mehr als 6 Hebeln: gespeicherter Hebelzustand plus jeder Hebel einzeln umgelegt
  (seg7: 9 von 10 Hebeln sind im Ruhezustand an). Beispiel `examples/specs/encoder7.yaml`, im Spiel identisch.
- Agents: 40 weitere Aussagen im Spiel verifiziert (130/272), ZT-006 widerlegt (Repeater verlängern 0-Tick-Pulse).

## Session 8 (2026-11-10): parallel M2/M3/M4 (Opus-Hauptsession, 1 Opus- und 2 Sonnet-Agents)

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

## Session 7 (2026-11-10): Rust-Kern fertig

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

## Session 5 (2026-11-10)

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

## Session 4 (2026-11-05)

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

## Session 3 (2026-11-04)

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

