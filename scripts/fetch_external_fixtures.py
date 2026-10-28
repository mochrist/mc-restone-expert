"""Download test schematics that may not be redistributed in this repo.

They come from https://github.com/azazo1/redstone-rs (no license file, so we only
fetch them locally). Tests that need them are skipped when the files are missing.

    uv run python scripts/fetch_external_fixtures.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/azazo1/redstone-rs/sol/assets/schematics/"
FILES = [
    # same circuit in two formats: cross-format parser test
    "piston-gate-3x3.litematic",
    "piston-gate-3x3.nbt",
    "mux3-8.litematic",
    "mux3-8.nbt",
    "tripple-piston-extender.litematic",
    "tripple-piston-extender.nbt",
    "observer-clock-100.schem",
    "seg7.litematic",
    "seg7.nbt",
]
TARGET = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "external"


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest = TARGET / name
        if dest.exists():
            print(f"exists   {name}")
            continue
        with urllib.request.urlopen(BASE + name, timeout=30) as resp:
            dest.write_bytes(resp.read())
        print(f"fetched  {name}")


if __name__ == "__main__":
    main()
