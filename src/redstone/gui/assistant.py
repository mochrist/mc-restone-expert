"""Chat assistant of the GUI: plain German request -> design search, explanation, examples (Claude via the
Anthropic SDK, manual tool loop, streamed). One turn runs in its own thread; the browser polls the chat's events:
user (the user's message), status (what happens right now), job (a design search was started, follow it),
load (open this file), delta (a piece of answer text while it streams, keyed by `key`), text (a finished answer
block; replaces the deltas with the same `key`), error, cancelled. The whole event list can be fetched again
(since=0), so a reloaded page shows the chat as it was.

The API key comes from ANTHROPIC_API_KEY (environment, then the project's .env) or from KEY_FILE (written by the
GUI, never into the repository)."""

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
DELTA_EVERY = 0.2  # seconds between streamed text events (fewer, larger pieces)

NO_KEY = ("Für den Assistenten fehlt noch ein API-Schlüssel von Anthropic. Er lässt sich oben im Reiter "
          "„Assistent“ eintragen oder als ANTHROPIC_API_KEY in die Datei .env im Projektordner schreiben.")

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

Statt Hebel oder Knopf kann der Auslöser eine Druckplatte sein (Parameter input: stone_pressure_plate Steindruck-
platte, oak_pressure_plate Holzdruckplatte), aber nur bei Wünschen mit einem Impuls: monostable, pulse-extender,
t-flip-flop, rs-latch. Eine Druckplatte ist ein Taster und schaltet sich nach etwa 1 Sekunde ab; für „bleibt an,
solange ich stehe“ oder Logik mit mehreren Hebeln (a and b) geht sie nicht, dort sagst du das und bleibst beim
Hebel. Sag bei Druckplatten ehrlich, dass sie nur im Simulator geprüft ist, nicht im echten Spiel (Steinplatten
reagieren nur auf Lebewesen, Holzplatten auch auf Gegenstände).

Ein Tageslichtsensor ersetzt einen Hebel (Parameter input: daylight_detector = „an, solange es Tag ist“,
daylight_detector_inverted = „an, solange es Nacht ist“), nur bei Vorgaben mit genau einem Hebel-Eingang. Für
„Lampe geht nachts an“: inputs: [nacht], function: lampe: nacht, input: daylight_detector_inverted. Der Sensor
schaltet nicht genau bei Sonnenuntergang; nenne die Uhrzeiten aus dem Bericht. Über dem Sensor darf nichts gebaut
werden.

Fertige Bauwerke (Katalog): Kolbentür 2×2 mit Hebel, versteckte Tür 1×2 mit Holzknopf (schließt nach etwa
3 Sekunden von selbst) und ein Itemsortierer für eine Sorte. Sie lassen sich nicht mit design_circuit entwerfen;
such sie mit find_examples (z. B. „kolbentür“, „geheimtür“, „itemsortierer“) und lade sie mit load_example. Sie
sind im echten Spiel aufgenommen und im Simulator an vielen Orten und in allen Drehungen geprüft. Erkläre die
Bedienung so, wie sie in der Beschreibung steht.

Ehrlichkeit: Sag klar, was die App nicht kann (z. B. Sensoren für Spieler oder
Mobs als Auslöser, größere Kolbentüren als 2×2, Sortierer für mehrere Sorten, Zahlenanzeigen). Biete dann den nächstbesten
baubaren Ersatz an (z. B. Knopf statt Druckplatte). Behaupte nie, eine Schaltung funktioniere, wenn die Suche
gescheitert ist; die Entwürfe sind im Simulator geprüft, das darfst du sagen. Nenne Größe und Blockzahl des
Ergebnisses. Beschreibe Aufbau und Bauteile nur so, wie sie im Bericht des Werkzeugs stehen; erfinde nichts
dazu. Halte Antworten kurz (wenige Sätze oder eine kurze Liste)."""


def _actuators() -> list[str]:
    from ..design.actuators import ACTUATORS

    return list(ACTUATORS)


def _sensors() -> list[str]:
    from ..design.sensors import SENSORS

    return list(SENSORS)


def tools_schema() -> list[dict]:
    limits = {
        "output": {"type": "string", "enum": _actuators(),
                   "description": "Block statt Lampe am Ausgang (optional)"},
        "input": {"type": "string", "enum": _sensors(),
                  "description": "Druckplatte statt Hebel/Knopf (nur Impuls-Wünsche) oder Tageslichtsensor statt des einen Hebels (optional)"},
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
         "description": "Sucht fertige, meist im echten Spiel geprüfte Beispielschaltungen und Bauwerke des "
                        "Katalogs nach Stichworten (z. B. addierer, blinker, t-flip-flop, xor, kolbentür, "
                        "itemsortierer). Gibt Pfade und Beschreibungen zurück, Katalog-Bauwerke zuerst.",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "load_example",
         "description": "Lädt ein Beispiel (Pfad aus find_examples) als aktuelle Schaltung in die App.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]


# ---------------------------------------------------------------------------------------------- API key
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"  # project root, ignored by git


def _dotenv_key() -> str | None:
    """ANTHROPIC_API_KEY from the project's .env (KEY=value lines, optional quotes, # comments)."""
    try:
        lines = ENV_FILE.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, sep, value = line.partition("=")
        if sep and name.strip() == "ANTHROPIC_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            return value.strip() or None
    return None


