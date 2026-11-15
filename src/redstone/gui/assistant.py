"""Chat assistant of the GUI: plain German request -> design search, explanation, examples (Claude via the
Anthropic SDK, manual tool loop). One turn runs in its own thread; the browser polls the chat's events:
status (what happens right now), job (a design search was started, follow it), load (open this file),
text (answer of the assistant), error.

The API key comes from ANTHROPIC_API_KEY or from KEY_FILE (written by the GUI, never into the repository)."""

from __future__ import annotations

import os
import threading
import time
import traceback
from pathlib import Path

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
KEY_FILE = Path.home() / ".rsx" / "anthropic_api_key"
MAX_STEPS = 12  # model calls per turn
JOB_WAIT = 900  # seconds a design search may take inside a turn
MAX_RESULT = 6000  # characters of a report handed back to the model

NO_KEY = ("Für den Assistenten fehlt noch ein API-Schlüssel von Anthropic. Er lässt sich oben im Reiter "
          "„Assistent“ eintragen oder als Umgebungsvariable ANTHROPIC_API_KEY setzen.")

SYSTEM = """Du bist der Assistent der „Redstone-Werkstatt“, einer Desktop-App für Minecraft Java 26.3. Die Nutzer sind
Laien: Sie wissen, was sie in ihrer Welt haben möchten, kennen aber kaum Redstone-Begriffe. Antworte immer auf
Deutsch, kurz, freundlich und in Alltagssprache. Fachwörter (Komparator, Verstärker, Flip-Flop …) nur, wenn nötig,
und dann kurz erklärt. Frag nicht nach Dingen, die du sinnvoll selbst festlegen kannst; frag nur, wenn eine
Entscheidung wirklich beim Nutzer liegt.

Du hast Werkzeuge: Entwurf suchen (design_circuit), die aktuelle Schaltung untersuchen (explain_circuit), die
aktuelle Schaltung verkleinern (shrink_circuit), Beispiele suchen und laden (find_examples, load_example). Was
du entwirfst oder lädst, erscheint sofort in der Ansicht der App und ist dann die „aktuelle Schaltung“; der
Nutzer kann sie dort ausprobieren und nachbauen (Material, Bauanleitung). Erkläre am Ende, wie man sie bedient
(welcher Hebel/Knopf was tut) und was herauskommt.

Vorgabe für design_circuit (YAML), nur diese Formen:
1. Logik mit Hebeln (bis 8 Eingänge, Namen frei, kurz und klein geschrieben):
   inputs: [a, b, c]
   function:
     tuer: (a and not b) or c        # Operatoren: and, or, not, ^ (xor), !=, Klammern
   Mehrere Ausgänge = mehrere Zeilen unter function. Alternativ table: mit Bitmustern (outputs: [...],
   table: {"101": "1"}, others: dont_care).
2. Zeitverhalten (ein Eingang):
   behaviour: monostable, length: L, optional kind: button   # Druck -> Impuls fester Länge
   behaviour: pulse-extender, length: L                       # bleibt mindestens L an
   behaviour: t-flip-flop, optional kind: button              # jeder Druck schaltet um
   behaviour: rs-latch                                         # Knopf „set“ an, Knopf „reset“ aus
   behaviour: clock, period: P, on_ticks: O                   # Blinker, läuft von selbst
   behaviour: delay, delay: D                                 # Verzögerung
   Vor monostable, pulse-extender und t-flip-flop darf Logik stehen: inputs: [a, b] plus gate: a and b.
Zeiten in Gameticks (20 Ticks = 1 Sekunde). Nur diese Werte sind baubar:
   monostable length: 2, 4, 6, 8, 12, 16, 20, 30, 40
   pulse-extender length: 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 26, 30, 34, 40, 42, 50
   clock (period/on_ticks): 6/2, 8/2, 10/4, 12/6, 16/4, 16/8, 20/10, 24/6, 32/8, 36/18
   delay: gerade Zahlen 2 … 16
Wähle den nächstliegenden baubaren Wert und sag, wenn er vom Wunsch abweicht. Statt einer Lampe kann am Ausgang
stehen (Parameter output): iron_door (Eisentür), iron_trapdoor (Eisenfalltür), piston, sticky_piston (Kolben nach
oben), note_block (Notenblock, Ton), dispenser (Spender), dropper (Werfer).

Ehrlichkeit: Sag klar, was die App nicht kann (z. B. Druckplatten, Tageslichtsensoren, Sensoren für Spieler oder
Mobs als Auslöser, Kolbentüren aus vielen Kolben, Itemsortierer, Zahlenanzeigen). Biete dann den nächstbesten
baubaren Ersatz an (z. B. Knopf statt Druckplatte). Behaupte nie, eine Schaltung funktioniere, wenn die Suche
gescheitert ist; die Entwürfe sind im Simulator geprüft, das darfst du sagen. Nenne Größe und Blockzahl des
Ergebnisses. Halte Antworten kurz (wenige Sätze oder eine kurze Liste)."""


