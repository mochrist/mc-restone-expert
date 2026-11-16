# 10 Aufräumen

Modell: Sonnet · hängt ab von: nichts · klein (unter einer halben Stunde)

## Schritte

1. Erledigter Agent-Worktree `.claude/worktrees/agent-a6b1599dfd1ca983e` (Branch
   `worktree-agent-a6b1599dfd1ca983e`, Stand 564c869, in `master` enthalten):
   - `git -C .claude/worktrees/agent-a6b1599dfd1ca983e status --short` muss leer sein; sonst aufhören und fragen.
   - `git worktree unlock …`, `git worktree remove …`, `git branch -d worktree-agent-a6b1599dfd1ca983e`
     (kleines `-d`: verweigert, falls doch nicht zusammengeführt).
2. `.cache/` (nicht im Repo): Die Ordner `bas-*`, `dec-*`, `ge-*`, `mcsrc-in*` und die `*.log` sind
   Zwischenstände vom Dekompilieren. Nur Größe auflisten (`du -sh .cache/*`) und den Nutzer fragen, ob sie weg
   können; `.cache/mcsrc`, `.cache/mc`, `.cache/gui`, `.cache/assistant-eval` bleiben.
3. `__pycache__` im Projektordner: prüfen, dass es in `.gitignore` steht.
4. `uv run python -m redstone.knowledge lint` und `uv run pytest -q` als Schlussprüfung.

## Abnahme

`git worktree list` zeigt nur noch den Hauptordner; `git status` sauber.
