// 2D layer view: top-down canvas of one y-layer, the layer below shown faded.
import {
  DIRS, OPPOSITE, keyOf, parseState, isAir, isInteractive, classify, baseColor, wireColor, hex,
} from './blockstyle.js';

export class LayerView {
  /** @param {HTMLElement} container  @param {{onHover?:Function,onUse?:Function,onLayer?:Function}} cb */
  constructor(container, cb = {}) {
    this.container = container; this.cb = cb;
    this.blocks = new Map(); // key -> {p, s, st}
    this.order = new Map();
    this.revealCount = Infinity;
    this.size = [1, 1, 1];
    this.y = 0;
    this.inputs = []; this.outputs = [];
    this.hover = null;
    this.canvas = document.createElement('canvas');
    this.canvas.style.cssText = 'width:100%;height:100%;display:block';
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');
    new ResizeObserver(() => this.resize()).observe(container);
    this._bind();
    this.setTheme();
  }

  setTheme() {
    const css = getComputedStyle(document.documentElement);
    this.colors = {
      bg: css.getPropertyValue('--view-bg').trim() || '#20242a',
      grid: css.getPropertyValue('--grid-b').trim() || '#334',
      text: css.getPropertyValue('--fg').trim() || '#ddd',
    };
    this.requestDraw();
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.requestDraw();
  }

