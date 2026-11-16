# 09 Assistent im Browser durchklicken

Modell: Sonnet · hängt ab von: Nutzer (Rückmeldung) · braucht den API-Schlüssel in `.env` und die Chrome-Erweiterung

## Ziel

Der Reiter „Assistent“ ist einmal vollständig im echten Browser geprüft; bisher nur per Tests
(`tests/gui/test_assistant.py`) und Skript (`scripts/assistant_eval.py`, 10 von 10).

## Schritte

`uv run rsx gui` starten (http://127.0.0.1:8737), dann der Reihe nach, je mit Screenshot:

1. Wunsch „Eine Lampe, die mit zwei Hebeln von zwei Stellen aus geschaltet wird“: Text erscheint stückweise
   (Streaming), die Suche läuft sichtbar in der Ansicht, das Ergebnis ist danach die aktuelle Schaltung.
2. Im Reiter „Ausprobieren“ beide Hebel umlegen: Lampe verhält sich wie beschrieben.
3. Neuer Wunsch mit langer Suche (4-Bit-Addierer), nach 5 s „Stopp“: Runde endet, kein halber Text bleibt
   stehen, ein weiterer Wunsch funktioniert danach.
4. Seite neu laden: der Chat ist wieder da, es startet keine neue Suche.
5. „Neue Unterhaltung“: Chat leer, alte Schaltung bleibt in der Ansicht.
6. Wunsch, der nicht geht („Itemsortierer für Diamanten“): ehrliche Absage mit Ersatzvorschlag.
7. Schlüssel fehlt (`.env` kurz umbenennen, GUI neu starten): Hinweis und Eingabefeld erscheinen; danach zurückbenennen.
8. Fenster schmal (Handybreite 390 px): Chat bleibt bedienbar.

Fehler sofort beheben, wenn es eine klare Ursache in `gui/static/` oder `gui/assistant.py` gibt (mit Test in
`tests/gui/test_assistant.py`, wo möglich); sonst als Liste an den Nutzer.

## Abnahme

Screenshots und eine kurze Liste „geht / geht nicht“ an den Nutzer; dessen Rückmeldung abwarten und daraus
neue Zeilen für `docs/backlog.md` oder einen eigenen Auftrag machen.

## Abbruch

Die Erweiterung antwortet nicht: nach drei Versuchen aufhören und den Nutzer fragen.
