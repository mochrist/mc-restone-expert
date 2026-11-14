"""Local HTTP server of the GUI (docs/gui-api.md): static files plus a JSON API for models, simulations and
design searches. Standard library only; listens on 127.0.0.1.

Rust worlds may only be used from the thread that created them, so every simulation owns one worker thread."""

from __future__ import annotations

import itertools
import socket
import sys
import json
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..model import Grid, Pos
from . import model as gmodel

ROOT = Path(__file__).resolve().parents[3]  # the repository (src/redstone/gui/server.py)
STATIC = Path(__file__).resolve().parent / "static"
SCHEMATIC_SUFFIXES = (".litematic", ".schem", ".nbt")
DEFAULT_PORT = 8737  # unusual on purpose: other local apps (and their service workers) like 8765/8000/8080
MAX_FRAMES = 3000
MAX_TICKS = 1000
MAX_SIMS = 16
MAX_JOBS = 8
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml",
                 ".png": "image/png", ".ico": "image/x-icon"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------------------------- simulation
class Simulation:
    """A world in the simulator at the oracle position; `changed` lists the blocks that differ from the last
    answer. The box of the model is watched (blocks can appear where air was, e.g. piston heads)."""

    MAX_WATCHED = 200_000

    def __init__(self, grid: Grid) -> None:
        self.grid = grid
        self.tick = 0
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._pool.submit(self._setup).result()

    def _setup(self) -> None:
        from ..sim import blocks  # noqa: F401  (registers block behaviours)
        from ..sim.core import World
        from ..sim.runner import ORACLE_ORIGIN

        self.origin = ORACLE_ORIGIN
        self.world = World()
        self.world.place_grid(self.grid, self.origin)
        sx, sy, sz = self.grid.size
        if sx * sy * sz <= self.MAX_WATCHED:
            self.watched = [Pos(x, y, z) for y in range(sy) for x in range(sx) for z in range(sz)]
        else:
            self.watched = sorted(p for p, _ in self.grid.items())
        self.last = self._states()

    def _states(self) -> list[str]:
        from ..sim.runner import probe_value

        absolute = [p + self.origin for p in self.watched]
        many = getattr(self.world, "probe_values", None)
        values = many(absolute) if many is not None else [probe_value(self.world, p) for p in absolute]
        return [gmodel.state_str(v) for v in values]

    def _changed(self) -> list[dict]:
        now = self._states()
        out = [{"p": list(p), "s": s} for p, s, old in zip(self.watched, now, self.last) if s != old]
        self.last = now
        return out

    def _use(self, p: Pos) -> dict:
        from ..analysis.ports import input_kind
        from ..sim.runner import apply_input

        if not self.grid.in_bounds(p):
            raise ApiError(f"Position {list(p)} liegt außerhalb der Schaltung")
        state = self.world.get(p + self.origin)
        kind = input_kind(state)
        if kind is None:
            raise ApiError(f"{gmodel.state_str(state)} bei {list(p)} lässt sich nicht bedienen")
        apply_input(self.world, "step" if kind == "plate" else "use", p + self.origin, None)
        return {"tick": self.tick, "changed": self._changed()}

    def _ticks(self, n: int) -> dict:
        for _ in range(n):
            self.world.tick()
            self.tick += 1
        return {"tick": self.tick, "changed": self._changed()}

    def use(self, p: Pos) -> dict:
        return self._pool.submit(self._use, p).result()

    def ticks(self, n: int) -> dict:
        return self._pool.submit(self._ticks, n).result()

    def _drop(self) -> None:
        self.world = None  # the Rust world must be freed on its own thread

    def close(self) -> None:
        self._pool.submit(self._drop)
        self._pool.shutdown(wait=True)


