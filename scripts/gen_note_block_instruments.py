"""Add the note block ``instrument`` of every block to src/redstone/sim/data/blocks_26.3.json.

The oracle mod's BlockDump.java dumps ``BlockState#instrument()`` itself (key ``instrument``); this script
derives the same values from the decompiled 26.3 ``Blocks.java`` so the table can be updated without running
the game. Usage:  uv run python scripts/gen_note_block_instruments.py [path/to/Blocks.java] [--check]

Rules (BlockBehaviour.Properties): the default is HARP; ``.instrument(X)`` sets it; ``ofFullCopy(B)`` /
``ofLegacyCopy(B)`` copy it from block B (an explicit ``.instrument`` later in the chain wins);
``wallVariant(...)`` starts from ``Properties.of()`` and therefore gives HARP; the helpers logProperties and
netherStemProperties set BASS; registerStair/Slab/Wall(id, base) copy from base.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "redstone" / "sim" / "data" / "blocks_26.3.json"
DEFAULT_SRC = Path("C:/Users/Moritz/Documents/dev/minecraft-redstone-expert/.cache/mcsrc/"
                   "net/minecraft/world/level/block/Blocks.java")

HELPER_BASS = ("logProperties(", "netherStemProperties(")
BASE_HELPERS = re.compile(r"register(?:Legacy)?(?:Stair|Slab|Wall)\(\s*\w+(?:\.\w+)*\s*,\s*(\w+)")
COPY = re.compile(r"of(?:Full|Legacy)Copy\((\w+)")
INSTR = re.compile(r"\.instrument\(NoteBlockInstrument\.(\w+)\)")
SWITCH_INSTR = re.compile(r"\.instrument\(switch")
CASE = re.compile(r"case (\w+) -> NoteBlockInstrument\.(\w+)")
REGISTER_ID = re.compile(r"^\s*register\(\s*BlockIds\.(\w+)")
FIELD = re.compile(r"^   public static final (Block|ColorCollection<Block>|WeatheringCopperCollection<Block>) (\w+) = ",
                   re.M)
END = re.compile(r"^   (?:public|private) static|^   static ", re.M)
COLORS = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan",
          "purple", "blue", "brown", "green", "red", "black")
STAGES = ("unaffected", "exposed", "weathered", "oxidized")


def statements(src: str) -> dict[str, tuple[str, str]]:
    """field name -> (kind, source text of its initializer)."""
    out = {}
    for m in FIELD.finditer(src):
        nxt = END.search(src, m.end())
        out[m.group(2)] = (m.group(1), src[m.end():nxt.start() if nxt else len(src)])
    return out


def resolve(stmts: dict[str, tuple[str, str]]) -> dict[str, dict[str, str]]:
    """field name -> {stage or '': instrument}; plain blocks and color collections only use the '' key."""
    cache: dict[str, dict[str, str]] = {}

    def inst(name: str) -> dict[str, str]:
        if name in cache:
            return cache[name]
        kind, text = stmts[name]
        stages = STAGES if kind.startswith("Weathering") else ("",)
        result = dict.fromkeys(stages, "HARP")
        base = BASE_HELPERS.search(text) or COPY.search(text)
        if base:
            src = inst(base.group(1))
            # a weathering collection copies stage by stage; everything else has a single value
            result = dict(src) if len(src) > 1 else dict.fromkeys(stages, next(iter(src.values())))
        if any(h in text for h in HELPER_BASS):
            result = dict.fromkeys(stages, "BASS")
        if SWITCH_INSTR.search(text):
            result = {st.lower(): inst_name for st, inst_name in ((c[0].lower(), c[1]) for c in CASE.findall(text))}
        else:
            found = INSTR.findall(text)
            if found:
                result = dict.fromkeys(stages, found[-1])
        cache[name] = result
        return result

    return {n: inst(n) for n in stmts}


def block_names(stmts: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """block id -> (field name, stage) for every block the fields register."""
    out: dict[str, tuple[str, str]] = {}
    for name, (kind, text) in stmts.items():
        key = name.lower()
        if kind == "Block":
            # the field name differs from the id in a few cases (POTTED_AZALEA -> potted_azalea_bush)
            reg = REGISTER_ID.search(text)
            out[f"minecraft:{(reg.group(1) if reg else name).lower()}"] = (name, "")
        elif kind.startswith("Color"):
            for color in COLORS:
                out[f"minecraft:{color}_{key.removeprefix('dyed_')}"] = (name, "")
        else:
            for stage in STAGES:
                if key == "copper_block":
                    base = "copper_block" if stage == "unaffected" else f"{stage}_copper"
                else:
                    base = key if stage == "unaffected" else f"{stage}_{key}"
                out[f"minecraft:{base}"] = (name, stage)
                out[f"minecraft:waxed_{base}"] = (name, stage)
    return out


def _instrument_of(resolved: dict[str, dict[str, str]], key: tuple[str, str]) -> str:
    field, stage = key
    per_stage = resolved[field]
    return (per_stage[stage] if stage in per_stage else per_stage[""]).lower()


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = Path(args[0]) if args else DEFAULT_SRC
    stmts = statements(src.read_text(encoding="utf-8"))
    resolved, names = resolve(stmts), block_names(stmts)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    blocks = data["blocks"]
    missing = [b for b in blocks if b not in names]
    if missing:
        raise SystemExit(f"blocks without a Blocks.java field: {missing[:10]} ({len(missing)})")
    for name, entry in blocks.items():
        entry["v"]["instrument"] = _instrument_of(resolved, names[name])
    if "instrument" not in data["keys"]:
        data["keys"].append("instrument")
    if "--check" in sys.argv:
        for k, v in blocks.items():
            print(k, v["v"]["instrument"])
        return
    DATA.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"wrote instruments for {len(blocks)} blocks")


if __name__ == "__main__":
    main()
