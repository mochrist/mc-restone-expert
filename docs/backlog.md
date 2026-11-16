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
- Router (`compose._route`) in Python ist nach dem Simulator der nächste Engpass bei kleinen Entwürfen (Rust-Fassung
  `rust/rsx-core/src/route.rs` gibt es für den BFS-Kern).
- Kompaktieren: es fehlen größere Züge (ganze Kaskadenstufen neu anordnen); Budget ist kein Engpass.

## M6 Oberfläche

- `rsx oracle --dump-blocks` nur auf der Kommandozeile (Entwicklerwerkzeug, absichtlich).
- Demo-GIF der GUI liegt nicht im Repo.

## Notizen aus laufenden Aufträgen

(Hier tragen Sessions Auffälligkeiten ein, die nicht zu ihrem Auftrag gehören.)
- Wizard: „alle Hebel an“ (AND) mit Eisentür/Kolben/Spender meldet nur „Entwurfssuche ohne Erfolg“; besser eine andere AND-Vorlage nehmen oder dem Laien den Grund nennen (Fackel-AND passt nicht zu diesen Aktoren).
- GUI 3D: Bilder je Sekunde für seg7/cmp5 mit echter GPU messen (Chrome Performance); headless war nicht aussagekräftig. Screenshot Reiter „Entwerfen“ mit „Kurz erklärt“ fehlt noch.