# ---------------------------------------------------------------------------------------------- design search
class Job:
    """A design search (`rsx redesign`) in its own thread; frames come from `design.observe`."""

    def __init__(self, path: Path, compact: int) -> None:
        self.path = path
        self.compact = compact
        self.frames: list[dict] = []
        self.log: list[str] = []
        self.done = False
        self.error: str | None = None
        self.result: dict | None = None
        self.grid: Grid | None = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"rsx-job-{path.stem}")
        self._thread.start()

    def _frame(self, cand, phase: str, label: str, accepted: bool) -> None:
        with self._lock:
            if len(self.frames) >= MAX_FRAMES and not accepted:
                return
            self.frames.append({"i": len(self.frames), "phase": phase, "label": label, "accepted": bool(accepted),
                                "size": list(cand.grid.size), "blocks": gmodel.blocks(cand.grid)})

    def _run(self) -> None:
        from ..cli import RedesignInputError, run_redesign
        from ..design import observe

        try:
            with observe.observing(self._frame):
                best, text, spec = run_redesign(self.path, compact=self.compact, steps=self.log)
            result = gmodel.of_candidate(best, spec) if best is not None else {}
            result["summary"] = text
            with self._lock:
                self.grid = best.grid if best is not None else None
                self.result = result
                if best is None:
                    self.error = "Kein funktionierender Entwurf gefunden (Bericht unter „summary“)."
        except RedesignInputError as e:
            self.error = str(e)
        except Exception as e:  # report to the GUI instead of losing the thread
            traceback.print_exc()
            self.error = f"Fehler in der Entwurfssuche: {type(e).__name__}: {e}"
        finally:
            self.done = True

    def snapshot(self, since: int) -> dict:
        with self._lock:
            return {"done": self.done, "error": self.error, "frames": self.frames[max(since, 0):],
                    "log": list(self.log), "result": self.result if self.done else None}


# ---------------------------------------------------------------------------------------------- server state
class State:
    def __init__(self, root: Path = ROOT, extra: Path | None = None) -> None:
        self.root = root.resolve()
        self.extra = extra.resolve() if extra is not None else None
        self.sims: dict[str, Simulation] = {}
        self.jobs: dict[str, Job] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def resolve(self, rel: str) -> Path:
        """A path from the client: relative to the repository (or the file given on the command line)."""
        if not rel:
            raise ApiError("Pfad fehlt")
        p = Path(rel)
        full = (p if p.is_absolute() else self.root / p).resolve()
        if full != self.extra and not full.is_relative_to(self.root):
            raise ApiError(f"Pfad außerhalb des Projekts: {rel}", HTTPStatus.FORBIDDEN)
        if not full.is_file():
            raise ApiError(f"Datei nicht gefunden: {rel}", HTTPStatus.NOT_FOUND)
        return full

    def rel(self, p: Path) -> str:
        try:
            return p.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    def files(self) -> dict:
        def listed(paths) -> list[str]:
            return sorted({self.rel(p) for p in paths if ".cache" not in p.parts and ".venv" not in p.parts})

        schematics = [p for s in SCHEMATIC_SUFFIXES for d in ("examples", "tests/fixtures", "out")
                      for p in (self.root / d).rglob(f"*{s}")]
        specs = list((self.root / "examples").rglob("*.yaml"))
        out = {"schematics": listed(schematics), "scenarios": listed((self.root / "scenarios").glob("*.yaml")),
               "specs": listed(specs)}
        if self.extra is not None:
            key = "schematics" if self.extra.suffix in SCHEMATIC_SUFFIXES else "scenarios"
            out[key].insert(0, self.rel(self.extra))
        return out

    def new_id(self) -> str:
        return str(next(self._ids))

    def add_sim(self, sim: Simulation) -> str:
        with self._lock:
            while len(self.sims) >= MAX_SIMS:  # drop the oldest
                self.sims.pop(next(iter(self.sims))).close()
            sid = self.new_id()
            self.sims[sid] = sim
            return sid

    def add_job(self, job: Job) -> str:
        with self._lock:
            for k in [k for k, j in self.jobs.items() if j.done][: max(0, len(self.jobs) - MAX_JOBS + 1)]:
                del self.jobs[k]
            jid = self.new_id()
            self.jobs[jid] = job
            return jid


def _pos(value) -> Pos:
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) for v in value)):
        raise ApiError("Position muss [x, y, z] mit ganzen Zahlen sein")
    return Pos(*value)


