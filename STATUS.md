# Projektstatus und Übergabe

Stand: 2026-11-14, Session 17. Geschätzter Gesamtfortschritt: **ca. 90 %** (gewichtet nach Aufwand der Meilensteine; seit Session 16 zählt die GUI M6 mit 15 % zusätzlich, ohne sie ca. 96 %).

| Meilenstein | Gewicht | Stand | Kurz |
|---|---|---|---|
| M0 Wissensbasis | 10 % | ~98 % | 295 Aussagen aus dem 26.3-Code belegt, 224 davon im Spiel verifiziert; Linter, Index (`knowledge/UNVERIFIED.md`) |
| M1 Parser + Textdump | 10 % | 100 % | `.litematic`, `.schem` (v1–3), `.nbt` lesen und schreiben; `rsx dump`, `rsx convert` |
| M2 Oracle + Simulator | 35 % | ~96 % | Oracle läuft; Simulator (Python-Referenz und Rust-Kern, ~150× schneller) stimmt mit allen 149 Golden Traces tick-genau überein; Truhen, Crafter, Tageslichtsensor, Kuchen, Sculk-Sensoren |
| M3 Analyse + Erklärung | 20 % | ~94 % | `rsx explain`: Experimente, Klassifikation, Wahrheitstabelle (Teiltabellen mit Paar- und Stichproben-Abhängigkeiten), Pulsantwort (auch hinter Logik), RS-Latch, Decoder, Logik vor T-FF/Pulsgeber/Set-only-Speicher/Zeitglied, Sonderfall-Notizen |
| M4 Redesign | 25 % | ~87 % | Vorlagen (Logik inkl. Volladdierer, Zeitverhalten/Speicher), Fackel-PLA (bis 8 Eingänge, auch mit ansteuerbaren Eingängen, gleiche Ausgänge auf einer Leitung), Komposition mit Router (Logik vor Speicher, Zerlegung auch mit einem oder zwei gemeinsamen Signalen mehrerer Ausgänge, z. B. Ripple-Carry-Addierer bis 4 Bit, Komparator bis 5 Bit, mit Komparator-Vorlagen, Ausgänge nebeneinander), Kompaktieren; alles im Spiel geprüft |
| M5 Export-Mod, Screenshot | optional | 0 % | — |
| M6 GUI | 15 % | ~85 % | `rsx gui`: lokale Web-App (three.js), 3D- und Ebenen-Ansicht, Materialliste, Bauanleitung, Entwurfssuche live, Simulation; `rsx materials`. alle drei Modi im Browser geprüft (Session 17) |

## Übergabe (aus Session 17)

Alles committet, Suite grün (1560 Tests, 149 Golden Traces). Nächste Aufgaben:

| Aufgabe | Modell | Hängt ab von |
|---|---|---|
| M4: Bausteine mit Komparator-Signalen umziehen: bei `cmp3`/`cmp4` werden jetzt Umzüge simuliert, scheitern aber (cmp1 speist die Stufe direkt; als Staubleitung fehlt die Signalstärke, die die Subtraktion braucht). Leitungen in Komparator-Eingänge mit voller Stärke (Verstärker am Ende) oder solche Bausteine nur zusammen verschieben | Opus | – |
| M4: `examples/specs/large/cmp5.yaml` im Spiel aufnehmen (1024 Kombinationen, Oracle ~45 min; nicht während der Nutzer spielt) und ggf. nach `composed/` | Opus | – |

## Verlauf

### Session 17 (2026-11-14): Fortsetzung der abgebrochenen Session 16 (Opus-Hauptsession, 2 Sonnet-Agents)

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

### Session 16 (2026-11-13, abgebrochen durch Login-Fehler, nicht in STATUS eingetragen)

- `cmp4` als Beispiel, im Spiel aufgenommen (362 Blöcke). Fehler bei 5 Bit in `decompose._shared_split`
  (Spalten mit „egal“) behoben. BFS-Router in Rust (`rust/rsx-core/src/route.rs`, Differenztest
  `tests/design/test_route.py`).


