# Redstone-Experte

Werkzeug für Redstone-Schaltungen in Minecraft Java **26.3**: Schaltungen einlesen, im Simulator
untersuchen und erklären, und kompakter neu entwerfen. Jede Aussage und jeder Entwurf wird im Simulator
geprüft; der Simulator ist tick-genau gegen das echte Spiel validiert (Golden Traces aus einem
Fabric-Server, siehe `oracle/`).

Aktueller Stand: `STATUS.md`, offene Aufträge: `docs/tasks/`, Verlauf: `docs/history.md`.
Ursprüngliche Idee und Plan (historisch): `idea.md`, `plan.md`.

## Installation

```
uv sync                    # Python-Paket und Rust-Simulatorkern (braucht eine Rust-Toolchain)
uv sync --no-group rust    # ohne Rust: langsamerer Python-Kern
```

Alle Befehle laufen als `uv run rsx <befehl>`. `--sim-core python|rust` wählt den Simulatorkern
(Standard: Rust, wenn installiert).

## Oberfläche

`uv run rsx gui [datei]` (unter Windows auch `gui.bat`) startet eine lokale Web-App im Browser. Dort geht alles,
was die Befehle unten können: Schaltpläne öffnen (auch per Ziehen ins Fenster) und in 3D oder Ebene für Ebene
ansehen, analysieren, simulieren (Hebel anklicken), Material und Bauanleitung, Spezifikationen schreiben und
Entwürfe suchen (mit Größen-, Block- und Verzögerungsgrenzen), Ergebnisse als `.litematic`/`.schem`/`.nbt`
herunterladen, Szenarien ablaufen lassen und im echten Spiel prüfen. Aufbau und Schnittstelle: `docs/gui-api.md`.

## Typischer Ablauf

1. **Ansehen:** `rsx dump schaltung.litematic` zeigt die Schaltung Ebene für Ebene als Text,
   `--components` listet alle Bauteile mit Zustand.
2. **Verstehen:** `rsx explain schaltung.litematic -o analyse.md [--svg diagramme/]`
   - findet Hebel/Knöpfe als Eingänge und Lampen u. a. als Ausgänge,
   - betätigt jeden Eingang und misst Verzögerungen, Pulse, Speicherverhalten, Clocks,
   - erstellt die Wahrheitstabelle (bis 6 Hebel; darüber Teiltabellen),
   - erkennt Bausteine: Decoder, RS-Latch, T-Flip-Flop, Monoflop, Pulsverlängerer/-filter, Logik vor einem
     Baustein (z. B. „T-Flip-Flop, getaktet durch in1 AND in2“),
   - nennt genutzte Sonderfälle (Quasi-Connectivity, BUD, 0-Tick …),
   - schreibt mit `--svg` zusätzlich SVG-Zeitdiagramme.
3. **Neu entwerfen:** `rsx redesign schaltung.litematic -o neu.litematic --report bericht.md`
   - Ziel ist dieselbe Funktion: die Wahrheitstabelle, bei Zeitverhalten das aufgezeichnete Verhalten
     (bis 6 Eingänge), bei Clocks Periode und An-Zeit,
   - Grenzen: `--max-size X,Y,Z`, `--allow`/`--forbid` (Block-IDs), `--no-qc`, `--max-delay`,
   - `--outputs out1,out3` wählt die Ausgänge, die erhalten bleiben müssen.

Statt einer Schematic geht auch eine Spezifikation als YAML:

```yaml
# examples/specs/xor.yaml: Wahrheitstabelle als Ausdrücke
inputs: [a, b]
function:
  y: a != b
```

```yaml
# examples/behaviour/t-flip-flop-and.yaml: Zeitverhalten hinter Logik
behaviour: t-flip-flop
inputs: [a, b]
gate: a and b
```

Weitere Beispiele in `examples/specs/` (auch Teiltabellen mit `others: dont_care`) und
`examples/behaviour/` (monostable, pulse-extender, delay, t-flip-flop, rs-latch, clock).

## Was der Entwurf kann

- Vorlagen für Gatter (bis Volladdierer) und Zeitbausteine (Monoflop, Pulsverlängerer, T-Flip-Flop, RS-Latch,
  Clocks), alle im echten Spiel geprüft.
- Fackel-PLA (Summe von Produkten) für beliebige Wahrheitstabellen bis 8 Eingänge, bei Teiltabellen bis 16.
- Zerlegung in verbundene Bausteine (z. B. Ripple-Carry-Addierer bis 4 Bit) und Logik vor Zeitbausteinen.
- Kompaktieren: Ebenen und Blöcke entfernen, Teile verschieben, umsetzen und drehen, Leitungen kürzer verlegen.

## Grenzen

- Ergebnisse gelten an der Position, an der Oracle und Simulator rechnen (Min-Ecke 0, 200, 0): Die
  Update-Reihenfolge von Redstone-Staub hängt in Java von den Koordinaten ab. An anderer Stelle kann eine
  Schaltung mit knappem Timing anders laufen.
- Keine Entities (Pfeile, Loren, Spieler); Druckplatten werden nur nachgebildet, Sculk-Sensoren reagieren nur auf
  Blöcke (Hebel, Kolben, Notenblock …).
- Tageslichtsensor nur bei fester Tageszeit; die Detektorschiene fehlt.

## Für Entwicklung

```
uv run pytest -q [--sim-core python|rust] [--slow]
uv run rsx sim scenarios/<x>.yaml --diff     # Simulator gegen Spielaufnahme
uv run rsx oracle scenarios/<x>.yaml --golden  # im echten Spiel aufzeichnen (lokaler Fabric-Server)
```

Szenario- und Trace-Format: `docs/scenario-format.md`. Wissensbasis (Mechaniken mit Belegen aus dem
Spielcode und Prüfstatus): `knowledge/`, Übersicht der noch ungeprüften Aussagen in `knowledge/UNVERIFIED.md`.