def _actuators() -> list[str]:
    from ..design.actuators import ACTUATORS

    return list(ACTUATORS)


def tools_schema() -> list[dict]:
    limits = {
        "output": {"type": "string", "enum": _actuators(),
                   "description": "Block statt Lampe am Ausgang (optional)"},
        "max_size": {"type": "string", "description": "Höchstmaße X,Y,Z (optional), z. B. 9,5,9"},
        "forbid": {"type": "array", "items": {"type": "string"},
                   "description": "Block-IDs, die nicht vorkommen dürfen (optional), z. B. piston"},
    }
    return [
        {"name": "design_circuit",
         "description": "Sucht einen im Simulator geprüften Bauplan für eine Vorgabe (YAML wie im Systemprompt) "
                        "und zeigt ihn in der App. Dauert Sekunden bis Minuten. Gibt Größe, Blockzahl, Material "
                        "und den (fachsprachlichen) Bericht zurück oder den Grund, warum nichts gefunden wurde.",
         "input_schema": {"type": "object", "properties": {
             "name": {"type": "string", "description": "kurzer Dateiname ohne Endung, z. B. codeschloss"},
             "spec_yaml": {"type": "string", "description": "die Vorgabe als YAML"}, **limits},
             "required": ["name", "spec_yaml"]}},
        {"name": "explain_circuit",
         "description": "Untersucht die aktuelle Schaltung der App im Simulator (Eingänge, Ausgänge, "
                        "Wahrheitstabelle, Zeitverhalten) und gibt den Bericht zurück.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "shrink_circuit",
         "description": "Sucht eine kleinere Schaltung mit demselben Verhalten wie die aktuelle und zeigt sie.",
         "input_schema": {"type": "object", "properties": {
             "outputs": {"type": "string", "description": "nur diese Ausgänge erhalten (optional), z. B. out1,out3"},
             **limits}}},
        {"name": "find_examples",
         "description": "Sucht fertige, meist im echten Spiel geprüfte Beispielschaltungen nach Stichworten "
                        "(z. B. addierer, blinker, t-flip-flop, xor). Gibt Pfade und Beschreibungen zurück.",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "load_example",
         "description": "Lädt ein Beispiel (Pfad aus find_examples) als aktuelle Schaltung in die App.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]


# ---------------------------------------------------------------------------------------------- API key
def key_source() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "env"
    if KEY_FILE.is_file() and KEY_FILE.read_text(encoding="utf-8").strip():
        return "file"
    return None


def api_key() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if KEY_FILE.is_file():
        return KEY_FILE.read_text(encoding="utf-8").strip() or None
    return None


def save_key(key: str) -> None:
    """Store the key in the user's home (empty: remove it)."""
    key = key.strip()
    if not key:
        KEY_FILE.unlink(missing_ok=True)
        return
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key, encoding="utf-8")
    try:
        KEY_FILE.chmod(0o600)
    except OSError:
        pass


def default_client():
    """Anthropic client, or None without a key."""
    key = api_key()
    if not key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=key)


