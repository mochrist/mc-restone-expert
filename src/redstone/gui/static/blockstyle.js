// Shared helpers: state-string parsing, colours and block classification (used by 3D and 2D views).

export const DIRS = {
  north: [0, 0, -1], south: [0, 0, 1], east: [1, 0, 0], west: [-1, 0, 0], up: [0, 1, 0], down: [0, -1, 0],
};
export const OPPOSITE = { north: 'south', south: 'north', east: 'west', west: 'east', up: 'down', down: 'up' };
// Yaw (rotation about +y) that turns a shape facing north (-z) to the given horizontal direction.
export const YAW = { north: 0, east: -Math.PI / 2, south: Math.PI, west: Math.PI / 2 };

export const keyOf = (p) => `${p[0]},${p[1]},${p[2]}`;

const parseCache = new Map();

/** "minecraft:foo[a=b,c=d]|output=3" -> {id, props, output, raw}. */
export function parseState(s) {
  let st = parseCache.get(s);
  if (st) return st;
  let output = null;
  let body = s;
  const bar = body.indexOf('|');
  if (bar >= 0) {
    const m = /output=(\d+)/.exec(body.slice(bar));
    if (m) output = +m[1];
    body = body.slice(0, bar);
  }
  if (body.startsWith('minecraft:')) body = body.slice(10);
  const br = body.indexOf('[');
  const id = br < 0 ? body : body.slice(0, br);
  const props = {};
  if (br >= 0) {
    for (const kv of body.slice(br + 1, body.lastIndexOf(']')).split(',')) {
      const eq = kv.indexOf('=');
      if (eq > 0) props[kv.slice(0, eq).trim()] = kv.slice(eq + 1).trim();
    }
  }
  st = { id, props, output, raw: s };
  parseCache.set(s, st);
  return st;
}

export const isAir = (s) => !s || s === 'air' || s === 'cave_air' || s === 'void_air' ||
  s.startsWith('air[') || s.startsWith('minecraft:air');

export const isInteractive = (st) => st.id === 'lever' || st.id.endsWith('_button');

export const COLOR_NAMES = {
  white: 0xe9ecec, orange: 0xf07613, magenta: 0xbd44b3, light_blue: 0x3ab3da, yellow: 0xf8c527, lime: 0x70b919,
  pink: 0xed8dac, gray: 0x3e4447, light_gray: 0x8e8e86, cyan: 0x158991, purple: 0x792aac, blue: 0x35399d,
  brown: 0x724728, green: 0x546d1b, red: 0xa12722, black: 0x141519,
};
const COLOR_KEYS = Object.keys(COLOR_NAMES).sort((a, b) => b.length - a.length);

export function colorName(id) {
  for (const k of COLOR_KEYS) if (id.startsWith(k + '_')) return k;
  return null;
}

const FIXED = {
  stone: 0x8a8a8a, cobblestone: 0x777777, smooth_stone: 0x9d9d9d, stone_bricks: 0x7f7f7f, andesite: 0x888a88,
  polished_andesite: 0x8c8e8c, granite: 0x9a6b57, diorite: 0xc8c8c4, deepslate: 0x4d4d52, redstone_block: 0xb01808,
  glowstone: 0xf0c060, sea_lantern: 0xbfe6dc, obsidian: 0x1a1428, dirt: 0x866043, grass_block: 0x5a9a3c,
  sand: 0xdbcf9d, gravel: 0x857f7c, iron_block: 0xdcdcdc, gold_block: 0xf5d63c, diamond_block: 0x5fd9d1,
  coal_block: 0x1b1b1b, quartz_block: 0xe8e2d6, netherrack: 0x6e2f2f, bricks: 0x96564a, target: 0xe0b9a8,
  note_block: 0x7a5230, sculk: 0x0d3b44, hopper: 0x4a4a4a, dropper: 0x777777, dispenser: 0x777777,
  observer: 0x6e6e6e, piston: 0xb08a52, sticky_piston: 0xb08a52, tnt: 0xd04030, bedrock: 0x333333,
  rail: 0x6a5a48, powered_rail: 0x8a6a30, detector_rail: 0x6a5a48, activator_rail: 0x6a5a48, chest: 0x9a6a30,
  trapped_chest: 0x8a4a2a, water: 0x3355cc, ice: 0xa5c8f5, slime_block: 0x7bc255, honey_block: 0xe9a73a, glass: 0xcfe8f0,
  lectern: 0x9b7a45, daylight_sensor: 0xc9b98c, daylight_detector: 0xc9b98c, sculk_sensor: 0x1f5a66, calibrated_sculk_sensor: 0x2a6b8a,
  oak_planks: 0xb08a52, redstone_lamp: 0x5a3318, copper_block: 0xc4694a, bamboo_block: 0xb5a64a, crafter: 0x8a7a68,
};

