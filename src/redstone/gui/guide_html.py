"""Printable build instructions: one standalone HTML page with a top-down SVG per layer (bottom to top).

Colours and symbols follow the 2D layer view of the GUI (`static/layers2d.js`, `static/blockstyle.js`); north is up.
The layer below is drawn faded as a guide. Repeaters and comparators carry an arrow towards their output."""

from __future__ import annotations

import html
import zlib

from ..model import BlockState, Grid

T = 34  # tile size in SVG units
DIR = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}
AIR = ("air", "cave_air", "void_air")

FIXED = {
    "stone": 0x8a8a8a, "cobblestone": 0x777777, "smooth_stone": 0x9d9d9d, "stone_bricks": 0x7f7f7f,
    "andesite": 0x888a88, "granite": 0x9a6b57, "diorite": 0xc8c8c4, "deepslate": 0x4d4d52,
    "redstone_block": 0xb01808, "glowstone": 0xf0c060, "obsidian": 0x1a1428, "dirt": 0x866043, "sand": 0xdbcf9d,
    "gravel": 0x857f7c, "iron_block": 0xdcdcdc, "gold_block": 0xf5d63c, "quartz_block": 0xe8e2d6,
    "netherrack": 0x6e2f2f, "bricks": 0x96564a, "target": 0xe0b9a8, "note_block": 0x7a5230, "hopper": 0x4a4a4a,
    "dropper": 0x777777, "dispenser": 0x777777, "observer": 0x6e6e6e, "piston": 0xb08a52,
    "sticky_piston": 0xb08a52, "slime_block": 0x7bc255, "honey_block": 0xe9a73a, "glass": 0xcfe8f0,
    "oak_planks": 0xb08a52, "redstone_lamp": 0x5a3318, "copper_block": 0xc4694a, "chest": 0x9a6a30,
}
COLOURS = {"white": 0xe9ecec, "orange": 0xf07613, "magenta": 0xbd44b3, "light_blue": 0x3ab3da, "yellow": 0xf8c527,
           "lime": 0x70b919, "pink": 0xed8dac, "gray": 0x3e4447, "light_gray": 0x8e8e86, "cyan": 0x158991,
           "purple": 0x792aac, "blue": 0x35399d, "brown": 0x724728, "green": 0x546d1b, "red": 0xa12722,
           "black": 0x141519}


def base_color(sid: str, props: dict) -> int:
    if sid in FIXED:
        return FIXED[sid]
    for c in sorted(COLOURS, key=len, reverse=True):
        if sid.startswith(c + "_"):
            return COLOURS[c]
    if sid.endswith(("_planks", "_wood")):
        return 0xb08a52
    if sid.endswith(("_log", "_stem")):
        return 0x6b5233
    if "stone" in sid or sid.startswith("polished_") or sid.endswith("_bricks"):
        return 0x888888
    return 0x404040 + (zlib.crc32(sid.encode()) & 0x7f7f7f)


def _hex(c: int) -> str:
    return f"#{c:06x}"


def _arrow(cx: float, cy: float, d: tuple[int, int], size: float, color: str) -> str:
    dx, dz = d
    px, pz = -dz, dx
    tip = (cx + dx * size * 0.75, cy + dz * size * 0.75)
    b1 = (cx + dx * size * 0.05 + px * size * 0.5, cy + dz * size * 0.05 + pz * size * 0.5)
    b2 = (cx + dx * size * 0.05 - px * size * 0.5, cy + dz * size * 0.05 - pz * size * 0.5)
    tail = (cx - dx * size * 0.6, cy - dz * size * 0.6)
    return (f'<line x1="{tail[0]:.1f}" y1="{tail[1]:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="{color}" '
            f'stroke-width="{size * 0.22:.1f}"/><polygon class="arrow" points="{tip[0]:.1f},{tip[1]:.1f} '
            f'{b1[0]:.1f},{b1[1]:.1f} {b2[0]:.1f},{b2[1]:.1f}" fill="{color}"/>')


