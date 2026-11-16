# Ortsfestigkeit der Entwürfe

Stand 2026-11-16 (Session 23, Auftrag 01). Messung: `uv run python scripts/bench_robust.py --out …`.

## Frage

Redstone-Staub aktualisiert seine Nachbarn in der Reihenfolge eines Java-`HashSet<BlockPos>` (DUST-018), und die
hängt von den absoluten Koordinaten ab. Simulator, Bewertung und alle Golden Traces rechnen mit der Min-Ecke bei
(0, 200, 0). Verhält sich ein Entwurf an einer anderen Stelle oder gedreht anders?

## Ergebnis

**Keiner der 125 geprüften Entwürfe hängt vom Bauort oder der Drehung ab.** Geprüft wurden alle 28
Logik-Vorlagen, alle 77 Varianten der Zeit-Vorlagen und die 20 im Spiel aufgenommenen Beispielentwürfe
(`scenarios/cmp-*`, `pla-*`), je an 48 Ursprüngen in 4 Drehungen (mux8 und cmp5: 12 Ursprünge, Schnellprüfung).
Das sind 23 712 Lagen und rund 520 000 Simulatorläufe; „Abweichung“ heißt falscher Endzustand **oder** eine
andere größte Verzögerung als bei (0, 200, 0).

Dass die Prüfung Ortsabhängigkeit überhaupt findet, zeigt ein absichtlich gebauter Entwurf
(`design/robust.py: piston_race`, zwei Kolben am selben Staub schieben dieselbe Lampe): falsch in 40 von 192
Lagen. Im echten Spiel aufgenommen (`scenarios/pos-race-5`, `pos-race-7`): bei x = 5 gewinnt der Kolben nach
unten, bei x = 7 der nach Osten, genau wie der Simulator vorhersagt. Ebenso stimmen `pos-zero-tick-piston`
(Ursprung (5, 200, 0)) und `pos-dust-network` ((3, 64, 9)) mit dem Simulator überein.

Warum die Vorlagen ortsfest sind: ihre Ausgänge hängen an Signalstärken und Verzögerungen, nicht an der
Reihenfolge gleichzeitiger Updates. Ortsabhängig werden Schaltungen, in denen zwei Reaktionen im selben Tick
um denselben Block konkurrieren (Kolben-Rennen, 0-Tick-Tricks).

## Wahl der Ursprünge (`design/robust.py: origins`)

`hashCode = (y + 31·z)·31 + x`, danach `h ^ (h >>> 16)`. Modulo 16 gilt 31 ≡ −1, 961 ≡ 1: ein Schritt in x, y, z
verschiebt die unteren Bits um +1, −1, +1. Solange k = `h >>> 16` für alle Zellen gleich ist, hängt die Reihenfolge
in einer 16er-Tabelle nur von (Verschiebung mod 16, k) ab. Bestätigt mit `piston_race`: bei k = 0 wiederholt sich
das Ergebnis exakt alle 16 Blöcke in x (`tests/design/test_robust.py`), andere k (z = 68, 136, negative
Koordinaten) ergeben andere Muster. Größere Mengen (über 12 Einträge) wachsen auf 32, 64 … Fächer und sehen mehr
Bits; dafür gibt es 8 zufällige ferne Ursprünge. Auswahl: alle 16 Verschiebungen bei k = 0, je 4 bei z = 68·j
(j = 1, 2, 5, 11), bei (−1000, 200, −1000) und bei y = 64, dazu 8 zufällige (Seed fest) im Bereich ±30 000.

Spiegeln wird nicht geprüft (der Nutzer dreht, spiegelt aber selten).

## Im Werkzeug

`rsx redesign` (und damit GUI und Assistent) prüft den besten Entwurf mit `robust.check` und schreibt einen
Abschnitt „Ortsfestigkeit“ in den Bericht. Zeitbudget etwa 5 s je Entwurf (`cli.ROBUST_BUDGET`, `robust.plan`):
kleine Entwürfe an allen 48 Ursprüngen (XOR: 0,9 s), große an weniger (mindestens 4, immer 4 Drehungen), ab 7
Eingängen nur die Schnellprüfung. Ist der beste Entwurf ortsabhängig, wird unter den nächsten vier der erste
ortsfeste genommen; sonst warnt der Bericht.

## Messung

125 Entwürfe, 23 712 Lagen, ~520 000 Simulatorläufe, ~28 min mit 6 Prozessen (ohne die drei nachgemessenen Zeit-Kompositionen: 518 016 Läufe, 1681 s); ortsabhängig: 0.