  requestDraw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this.draw(); });
  }

  setBlocks(blocks, size) {
    this.blocks.clear();
    if (size) this.size = size.slice();
    for (const b of blocks) if (!isAir(b.s)) this.blocks.set(keyOf(b.p), { p: b.p, s: b.s, st: parseState(b.s) });
    this.y = Math.min(this.y, Math.max(0, this.size[1] - 1));
    this.requestDraw();
  }

  applyChanges(blocks) {
    for (const b of blocks) {
      const k = keyOf(b.p);
      if (isAir(b.s)) this.blocks.delete(k);
      else this.blocks.set(k, { p: b.p, s: b.s, st: parseState(b.s) });
    }
    this.requestDraw();
  }

  setReveal(order) {
    this.order = new Map();
    if (order) order.forEach((p, i) => this.order.set(keyOf(p), i));
    this.revealCount = Infinity;
    this.requestDraw();
  }

  setRevealCount(n) { this.revealCount = n; this.requestDraw(); }
  setLayer(y) { this.y = y; this.requestDraw(); }
  setIO(inputs = [], outputs = []) { this.inputs = inputs; this.outputs = outputs; this.requestDraw(); }

  _shown(b) {
    const r = this.order.get(keyOf(b.p));
    return r === undefined || r < this.revealCount;
  }

  _layout() {
    const W = this.canvas.width, H = this.canvas.height, dpr = window.devicePixelRatio || 1;
    const pad = 26 * dpr;
    const [sx, , sz] = this.size;
    const t = Math.max(6 * dpr, Math.floor(Math.min((W - 2 * pad) / sx, (H - 2 * pad) / sz)));
    return { t, ox: Math.round((W - t * sx) / 2), oy: Math.round((H - t * sz) / 2), dpr };
  }

  draw() {
    const { ctx, canvas } = this;
    const { t, ox, oy, dpr } = this._layout();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = this.colors.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const [sx, , sz] = this.size;
    // floor grid
    ctx.strokeStyle = this.colors.grid;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    for (let x = 0; x <= sx; x++) { ctx.moveTo(ox + x * t + 0.5, oy); ctx.lineTo(ox + x * t + 0.5, oy + sz * t); }
    for (let z = 0; z <= sz; z++) { ctx.moveTo(ox, oy + z * t + 0.5); ctx.lineTo(ox + sx * t, oy + z * t + 0.5); }
    ctx.stroke();
    ctx.globalAlpha = 1;

    const below = [], here = [];
    for (const b of this.blocks.values()) {
      if (b.p[1] === this.y - 1) below.push(b);
      else if (b.p[1] === this.y) here.push(b);
    }
    ctx.globalAlpha = 0.3;
    for (const b of below) if (this._shown(b)) this._tile(b, ox + b.p[0] * t, oy + b.p[2] * t, t, true);
    ctx.globalAlpha = 1;
    for (const b of here) if (this._shown(b)) this._tile(b, ox + b.p[0] * t, oy + b.p[2] * t, t, false);

    // axis labels
    ctx.fillStyle = this.colors.text;
    ctx.font = `bold ${Math.round(13 * dpr)}px system-ui, sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('N', ox + sx * t / 2, oy - 12 * dpr);
    ctx.fillText('S', ox + sx * t / 2, oy + sz * t + 12 * dpr);
    ctx.fillText('W', ox - 12 * dpr, oy + sz * t / 2);
    ctx.fillText('O', ox + sx * t + 12 * dpr, oy + sz * t / 2);

    // IO labels
    const io = (list, color) => {
      for (const o of list) {
        if (o.p[1] !== this.y) continue;
        const x = ox + o.p[0] * t, y = oy + o.p[2] * t;
        ctx.strokeStyle = color; ctx.lineWidth = 2 * dpr;
        ctx.strokeRect(x + 1, y + 1, t - 2, t - 2);
        const fs = Math.round(11 * dpr);
        ctx.font = `bold ${fs}px system-ui, sans-serif`;
        const tw = ctx.measureText(o.name).width + 8 * dpr;
        const ty = y - fs * 0.9 < 0 ? y + t + fs * 0.9 : y - fs * 0.9;
        ctx.fillStyle = color;
        ctx.fillRect(x + t / 2 - tw / 2, ty - fs * 0.7, tw, fs * 1.4);
        ctx.fillStyle = '#fff';
        ctx.fillText(o.name, x + t / 2, ty);
      }
    };
    io(this.inputs, '#2f6fdc'); io(this.outputs, '#1c9a4a');

    if (this.hover) {
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 * dpr;
      ctx.strokeRect(ox + this.hover[0] * t + 1, oy + this.hover[1] * t + 1, t - 2, t - 2);
    }
  }

  // --- glyphs -------------------------------------------------------------------------------------------------------

  _arrow(cx, cy, dir, size, color) {
    const { ctx } = this;
    const [dx, , dz] = dir;
    if (!dx && !dz) { // up/down: dot / cross
      ctx.fillStyle = color; ctx.beginPath(); ctx.arc(cx, cy, size * 0.35, 0, Math.PI * 2); ctx.fill();
      return;
    }
    const px = -dz, pz = dx; // perpendicular
    ctx.fillStyle = color; ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(2, size * 0.22);
    ctx.beginPath(); ctx.moveTo(cx - dx * size * 0.6, cy - dz * size * 0.6); ctx.lineTo(cx + dx * size * 0.1, cy + dz * size * 0.1); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + dx * size * 0.75, cy + dz * size * 0.75);
    ctx.lineTo(cx + dx * size * 0.05 + px * size * 0.5, cy + dz * size * 0.05 + pz * size * 0.5);
    ctx.lineTo(cx + dx * size * 0.05 - px * size * 0.5, cy + dz * size * 0.05 - pz * size * 0.5);
    ctx.closePath(); ctx.fill();
  }

  _tile(b, x, y, t, faded) {
    const { ctx } = this;
    const { id, props: P } = b.st;
    const cx = x + t / 2, cy = y + t / 2;
    const inset = Math.max(1, t * 0.04);
    const fillBg = (c, a = 1) => {
      ctx.globalAlpha *= a; ctx.fillStyle = hex(c); ctx.fillRect(x + inset, y + inset, t - 2 * inset, t - 2 * inset); ctx.globalAlpha /= a;
    };
    const text = (s, c = '#fff', f = 0.38, ox = 0, oy = 0) => {
      ctx.fillStyle = c; ctx.font = `bold ${Math.round(t * f)}px system-ui, sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(s, cx + ox, cy + oy);
    };
    const facingDir = (f) => DIRS[f] || DIRS.north;

    switch (id) {
      case 'redstone_wire': {
        const pw = +P.power || 0, col = hex(wireColor(pw));
        const arms = [['north', 0, -1], ['east', 1, 0], ['south', 0, 1], ['west', -1, 0]].filter(([n]) => P[n] && P[n] !== 'none');
        ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineCap = 'round';
        ctx.lineWidth = Math.max(2, t * 0.2);
        for (const [n, dx, dz] of arms) {
          ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + dx * t / 2, cy + dz * t / 2); ctx.stroke();
          if (P[n] === 'up') { // small bar at the edge marks a climb
            ctx.fillStyle = '#fff';
            ctx.fillRect(cx + dx * t * 0.42 - (dz ? t * 0.14 : t * 0.04), cy + dz * t * 0.42 - (dx ? t * 0.14 : t * 0.04),
              dz ? t * 0.28 : t * 0.08, dx ? t * 0.28 : t * 0.08);
            ctx.fillStyle = col;
          }
        }
        ctx.beginPath(); ctx.arc(cx, cy, t * (arms.length ? 0.15 : 0.24), 0, Math.PI * 2); ctx.fill();
        if (t >= 26 * (window.devicePixelRatio || 1) && pw > 0) text(String(pw), '#fff', 0.3, 0, t * 0.3);
        ctx.lineCap = 'butt';
        return;
      }
      case 'redstone_torch': case 'redstone_wall_torch': {
        const lit = P.lit === 'true';
        if (id === 'redstone_wall_torch') {
          const d = facingDir(OPPOSITE[P.facing] || 'south'); // towards the wall
          ctx.strokeStyle = '#7a5a2e'; ctx.lineWidth = Math.max(2, t * 0.12);
          ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + d[0] * t * 0.45, cy + d[2] * t * 0.45); ctx.stroke();
        }
        if (lit) { ctx.fillStyle = 'rgba(255,60,30,0.3)'; ctx.beginPath(); ctx.arc(cx, cy, t * 0.4, 0, Math.PI * 2); ctx.fill(); }
        ctx.fillStyle = lit ? '#ff3b1f' : '#5a1a10';
        ctx.strokeStyle = '#2a1005'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(cx, cy, t * 0.22, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        return;
      }
      case 'repeater': case 'comparator': {
        const lit = P.powered === 'true';
        fillBg(id === 'repeater' ? (lit ? 0xb06a5c : 0x8e8a80) : (lit ? 0xc0867a : 0xa7a39a));
        // diode: facing = input side, output = opposite (see sim/blocks/diode.py)
        const out = facingDir(OPPOSITE[P.facing] || 'south');
        this._arrow(cx, cy, out, t * 0.32, lit ? '#ff3b1f' : '#333');
        if (t >= 22) {
          if (id === 'repeater') {
            const inp = facingDir(P.facing);
            ctx.fillStyle = '#222';
            for (let i = 0; i < (+P.delay || 1); i++) ctx.fillRect(cx + inp[0] * t * 0.38 - t * 0.04 + (inp[2] ? (i - 1.5) * t * 0.1 : 0), cy + inp[2] * t * 0.38 - t * 0.04 + (inp[0] ? (i - 1.5) * t * 0.1 : 0), t * 0.08, t * 0.08);
          } else {
            if (P.mode === 'subtract') { // subtract: red-framed tile with a minus sign
              ctx.strokeStyle = '#ff3b1f'; ctx.lineWidth = Math.max(2, t * 0.07); ctx.strokeRect(x + inset + 1, y + inset + 1, t - 2 * inset - 2, t - 2 * inset - 2);
            }
            text(P.mode === 'subtract' ? '−' : '=', P.mode === 'subtract' ? '#c01808' : '#222', 0.4, t * 0.25, t * 0.25);
            if (b.st.output != null) text(String(b.st.output), '#fff', 0.26, -t * 0.25, t * 0.3);
          }
        }
        return;
      }
      case 'lever': {
        fillBg(0x777777, 0.55);
        const on = P.powered === 'true';
        const d = facingDir(P.facing);
        const ax = d[0] ? [1, 0] : [0, 1];
        const k = on ? 0.22 : -0.22;
        ctx.strokeStyle = on ? '#e8c070' : '#8b6b3a'; ctx.lineWidth = Math.max(2, t * 0.14);
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + ax[0] * t * k * 1.6, cy + ax[1] * t * k * 1.6); ctx.stroke();
        ctx.fillStyle = on ? '#ff5a30' : '#444';
        ctx.beginPath(); ctx.arc(cx + ax[0] * t * k * 1.6, cy + ax[1] * t * k * 1.6, t * 0.1, 0, Math.PI * 2); ctx.fill();
        if (P.face && P.face !== 'floor' && t >= 18) text(P.face === 'wall' ? 'W' : 'D', '#fff', 0.22, t * 0.3, -t * 0.32);
        return;
      }
      case 'piston': case 'sticky_piston': case 'piston_head': {
        fillBg(id === 'piston_head' ? 0xb08a52 : 0x808080);
        const f = facingDir(P.facing);
        if (id === 'piston_head') ctx.fillStyle = '#6b5233';
        else ctx.fillStyle = id === 'sticky_piston' ? '#7bc255' : '#b08a52';
        ctx.fillRect(cx + f[0] * t * 0.3 - (f[0] ? t * 0.08 : t * 0.4), cy + f[2] * t * 0.3 - (f[2] ? t * 0.08 : t * 0.4), f[0] ? t * 0.16 : t * 0.8, f[2] ? t * 0.16 : t * 0.8);
        this._arrow(cx, cy, f, t * 0.25, P.extended === 'true' ? '#fff' : '#222');
        return;
      }
      case 'observer': {
        fillBg(0x6e6e6e);
        const f = facingDir(P.facing);
        this._arrow(cx, cy, f, t * 0.26, '#eee');
        ctx.fillStyle = P.powered === 'true' ? '#ff3020' : '#802020';
        ctx.beginPath(); ctx.arc(cx - f[0] * t * 0.32, cy - f[2] * t * 0.32, t * 0.1, 0, Math.PI * 2); ctx.fill();
        return;
      }
      case 'target': {
        fillBg(0xf0e8e0);
        ctx.strokeStyle = '#d03030'; ctx.lineWidth = Math.max(1, t * 0.08);
        ctx.beginPath(); ctx.arc(cx, cy, t * 0.3, 0, Math.PI * 2); ctx.stroke();
        ctx.beginPath(); ctx.arc(cx, cy, t * 0.12, 0, Math.PI * 2); ctx.stroke();
        return;
      }
      case 'redstone_lamp': {
        const lit = P.lit === 'true';
        fillBg(lit ? 0xb58a30 : 0x3a2412);
        ctx.fillStyle = lit ? '#ffe9a0' : '#7a4a26';
        ctx.beginPath(); ctx.arc(cx, cy, t * 0.32, 0, Math.PI * 2); ctx.fill();
        return;
      }
      default:
    }
    if (id.endsWith('_button')) {
      fillBg(0x777777, 0.4);
      const on = P.powered === 'true';
      ctx.fillStyle = on ? '#ff7a50' : (id.startsWith('stone') ? '#9a9a9a' : '#b08a52');
      ctx.fillRect(cx - t * 0.2, cy - t * 0.14, t * 0.4, t * 0.28);
      ctx.strokeStyle = '#222'; ctx.lineWidth = 1; ctx.strokeRect(cx - t * 0.2, cy - t * 0.14, t * 0.4, t * 0.28);
      return;
    }
    const kind = classify(b.st);
    const bc = baseColor(id, P);
    if (kind === 'glass') {
      ctx.globalAlpha *= 0.55; fillBg(bc.color); ctx.globalAlpha /= 0.55;
      ctx.strokeStyle = hex(bc.color); ctx.lineWidth = 2; ctx.strokeRect(x + inset, y + inset, t - 2 * inset, t - 2 * inset);
      return;
    }
    if (id.endsWith('_slab') || id.endsWith('_stairs') || id.endsWith('_carpet')) {
      const col = hex(bc.color), w = t - 2 * inset;
      const shade = (a) => { ctx.fillStyle = `rgba(${a ? '255,255,255' : '0,0,0'},${a ? 0.28 : 0.38})`; };
      fillBg(bc.color);
      if (id.endsWith('_slab') && P.type !== 'double') {
        // bottom slab: darkened with a dashed outline; top slab: brightened with a solid outline
        const top = P.type === 'top';
        shade(top); ctx.fillRect(x + inset, y + inset, w, w);
        ctx.strokeStyle = top ? '#fff' : 'rgba(0,0,0,0.6)'; ctx.lineWidth = Math.max(1, t * 0.06);
        ctx.setLineDash(top ? [] : [3, 3]); ctx.strokeRect(x + inset + 1, y + inset + 1, w - 2, w - 2); ctx.setLineDash([]);
        if (t >= 14) text(top ? '▔' : '▁', '#fff', 0.4);
      } else if (id.endsWith('_stairs')) {
        // high step on the facing side: brighter half plus an arrow towards it (upside-down stairs: darker)
        const f = facingDir(P.facing), up = P.half !== 'top';
        shade(up); ctx.fillRect(x + inset + (f[0] > 0 ? w / 2 : 0), y + inset + (f[2] > 0 ? w / 2 : 0), f[0] ? w / 2 : w, f[2] ? w / 2 : w);
        this._arrow(cx, cy, f, t * 0.22, '#fff');
      } else if (id.endsWith('_carpet')) {
        ctx.strokeStyle = 'rgba(0,0,0,0.5)'; ctx.setLineDash([3, 3]); ctx.strokeRect(x + inset + 1, y + inset + 1, w - 2, w - 2); ctx.setLineDash([]);
      } else if (P.type === 'double') {
        ctx.strokeStyle = 'rgba(0,0,0,0.6)'; ctx.lineWidth = 1; ctx.strokeRect(x + inset + 0.5, y + inset + 0.5, w - 1, w - 1);
      }
      return;
    }
    fillBg(bc.color);
    if (id === 'dispenser' || id === 'dropper') this._arrow(cx, cy, facingDir(P.facing), t * 0.25, '#eee');
    else if (id === 'hopper') {
      ctx.fillStyle = '#111'; ctx.beginPath(); ctx.arc(cx, cy, t * 0.3, 0, Math.PI * 2); ctx.fill();
      if (P.facing && P.facing !== 'down') this._arrow(cx, cy, facingDir(P.facing), t * 0.28, '#eee');
      else { ctx.fillStyle = '#777'; ctx.beginPath(); ctx.arc(cx, cy, t * 0.12, 0, Math.PI * 2); ctx.fill(); }
    } else if (id.endsWith('chest')) {
      ctx.strokeStyle = '#3a2410'; ctx.lineWidth = Math.max(1, t * 0.06); ctx.strokeRect(x + t * 0.15, y + t * 0.15, t * 0.7, t * 0.7);
      ctx.fillStyle = '#d8d8d8'; const f = facingDir(P.facing);
      ctx.fillRect(cx + f[0] * t * 0.32 - t * 0.05, cy + f[2] * t * 0.32 - t * 0.05, t * 0.1, t * 0.1);
    } else if (id === 'daylight_detector' || id === 'daylight_sensor') {
      ctx.fillStyle = P.inverted === 'true' ? '#2a3a5a' : '#e8d890'; ctx.fillRect(x + t * 0.15, y + t * 0.15, t * 0.7, t * 0.7);
      if (t >= 14) text(P.inverted === 'true' ? '☾' : '☀', '#333', 0.4);
    } else if (id.endsWith('sculk_sensor')) {
      ctx.fillStyle = +P.power > 0 ? '#80f0ff' : '#59d0e0'; ctx.beginPath(); ctx.arc(cx, cy, t * 0.22, 0, Math.PI * 2); ctx.fill();
    } else if (id.endsWith('copper_bulb')) {
      ctx.fillStyle = P.lit === 'true' ? '#fff3b0' : '#5a2a18'; ctx.beginPath(); ctx.arc(cx, cy, t * 0.24, 0, Math.PI * 2); ctx.fill();
    } else if (id.endsWith('rail')) {
      ctx.strokeStyle = P.powered === 'true' ? '#e8b030' : '#444'; ctx.lineWidth = Math.max(2, t * 0.1);
      const ew = /east_west/.test(P.shape || '');
      ctx.beginPath(); ctx.moveTo(cx - (ew ? t * 0.4 : 0), cy - (ew ? 0 : t * 0.4)); ctx.lineTo(cx + (ew ? t * 0.4 : 0), cy + (ew ? 0 : t * 0.4)); ctx.stroke();
    } else if (!bc.known && t >= 14) text(id.slice(0, 2), '#fff', 0.34);
    else if (id === 'redstone_block' && t >= 14) text('R', '#fff', 0.4);
    else if (id === 'note_block' && t >= 14) text('♪', '#fff', 0.45);
  }

  // --- interaction --------------------------------------------------------------------------------------------------

  _cell(ev) {
    const r = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const { t, ox, oy } = this._layout();
    const x = Math.floor(((ev.clientX - r.left) * dpr - ox) / t), z = Math.floor(((ev.clientY - r.top) * dpr - oy) / t);
    if (x < 0 || z < 0 || x >= this.size[0] || z >= this.size[2]) return null;
    return [x, z];
  }

  _bind() {
    const c = this.canvas;
    c.addEventListener('wheel', (ev) => {
      ev.preventDefault();
      const ny = Math.max(0, Math.min(this.size[1] - 1, this.y + (ev.deltaY < 0 ? 1 : -1)));
      if (ny !== this.y) { this.y = ny; this.cb.onLayer?.(ny); this.requestDraw(); }
    }, { passive: false });
    c.addEventListener('pointermove', (ev) => {
      const cell = this._cell(ev);
      this.hover = cell;
      this.requestDraw();
      if (!cell) { this.cb.onHover?.(null); return; }
      const b = this.blocks.get(keyOf([cell[0], this.y, cell[1]]));
      this.cb.onHover?.({ p: [cell[0], this.y, cell[1]], s: b && this._shown(b) ? b.s : null }, ev);
    });
    c.addEventListener('pointerleave', () => { this.hover = null; this.cb.onHover?.(null); this.requestDraw(); });
    c.addEventListener('click', (ev) => {
      const cell = this._cell(ev);
      if (!cell) return;
      const b = this.blocks.get(keyOf([cell[0], this.y, cell[1]]));
      if (b && isInteractive(b.st)) this.cb.onUse?.(b.p);
    });
  }
}