def _file_key() -> str | None:
    if KEY_FILE.is_file():
        return KEY_FILE.read_text(encoding="utf-8").strip() or None
    return None


def key_source() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "env"
    if _dotenv_key():
        return "dotenv"
    if _file_key():
        return "file"
    return None


def api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or _dotenv_key() or _file_key()


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
        self._cancel = threading.Event()
        self._step = 0  # model calls so far (keys of streamed text blocks)

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
        self._cancel.clear()
        self.emit("user", text=text)
        if current:
            self.current = current
        threading.Thread(target=self._turn, args=(text,), daemon=True, name="rsx-chat").start()

    def cancel(self) -> bool:
        """Stop the running turn as soon as possible (a running design search keeps running in the app)."""
        with self._lock:
            if not self.busy:
                return False
        self._cancel.set()
        return True

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
        except Cancelled:
            self.emit("cancelled", text="Abgebrochen.")
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
            response = self._call(client, tools)
            self.messages.append({"role": "assistant", "content": response.content})
            for i, block in enumerate(response.content):
                if block.type == "text" and block.text.strip():
                    self.emit("text", text=block.text, key=f"{self._step}:{i}")
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
                if self._cancel.is_set():  # every tool_use still needs its result in the history
                    out, error = "Vom Nutzer abgebrochen.", True
                else:
                    try:
                        out, error = self.run_tool(use.name, dict(use.input or {})), False
                    except Cancelled:
                        out, error = "Vom Nutzer abgebrochen.", True
                    except ToolError as e:
                        out, error = str(e), True
                    except Exception as e:
                        traceback.print_exc()
                        out, error = f"Interner Fehler: {type(e).__name__}: {e}", True
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": out, "is_error": error})
            self.messages.append({"role": "user", "content": results})
            if self._cancel.is_set():
                raise Cancelled
        self.emit("error", text="Der Assistent hat zu viele Schritte gebraucht und hört hier auf.")

    def _call(self, client, tools):
        """One streamed model call; text pieces go out as delta events. A cancelled call leaves no trace in the
        history (the user's message stays; the next one follows it directly)."""
        self._step += 1
        step = self._step
        with client.beta.messages.stream(
                model=MODEL, max_tokens=64000, system=SYSTEM, tools=tools, messages=self.messages,
                output_config={"effort": "medium"}, cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA], fallbacks="default") as stream:
            pending, key, last = "", None, time.monotonic()

            def flush():
                nonlocal pending
                if pending:
                    self.emit("delta", text=pending, key=key)
                    pending = ""

            for event in stream:
                if self._cancel.is_set():
                    raise Cancelled
                if event.type == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
                    k = f"{step}:{event.index}"
                    if k != key:
                        flush()
                        key = k
                    pending += event.delta.text
                    if time.monotonic() - last > DELTA_EVERY:
                        flush()
                        last = time.monotonic()
            flush()
            if self._cancel.is_set():
                raise Cancelled
            return stream.get_final_message()

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

    def _input(self, args: dict) -> str | None:
        inp = args.get("input") or None
        if inp is not None and inp not in _sensors():
            raise ToolError("input muss einer von " + ", ".join(_sensors()) + " sein")
        return inp

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
        return self._search(self.state.resolve(rel), name, self._constraints(args), self._output(args), None, self._input(args))

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
        return self._search(path, title, self._constraints(args), self._output(args), outputs, self._input(args))

    def _search(self, path: Path, title: str, constraints, output, outputs, sensor=None) -> str:
        from .server import Job

        job = Job(path, 100, constraints, 60, outputs, 10, output, sensor)
        jid = self.state.add_job(job)
        self.emit("job", job=jid, path=self.state.rel(path), title=title)
        self.emit("status", text=f"Suche einen Bauplan für „{title}“ …")
        start = time.monotonic()
        while not job.done:
            if self._cancel.is_set():
                raise Cancelled
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
        from ..catalog import find

        words = [w for w in query.lower().replace(",", " ").split() if w]
        catalog = {e.key: rel for rel, e in self.state.catalog()}
        first = [catalog[e.key] for e in find(query) if e.key in catalog]
        hits = [(rel, desc) for rel, desc in self._examples()
                if rel in first or not words or any(w in (rel + " " + desc).lower() for w in words)]
        hits.sort(key=lambda h: first.index(h[0]) if h[0] in first else len(first))
        if not hits:
            return "Keine passenden Beispiele."
        # catalog entries with their whole description and usage (how to change the sorted item ...)
        return "\n".join(f"{rel}: {desc if rel in first else desc[:200]}" for rel, desc in hits[:15])

    def _load(self, rel: str) -> str:
        if rel not in {r for r, _ in self._examples()}:
            raise ToolError(f"Unbekanntes Beispiel {rel}; erst find_examples benutzen.")
        self.current = {"path": rel}
        self.emit("load", path=rel, group="scenarios")
        return f"{rel} ist jetzt in der App geladen."


class ToolError(Exception):
    """A tool failed for a reason the model should see (German)."""


class Cancelled(Exception):
    """The user stopped the turn."""


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