| Gruppe | Entwurf | Eingänge | Lagen | Abweichungen | Art | Zeit |
|---|---|---|---|---|---|---|
| Logik-Vorlage | buffer-direct | 1 | 48 × 4 | 0 | – | 0.1 s |
| Logik-Vorlage | buffer-dust | 1 | 48 × 4 | 0 | – | 0.1 s |
| Logik-Vorlage | buffer-repeater | 1 | 48 × 4 | 0 | – | 0.1 s |
| Logik-Vorlage | not-torch | 1 | 48 × 4 | 0 | – | 0.1 s |
| Logik-Vorlage | not-torch-below | 1 | 48 × 4 | 0 | – | 0.1 s |
| Logik-Vorlage | or2-direct | 2 | 48 × 4 | 0 | – | 0.2 s |
| Logik-Vorlage | or2-stacked | 2 | 48 × 4 | 0 | – | 0.2 s |
| Logik-Vorlage | or3-direct | 3 | 48 × 4 | 0 | – | 0.6 s |
| Logik-Vorlage | or3-stacked | 3 | 48 × 4 | 0 | – | 0.6 s |
| Logik-Vorlage | nor2-torch | 2 | 48 × 4 | 0 | – | 0.3 s |
| Logik-Vorlage | nor2-torch-flat | 2 | 48 × 4 | 0 | – | 0.3 s |
| Logik-Vorlage | and2-torch | 2 | 48 × 4 | 0 | – | 0.3 s |
| Logik-Vorlage | and2-torch-flat | 2 | 48 × 4 | 0 | – | 0.3 s |
| Logik-Vorlage | and3-torch | 3 | 48 × 4 | 0 | – | 0.8 s |
| Logik-Vorlage | nand2-torch | 2 | 48 × 4 | 0 | – | 0.3 s |
| Logik-Vorlage | nand2-torch-corner | 2 | 48 × 4 | 0 | – | 0.3 s |
| Logik-Vorlage | a-and-not-b-torch | 2 | 48 × 4 | 0 | – | 0.2 s |
| Logik-Vorlage | a-and-not-b-comparator | 2 | 48 × 4 | 0 | – | 0.5 s |
| Logik-Vorlage | mux2-comparator | 3 | 48 × 4 | 0 | – | 2.2 s |
| Logik-Vorlage | mux2-comparator-select | 3 | 48 × 4 | 0 | – | 2.3 s |
| Logik-Vorlage | cmp1-comparator | 2 | 48 × 4 | 0 | – | 0.8 s |
| Logik-Vorlage | cmp-stage-comparator | 4 | 48 × 4 | 0 | – | 11.4 s |
| Logik-Vorlage | xor2-comparator | 2 | 48 × 4 | 0 | – | 1.0 s |
| Logik-Vorlage | xor2-comparator-repeater | 2 | 48 × 4 | 0 | – | 1.1 s |
| Logik-Vorlage | xnor2-comparator | 2 | 48 × 4 | 0 | – | 1.0 s |
| Logik-Vorlage | xnor2-comparator-repeater | 2 | 48 × 4 | 0 | – | 1.1 s |
| Logik-Vorlage | halfadder-comparator | 2 | 48 × 4 | 0 | – | 1.4 s |
| Logik-Vorlage | fulladder-comparator | 3 | 48 × 4 | 0 | – | 7.7 s |
| Zeit-Vorlage | delay-repeater[delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | delay-repeater[delay=4] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | delay-repeater[delay=6] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | delay-repeater[delay=8] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | delay-repeater[delay=10] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | delay-repeater[delay=12] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | delay-repeater[delay=14] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | delay-repeater[delay=16] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | delay-torch-pair[delay=4] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | monostable-comparator[length=4,delay=6] | 1 | 48 × 4 | 0 | – | 0.5 s |
| Zeit-Vorlage | monostable-comparator[length=6,delay=8] | 1 | 48 × 4 | 0 | – | 0.5 s |
| Zeit-Vorlage | monostable-comparator[length=8,delay=10] | 1 | 48 × 4 | 0 | – | 0.5 s |
| Zeit-Vorlage | monostable-comparator-button[length=4,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-comparator-button[length=6,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-comparator-button[length=8,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-comparator-button[length=10,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-comparator-button[length=12,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-comparator-button[length=16,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-comparator-button[length=20,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-observer[length=2,delay=4] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | monostable-observer-button[length=2,delay=4] | 1 | 48 × 4 | 0 | – | 0.0 s |
| Zeit-Vorlage | monostable-copper-bulb[length=8,delay=8] | 1 | 48 × 4 | 0 | – | 0.7 s |
| Zeit-Vorlage | monostable-copper-bulb[length=12,delay=8] | 1 | 48 × 4 | 0 | – | 0.7 s |
| Zeit-Vorlage | monostable-copper-bulb[length=16,delay=8] | 1 | 48 × 4 | 0 | – | 0.8 s |
| Zeit-Vorlage | monostable-copper-bulb[length=20,delay=8] | 1 | 48 × 4 | 0 | – | 0.8 s |
| Zeit-Vorlage | monostable-copper-bulb[length=26,delay=8] | 1 | 48 × 4 | 0 | – | 0.9 s |
| Zeit-Vorlage | monostable-copper-bulb[length=30,delay=8] | 1 | 48 × 4 | 0 | – | 0.9 s |
| Zeit-Vorlage | monostable-copper-bulb[length=40,delay=8] | 1 | 48 × 4 | 0 | – | 1.0 s |
| Zeit-Vorlage | monostable-copper-bulb-button[length=8,delay=8] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-copper-bulb-button[length=16,delay=8] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-copper-bulb-button[length=30,delay=8] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | monostable-copper-bulb-button[length=40,delay=8] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | pulse-extender-copper-bulb[length=8,delay=8] | 1 | 48 × 4 | 0 | – | 0.8 s |
| Zeit-Vorlage | pulse-extender-copper-bulb[length=12,delay=8] | 1 | 48 × 4 | 0 | – | 0.8 s |
| Zeit-Vorlage | pulse-extender-copper-bulb[length=16,delay=8] | 1 | 48 × 4 | 0 | – | 0.9 s |
| Zeit-Vorlage | pulse-extender-copper-bulb[length=20,delay=8] | 1 | 48 × 4 | 0 | – | 0.9 s |
| Zeit-Vorlage | pulse-extender-copper-bulb[length=30,delay=8] | 1 | 48 × 4 | 0 | – | 1.1 s |
| Zeit-Vorlage | pulse-extender-copper-bulb[length=40,delay=8] | 1 | 48 × 4 | 0 | – | 1.2 s |
| Zeit-Vorlage | monostable-piston-button[length=3,delay=2] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | pulse-extender-comparator-fade[length=26,delay=8] | 1 | 48 × 4 | 0 | – | 1.5 s |
| Zeit-Vorlage | pulse-extender-comparator-fade[length=22,delay=8] | 1 | 48 × 4 | 0 | – | 1.6 s |
| Zeit-Vorlage | pulse-extender-comparator-fade[length=18,delay=8] | 1 | 48 × 4 | 0 | – | 1.6 s |
| Zeit-Vorlage | pulse-extender-comparator-fade[length=14,delay=8] | 1 | 48 × 4 | 0 | – | 1.6 s |
| Zeit-Vorlage | pulse-extender-comparator-fade[length=10,delay=8] | 1 | 48 × 4 | 0 | – | 1.5 s |
| Zeit-Vorlage | pulse-extender-comparator-fade-long[length=50,delay=10] | 1 | 48 × 4 | 0 | – | 2.2 s |
| Zeit-Vorlage | pulse-extender-comparator-fade-long[length=42,delay=10] | 1 | 48 × 4 | 0 | – | 2.2 s |
| Zeit-Vorlage | pulse-extender-comparator-fade-long[length=34,delay=10] | 1 | 48 × 4 | 0 | – | 2.2 s |
| Zeit-Vorlage | monostable-comparator-fade[length=24,delay=12] | 1 | 48 × 4 | 0 | – | 2.9 s |
| Zeit-Vorlage | monostable-comparator-fade[length=10,delay=12] | 1 | 48 × 4 | 0 | – | 2.6 s |
| Zeit-Vorlage | monostable-comparator-fade[length=14,delay=12] | 1 | 48 × 4 | 0 | – | 2.7 s |
| Zeit-Vorlage | monostable-comparator-fade[length=18,delay=12] | 1 | 48 × 4 | 0 | – | 2.8 s |
| Zeit-Vorlage | monostable-comparator-fade[length=30,delay=12] | 1 | 48 × 4 | 0 | – | 3.1 s |
| Zeit-Vorlage | monostable-comparator-fade[length=34,delay=12] | 1 | 48 × 4 | 0 | – | 3.0 s |
| Zeit-Vorlage | monostable-comparator-fade[length=40,delay=12] | 1 | 48 × 4 | 0 | – | 3.2 s |
| Zeit-Vorlage | pulse-extender-repeater[length=2,delay=2] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | pulse-extender-repeater[length=4,delay=4] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | pulse-extender-repeater[length=6,delay=6] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | pulse-extender-repeater[length=8,delay=8] | 1 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | t-flip-flop-copper-bulb[delay=2] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | t-flip-flop-copper-bulb-button[delay=2] | 1 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | rs-latch-torch[delay=4] | 2 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | rs-latch-torch-lever[delay=8] | 2 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | clock-observer[period=6,on_ticks=2] | 0 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | clock-repeater-ring[period=8,on_ticks=2] | 0 | 48 × 4 | 0 | – | 0.4 s |
| Zeit-Vorlage | clock-repeater-ring[period=10,on_ticks=4] | 0 | 48 × 4 | 0 | – | 0.3 s |
| Zeit-Vorlage | clock-repeater-ring[period=16,on_ticks=4] | 0 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | clock-repeater-ring[period=24,on_ticks=6] | 0 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | clock-repeater-ring[period=32,on_ticks=8] | 0 | 48 × 4 | 0 | – | 0.1 s |
| Zeit-Vorlage | clock-repeater-pair[period=12,on_ticks=6] | 0 | 48 × 4 | 0 | – | 0.4 s |
| Zeit-Vorlage | clock-repeater-pair[period=16,on_ticks=8] | 0 | 48 × 4 | 0 | – | 0.3 s |
| Zeit-Vorlage | clock-torch-repeater[period=12,on_ticks=6] | 0 | 48 × 4 | 0 | – | 0.3 s |
| Zeit-Vorlage | clock-torch-repeater[period=16,on_ticks=8] | 0 | 48 × 4 | 0 | – | 0.3 s |
| Zeit-Vorlage | clock-torch-repeater[period=20,on_ticks=10] | 0 | 48 × 4 | 0 | – | 0.2 s |
| Zeit-Vorlage | clock-comparator[period=12,on_ticks=6] | 0 | 48 × 4 | 0 | – | 0.3 s |
| Zeit-Vorlage | clock-comparator[period=16,on_ticks=8] | 0 | 48 × 4 | 0 | – | 0.3 s |
| Zeit-Vorlage | clock-comparator[period=20,on_ticks=10] | 0 | 48 × 4 | 0 | – | 0.3 s |
| Zeit-Vorlage | clock-comparator[period=36,on_ticks=18] | 0 | 48 × 4 | 0 | – | 0.2 s |
| Beispiel | cmp-adder2 | 4 | 48 × 4 | 0 | – | 27.0 s |
| Beispiel | cmp-adder3 | 6 | 48 × 4 | 0 | – | 300.7 s |
| Beispiel | cmp-and-or-shared | 3 | 48 × 4 | 0 | – | 1.1 s |
| Beispiel | cmp-and5 | 5 | 48 × 4 | 0 | – | 5.9 s |
| Beispiel | cmp-cmp3 | 6 | 48 × 4 | 0 | – | 191.4 s |
| Beispiel | cmp-cmp4 | 8 | 48 × 4 | 0 | – | 1665.2 s |
| Beispiel | cmp-cmp5 | 10 | 12 × 4 (schnell) | 0 | – | 141.8 s |
| Beispiel | cmp-drivable-pla | 5 | 48 × 4 | 0 | – | 18.6 s |
| Beispiel | cmp-mux8 | 11 | 12 × 4 (schnell) | 0 | – | 175.0 s |
| Beispiel | cmp-xor4 | 4 | 48 × 4 | 0 | – | 21.6 s |
| Beispiel | cmp-monoflop-or | 2 | 48 × 4 | 0 | – | 0.9 s |
| Beispiel | cmp-pulse-extender-and | 2 | 48 × 4 | 0 | – | 1.5 s |
| Beispiel | cmp-t-flip-flop-and | 2 | 48 × 4 | 0 | – | 0.5 s |
| Fackel-PLA | pla-encoder7 | 7 | 48 × 4 | 0 | – | 3.7 s |
| Fackel-PLA | pla-fulladder | 3 | 48 × 4 | 0 | – | 8.7 s |
| Fackel-PLA | pla-halfadder | 2 | 48 × 4 | 0 | – | 1.3 s |
| Fackel-PLA | pla-lock7 | 7 | 48 × 4 | 0 | – | 98.4 s |
| Fackel-PLA | pla-majority | 3 | 48 × 4 | 0 | – | 2.5 s |
| Fackel-PLA | pla-shared-lines | 3 | 48 × 4 | 0 | – | 7.1 s |
| Fackel-PLA | pla-xor | 2 | 48 × 4 | 0 | – | 0.9 s |
