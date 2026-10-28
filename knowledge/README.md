# Wissensbasis

Belegtes Wissen über Redstone-Mechaniken der **Java Edition 26.3** (Ziel-Version, `DataVersion` 5023).
Bedrock ist out of scope. Das experimentelle Redstone (Feature-Flag „Redstone Experiments", Klasse
`ExperimentalRedstoneWireEvaluator`) wird nur als Abweichung erwähnt.

## Aufbau

```
knowledge/
├── README.md            # dieses Dokument (Format)
├── SOURCES.md           # allgemeine Quellen (Spielcode, Versionen)
├── sources/             # weitere Quellen, eine Datei pro Themenbereich
├── UNVERIFIED.md        # generiert: alle Aussagen, die nicht "belegt" oder "im-Spiel-verifiziert" sind
├── basics/              # Signalstärke, Powering, Ticks, Updates
├── components/          # eine Datei pro Komponente
└── mechanics/           # Quasi-Connectivity, Update-Reihenfolge, BUD, 0-Tick, ...
```

## Format einer Datei

```markdown
---
topic: Redstone Repeater
prefix: REP
---

# Redstone Repeater

Kurze Einordnung in Prosa (optional).

### REP-001: Der Eingang liegt auf der Seite, auf die `facing` zeigt
- Aussage: Ein Repeater mit `facing=north` liest sein Eingangssignal vom Block nördlich und gibt nach Süden aus.
- Version: 26.3
- Quelle: [SRC-MC-CODE] `DiodeBlock#getInputSignal`; [SRC-WIKI-REPEATER]
- Konfidenz: hoch
- Status: belegt
- Hinweise: optional (Versionsunterschiede, Gegenquellen, offene Fragen)
```

Regeln:

- **ID**: `<PREFIX>-<dreistellige Nummer>`, eindeutig über die ganze Wissensbasis, wird nie neu vergeben.
- **Aussage**: genau eine prüfbare Behauptung. Lieber zwei Einträge als ein „und".
- **Version**: die Version, für die die Aussage geprüft wurde, ggf. „26.3 (seit 1.x)".
- **Quelle**: mindestens eine Quellen-ID aus `SOURCES.md` in eckigen Klammern. Beim Spielcode zusätzlich
  `Klasse#methode`. **Keinen Spielcode ins Repo kopieren**, nur referenzieren und in eigenen Worten beschreiben.
- **Konfidenz**: `hoch` (Code gelesen oder mehrere unabhängige Quellen), `mittel` (eine verlässliche Quelle),
  `niedrig` (Community-Aussage, Forum, unklar).
- **Status**:
  - `belegt`: durch Quelle gedeckt, noch nicht im Oracle geprüft
  - `ungeprüft`: plausibel, aber ohne ausreichende Quelle
  - `widersprüchlich`: Quellen widersprechen sich; beide in „Hinweise" nennen, nicht glätten
  - `im-Spiel-verifiziert`: durch ein Szenario im Oracle bestätigt; Format `im-Spiel-verifiziert (scenarios/<datei>)`
- **Hinweise**: Versionsunterschiede (z. B. „vor 1.21.2 anders"), Widersprüche, Bug-Reports (MC-xxxxx).

## Quellen (`SOURCES.md` und `sources/*.md`)

```markdown
- [SRC-MC-CODE] Minecraft Java 26.3 Server, unobfuskiert, dekompiliert mit Vineflower 1.12.0. Lokal unter `.cache/mcsrc/` (nicht im Repo).
- [SRC-WIKI-REPEATER] https://minecraft.wiki/w/Redstone_Repeater (abgerufen 2026-10-28)
```

## Werkzeuge

- `uv run python -m redstone.knowledge lint` prüft das Format aller Dateien.
- `uv run python -m redstone.knowledge index` erzeugt `UNVERIFIED.md` neu.
