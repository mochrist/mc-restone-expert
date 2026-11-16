# 01 Ortsfestigkeit messen und absichern

Modell: Opus · hängt ab von: nichts · höchste Priorität

## Ziel

Jeder Entwurf, den `rsx redesign`, die GUI oder der Assistent ausgibt, ist an vielen Positionen und in allen vier
Drehungen im Simulator geprüft, und der Bericht sagt das. Vorher wird gemessen, wie viele der bestehenden
Vorlagen und Beispiele überhaupt vom Ort abhängen.

## Warum

Redstone-Staub aktualisiert seine Nachbarn in der Reihenfolge eines Java-`HashSet<BlockPos>`; die hängt von den
Koordinaten ab (DUST-018 in `knowledge/components/redstone-wire.md`). Der Simulator bildet das nach, aber alles
(Bewertung, Kompaktieren, Aktoren, Vorlagen, Golden Traces) rechnet nur mit der Min-Ecke bei (0, 200, 0). Der
Nutzer baut irgendwo und irgendwie gedreht. README nennt das als Grenze; gemessen wurde es nie. Solange das
offen ist, ist „im Simulator geprüft“ für den Nutzer eine schwächere Aussage, als sie klingt.

## Einstieg

- `src/redstone/analysis/experiment.py: Circuit(grid, origin=ORACLE_ORIGIN)` kann schon an anderem Ursprung rechnen.
- `src/redstone/design/evaluate.py: evaluate`, `observe` und `design/behaviour.py: evaluate_behaviour` bauen
  `Circuit(candidate.grid)` ohne Ursprung.
- `src/redstone/design/compose.py: rotate(c, turns)` dreht einen Kandidaten (gibt `None`, wenn Schienen enthalten sind).
- `src/redstone/sim/blocks/wire.py`: `block_pos_hash`, `_spread`, Klasse für die HashSet-Reihenfolge; Tests in `tests/sim/test_wire.py`.
- `oracle/src/main/java/redstone/oracle/ScenarioRun.java:59`: `ORIGIN = new BlockPos(0, Integer.getInteger("rsx.originY", 200), 0)`; x und z sind fest.
- `src/redstone/cli.py: run_redesign` wählt den besten Entwurf (`ok[0]`) und schreibt den Bericht.

## Überlegung zur Wahl der Ursprünge (nachrechnen, bevor sie verwendet wird)

`hashCode = (y + 31·z)·31 + x`, danach `h ^ (h >>> 16)`, Bucket = unterste 4 Bit. Modulo 16 gilt 31 ≡ −1 und
961 ≡ 1: ein Schritt in x ändert den Hash um +1, in y um −1, in z um +1. Solange `h >>> 16` für alle Zellen einer
Schaltung denselben Wert k hat, hängt die Bucket-Folge aller Staubzellen nur von (Verschiebung mod 16, k mod 16)
ab: höchstens 16 × 16 Muster. Bei (0, 200, 0) ist h ≈ 6200, also k = 0. k ändert sich etwa alle 68 Blöcke in z
(961 · 68 ≈ 65 536) und ist bei negativen Koordinaten groß (Vorzeichenbits).

Vorschlag für `origins()`: (dx, 200, 0) für dx = 0…15 (alle Verschiebungen bei k = 0), dazu für einige k
(z = 68·j für j = 1, 2, 5, 11; ein Ursprung mit negativem x und z; einer bei y = 64) je 4 Verschiebungen, dazu
8 zufällige mit festem Seed im Bereich ±30 000. Das sind rund 50 Ursprünge. Mit einem kleinen Test belegen, dass
zwei Ursprünge mit gleichem (Verschiebung mod 16, k) für eine Beispielschaltung dieselbe Reihenfolge liefern;
stimmt das nicht, ist die Überlegung falsch und die Auswahl muss breiter werden (mehr Zufall).

## Schritte

1. `evaluate`, `observe`, `evaluate_behaviour`, `evaluate_any` bekommen einen Parameter `origin` (Standard
   `ORACLE_ORIGIN`), der an `Circuit` durchgereicht wird. Verhalten ohne Parameter unverändert.
2. Neues Modul `src/redstone/design/robust.py`:
   - `origins(sample: int | None = None) -> list[Pos]` wie oben,
   - `robust(candidate, spec, constraints=None, quick=False, sample=None) -> list[str]`: prüft alle Ursprünge ×
     vier Drehungen und gibt deutsche Befunde zurück („bei Ursprung (5, 200, 0), 90° gedreht: …“), leer = ortsfest.
     Bricht je Kandidat beim ersten Befund ab, wenn `stop_early` gesetzt ist.
