"""Run scenarios on the Fabric oracle server (``oracle/``) and collect the traces.

The oracle mod reads ``oracle/run/rsx/in/*.scenario.json`` on server start, executes them as described in
docs/scenario-format.md and writes ``oracle/run/rsx/out/<name>.trace.json``. This module compiles the YAML
scenarios into that folder, starts the server via ``gradlew runServer`` (which also builds the mod when the
sources changed) and waits until the server stops by itself.

``dump_blocks`` instead starts the server with ``-Prsx.dumpBlocks`` to regenerate the static block state table
used by ``redstone.sim.blockdata`` (``src/redstone/sim/data/blocks_26.3.json``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from .verify.scenario import load

ROOT = Path(__file__).resolve().parents[2]
ORACLE_DIR = ROOT / "oracle"
RUN_DIR = ORACLE_DIR / "run"
IN_DIR = RUN_DIR / "rsx" / "in"
OUT_DIR = RUN_DIR / "rsx" / "out"
LOG_FILE = RUN_DIR / "rsx" / "oracle.log"
BLOCK_DATA_FILE = ROOT / "src" / "redstone" / "sim" / "data" / "blocks_26.3.json"

# Flat world without structures or mobs; never pause, never kill a slow tick, no players needed.
SERVER_PROPERTIES = {
    "level-name": "rsx-world",
    "level-type": "minecraft\\:flat",
    "generate-structures": "false",
    "spawn-monsters": "false",
    "spawn-protection": "0",
    "online-mode": "false",
    "pause-when-empty-seconds": "0",
    "max-tick-time": "-1",
    "view-distance": "3",
    "simulation-distance": "3",
    "server-port": "25599",
    "enable-query": "false",
    "enable-rcon": "false",
    "motd": "rsx oracle",
}


class OracleError(RuntimeError):
    pass


def prepare_run_dir(run_dir: Path = RUN_DIR) -> None:
    """Write eula.txt (accepted by the user for this local test server) and the required server.properties."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    props_file = run_dir / "server.properties"
    lines = props_file.read_text(encoding="utf-8").splitlines() if props_file.exists() else []
    missing = dict(SERVER_PROPERTIES)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if not line.startswith("#") and key in missing:
            line = f"{key}={missing.pop(key)}"
        out.append(line)
    out += [f"{k}={v}" for k, v in missing.items()]
    props_file.write_text("\n".join(out) + "\n", encoding="utf-8")


def _gradle_command(*extra: str) -> list[str]:
    wrapper = ORACLE_DIR / ("gradlew.bat" if os.name == "nt" else "gradlew")
    return [str(wrapper), "runServer", "-Prsx.exitWhenDone=true", *extra, "--console=plain"]


def _run_server(command: list[str], timeout: float, verbose: bool) -> None:
    """Run the gradle server command until it exits; raises OracleError on failure or timeout."""
    with LOG_FILE.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            command,
            cwd=ORACLE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        timer = threading.Timer(timeout, proc.kill)
        timer.start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                log.write(line)
                if verbose or "[rsx-oracle]" in line or "FAILED" in line or "error:" in line:
                    sys.stdout.write(line)
            proc.wait()
        except BaseException:
            proc.kill()
            raise
        finally:
            timed_out = not timer.is_alive() and proc.returncode != 0
            timer.cancel()
    if timed_out:
        raise OracleError(f"oracle server did not finish within {timeout:.0f} s, see {LOG_FILE}")
    if proc.returncode != 0:
        raise OracleError(f"oracle server exited with {proc.returncode}, see {LOG_FILE}")


def run(scenarios: list[Path], timeout: float = 900, verbose: bool = False) -> list[Path]:
    """Run the given scenario YAML files on the oracle server; returns the trace paths in the same order.

    Raises OracleError if the server fails or a scenario produced no trace. The server log is written to
    ``oracle/run/rsx/oracle.log``.
    """
    compiled = [load(p).compile() for p in scenarios]
    names = [c["name"] for c in compiled]
    if len(set(names)) != len(names):
        raise OracleError(f"duplicate scenario names: {names}")
    prepare_run_dir()
    IN_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in IN_DIR.glob("*.scenario.json"):
        stale.unlink()
    for data in compiled:
        for old in (OUT_DIR / f"{data['name']}.trace.json", OUT_DIR / f"{data['name']}.error.txt"):
            old.unlink(missing_ok=True)
        (IN_DIR / f"{data['name']}.scenario.json").write_text(json.dumps(data, indent=1), encoding="utf-8")

    _run_server(_gradle_command(), timeout, verbose)

    traces = []
    for name in names:
        trace, error = OUT_DIR / f"{name}.trace.json", OUT_DIR / f"{name}.error.txt"
        if error.exists():
            raise OracleError(f"scenario {name} failed in the oracle:\n{error.read_text(encoding='utf-8')}")
        if not trace.exists():
            raise OracleError(f"no trace for scenario {name}, see {LOG_FILE}")
        traces.append(trace)
    return traces


def dump_blocks(dst: Path = BLOCK_DATA_FILE, timeout: float = 900, verbose: bool = False) -> Path:
    """Dump every block state's static properties (see oracle BlockDump.java) to ``dst``."""
    prepare_run_dir()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    dst = dst.resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.unlink(missing_ok=True)
    _run_server(_gradle_command(f"-Prsx.dumpBlocks={tmp}"), timeout, verbose)
    if not tmp.exists():
        raise OracleError(f"oracle wrote no block dump, see {LOG_FILE}")
    tmp.replace(dst)
    return dst
