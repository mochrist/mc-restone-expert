# Ungeprüfte und widersprüchliche Aussagen

Generiert mit `uv run python -m redstone.knowledge index`. Nicht von Hand bearbeiten.

Stand: 3 offene von 279 Aussagen; 137 davon sind im Spiel verifiziert, die übrigen sind durch Quellen (meist den Spielcode) belegt.

| ID | Status | Konfidenz | Aussage | Datei |
|---|---|---|---|---|
| DUST-019 | widersprüchlich | hoch | Wiki nennt die Update-Reihenfolge von Staub „zufällig", der Code ist deterministisch | [components/redstone-wire.md](components/redstone-wire.md) |
| ORD-014 | widersprüchlich | mittel | Spieleraktionen passieren zwischen zwei Game-Ticks | [mechanics/tick-phases-and-order.md](mechanics/tick-phases-and-order.md) |
| ZT-006 | widersprüchlich | hoch | Wiki: Repeater verlieren 0-Tick-Pulse; im Spiel verlängert der Repeater sie, nur Comparatoren ignorieren sie | [mechanics/zero-tick.md](mechanics/zero-tick.md) |