# ---------------------------------------------------------------------------------------------- chat
class Chat:
    """One conversation. `state` is the server's State (files, jobs); `client_factory()` returns an Anthropic
    client or None."""

    def __init__(self, state, client_factory) -> None:
        self.state = state
        self.client_factory = client_factory
        self.messages: list[dict] = []
        self.events: list[dict] = []
        self.busy = False
        self.current: dict | None = None  # {"path": P} or {"job": id}
        self._lock = threading.Lock()

    # -- events
    def emit(self, kind: str, **data) -> None:
        with self._lock:
            self.events.append({"i": len(self.events), "type": kind, **data})

    def snapshot(self, since: int) -> dict:
        with self._lock:
            return {"busy": self.busy, "events": self.events[max(since, 0):]}

    # -- turns
    def start(self, text: str, current: dict | None) -> None:
        with self._lock:
            if self.busy:
                raise RuntimeError("Der Assistent antwortet noch.")
            self.busy = True
        if current:
            self.current = current
        threading.Thread(target=self._turn, args=(text,), daemon=True, name="rsx-chat").start()

    def _context(self) -> str:
        if not self.current:
            return "(In der App ist gerade keine Schaltung geladen.)"
        if self.current.get("job"):
            job = self.state.jobs.get(str(self.current["job"]))
            return f"(Aktuelle Schaltung in der App: Entwurf „{job.title if job else '?'}“ aus einer Suche.)"
        return f"(Aktuelle Schaltung in der App: {self.current.get('path')}.)"

    def _turn(self, text: str) -> None:
        try:
            self.run_turn(text)
        except Exception as e:  # never lose the thread silently
            traceback.print_exc()
            self.emit("error", text=_api_error(e))
        finally:
            with self._lock:
                self.busy = False

    def run_turn(self, text: str) -> None:
        client = self.client_factory()
        if client is None:
            self.emit("error", text=NO_KEY)
            return
        self.messages.append({"role": "user", "content": [{"type": "text", "text": self._context()},
                                                          {"type": "text", "text": text}]})
        tools = tools_schema()
        for _ in range(MAX_STEPS):
            self.emit("status", text="Der Assistent denkt nach …")
            response = client.beta.messages.create(
                model=MODEL, max_tokens=16000, system=SYSTEM, tools=tools, messages=self.messages,
                output_config={"effort": "medium"}, cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA], fallbacks="default")
            self.messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    self.emit("text", text=block.text)
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason == "refusal":
                self.emit("error", text="Dazu kann der Assistent leider nichts sagen. Bitte anders formulieren.")
                return
            if response.stop_reason == "max_tokens":
                self.emit("error", text="Die Antwort wurde zu lang und ist abgeschnitten.")
                return
            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                return
            results = []
            for use in uses:
                try:
                    out, error = self.run_tool(use.name, dict(use.input or {})), False
                except ToolError as e:
                    out, error = str(e), True
                except Exception as e:
                    traceback.print_exc()
                    out, error = f"Interner Fehler: {type(e).__name__}: {e}", True
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": out, "is_error": error})
            self.messages.append({"role": "user", "content": results})
        self.emit("error", text="Der Assistent hat zu viele Schritte gebraucht und hört hier auf.")

    # -- tools
    def run_tool(self, name: str, args: dict) -> str:
        if name == "design_circuit":
            return self._design(args)
        if name == "explain_circuit":
            return self._explain()
        if name == "shrink_circuit":
            return self._shrink(args)
        if name == "find_examples":
            return self._find(str(args.get("query", "")))
        if name == "load_example":
            return self._load(str(args.get("path", "")))
        raise ToolError(f"Unbekanntes Werkzeug {name}")

    def _constraints(self, args: dict):
        from .server import ApiError, _constraints

        try:
            return _constraints({"max_size": args.get("max_size"), "forbid": args.get("forbid")})
        except ApiError as e:
            raise ToolError(str(e)) from e

    def _output(self, args: dict) -> str | None:
        out = args.get("output") or None
        if out is not None and out not in _actuators():
            raise ToolError("output muss einer von " + ", ".join(_actuators()) + " sein")
        return out

    def _design(self, args: dict) -> str:
        from .server import ApiError

        text, name = str(args.get("spec_yaml") or ""), str(args.get("name") or "wunsch")
        if not text.strip():
            raise ToolError("spec_yaml ist leer")
        try:
            rel, group = self.state.store("specs", Path(name).stem + ".yaml", text.encode("utf-8"))
        except ApiError as e:
            raise ToolError(f"Vorgabe ungültig: {e}") from e
        if group != "specs":
            raise ToolError("Das ist keine Vorgabe (kein Abschnitt build erlaubt)")
        return self._search(self.state.resolve(rel), name, self._constraints(args), self._output(args), None)

    def _shrink(self, args: dict) -> str:
        if not self.current:
            raise ToolError("In der App ist keine Schaltung geladen.")
        grid, title, path = self.state.source(self.current)
        if path is None:  # result of a search: give it a file
            from .. import io
            from . import tools

            path = self.state.work / "assistant" / f"{tools.safe_name(title)}.litematic"
            path.parent.mkdir(parents=True, exist_ok=True)
            io.save(grid, path)
        outputs = args.get("outputs") or None
        return self._search(path, title, self._constraints(args), self._output(args), outputs)

    def _search(self, path: Path, title: str, constraints, output, outputs) -> str:
        from .server import Job

        job = Job(path, 100, constraints, 60, outputs, 10, output)
        jid = self.state.add_job(job)
        self.emit("job", job=jid, path=self.state.rel(path), title=title)
        self.emit("status", text=f"Suche einen Bauplan für „{title}“ …")
        start = time.monotonic()
        while not job.done:
            if time.monotonic() - start > JOB_WAIT:
                raise ToolError("Die Suche dauert zu lange; sie läuft in der App weiter.")
            time.sleep(0.5)
        if job.grid is not None:
            self.current = {"job": jid}
        r = job.result or {}
        lines = [f"Fehler: {job.error}"] if job.error else []
        if r.get("blocks"):
            lines.append(f"Gefunden: {'×'.join(map(str, r['size']))} (x×y×z), {len(r['blocks'])} Blöcke. "
                         f"Eingänge: {', '.join(i['name'] for i in r.get('inputs', []))}; "
                         f"Ausgänge: {', '.join(o['name'] for o in r.get('outputs', []))}.")
            lines.append("Material: " + ", ".join(f"{m['count']}× {m['label']}" for m in r.get("materials", [])[:12]))
        if r.get("summary"):
            lines.append("Bericht:\n" + r["summary"][:MAX_RESULT])
        return "\n".join(lines) or "Keine Rückmeldung der Suche."

    def _explain(self) -> str:
        from . import tools

        if not self.current:
            raise ToolError("In der App ist keine Schaltung geladen.")
        self.emit("status", text="Untersuche die Schaltung …")
        grid, title, _ = self.state.source(self.current)
        try:
            return tools.explain(grid, title)["markdown"][:MAX_RESULT]
        except ValueError as e:
            raise ToolError(f"Analyse nicht möglich: {e}") from e

    def _examples(self) -> list[tuple[str, str]]:
        import yaml

        cache = getattr(self.state, "_example_index", None)
        if cache is None:
            cache = []
            for rel in self.state.files()["scenarios"]:
                try:
                    raw = yaml.safe_load((self.state.root / rel).read_text(encoding="utf-8"))
                    desc = str(raw.get("description") or "") if isinstance(raw, dict) else ""
                except Exception:
                    desc = ""
                cache.append((rel, desc))
            self.state._example_index = cache
        return cache

    def _find(self, query: str) -> str:
        words = [w for w in query.lower().replace(",", " ").split() if w]
        hits = [(rel, desc) for rel, desc in self._examples()
                if not words or any(w in (rel + " " + desc).lower() for w in words)]
        if not hits:
            return "Keine passenden Beispiele."
        return "\n".join(f"{rel}: {desc[:200]}" for rel, desc in hits[:15])

    def _load(self, rel: str) -> str:
        if rel not in {r for r, _ in self._examples()}:
            raise ToolError(f"Unbekanntes Beispiel {rel}; erst find_examples benutzen.")
        self.current = {"path": rel}
        self.emit("load", path=rel, group="scenarios")
        return f"{rel} ist jetzt in der App geladen."


class ToolError(Exception):
    """A tool failed for a reason the model should see (German)."""


def _api_error(e: Exception) -> str:
    try:
        import anthropic
    except ImportError:
        return f"Fehler im Assistenten: {e}"
    if isinstance(e, anthropic.AuthenticationError):
        return "Der API-Schlüssel wird nicht angenommen. Bitte im Reiter „Assistent“ einen gültigen eintragen."
    if isinstance(e, anthropic.RateLimitError):
        return "Zu viele Anfragen an den Assistenten. Bitte kurz warten und nochmal versuchen."
    if isinstance(e, anthropic.APIConnectionError):
        return "Der Assistent ist nicht erreichbar (keine Internetverbindung?)."
    if isinstance(e, anthropic.APIStatusError):
        return f"Der Assistent meldet einen Fehler ({e.status_code}): {e.message}"
    return f"Fehler im Assistenten: {type(e).__name__}: {e}"
