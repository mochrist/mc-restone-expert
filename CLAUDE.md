# Hinweise für Claude

## „weiter“

Schreibt der Nutzer nur „weiter“ (oder sinngemäß „mach weiter“), dann:

1. `STATUS.md` lesen (kurz) und `docs/tasks/README.md` (Regeln für alle Aufträge).
2. In der Tabelle „Aufträge“ von oben den ersten Auftrag nehmen, der dem Modell der laufenden Session
   zugeordnet ist und dessen Abhängigkeiten erledigt sind. Seine Datei in `docs/tasks/` **ganz** lesen und nur
   diesen Auftrag bearbeiten.
3. Für Aufträge, die einem anderen Modell zugeordnet sind, Agents mit diesem Modell starten
   (Agent-Tool, `model: "sonnet"` bzw. `"opus"`, `isolation: "worktree"`). Das ist hiermit erlaubt.
   Parallel nur, was laut `STATUS.md` gleichzeitig möglich ist. Der Agent bekommt als Auftrag: „Lies
   `docs/tasks/README.md` und `docs/tasks/<datei>` und arbeite den Auftrag ab.“
4. Ohne Rückfrage loslegen; nur bei echten Entscheidungen des Nutzers nachfragen.
5. Ist ein Auftrag abgenommen: Auftragsdatei löschen, Zeile in `STATUS.md` entfernen, 3–6 Zeilen oben in
   `docs/history.md`. Ist das Abbruchkriterium erreicht: Befund in den Auftrag, Zeile als „blockiert“ markieren.

Ist die Tabelle leer, `docs/backlog.md` lesen und dem Nutzer drei Vorschläge machen.

## Arbeitsweise

- Antworten auf Deutsch, Code und Commit-Nachrichten auf Englisch.
- Selbstständig arbeiten und an passenden Stellen committen.
- `STATUS.md` kurz halten (unter 150 Zeilen): Verlauf gehört nach `docs/history.md`, Einzelheiten einer Aufgabe
  in ihren Auftrag, Zurückgestelltes nach `docs/backlog.md`.
- In Git Bash für Rust zuerst `export PATH="$HOME/.cargo/bin:$PATH"`.
- Simulator-Änderungen immer in beiden Kernen (Python und Rust); im Spiel geprüfte Entwürfe nur mit Neuaufnahme ändern.