def make_handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "rsx-gui"
        app_state = state

        def log_message(self, fmt: str, *args) -> None:  # quiet; errors still go to stderr
            pass

        # -------------------------------------------------------------- plumbing
        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n == 0:
                return {}
            try:
                data = json.loads(self.rfile.read(n).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ApiError("Anfrage ist kein gültiges JSON") from None
            if not isinstance(data, dict):
                raise ApiError("Anfrage muss ein JSON-Objekt sein")
            return data

        def _handle(self, method: str) -> None:
            url = urlparse(self.path)
            try:
                if method == "GET" and not url.path.startswith("/api/"):
                    return self._static(url.path)
                self._json(self._api(method, url.path, parse_qs(url.query)))
            except ApiError as e:
                self._json({"error": str(e)}, e.status)
            except Exception as e:
                traceback.print_exc()
                self._json({"error": f"Interner Fehler: {type(e).__name__}: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def _static(self, path: str) -> None:
            rel = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/").lstrip("/")
            full = (STATIC / rel).resolve()
            if not full.is_relative_to(STATIC) or not full.is_file():
                return self._json({"error": f"Nicht gefunden: {path}"}, HTTPStatus.NOT_FOUND)
            self._send(HTTPStatus.OK, full.read_bytes(), CONTENT_TYPES.get(full.suffix, "application/octet-stream"))

        # -------------------------------------------------------------- API
        def _api(self, method: str, path: str, query: dict) -> dict:
            parts = path.strip("/").split("/")[1:]  # without "api"
            if method == "GET" and parts == ["files"]:
                return state.files()
            if method == "GET" and parts == ["model"]:
                full = state.resolve((query.get("path") or [""])[0])
                try:
                    return gmodel.load(full)[1]
                except (ValueError, KeyError) as e:
                    raise ApiError(f"{full.name} lässt sich nicht laden: {e}") from e
            if method == "POST" and parts == ["sim"]:
                return self._new_sim(self._body())
            if method == "POST" and len(parts) == 3 and parts[0] == "sim":
                sim = state.sims.get(parts[1])
                if sim is None:
                    raise ApiError("Simulation unbekannt (abgelaufen?)", HTTPStatus.NOT_FOUND)
                body = self._body()
                if parts[2] == "use":
                    return sim.use(_pos(body.get("p")))
                if parts[2] == "tick":
                    n = body.get("n", 1)
                    if not isinstance(n, int) or not 1 <= n <= MAX_TICKS:
                        raise ApiError(f"n muss eine ganze Zahl von 1 bis {MAX_TICKS} sein")
                    return sim.ticks(n)
            if method == "POST" and parts == ["redesign"]:
                body = self._body()
                full = state.resolve(body.get("path", ""))
                compact = body.get("compact", 100)
                if not isinstance(compact, int) or compact < 0:
                    raise ApiError("compact muss eine ganze Zahl ≥ 0 sein")
                return {"job": state.add_job(Job(full, compact))}
            if method == "GET" and len(parts) == 2 and parts[0] == "job":
                job = state.jobs.get(parts[1])
                if job is None:
                    raise ApiError("Suche unbekannt", HTTPStatus.NOT_FOUND)
                try:
                    since = int((query.get("since") or ["0"])[0])
                except ValueError:
                    raise ApiError("since muss eine ganze Zahl sein") from None
                return job.snapshot(since)
            raise ApiError(f"Unbekannter Endpunkt: {method} {path}", HTTPStatus.NOT_FOUND)

        def _new_sim(self, body: dict) -> dict:
            if "job" in body:
                job = state.jobs.get(str(body["job"]))
                if job is None or not job.done or job.grid is None:
                    raise ApiError("Die Suche ist unbekannt, läuft noch oder hat keinen Entwurf")
                grid, model = job.grid, {k: v for k, v in job.result.items() if k != "summary"}
            else:
                full = state.resolve(body.get("path", ""))
                try:
                    grid, model = gmodel.load(full)
                except (ValueError, KeyError) as e:
                    raise ApiError(f"{full.name} lässt sich nicht laden: {e}") from e
            sid = state.add_sim(Simulation(grid))
            return {"sim": sid, "tick": 0, "model": model}

    return Handler


class _Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind a busy port silently (requests then go to either);
    # claim the port exclusively there instead, so a busy port fails at startup.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(port: int = DEFAULT_PORT, extra: Path | None = None, root: Path = ROOT) -> ThreadingHTTPServer:
    server = _Server(("127.0.0.1", port), make_handler(State(root, extra)))
    server.daemon_threads = True
    return server


def serve(port: int = DEFAULT_PORT, file: str | None = None, open_browser: bool = True) -> None:
    from urllib.parse import quote

    extra = Path(file) if file else None
    try:
        server = make_server(port, extra)
    except OSError as e:
        raise SystemExit(f"Port {port} ist belegt ({e.strerror}); läuft die GUI schon? Sonst: rsx gui --port N") from None
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if extra is not None:
        url += f"?path={quote(State(ROOT, extra).rel(extra))}"
    print(f"GUI läuft auf {url} (Strg+C beendet)")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state = server.RequestHandlerClass.app_state
        for sim in list(state.sims.values()):
            sim.close()
