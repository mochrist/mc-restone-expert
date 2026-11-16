# 08 Zerlegung für mehrere Ausgänge mit gemeinsamen Eingängen

Modell: Opus · hängt ab von: 03 (ohne schnellere Bewertung dauert jeder Versuch zu lange) · niedrige Priorität

## Ziel

Funktionen mit mehreren Ausgängen, bei denen ein Steuereingang in jede Stufe geht, werden als Kaskade
entworfen. Prüfstein: 4-Bit-Addierer/Subtrahierer (`op, a3..a0, b3..b0` → `s3..s0, carry`; 9 Eingänge, über dem PLA-Limit).

## Einstieg (alles in `src/redstone/design/decompose.py`)

- `shared_splits(spec, width)` / `_shared_split` / `_shared`: mehrere Ausgänge, G liefert 1–2 gemeinsame
  Signale an H; bisher nur **disjunkt** (jeder Eingang gehört G oder H).
- `nondisjoint_splits` / `_common_split` / `_nondisjoint` / `_apart` / `_tapped`: **ein** Ausgang, gemeinsame
  Eingänge C (höchstens `MAX_COMMON = 2`); H's Hebel für C werden über angezapfte Leitungen von G's Hebeln gespeist.
- `shared()` ist der Einstieg für mehrere Ausgänge, aufgerufen in `search.redesign` und `_design_part`.

## Schritte

1. `shared_common_splits(spec)`: wie `shared_splits(width=1)`, aber mit C (1 bis `MAX_COMMON` Eingänge) in beiden
   Teilen. Bedingung: für **jede** Belegung von C hat die Mehrausgangs-Tabelle der Rest-Ausgänge über S × F
   höchstens zwei verschiedene Spalten. G: Eingänge C ∪ S, Ausgänge g plus die lokalen Ausgänge (die nur von
   C ∪ S abhängen). H: Eingänge g, C ∪ F, Ausgänge der Rest. Reihenfolge wie bei `shared_splits`: viele lokale
   Ausgänge und kleines F zuerst.
2. `_shared_common`: Verbindung wie `_nondisjoint`: erst `chains(G, 0, H, 0)`, Prüfung mit getrennten Hebeln
   gegen eine Spezifikation wie `_apart` (für mehrere Ausgänge verallgemeinern), dann `_tapped` für C.
   Ein- und Ausgänge in Spezifikationsreihenfolge bringen wie in `_shared`.
3. In `shared()` nur aufrufen, wenn weder ein noch zwei disjunkte Signale einen Entwurf geben.
4. Beispiel `examples/specs/composed/addsub4.yaml`, Test in `tests/design/test_compose.py` (Marker `slow`),
   Szenario über `scripts/compose_scenarios.py`, im Spiel aufnehmen (512 Kombinationen).

## Abnahme

- 2-Bit-Addierer/Subtrahierer (5 Eingänge) in unter 2 min, kleiner als das PLA; 4 Bit wird gefunden.
- Bestehende Beispiele unverändert (Blockzahl, Maße); `pytest --slow` grün; `cmp-addsub4` im Spiel identisch.

## Fallstricke

- Rekursion: Der Rest H eines Schnitts hat wieder `op` als Eingang und wird wieder so zerlegt. `_best` ist nach
  Eingangsnamen, Tabelle und Tiefe gecacht; die Tiefe muss für 4 Stufen reichen (`shared(depth=3)` prüfen).
- In Session 18 vervielfachten nicht-disjunkte Schnitte innerhalb der Teile die Suchzeit (mux8: 17 min statt
  1 min); deshalb die Bedingung in Schritt 3 und ein Zähler für die Versuche im Protokoll.
- Ein angezapfter Hebel kann nicht zugleich von einem anderen Teil getrieben werden (`driven`): wie in
  `_shannon` solche Schnitte überspringen.

## Abbruch

4 Bit nach einer Session nicht gefunden: 2 Bit als Beispiel behalten, Befund notieren, schließen.
