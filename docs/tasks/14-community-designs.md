# 14 Bewährte Community-Bauweisen übernehmen

Modell: Opus · hängt ab von: – · Wunsch des Nutzers (Session 29): „nicht das Rad neu erfinden“; vor Auftrag 12
(dessen kleinere Bausteine kommen zum Teil genau von hier)

## Ziel

Für häufig gebaute Schaltungen nutzt das Projekt die über Jahre optimierten Bauweisen der Community statt eigener
Entwürfe: im Katalog (`src/redstone/catalog/entries.py`) und als Vorlagen bzw. Startentwürfe der Suche
(`design/templates.py`, `seq_templates.py`). Eigene Entwurfsarbeit bleibt für das, was es nicht fertig gibt.
Erster Fall, vom Nutzer bemerkt: **Itemsortierer**. Unserer braucht ein Raster von 3 Blöcken je Fach
(`SLOT_PITCH = 3`, Barrel und Subtraktions-Komparator statt Fackel), die üblichen Bauweisen sind **1 Block breit und
beliebig aneinanderreihbar**.

## Befund der Recherche (Session 29, Minecraft Wiki „Tutorial:Hopper“, Abschnitt Item sorter)

- „Basic hopper item sorter“: 1 breit, kachelbar, leise, einfacher Überlaufschutz, 2,5 Items/s, 10 Redstone-Teile.
  Filtertrichter: 41 Sortier-Items + 4 billige Füller (umbenannt). Doppeltempo-Variante 5 Items/s.
- „Compact hopper item sorter“: ohne Überlaufschutz, 9 Teile, Filter 1 + 21 Füller (16er-Items: 1 + 15).
- **Fackel-Durchbrennen ab Java 1.18:** Laut Wiki brennen bei Dauerbetrieb (2,5 Items/s) die Fackeln der Bauweise
  „oh4“ (Typ IV) durch, die Filter laufen leer. **„oh5“ (Typ V, u/Agantas)** gilt ausdrücklich als 1.18+-fest (alle
  Fackeln hinter Verstärkern), 1 breit, 2,5 bzw. 5 Items/s; „oh-basic“ ebenso (mehr Füller). Das war unser Grund,
  die Fackel durch Komparator+Barrel zu ersetzen – das geht also auch 1 breit.
- Die Wiki-Seite zeigt die Aufbauten nur als Bilder; Blockpositionen kommen aus den Bildern/Videos oder aus
  herunterladbaren Schematics.

Quellen: https://minecraft.wiki/w/Tutorial:Hopper (Item_filter leitet dorthin),
https://minecraft.wiki/w/Redstone_circuits/Logic (XOR-Tabelle mit Größen),
https://minecraft.wiki/w/Tutorial:Piston_uses (kleinste Kolbentüren, z. B. 3×3 von SacredRedstone mit 56 Blöcken).

## Schritte

1. **Sortierer zuerst.** Aufbau von oh5 (bzw. dem Basic-Sortierer mit Überlaufschutz, falls oh5 im Simulator
   Fackelprobleme hat) aus Wiki-Bild/Video oder einer lizenzierten Schematic übernehmen (CLAUDE.md: echte Daten
   bevorzugen, Quelle und Lizenz notieren). Im Simulator nachbauen, dann im Spiel aufnehmen (`rsx oracle … --golden`),
   Dauerbetrieb prüfen (Kiste mit mehreren Stacks gemischt, Fackeln brennen nicht durch, kein Filter läuft leer).
   `item-sorter` und `item-sorter-4` ersetzen: Fächer im Abstand 1, Abnahme wie heute plus „vier Fächer nebeneinander
   in 4 Blöcken Breite“. Szenarien `cat-item-sorter*` neu aufnehmen.
2. **Liste der Standardbauten** anlegen (`docs/community-designs.md`): Name, Quelle, Größe/Blöcke, Java-Fassung, ob
   kachelbar, Stand bei uns. Mindestens: Itemsortierer, Kolbentüren 2×2/3×3 (flush), versteckte Tür, T-Flip-Flop,
   Monoflop/Impulsverkürzer, Blinker, XOR/XNOR, Mehrheit, Halb-/Volladdierer, Komparator-Speicher, Zähler.
3. **Vergleich mit unseren Entwürfen** (Blöcke, Volumen, Breite, Verzögerung). Wo die Community-Bauweise besser ist:
   als Vorlage bzw. Katalogeintrag übernehmen (mit Quelle im Beschreibungstext), im Spiel aufnehmen, Szenario
   ersetzen. Für Logik-Bausteine eingehen in `templates.py` (dann profitiert die Zerlegung, siehe Auftrag 12).
4. Gelernte Regeln (z. B. „1 breit kachelbar“ als Anforderung an Katalogbauten) in `knowledge/` festhalten.

## Abnahme

- Itemsortierer 1 breit kachelbar, im Spiel aufgenommen, Dauerbetrieb ohne Ausfall; Katalog und GUI zeigen ihn.
- `docs/community-designs.md` mit mindestens 10 Bauten, jede mit Quelle und Vergleich.
- Jede übernommene Bauweise im Spiel aufgenommen, beide Kerne identisch; `uv run pytest -q` grün.

## Abbruch

Lässt sich für einen Bau keine verlässliche Blockliste finden (nur Video ohne Ansicht aller Schichten): in der Liste
als „offen“ vermerken und mit dem nächsten Bau weitermachen; nicht raten.