def tile(state: BlockState, x: float, y: float) -> str:
    """SVG of one block seen from above, in the tile at (x, y)."""
    sid = state.id
    P = {k: v for k, v in state.props}
    cx, cy = x + T / 2, y + T / 2
    inset = 1.5

    def bg(c: int, opacity: float = 1) -> str:
        return (f'<rect x="{x + inset}" y="{y + inset}" width="{T - 2 * inset}" height="{T - 2 * inset}" '
                f'fill="{_hex(c)}" opacity="{opacity}"/>')

    def label(s: str, color: str = "#fff", size: float = 13) -> str:
        return (f'<text x="{cx}" y="{cy + size * 0.35:.1f}" text-anchor="middle" font-size="{size}" '
                f'font-weight="bold" fill="{color}">{html.escape(s)}</text>')

    if sid == "redstone_wire":
        arms = [(n, d) for n, d in DIR.items() if P.get(n, "none") != "none"]
        out = "".join(f'<line x1="{cx}" y1="{cy}" x2="{cx + d[0] * T / 2}" y2="{cy + d[1] * T / 2}" stroke="#c0200c" '
                      f'stroke-width="6" stroke-linecap="round"/>' for _, d in arms)
        out += "".join(f'<circle cx="{cx + d[0] * T * 0.42}" cy="{cy + d[1] * T * 0.42}" r="3" fill="#fff"/>'
                       for n, d in arms if P.get(n) == "up")
        return out + f'<circle cx="{cx}" cy="{cy}" r="{5 if arms else 8}" fill="#c0200c"/>'
    if sid in ("redstone_torch", "redstone_wall_torch"):
        tx, ty = cx, cy
        stick = ""
        if sid == "redstone_wall_torch":
            d = DIR[OPP.get(P.get("facing", "south"), "north")]
            stick = (bg(0x777777, 0.25) +
                     f'<line x1="{cx + d[0] * T * 0.46}" y1="{cy + d[1] * T * 0.46}" x2="{cx}" y2="{cy}" '
                     f'stroke="#7a5a2e" stroke-width="5" stroke-linecap="round"/>')
            tx, ty = cx - d[0] * T * 0.08, cy - d[1] * T * 0.08
        return stick + f'<circle cx="{tx}" cy="{ty}" r="{T * 0.22:.1f}" fill="#ff3b1f" stroke="#2a1005"/>'
    if sid in ("repeater", "comparator"):
        out_dir = DIR[OPP.get(P.get("facing", "south"), "north")]
        s = bg(0x8e8a80 if sid == "repeater" else 0xa7a39a) + _arrow(cx, cy, out_dir, T * 0.32, "#333")
        if sid == "repeater":
            inp = DIR[P.get("facing", "south")]
            n = int(P.get("delay", "1"))
            for i in range(n):
                off = (i - (n - 1) / 2) * T * 0.14
                s += (f'<rect x="{cx + inp[0] * T * 0.38 - 2 + (off if inp[1] else 0):.1f}" '
                      f'y="{cy + inp[1] * T * 0.38 - 2 + (off if inp[0] else 0):.1f}" width="4" height="4" '
                      f'fill="#222"/>')
        else:
            s += label("−" if P.get("mode") == "subtract" else "=", "#222", 14)
        return s
    if sid == "lever":
        return bg(0x777777, 0.4) + label("H", "#8b6b3a", 15) + f'<circle cx="{x + T - 7}" cy="{y + 7}" r="3.5" fill="#e8c070"/>'
    if sid.endswith("_button"):
        return bg(0x777777, 0.4) + f'<rect x="{cx - 8}" y="{cy - 6}" width="16" height="12" fill="#b08a52" stroke="#222"/>'
    if sid.endswith("_pressure_plate"):
        return bg(0x999999, 0.5) + label("P", "#222", 13)
    if sid in ("piston", "sticky_piston", "observer", "dispenser", "dropper", "hopper"):
        s = bg(base_color(sid, P))
        face = P.get("facing", "up")
        if face in DIR:
            s += _arrow(cx, cy, DIR[face], T * 0.26, "#eee")
        elif face == "up":
            s += f'<circle cx="{cx}" cy="{cy}" r="5" fill="#eee"/>'
        else:
            s += label("×", "#eee", 16)
        return s
    if sid == "target":
        return (bg(0xf0e8e0) + f'<circle cx="{cx}" cy="{cy}" r="{T * 0.3:.1f}" fill="none" stroke="#d03030" '
                f'stroke-width="2"/><circle cx="{cx}" cy="{cy}" r="{T * 0.12:.1f}" fill="none" stroke="#d03030" '
                f'stroke-width="2"/>')
    if sid == "redstone_lamp":
        return bg(0x3a2412) + f'<circle cx="{cx}" cy="{cy}" r="{T * 0.32:.1f}" fill="#7a4a26"/>'
    return bg(base_color(sid, P))


