"""Standalone SVG timing diagrams (pure Python, deterministic, explicit background)."""

from __future__ import annotations

from xml.sax.saxutils import escape

TICK_W = 6  # px per game tick
ROW_H = 26
LABEL_PAD = 12
AXIS_H = 34
BG, FG, GRID, MARK, WAVE = "#ffffff", "#222222", "#d0d0d0", "#c0392b", "#1f6fb5"


def render_timing(rows: list[tuple[str, list[bool]]], marks: list[int] | None = None, title: str | None = None) -> str:
    """One row per (name, per-tick on/off list); marks = ticks of input steps (red markers).

    Tick t is drawn as the interval [t, t+1) on the time axis, axis labels every 10 gt.
    """
    marks = marks or []
    ticks = max((len(v) for _, v in rows), default=1)
    label_w = 8 * max((len(n) for n, _ in rows), default=4) + 2 * LABEL_PAD
    top = AXIS_H + (22 if title else 0)
    width = label_w + ticks * TICK_W + LABEL_PAD
    height = top + ROW_H * len(rows) + 8
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="monospace" font-size="12">',
           f'<rect width="{width}" height="{height}" fill="{BG}"/>']
    if title:
        out.append(f'<text x="{LABEL_PAD}" y="16" fill="{FG}" font-weight="bold">{escape(title)}</text>')
    x0 = label_w
    for t in range(0, ticks + 1, 10):
        x = x0 + t * TICK_W
        out.append(f'<line x1="{x}" y1="{top - 8}" x2="{x}" y2="{height - 8}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{x}" y="{top - 12}" fill="{FG}" text-anchor="middle">{t}</text>')
    for t in sorted(set(marks)):
        x = x0 + t * TICK_W
        out.append(f'<polygon points="{x - 4},{top - 22} {x + 4},{top - 22} {x},{top - 14}" fill="{MARK}"/>'
                   f'<line x1="{x}" y1="{top - 14}" x2="{x}" y2="{height - 8}" stroke="{MARK}" '
                   f'stroke-width="1" stroke-dasharray="3,3"/>')
    for i, (name, vals) in enumerate(rows):
        base = top + ROW_H * i + ROW_H - 6  # low level y
        high = base - ROW_H + 10
        out.append(f'<text x="{label_w - LABEL_PAD}" y="{base - 2}" fill="{FG}" text-anchor="end">{escape(name)}</text>')
        pts: list[str] = []
        prev = None
        for t, v in enumerate(vals):
            y = high if v else base
            x = x0 + t * TICK_W
            if prev is None:
                pts.append(f"{x},{y}")
            elif prev != v:
                pts.append(f"{x},{high if prev else base}")
                pts.append(f"{x},{y}")
            prev = v
        pts.append(f"{x0 + len(vals) * TICK_W},{high if prev else base}")
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{WAVE}" stroke-width="2" '
                   f'stroke-linejoin="miter" data-signal="{escape(name)}"/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