const WOOD = {
  oak: 0xb08a52, spruce: 0x7a5a34, birch: 0xc8b77a, jungle: 0xa0734f, acacia: 0xa85a32, dark_oak: 0x4a3018,
  mangrove: 0x76363a, cherry: 0xe0a8a8, pale_oak: 0xe3d9d0, bamboo: 0xc8b04a, crimson: 0x6a3050, warped: 0x2b7f78,
};

function hashColor(id) {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) { h ^= id.charCodeAt(i); h = Math.imul(h, 16777619); }
  h >>>= 0;
  const hue = (h % 360) / 360;
  const f = (n) => { const k = (n + hue * 12) % 12; return 0.55 - 0.3 * Math.max(-1, Math.min(k - 3, 9 - k, 1)); };
  const c = (v) => Math.round(Math.max(0, Math.min(1, v)) * 255);
  return (c(f(0)) << 16) | (c(f(8)) << 8) | c(f(4));
}

/** Base colour (0xRRGGBB) and whether the id is in a known table (else hashed). */
export function baseColor(id, props = {}) {
  if (id === 'redstone_lamp') return { color: props.lit === 'true' ? 0xffd36a : 0x5a3318, known: true };
  if (id.endsWith('copper_bulb')) return { color: props.lit === 'true' ? 0xf2c96a : 0xa8573c, known: true };
  if (FIXED[id] !== undefined) return { color: FIXED[id], known: true };
  if (WOOD[id] !== undefined) return { color: WOOD[id], known: true }; // slab/stairs base names
  for (const w of Object.keys(WOOD)) if (id.startsWith(w + '_')) return { color: WOOD[w], known: true };
  const cn = colorName(id);
  if (cn) return { color: COLOR_NAMES[cn], known: true };
  if (id.endsWith('_planks') || id.endsWith('_wood')) return { color: 0xb08a52, known: true };
  if (id.endsWith('_log') || id.endsWith('_stem')) return { color: 0x6b5233, known: true };
  if (id.startsWith('polished_') || id.endsWith('_bricks')) return { color: 0x808080, known: true };
  if (id.includes('copper')) return { color: 0xc4694a, known: true };
  if (id.includes('deepslate')) return { color: 0x4d4d52, known: true };
  if (id.includes('stone')) return { color: 0x888888, known: true };
  return { color: hashColor(id), known: false };
}

const TRANSLUCENT = new Set(['glass', 'water', 'ice', 'slime_block', 'honey_block', 'glass_pane', 'tinted_glass']);
export const isGlassLike = (id) => TRANSLUCENT.has(id) || id.endsWith('_stained_glass') ||
  id.endsWith('_stained_glass_pane');

const SPECIAL_EXACT = new Set([
  'redstone_wire', 'redstone_torch', 'redstone_wall_torch', 'repeater', 'comparator', 'lever', 'piston',
  'sticky_piston', 'piston_head', 'moving_piston', 'observer', 'target', 'note_block', 'dispenser', 'dropper',
  'rail', 'powered_rail', 'detector_rail', 'activator_rail', 'daylight_sensor', 'daylight_detector', 'hopper', 'chest', 'trapped_chest',
  'ender_chest', 'sculk_sensor', 'calibrated_sculk_sensor',
]);

/** "cube" (instanced, coloured), "glass" (instanced translucent) or "obj" (individual shape). */
export function classify(st) {
  const id = st.id;
  if (isGlassLike(id)) return 'glass';
  if (SPECIAL_EXACT.has(id) || id.endsWith('_button') || id.endsWith('_slab') || id.endsWith('_stairs') ||
      id.endsWith('_carpet')) return 'obj';
  return 'cube';
}

export function wireColor(power) {
  const t = Math.max(0, Math.min(15, power)) / 15;
  const r = Math.round(0x4a + (0xff - 0x4a) * t);
  const g = Math.round(0x00 + 0x2a * t * t);
  const b = Math.round(0x00 + 0x10 * t * t);
  return (r << 16) | (g << 8) | b;
}

export const hex = (c) => '#' + c.toString(16).padStart(6, '0');

export function stacksText(n) {
  if (n < 64) return String(n);
  const s = Math.floor(n / 64), r = n % 64;
  return r ? `${s} Stacks + ${r}` : `${s} Stacks`;
}
