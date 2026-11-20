# Backlog

Offene Punkte, die **kein** Auftrag in `docs/tasks/` sind. Wer hier etwas angeht, macht zuerst einen Auftrag
daraus (Ziel, Einstieg, Abnahme, Abbruch). Vorgeschichte je Punkt: `docs/history.md`.

## Bewusst zurückgestellt

- **Topologie per SAT/SMT** (alter Plan in `docs/m4-search-and-performance.md`): nicht angehen. Die Komposition
  aus Vorlagen, PLA und Zerlegung löst Funktionen bis 11 Eingänge; der Engpass ist die Größe der Grundbausteine
  und der Leitungen, nicht die Wahl der Bauteile. Ersatz: Auftrag 07 (Offline-Suche nach kleineren Bausteinen).
  Wieder aufgreifen nur, wenn 07 scheitert und kleinere Entwürfe dem Nutzer wichtig sind.
- **M5 Export-Mod, Screenshot-Fallback:** optional, kein Bedarf geäußert.
- **Exakte BUD-Notiz** in `rsx explain`: die Heuristik meldet Staub zwei Blöcke entfernt nicht. Genau ginge es
  nur mit der Position des auslösenden Blocks (26.3 liefert in `neighborChanged` nur die Orientierung) oder mit
  einem Abfragen aller Kolben je Tick in beiden Kernen. Für eine Notiz nicht lohnend.
- **Experimentelles Redstone** (Feature-Flag): außerhalb des Ziels.

## M2 Simulator

- Spender/Werfer: item-spezifisches Verhalten fehlt, zufällige Slotwahl ist „erster Slot“ (ASSUMPTIONs in
  `sim/blocks/dispenser_hopper.py`).
- Keine Entities (Pfeile, Loren, Items am Boden, Spieler); Druckplatten nur per Aktion `step` nachgebildet;
  Detektorschiene fehlt; Sculk ohne Shrieker/Warden; SCULK-007 ohne Entities nicht prüfbar.
- Tageslichtsensor nur bei fester Tageszeit, Himmelslicht angenähert (wird in Auftrag 04 Teil 2 behoben).
- Crafter: nur wenige Rezepte, keine Reste. Kuchen: nur Komparator-Signal und Halt, kein Essen.
- Beobachtung (unbestätigt, Sessions 10/11): die erste Oracle-Aufnahme nach Serverstart lag bei
  Komparator-/Trichter-Timing vereinzelt einen Tick daneben; bei 1 Tick Versatz neu aufnehmen.
- Oracle löscht Nicht-Spieler-Entities vor jedem Szenario; Szenarien mit Item-Entities trotzdem einzeln laufen lassen.

## M3 Analyse

- Teiltabellen (mehr als 6 Hebel): sehr seltene Abhängigkeiten können fehlen (`analyze._refine_dependencies`).
- Logik vor einem Baustein wird bis 4 Hebel erkannt; darüber nur Einzelbausteine.
- OR und XOR vor einem Set-only-Speicher sind nicht unterscheidbar.
- Ausgänge, die schneller schwingen als die Lampe schaltet, werden falsch gelesen.
- SVG-Zeitdiagramme fehlen für Pulsantwort und Logik-vor-Baustein-Abschnitte.

## M4 Entwurf

- Vorlagen-Lücken: Monoflop 3 gt nur mit Knopf; Hebel-Komparator-Monoflop nicht für jede gerade Länge; Impuls-,
  Verlängerer- und Blinker-Längen nur für die Werte in `gui/static/wizard.js` (`PULSES`, `EXTENDS`, `CLOCKS`).
- Nicht ansteuerbare Vorlagen-Eingänge: `mux2-comparator` s, `halfadder` b, `fulladder` b/c,
  `a-and-not-b-torch` a, Repeater-XOR/XNOR a.
