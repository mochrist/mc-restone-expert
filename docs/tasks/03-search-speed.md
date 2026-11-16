# 03 Entwurfssuche für große Funktionen beschleunigen

Modell: Opus · hängt ab von: nichts

## Ziel

`rsx redesign examples/specs/composed/mux8.yaml` unter 10 Minuten (heute ~34), ohne dass sich ein Entwurf der
Beispiele ändert.

## Warum

Die GUI hat ein Zeitlimit von 60 s, der Assistent wartet höchstens 900 s (`gui/assistant.py: JOB_WAIT`).
Funktionen mit 9–11 Eingängen sind damit praktisch nicht nutzbar, und jeder weitere Auftrag an der Zerlegung
(08) lässt sich nur testen, wenn die Suche schneller wird.

## Einstieg

- `src/redstone/design/evaluate.py: evaluate`, `_check_transitions`.
- `src/redstone/analysis/experiment.py: Circuit.run` (Schleife mit Aufzeichnung, in Python, auch beim Rust-Kern).
- `src/redstone/design/search.py: redesign` (Schnellprüfung, volle Prüfung, Kompaktieren).
- `src/redstone/design/compact.py: compact` (ruft die Bewertung bis zu `MAX_EVALUATIONS` mal).
- `src/redstone/design/decompose.py: _shannon` (mux8 = sieben mux2).
- Messwerte bisher: `docs/m4-search-and-performance.md`.

## Schritte

1. **Messen, bevor etwas geändert wird.** `python -m cProfile -o .cache/mux4.prof` auf dem Neuentwurf eines
   4:1-Multiplexers (Spezifikation wie mux8, 6 Eingänge) und auf mux8 mit `--time 300`. Aufteilung in:
   Suche der Teile, Schnellprüfungen, volle Prüfung, Kompaktieren, davon jeweils Simulator (Rust) gegen
   Python-Schleife. Zahlen in `docs/m4-search-and-performance.md` als neuen Abschnitt.
2. Je nach Messung, in dieser Reihenfolge (nach jedem Punkt neu messen und committen):
   a. **Übergänge ohne Doppelarbeit.** `_check_transitions` startet aus jeder der 2ⁿ Kombinationen und legt jeden
      der n Hebel um und zurück: 2n·2ⁿ Phasen. Jeder Übergang „Kombination c, Hebel i umlegen“ kommt dabei
      zweimal vor: einmal als Hinweg von c, einmal als Rückweg von c mit umgelegtem i. Es genügt, Hebel i nur
      von Kombinationen mit `combo[i] == False` aus hin und zurück zu legen: n·2ⁿ Phasen, jeder gerichtete
      Übergang genau einmal.
   b. **Kompaktieren großer Entwürfe mit Stichprobe.** Während des Schrumpfens (viele Bewertungen) bei mehr als
      8 Eingängen nur eine feste Stichprobe der Startkombinationen für die Übergänge (z. B. 64, fester Seed);
      das Endergebnis wird wie bisher voll geprüft, und fällt es durch, gilt der Stand vor dem Kompaktieren.
   c. **Aufzeichnungsschleife nach Rust.** `Circuit.run` als eine Methode des Rust-Kerns (Aktionen, max_ticks,
      quiet → Änderungen je Tick), Python-Fassung bleibt Referenz; Vergleichstest beider Fassungen auf allen
      Vorlagen. Nur wenn die Messung zeigt, dass die Python-Schleife nach a und b noch über 30 % kostet.
   d. Teile-Cache `decompose._BEST` über Prozessgrenzen (Datei in `.cache/`, Schlüssel wie heute plus Version
      der Vorlagen). Nur wenn die Suche der Teile dominiert.
3. `tests/design` um einen Test ergänzen, der die Zahl der Läufe (`Evaluation.runs`) für eine Spezifikation mit
   4 Eingängen festhält, damit die Halbierung nicht still verloren geht.

## Abnahme

- Für alle `examples/specs/**` und `examples/behaviour/*`: gleiche Blockzahl und gleiche Maße wie vorher
  (vorher/nachher mit `scripts/bench_compact.py` oder einer kleinen Schleife festhalten; mux8 und cmp5 einmal).
- `uv run pytest -q --slow` grün (dauert lange; ansagen).
- mux8 unter 10 min auf ruhigem Rechner; Messwerte im Dokument.
- Die im Spiel geprüften Szenarien `cmp-*` unverändert (`git status scenarios tests/golden` leer).

## Fallstricke

- Zu (a): Der Rückweg prüft den Übergang aus einem Zustand, der selbst über einen Übergang erreicht wurde, nicht
  aus einer frischen Welt. Das ist heute schon so (jeder Rückweg). Trotzdem vorher zählen, ob die bestehenden
  Tests, die fehlerhafte Entwürfe erkennen sollen, weiter anschlagen: `tests/design/test_spec_evaluate.py`,
  `tests/design/test_compact.py`, `tests/design/test_cli_redesign.py`. Zusätzlich für die Beispiele bis 6
  Eingänge einmal alt und neu nebeneinander laufen lassen: dieselben Kandidaten müssen bestehen bzw. durchfallen.
- Zu (b): Ein kompaktierter Entwurf, der die Stichprobe besteht und die volle Prüfung nicht, darf nie ausgegeben
  werden. Test dafür schreiben.
- Die Verzögerung (`ev.max_delay`) wird aus den Übergängen mitbestimmt; mit weniger Phasen kann sie kleiner
  ausfallen. Bei (a) bleibt die Menge der Übergänge gleich, also auch das Maximum; bei (b) am Endergebnis voll messen.

## Abbruch

Ändert (a) das Urteil auch nur für einen Kandidaten der Beispiele, (a) zurücknehmen und mit (b)/(c) weitermachen.
Nach zwei Sessions ohne mux8 < 15 min: Stand und Messung notieren, schließen.
