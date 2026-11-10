# Hinweise für Claude

## „weiter“

Schreibt der Nutzer nur „weiter“ (oder sinngemäß „mach weiter“), dann:

1. `STATUS.md` lesen. Gibt es dort einen Abschnitt „Übergabe“, gilt er zuerst, samt Aufgabenverteilung.
2. Die Aufgaben, die dem Modell der laufenden Session zugeordnet sind, selbst übernehmen.
3. Für Aufgaben, die einem anderen Modell zugeordnet sind, Agents mit diesem Modell starten
   (Agent-Tool, `model: "sonnet"` bzw. `"opus"`, `isolation: "worktree"`). Das ist hiermit erlaubt.
   Parallel starten, was laut Tabelle nicht voneinander abhängt.
4. Ohne Rückfrage loslegen; nur bei echten Entscheidungen des Nutzers nachfragen.

Steht in `STATUS.md` keine Übergabe, den ersten Punkt unter „Offene Punkte“ angehen.

## Arbeitsweise

- Antworten auf Deutsch, Code und Commit-Nachrichten auf Englisch.
- Selbstständig arbeiten und an passenden Stellen committen.
- `STATUS.md` am Ende einer Session aktualisieren; erledigte Übergabe-Abschnitte entfernen.
- In Git Bash für Rust zuerst `export PATH="$HOME/.cargo/bin:$PATH"`.