### Session 15 (2026-11-12): Übergabe aus Session 14 (Opus-Hauptsession, 1 Sonnet-Agent), vorzeitig beendet

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

### Session 14 (2026-11-12): Übergabe aus Session 13 (Opus-Hauptsession, 1 Sonnet-Agent)

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

### Session 13 (2026-11-12): Übergabe aus Session 12 (Opus-Hauptsession, 1 Sonnet-Agent)

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

### Session 12 (2026-11-12): Übergabe aus Session 11 (Opus-Hauptsession, 2 Sonnet-Agents)

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

### Session 11 (2026-11-11): M3 und M4 (Fable-5.2-/Opus-Hauptsession; ab „Agents parallel“: 3 Sonnet-, 1 Opus-Agent)

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

### Session 10 (2026-11-11): Übergabe aus Session 9 abgearbeitet (Opus-Hauptsession, 1 Sonnet-Agent)

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

### Session 9 (2026-11-10)

- PLA bis 6 Eingänge (vorher 4; Zufallsfunktionen mit 5–6 Eingängen, auch mehrere Ausgänge und ansteuerbar, alle korrekt).
- Zerlegung: alle 55 zufälligen g(3)+h(3)-Funktionen gelöst (Budget pro Bausteinpaar).
- `rsx redesign --outputs out1,out3|all`: Ausgänge einer Bestandsschaltung wählen (Kolben-Extender: Lampe war nur Anzeige).
- Teil-Wahrheitstabellen (`others: dont_care` in YAML, `Spec.care`): Bewertung und Übergänge nur über relevante
  Kombinationen, Minimierung per Expand (`synth.minimize_partial`), PLA bis 16 Eingänge bei Teiltabellen.
  Bestandsschaltungen mit mehr als 6 Hebeln: gespeicherter Hebelzustand plus jeder Hebel einzeln umgelegt
  (seg7: 9 von 10 Hebeln sind im Ruhezustand an). Beispiel `examples/specs/encoder7.yaml`, im Spiel identisch.
- Agents: 40 weitere Aussagen im Spiel verifiziert (130/272), ZT-006 widerlegt (Repeater verlängern 0-Tick-Pulse).

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
uv run pytest -q [--sim-core python|rust] [--slow] # ~1520 Tests, alle grün (Rust ~70 s, Python ~9 min)
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

## Offene Punkte (nächste Schritte, nach Priorität)

1. **M3 fertigstellen:**
   - Erledigt (Session 3, Ende): Druckplatten als Eingang (Emulation „betreten und sofort verlassen“, `PressurePlateBlock` in `basic.py`, nicht gegen das Spiel validiert, weil der Oracle keine Entities hat); volle Wahrheitstabelle bis 6 Hebel, darüber Teiltabellen je Ausgangsgruppe (`seg7`: NAND über 4 Hebel); höchstens 64 Ausgänge; Gatternamen AND/OR/NAND/NOR für n Eingänge.
   - Teiltabellen sehen Abhängigkeiten aus Einzel- und Paar-Umschaltungen (Session 10) und aus Stichproben
     (Session 11). Session 17: `analyze._refine_dependencies` prüft die Abhängigkeitsmengen an ganzen Hebelstellungen
     (alle an, alle an bis auf einen, 80 zufällige): ändert sich ein Ausgang, wenn die Hebel außerhalb der Menge
     zurückgesetzt werden, kommen die nötigen Hebel hinzu. AND über 7/8 Hebel und ODER von UND-Termen mit 3+ Hebeln
     werden gefunden; Teiltabellen jetzt bis 8 Hebel (`MAX_PARTIAL_TABLE_LEVERS`), ca. +60 bis +300 Läufe
     (Tests `tests/analysis/test_rare_dependencies.py`). Weiter können nur noch sehr seltene Kombinationen fehlen.
   - Erledigt (Session 4): Clock-Erkennung an echten Clocks. SVG-Timing-Diagramm erledigt (Session 11). Geschwindigkeit erledigt (Rust-Kern).
   - BUD-Notiz ist eine Heuristik (Staub zwei Blöcke entfernt wird nicht gemeldet). Genau ginge es nur mit der
     Position des auslösenden Blocks (in 26.3 liefert `neighborChanged` nur die Orientierung) oder mit einem
     Abfragen aller Kolben je Tick in beiden Kernen; für eine Analyse-Notiz bisher nicht lohnend.
   - Logik vor Zeitglied: erledigt (Session 11), auch das Redesign dazu.