- Nicht zerlegbare Funktionen über 8 Eingängen ohne Shannon-Schnitt mit höchstens zwei gemeinsamen Eingängen bleiben ungelöst.
- Verhalten aus Bestandsschaltungen nur bis 6 Eingänge (`cli.MAX_RECORDED_INPUTS`).
- addsub4 (Auftrag 08) ist keine Bit-für-Bit-Kaskade, sondern ein PLA mit 7 Eingängen plus eine Stufe (5452 Blöcke, 91×7×54).
  Kleinstes G zuerst (`shared_common_splits`) ergibt 4622 Blöcke, aber mehr Volumen (55×7×98), weil `_pairs` und
  `_design_part` nach Volumen wählen und das PLA als Teil kompakter ist als die Kaskade (Rest mit 2 Bits: Kaskade
  954 Blöcke/9576 Volumen gegen PLA 3213/7300). Eine echte Kaskade bräuchte eine Stufenanordnung nebeneinander statt
  in einer Linie oder Wahl nach Blöcken.
- Router (`compose._route`) in Python ist nach dem Simulator der nächste Engpass bei kleinen Entwürfen (Rust-Fassung
  `rust/rsx-core/src/route.rs` gibt es für den BFS-Kern).
- Kompaktieren: es fehlen größere Züge (ganze Kaskadenstufen neu anordnen); Budget ist kein Engpass.
- Kompaktieren großer Entwürfe: `compact.relocations` (`_dust_path`, Python) ist nach Auftrag 03 der Engpass (mux8:
  354 s von 449 s) und prüft das Zeitlimit nicht, `--time` wird deutlich überzogen. Kandidaten: Zeitlimit in der
  Suche prüfen, Liste lazy erzeugen, `_dust_path` nach Rust.
- Schnellprüfung: je Lauf kosten Welt aufbauen (`place_grid`, Block-Entities laden) und der Anfangszustand als
  `Pos`-Objekte mehr als die Ticks (mux8: 1,4 s für 2048 Läufe); eine geklonte Rust-Welt je `Circuit` spart das.

## Kleinere Bausteine

- **Kleinere Bausteine (Rest von Auftrag 07):** Mehrheit von 3 unter 40 (heute 58 PLA). Ansatz Fackel-NOR je Paar,
  ODER-Staub auf einem Block mit Fackel als Umkehrer: Kern ~20 Blöcke; Problem ist das Paar gegenüberliegender NOR-Blöcke
  und dass ein stark versorgter Block (Hebel daran, Verstärker davor) jeden Staub daneben speist. Ebenso XNOR, AND3,
  Halbaddierer, mux2 mit `mine_templates.py` und Startentwürfen (`enum_xor.py` als Muster). Idee des Nutzers: bekannte
  Bauweisen aus Wiki/Community nachbauen und als Startentwürfe geben (eigene Zählweise mit Stützblöcken beachten).
  Kleine Punkte: mux8 in `_shannon` nebeneinander statt übereinander; `drivable-pla` mit `mux2-comparator-select`.

## Katalog (Auftrag 05)

- Weitere Bauwerke: Sortierer mit mehreren Fächern (Fächer nebeneinander, Trichterkette oben), Kolbentür 3×3,
  Tür mit Druckplatten beidseitig. Vorlage: `catalog/entries.py` (Abnahme zuerst als Check, dann bauen).
- Sortierer: Durchsatz ist 1 Item/8 gt; für volle Trichterketten-Geschwindigkeit mit mehreren Sorten müsste die
  Sperre auch bei dauerhaft vollem Filter offen bleiben (bei einem Fach nicht nötig).
- GUI-Simulation zeigt keine Gegenstände in Behältern; beim Sortierer sieht man nur Sperre und Komparatoren.

## M6 Oberfläche

- `rsx oracle --dump-blocks` nur auf der Kommandozeile (Entwicklerwerkzeug, absichtlich).
- Demo-GIF der GUI liegt nicht im Repo.

## Notizen aus laufenden Aufträgen

(Hier tragen Sessions Auffälligkeiten ein, die nicht zu ihrem Auftrag gehören.)
- GUI 3D: Bilder je Sekunde für seg7/cmp5 mit echter GPU messen (Chrome Performance); headless war nicht aussagekräftig. Screenshot Reiter „Entwerfen“ mit „Kurz erklärt“ fehlt noch.