3. Messung `scripts/bench_robust.py`: alle Logik-Vorlagen (`design/templates.py: TEMPLATES`), alle
   Sequenz-Vorlagen (`design/seq_templates.py`), die Entwürfe aller `examples/specs/**` und `examples/behaviour/*`
   (Entwürfe wie in `scripts/compose_scenarios.py: design`/`table_design`; mux8 und cmp5 nur mit Schnellprüfung
   und 12 Ursprüngen). Ergebnis als Tabelle nach `docs/robustness.md`: Entwurf, geprüfte Lagen, Abweichungen,
   Art der Abweichung (Endzustand falsch / nur Zeitpunkt anders).
4. Je nach Messung:
   - Gibt es Abweichungen: in `cli.run_redesign` die `ok`-Entwürfe der Reihe nach mit `robust` prüfen und den
     ersten ortsfesten nehmen (Zeitbudget beachten: höchstens die besten 5). Bericht bekommt einen Abschnitt
     „Ortsfestigkeit“: „an N Positionen und in 4 Drehungen geprüft“ oder eine klare Warnung, wenn nur
     ortsabhängige Entwürfe da sind. Ortsabhängige Vorlagen bekommen ein Tag `position` und stehen im Rang hinten.
   - Gibt es keine: nur die Prüfung des besten Entwurfs und die Berichtszeile.
   Entwürfe mit mehr als 8 Eingängen: Schnellprüfung (`quick=True`) und `sample=12`.
5. Oracle: `rsx.originX` und `rsx.originZ` wie `rsx.originY`; optionales Szenariofeld `origin: [x, y, z]`
   (`src/redstone/verify/scenario.py`, `docs/scenario-format.md`, `sim/runner.py: run` nutzt es,
   `src/redstone/oracle.py` reicht es als System-Property weiter). Wichtig: die Chunks am neuen Ursprung müssen
   geladen sein und block-ticken (siehe `SETTLE_TICKS` und die Prüfung in `ScenarioRun`); in der Nähe bleiben
   (z. B. (5, 200, 0), (0, 200, 70), (3, 64, 9)).
   Zwei bis drei Szenarien an verschobenem Ursprung aufnehmen: eines mit Kolben (`scenarios/zero-tick-piston.yaml`
   als Vorlage), eines mit Staubnetz (`dust-network`), und falls die Messung einen ortsabhängigen Entwurf zeigt,
   diesen an zwei Ursprüngen, an denen er sich unterscheidet. Simulator und Spiel müssen übereinstimmen.
6. README, Abschnitt „Grenzen“: den ersten Punkt durch das Ergebnis ersetzen.

## Abnahme

- `docs/robustness.md` enthält die Messung (Zahl der Entwürfe, Lagen, Abweichungen).
- `tests/design/test_robust.py`: `origins()` deckt alle 16 Verschiebungen ab; ein bewusst ortsabhängiger
  Kandidat (aus der Messung oder konstruiert: zwei Kolben am selben Staub) wird erkannt; ein AND-Gatter ist ortsfest.
- Die neuen Golden Traces an verschobenem Ursprung sind identisch zum Simulator (`uv run rsx sim … --diff`).
- `uv run rsx redesign examples/specs/xor.yaml --report x.md` nennt die Ortsfestigkeit; Laufzeit höchstens +2 s.
- Ganze Suite grün, auf beiden Kernen (`--sim-core python` dauert ~9 min, einmal am Ende).

## Fallstricke

- `compose.rotate` dreht um die Hochachse und verschiebt in die Min-Ecke; Ein- und Ausgänge wandern mit. Spiegeln
  ist nicht nötig (der Nutzer dreht, er spiegelt selten); als Notiz ins Dokument.
- Die Vorlagen werden beim Bauen am Ursprung eingeschwungen (`templates._settle`, `compact.normalize`): der
  gespeicherte Ruhezustand kann an anderem Ursprung derselbe sein, muss aber nicht. Die Prüfung beginnt wie
  `evaluate` mit einem Leerlauf und meldet, wenn die Schaltung dort nicht ruht.
- Die Zahl der Simulatorläufe wächst um Faktor ~200. Kleine Entwürfe brauchen Millisekunden; für große die
  Stichprobe nutzen und die Zeit im Bericht nennen.
- Golden Traces an anderem Ursprung dürfen die bestehenden 154 nicht verändern.

## Abbruch

Stimmen Simulator und Spiel an verschobenem Ursprung **nicht** überein, ist das ein Befund im Simulator
(Hash-Nachbildung): Szenario als fehlschlagenden Test festhalten, Auftrag als blockiert markieren, Nutzer informieren.