2. **Rust-Kern: erledigt** (Session 7). Bei Änderungen am Simulator beide Kerne pflegen; der Differenztest
   `tests/sim/test_core_equivalence.py` deckt Abweichungen auf. Mögliche Folgearbeit: BFS-Router
   (`design/compose.py: _route`) beschleunigen, Lauf-Schleife samt Aufzeichnung (`Circuit.run`) nach Rust.
3. **M4 weiter:** Leitlinie bleibt `docs/m4-search-and-performance.md`.
   - Lücken der Vorlagen: Monoflop 3 gt nur mit Knopf (Hebel unmöglich, siehe Session 8); Hebel-Comparator-Monoflop nicht für jede gerade Länge; XOR-Vorlagen groß (28–33 Blöcke).
   - Komposition: nicht ansteuerbare Vorlagen-Eingänge siehe Session 8 (`mux2 s`, Addierer b/c …); Nicht einfach zerlegbare Funktionen über 8 Eingängen bleiben ungelöst (PLA bis 8, Session 11; nur einfache disjunkte Zerlegung). Kompaktieren: Teile verschieben und Leitungen neu verlegen geht (Session 10); Bausteine umsetzen/drehen geht (Session 11), mit Teilzugehörigkeit auch bei sich berührenden Teilen; Budget ist kein Engpass mehr (Session 12), es fehlen größere Züge. Geteilte Teilfunktionen: eine oder zwei gemeinsame Leitungen je Zerlegung (Session 10/12); Signale aus verschiedenen gebundenen Mengen (nicht-disjunkt, z. B. Carry-Lookahead) nicht.
   - Verhalten aus Bestandsschaltungen bis 6 Eingänge (Session 11; Gatter nur aus der Analyse, über 4 Hebeln
     ohne Logik-vor-Baustein-Erkennung also nur Einzelbausteine); Ausgänge, die schneller schwingen als die Lampe, werden falsch gelesen.
   - M3-Analyse erkennt Logik vor T-FF/Pulsgeber (Session 8), Set-only-Speicher (Session 10) und Zeitgliedern (Session 11).
   - Danach: Topologie per SAT/SMT, gezielte Suche (Mutation, Kompaktieren) – der schnellere Kern ist jetzt da.
   - Achtung: Ergebnisse gelten zunächst nur an der Oracle-Position (DUST-018).
4. **Restliche Simulator-Lücken (M2):**
   - Sculk-Sensor erledigt (Session 12; Entities, Shrieker, Warden nicht modelliert).
   - Tageslichtsensor erledigt (Session 11, nur feste Tageszeit, Himmelslicht angenähert). Kuchen
     (Session 11, nur Comparator und Halt; Essen nicht). Druckplatten, Detektorschiene, Sculk. Truhen (Session 8) und Crafter (Session 10, wenige Rezepte) erledigt.
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
  gui/          server.py, model.py, materials.py, static/ (Web-Oberfläche)
  design/       observe.py, candidate.py, spec.py, behaviour.py, evaluate.py, templates.py, seq_templates.py, synth.py,
                search.py, compact.py, report.py, compose.py (Router), decompose.py
  knowledge.py  Linter, Index, mark
  oracle.py     Start des Fabric-Servers
rust/rsx-core/  Rust-Kern (PyO3): world.rs, wire/diode/torch/piston/container/outputs.rs; sim/rust_world.py ist die Python-Seite
oracle/         Fabric-Mod (Java)
knowledge/      Wissensbasis (Markdown)
scenarios/      Validierungsszenarien (YAML)
tests/golden/   im echten Spiel aufgezeichnete Traces
```