def layer_svg(grid: Grid, y: int, size: tuple[int, int, int]) -> str:
    sx, _, sz = size
    pad = 22
    W, H = sx * T + 2 * pad, sz * T + 2 * pad
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" class="layer-svg" viewBox="0 0 {W} {H}" width="{W}" '
             f'height="{H}" font-family="system-ui, sans-serif">', f'<rect width="{W}" height="{H}" fill="#fff"/>']
    lines = "".join(f'<line x1="{pad + i * T}" y1="{pad}" x2="{pad + i * T}" y2="{pad + sz * T}"/>'
                    for i in range(sx + 1))
    lines += "".join(f'<line x1="{pad}" y1="{pad + i * T}" x2="{pad + sx * T}" y2="{pad + i * T}"/>'
                     for i in range(sz + 1))
    parts.append(f'<g stroke="#c8c8c8" stroke-width="1">{lines}</g>')
    below = [(p, s) for p, s in grid.items() if p.y == y - 1 and s.id not in AIR]
    here = [(p, s) for p, s in grid.items() if p.y == y and s.id not in AIR]
    parts.append('<g opacity="0.3">' + "".join(tile(s, pad + p.x * T, pad + p.z * T) for p, s in below) + "</g>")
    parts.append("".join(tile(s, pad + p.x * T, pad + p.z * T) for p, s in here))
    mx, mz = pad + sx * T / 2, pad + sz * T / 2
    for txt, tx, ty in (("N", mx, pad - 7), ("S", mx, pad + sz * T + 16), ("W", pad - 10, mz + 5),
                        ("O", pad + sx * T + 10, mz + 5)):
        parts.append(f'<text x="{tx}" y="{ty}" text-anchor="middle" font-size="13" font-weight="bold" '
                     f'fill="#333">{txt}</text>')
    parts.append("</svg>")
    return "".join(parts)


def guide_html(grid: Grid, title: str) -> str:
    """The printable build guide of `grid` as one HTML page."""
    from .materials import label_for, materials

    sx, sy, sz = grid.size
    e = html.escape
    sections = []
    for y in range(sy):
        ids = sorted({s.id for p, s in grid.items() if p.y == y and s.id not in AIR})
        if not ids:
            continue
        legend = "".join(f'<li><span class="sw" style="background:{_hex(base_color(i, {}))}"></span>'
                         f'{e(label_for(i))}</li>' for i in ids)
        n = sum(1 for p, s in grid.items() if p.y == y and s.id not in AIR)
        sections.append(f'<section class="layer"><h2>Ebene {y + 1} von {sy} (von unten)</h2>'
                        f'<p class="meta">{n} Blöcke. Blick von oben, Norden (N) ist oben. Blasse Blöcke gehören zur '
                        f'Ebene darunter und helfen beim Ausrichten.</p>{layer_svg(grid, y, (sx, sy, sz))}'
                        f'<ul class="legend">{legend}</ul></section>')
    mats = "".join(f"<tr><td class='n'>{m['count']}</td><td>{e(m['label'])}</td></tr>" for m in materials(grid))
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bauanleitung: {e(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; color: #222; max-width: 900px; margin: 24px auto; padding: 0 16px; }}
h1 {{ margin-bottom: 4px; }} .meta {{ color: #555; margin: 4px 0 10px; }}
table {{ border-collapse: collapse; }} td {{ padding: 2px 12px 2px 0; }} td.n {{ text-align: right; font-weight: bold; }}
.layer {{ break-inside: avoid; page-break-inside: avoid; margin-top: 28px; }}
.layer svg {{ max-width: 100%; height: auto; border: 1px solid #ccc; }}
.legend {{ list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 18px; }}
.sw {{ display: inline-block; width: 14px; height: 14px; border: 1px solid #888; margin-right: 6px; vertical-align: -2px; }}
@media print {{ body {{ margin: 0; max-width: none; }} }}
</style></head><body>
<h1>Bauanleitung: {e(title)}</h1>
<p class="meta">Größe {sx} × {sy} × {sz} Blöcke (Ost–West × Höhe × Nord–Süd). Baue Ebene für Ebene von unten nach
oben. Auf jedem Bild ist Norden oben (N), Osten rechts (O). Pfeile bei Verstärkern und Komparatoren zeigen in
Signalrichtung, also zum Ausgang hin.</p>
<h2>Material</h2><table>{mats}</table>
{''.join(sections)}
</body></html>
"""
