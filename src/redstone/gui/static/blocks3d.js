// 3D view: simplified block shapes with three.js. Plain cubes are instanced; special shapes are small meshes.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import {
  DIRS, OPPOSITE, YAW, keyOf, parseState, isAir, isInteractive, classify, baseColor, wireColor,
} from './blockstyle.js';

const UP = new THREE.Vector3(0, 1, 0);
const matCache = new Map();
function mat(color, emissive = 0, double = false) {
  const k = `${color}:${emissive}:${double}`;
  let m = matCache.get(k);
  if (!m) {
    m = new THREE.MeshLambertMaterial({ color, emissive, side: double ? THREE.DoubleSide : THREE.FrontSide });
    matCache.set(k, m);
  }
  return m;
}

const boxGeoCache = new Map();
function boxGeo(w, h, d) {
  const k = `${w},${h},${d}`;
  let g = boxGeoCache.get(k);
  if (!g) { g = new THREE.BoxGeometry(w, h, d); boxGeoCache.set(k, g); }
  return g;
}
function box(w, h, d, material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(boxGeo(w, h, d), material);
  m.position.set(x, y, z);
  return m;
}

function mergeGeoms(list) {
  const pos = [], nor = [], idx = [];
  let off = 0;
  for (const g of list) {
    pos.push(...g.attributes.position.array);
    nor.push(...g.attributes.normal.array);
    for (const i of g.index.array) idx.push(i + off);
    off += g.attributes.position.count;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  out.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  out.setIndex(idx);
  return out;
}
function tbox(w, h, d, x, y, z) {
  const g = new THREE.BoxGeometry(w, h, d);
  g.translate(x, y, z);
  return g;
}

// --- shape builders; local origin is the cell centre, floor at y = -0.5 --------------------------------------------

const wireGeoCache = new Map();
function wireGeometry(P) {
  const arms = [P.north || 'none', P.east || 'none', P.south || 'none', P.west || 'none'];
  const key = arms.join(',');
  let g = wireGeoCache.get(key);
  if (g) return g;
  const T = 0.06, yc = -0.5 + T / 2, W = 0.2;
  const parts = [];
  const none = arms.every((a) => a === 'none');
  parts.push(tbox(0.26, T, 0.26, 0, yc, 0));
  const dirs = [['north', 0, -1], ['east', 1, 0], ['south', 0, 1], ['west', -1, 0]];
  dirs.forEach(([, dx, dz], i) => {
    const a = arms[i];
    if (a === 'none' && !none) return;
    const end = none ? 0.33 : 0.5;
    const L = end - 0.13;
    const c = 0.13 + L / 2;
    parts.push(dx ? tbox(L, T, W, dx * c, yc, 0) : tbox(W, T, L, 0, yc, dz * c));
    if (a === 'up') {
      // vertical strip on the neighbouring face
      parts.push(dx ? tbox(T, 1, W, dx * (0.5 - T / 2), 0, 0) : tbox(W, 1, T, 0, 0, dz * (0.5 - T / 2)));
    }
  });
  g = mergeGeoms(parts);
  parts.forEach((p) => p.dispose());
  wireGeoCache.set(key, g);
  return g;
}

function arrowMesh(color, apexZ = 0.22, baseZ = -0.1, y = 0) {
  const g = new THREE.BufferGeometry();
  const v = new Float32Array([-0.16, y, baseZ, 0.16, y, baseZ, 0, y, apexZ]);
  g.setAttribute('position', new THREE.BufferAttribute(v, 3));
  g.setAttribute('normal', new THREE.BufferAttribute(new Float32Array([0, 1, 0, 0, 1, 0, 0, 1, 0]), 3));
  // wind so that the front face looks up (+y)
  g.setIndex([0, 2, 1]);
  const m = new THREE.Mesh(g, mat(color, color === 0xff4030 ? 0x601008 : 0, true));
  return m;
}

function orientFacing(group, facing) {
  if (facing in YAW) group.rotation.y = YAW[facing];
  else if (facing === 'up') group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), UP);
  else if (facing === 'down') group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), new THREE.Vector3(0, -1, 0));
}

// Place a floor-built shape (origin = cell centre, floor at y=-0.5) on a floor/wall/ceiling face.
// For wall attachment `facing` points away from the wall.
function placeFaced(group, face, facing) {
  const q = new THREE.Quaternion();
  const yaw = new THREE.Quaternion().setFromAxisAngle(UP, YAW[facing] ?? 0);
  if (face === 'wall') {
    // tilt the floor shape up onto the wall (up -> north), then yaw it to the real direction
    q.copy(yaw).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2));
  } else {
    if (face === 'ceiling') q.setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
    q.multiply(yaw);
  }
  group.quaternion.copy(q);
}

function torchGroup(lit, wall, facing) {
  const outer = new THREE.Group();
  const inner = new THREE.Group();
  inner.add(box(0.125, 0.6, 0.125, mat(0x7a5a2e), 0, 0.3, 0));
  inner.add(box(0.2, 0.2, 0.2, mat(lit ? 0xff3b1f : 0x5a1a10, lit ? 0xff2000 : 0), 0, 0.62, 0));
  if (wall) {
    inner.position.set(0, -0.5 + 0.22, 0.33);
    inner.rotation.x = -0.45; // top leans away from the wall (wall is opposite of `facing`)
    outer.rotation.y = YAW[facing] ?? 0;
  } else {
    inner.position.set(0, -0.5, 0);
  }
  outer.add(inner);
  return outer;
}

function diodeGroup(st) {
  // NOTE: in Minecraft Java a diode's `facing` points toward its INPUT side; the output goes to
  // facing.opposite() (see src/redstone/sim/blocks/diode.py). The shape is built facing north (input at -z,
  // output at +z) and yawed by `facing`.
  const P = st.props, g = new THREE.Group();
  const lit = P.powered === 'true';
  const rep = st.id === 'repeater';
  const slabColor = rep ? (lit ? 0xb06a5c : 0x8e8a80) : (lit ? 0xc0867a : 0xa7a39a);
  g.add(box(1, 0.125, 1, mat(slabColor), 0, -0.5 + 0.0625, 0));
  g.add(arrowMesh(lit ? 0xff4030 : 0x444444, 0.24, -0.08, -0.5 + 0.127));
  const top = -0.5 + 0.125;
  const stub = (x, z, on) => box(0.12, 0.22, 0.12, mat(on ? 0xff3b1f : 0x5a1a10, on ? 0xff2000 : 0), x, top + 0.11, z);
  if (rep) {
    const delay = Math.max(1, Math.min(4, +P.delay || 1));
    g.add(stub(0, 0.34, lit));
    g.add(stub(0, -0.36 + 0.09 * (delay - 1), lit));
    if (P.locked === 'true') g.add(box(0.9, 0.05, 0.06, mat(0x222222), 0, top + 0.03, 0.12));
  } else {
    const sub = P.mode === 'subtract'; // front torch: tall and bright in subtract mode, a short dark stub in compare mode
    const fh = sub ? 0.3 : 0.1;
    g.add(box(0.12, fh, 0.12, mat(sub ? 0xff5a2a : 0x5a1a10, sub ? 0xff3000 : 0), 0, top + fh / 2, 0.34));
    g.add(stub(-0.28, -0.3, lit));
    g.add(stub(0.28, -0.3, lit));
  }
  g.rotation.y = YAW[P.facing] ?? 0;
  return g;
}

function leverGroup(st) {
  const P = st.props, on = P.powered === 'true';
  const g = new THREE.Group();
  g.add(box(0.3, 0.16, 0.4, mat(0x777777), 0, -0.5 + 0.08, 0));
  const pivot = new THREE.Group();
  pivot.position.set(0, -0.5 + 0.16, 0);
  // on a wall the local +z axis ends up pointing up: powered levers point up there, down otherwise
  const sign = (P.face === 'wall') ? -1 : 1;
  pivot.rotation.x = (on ? -0.65 : 0.65) * sign;
  pivot.add(box(0.1, 0.45, 0.1, mat(on ? 0xc8a060 : 0x8b6b3a), 0, 0.225, 0));
  g.add(pivot);
  const out = new THREE.Group();
  out.add(g);
  placeFaced(out, P.face || 'floor', P.facing || 'north');
  return out;
}

function buttonGroup(st) {
  const P = st.props, on = P.powered === 'true';
  const stone = st.id.startsWith('stone') || st.id.startsWith('polished');
  const g = new THREE.Group();
  const h = on ? 0.0625 : 0.125;
  g.add(box(0.375, h, 0.25, mat(stone ? 0x8c8c8c : 0xb08a52, on ? 0x331100 : 0), 0, -0.5 + h / 2, 0));
  const out = new THREE.Group();
  out.add(g);
  placeFaced(out, P.face || 'floor', P.facing || 'north');
  return out;
}

function pistonGroup(st) {
  const P = st.props, id = st.id, g = new THREE.Group();
  const sticky = id === 'sticky_piston';
  const planks = mat(0xb08a52), face = mat(sticky ? 0x7bc255 : 0xb08a52), body = mat(0x808080);
  if (id === 'piston_head') {
    g.add(box(1, 1, 0.25, mat(P.type === 'sticky' ? 0x7bc255 : 0xb08a52), 0, 0, -0.375));
    g.add(box(0.25, 0.25, 0.75, mat(0x6b5233), 0, 0, 0.125));
  } else if (id === 'moving_piston') {
    g.add(box(0.5, 0.5, 0.5, mat(0x909090)));
    return g;
  } else {
    const ext = P.extended === 'true';
    g.add(box(1, 1, 0.75, body, 0, 0, 0.125));
    if (!ext) g.add(box(1, 1, 0.25, face, 0, 0, -0.375));
    else g.add(box(1.01, 1.01, 0.04, planks, 0, 0, -0.35)); // open front
  }
  orientFacing(g, P.facing || 'north');
  return g;
}

function cubeWith(color, mark) {
  const g = new THREE.Group();
  g.add(box(1, 1, 1, mat(color)));
  if (mark) mark(g);
  return g;
}

function slabGroup(st) {
  const P = st.props, id = st.id;
  const { color } = baseColor(id.replace(/_(slab|stairs|carpet)$/, ''), P);
  const g = new THREE.Group();
  const m = mat(color);
  if (id.endsWith('_carpet')) {
    g.add(box(1, 0.0625, 1, m, 0, -0.5 + 0.03, 0));
  } else if (id.endsWith('_slab')) {
    if (P.type === 'double') g.add(box(1, 1, 1, m));
    else g.add(box(1, 0.5, 1, m, 0, P.type === 'top' ? 0.25 : -0.25, 0));
  } else { // stairs: the high step lies on the `facing` side (facing north -> high part at -z)
    // local frame: facing north, high part at -z, left = -x; shapes per Minecraft (straight/inner/outer, left/right)
    const top = P.half === 'top', yb = top ? 0.25 : -0.25, yt = top ? -0.25 : 0.25;
    g.add(box(1, 0.5, 1, m, 0, yb, 0));
    const shape = P.shape || 'straight', sx = shape.endsWith('left') ? -1 : 1;
    if (shape.startsWith('outer')) {
      g.add(box(0.5, 0.5, 0.5, m, sx * 0.25, yt, -0.25));
    } else {
      g.add(box(1, 0.5, 0.5, m, 0, yt, -0.25));
      if (shape.startsWith('inner')) g.add(box(0.5, 0.5, 0.5, m, sx * 0.25, yt, 0.25));
    }
    g.rotation.y = YAW[P.facing] ?? 0;
  }
  return g;
}

function buildObject(st) {
  const id = st.id, P = st.props;
  switch (id) {
    case 'redstone_wire': {
      const pw = +P.power || 0;
      return new THREE.Mesh(wireGeometry(P), mat(wireColor(pw), pw > 0 ? (wireColor(pw) & 0xfefefe) >> 2 : 0));
    }
    case 'redstone_torch': return torchGroup(P.lit === 'true', false);
    case 'redstone_wall_torch': return torchGroup(P.lit === 'true', true, P.facing || 'north');
    case 'repeater': case 'comparator': return diodeGroup(st);
    case 'lever': return leverGroup(st);
    case 'piston': case 'sticky_piston': case 'piston_head': case 'moving_piston': return pistonGroup(st);
    case 'observer': {
      const g = cubeWith(0x6e6e6e, (gr) => {
        gr.add(box(0.7, 0.3, 0.04, mat(0x2a2a2a), 0, 0.15, -0.5));
        gr.add(box(0.12, 0.12, 0.05, mat(0xe0e0e0), -0.2, 0.15, -0.5)); gr.add(box(0.12, 0.12, 0.05, mat(0xe0e0e0), 0.2, 0.15, -0.5));
        gr.add(box(0.2, 0.2, 0.04, mat(P.powered === 'true' ? 0xff3020 : 0x802020, P.powered === 'true' ? 0xff2000 : 0), 0, 0, 0.5));
      });
      orientFacing(g, P.facing || 'north');
      return g;
    }
    case 'dispenser': case 'dropper': {
      const g = cubeWith(0x777777, (gr) => gr.add(box(0.5, 0.5, 0.04, mat(0x2a2a2a), 0, 0, -0.5)));
      orientFacing(g, P.facing || 'north');
      return g;
    }
    case 'chest': case 'trapped_chest': case 'ender_chest': {
      const g = new THREE.Group();
      const wood = id === 'ender_chest' ? 0x1f3a3a : id === 'trapped_chest' ? 0x8a4a2a : 0x9a6a30;
      g.add(box(0.875, 0.875, 0.875, mat(wood), 0, -0.5 + 0.4375, 0));
      g.add(box(0.875, 0.06, 0.875, mat(0x6b4a20), 0, -0.5 + 0.55, 0)); // lid seam
      g.add(box(0.12, 0.16, 0.05, mat(0xc0c0c0), 0, -0.5 + 0.55, -0.45)); // latch on the front (facing side)
      g.rotation.y = YAW[P.facing] ?? 0;
      return g;
    }
    case 'hopper': {
      const g = new THREE.Group(), m = mat(0x4a4a4a), dk = mat(0x1a1a1a);
      g.add(box(1, 0.125, 1, m, 0, 0.4375, 0)); // rim (top)
      g.add(box(0.125, 0.375, 1, m, -0.4375, 0.25, 0)); g.add(box(0.125, 0.375, 1, m, 0.4375, 0.25, 0));
      g.add(box(0.75, 0.375, 0.125, m, 0, 0.25, -0.4375)); g.add(box(0.75, 0.375, 0.125, m, 0, 0.25, 0.4375));
      g.add(box(0.75, 0.04, 0.75, dk, 0, 0.1, 0));
      g.add(box(0.5, 0.25, 0.5, m, 0, -0.1, 0));
      const spout = box(0.25, 0.25, 0.25, m, 0, -0.35, 0);
      const f = P.facing || 'down';
      if (f in DIRS && f !== 'down') { spout.position.set(DIRS[f][0] * 0.375, -0.3, DIRS[f][2] * 0.375); } // spout toward the target inventory
      g.add(spout);
      return g;
    }
    case 'sculk_sensor': case 'calibrated_sculk_sensor': {
      const g = new THREE.Group(), pw = +P.power > 0 || P.sculk_sensor_phase === 'active';
      g.add(box(1, 0.5, 1, mat(id === 'sculk_sensor' ? 0x1f5a66 : 0x2a6b8a, pw ? 0x108090 : 0), 0, -0.25, 0));
      g.add(box(0.5, 0.06, 0.5, mat(0x59d0e0, pw ? 0x30c0d0 : 0), 0, 0.03, 0));
      return g;
    }
    case 'target': return cubeWith(0xf0e8e0, (gr) => gr.add(box(0.55, 0.02, 0.55, mat(0xd03030), 0, 0.5, 0)));
    case 'note_block': return cubeWith(0x7a5230, (gr) => gr.add(box(0.3, 0.02, 0.3, mat(0x222222), 0, 0.5, 0)));
    case 'daylight_detector': case 'daylight_sensor': {
      const g = new THREE.Group();
      g.add(box(1, 0.375, 1, mat(0x8a6a40), 0, -0.3125, 0));
      g.add(box(0.96, 0.02, 0.96, mat(P.inverted === 'true' ? 0x2a3a5a : 0xd8c690), 0, -0.5 + 0.375 + 0.005, 0));
      return g;
    }
    case 'rail': case 'powered_rail': case 'detector_rail': case 'activator_rail': {
      const g = new THREE.Group();
      g.add(box(0.7, 0.04, 1, mat(id === 'powered_rail' && P.powered === 'true' ? 0xd0a030 : 0x8a7a60), 0, -0.48, 0));
      return g;
    }
    default:
      if (id.endsWith('_button')) return buttonGroup(st);
      if (id.endsWith('_slab') || id.endsWith('_stairs') || id.endsWith('_carpet')) return slabGroup(st);
      return cubeWith(baseColor(id, P).color);
  }
}

// --- instanced pool ------------------------------------------------------------------------------------------------

const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _p = new THREE.Vector3(), _s = new THREE.Vector3();
const _c = new THREE.Color();

class Pool {
  constructor(parent, geom, material, cap = 2048) {
    this.parent = parent; this.geom = geom; this.material = material;
    this.cap = 0; this.n = 0; this.free = []; this.keys = []; this.mesh = null;
    this._alloc(cap);
  }

  _alloc(cap) {
    const old = this.mesh;
    const mesh = new THREE.InstancedMesh(this.geom, this.material, cap);
    mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(cap * 3).fill(1), 3);
    mesh.frustumCulled = false;
    mesh.count = this.n;
    const zero = new THREE.Matrix4().makeScale(0, 0, 0);
    for (let i = 0; i < cap; i++) mesh.setMatrixAt(i, zero);
    if (old) {
      mesh.instanceMatrix.array.set(old.instanceMatrix.array);
      mesh.instanceColor.array.set(old.instanceColor.array);
      this.parent.remove(old);
      old.dispose();
    }
    this.cap = cap; this.mesh = mesh;
    this.parent.add(mesh);
  }

  alloc(key) {
    let i;
    if (this.free.length) i = this.free.pop();
    else {
      if (this.n >= this.cap) this._alloc(this.cap * 2);
      i = this.n++;
      this.mesh.count = this.n;
    }
    this.keys[i] = key;
    return i;
  }

  release(i) { this.free.push(i); this.keys[i] = null; this.set(i, 0, 0, 0, false); }

  set(i, x, y, z, visible, color) {
    _p.set(x + 0.5, y + 0.5, z + 0.5);
    const sc = visible ? 0.985 : 0;
    _s.set(sc, sc, sc);
    _m.compose(_p, _q.identity(), _s);
    this.mesh.setMatrixAt(i, _m);
    this.mesh.instanceMatrix.needsUpdate = true;
    if (color !== undefined) {
      const shade = 0.93 + 0.07 * ((x + y + z) & 1);
      _c.setHex(color).multiplyScalar(shade);
      this.mesh.setColorAt(i, _c);
      this.mesh.instanceColor.needsUpdate = true;
    }
    this.mesh.boundingSphere = null;
  }
}

function makeLabel(text, color = '#fff', bg = 'rgba(0,0,0,0.6)', scale = 1) {
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d');
  const font = 'bold 40px system-ui, sans-serif';
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 24;
  c.width = w; c.height = 60;
  ctx.font = font;
  ctx.fillStyle = bg;
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(0, 0, w, 60, 12) : ctx.rect(0, 0, w, 60);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 12, 31);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  sp.scale.set((w / 60) * 0.55 * scale, 0.55 * scale, 1);
  sp.renderOrder = 10;
  return sp;
}

export class Scene3D {
  /** @param {HTMLElement} container  @param {{onHover?:Function,onUse?:Function}} cb */
  constructor(container, cb = {}) {
    this.container = container; this.cb = cb;
    this.entries = new Map(); // key -> {p, s, st, kind, pool, idx, obj, visible}
    this.order = new Map(); // key -> rank (build order)
    this.revealCount = Infinity;
    this.maxY = Infinity;
    this.size = [1, 1, 1];
    this.labels = []; this.ioSprites = [];

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    container.appendChild(this.renderer.domElement);
    this.renderer.domElement.style.cssText = 'width:100%;height:100%;display:block';
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.addEventListener('change', () => this.requestRender());
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x667077, 1.4));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-0.4, 1, 0.6);
    this.scene.add(sun);

    this.root = new THREE.Group(); // blocks
    this.scene.add(this.root);
    this.objRoot = new THREE.Group();
    this.root.add(this.objRoot);
    this.cubes = new Pool(this.root, new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }));
    this.glass = new Pool(this.root, new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshLambertMaterial({ color: 0xffffff, transparent: true, opacity: 0.35, depthWrite: false }), 256);

    this.helpers = new THREE.Group();
    this.scene.add(this.helpers);
    this.hl = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1.02, 1.02, 1.02)),
      new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false }));
    this.hl.visible = false; this.hl.renderOrder = 20;
    this.scene.add(this.hl);

    this.raycaster = new THREE.Raycaster();
    this._bindEvents();
    this.resizeObs = new ResizeObserver(() => this.resize());
    this.resizeObs.observe(container);
    this.setTheme();
    this.resize();
    this._loop();
  }

  setTheme() {
    const css = getComputedStyle(document.documentElement);
    const bg = css.getPropertyValue('--view-bg').trim() || '#20242a';
    this.scene.background = new THREE.Color(bg);
    this.gridColors = [css.getPropertyValue('--grid-a').trim() || '#556', css.getPropertyValue('--grid-b').trim() || '#334'];
    this._rebuildHelpers();
    this.requestRender();
  }

  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  requestRender() { this._dirty = true; }

  _loop() {
    requestAnimationFrame(() => this._loop());
    if (!this._dirty) return;
    this._dirty = false;
    this.renderer.render(this.scene, this.camera);
  }

  // --- model --------------------------------------------------------------------------------------------------------

  setSize(size) {
    const same = size.every((v, i) => v === this.size[i]);
    this.size = size.slice();
    if (!same) this._rebuildHelpers();
  }

  _rebuildHelpers() {
    for (const c of [...this.helpers.children]) {
      this.helpers.remove(c);
      c.geometry?.dispose();
      if (c.material?.map) c.material.map.dispose();
      if (c.material) c.material.dispose?.();
    }
    const [sx, sy, sz] = this.size;
    const span = Math.max(sx, sz) + 4;
    const grid = new THREE.GridHelper(span, span, this.gridColors[0], this.gridColors[1]);
    grid.position.set(sx / 2, -0.002, sz / 2);
    this.helpers.add(grid);
    const lab = (t, x, z) => { const s = makeLabel(t, '#fff', 'rgba(40,40,40,0.65)', 1.2); s.position.set(x, 0.3, z); this.helpers.add(s); };
    lab('N', sx / 2, -1.6); lab('S', sx / 2, sz + 1.6); lab('W', -1.6, sz / 2); lab('O', sx + 1.6, sz / 2);
    this.requestRender();
  }

  fit() {
    const [sx, sy, sz] = this.size;
    const c = new THREE.Vector3(sx / 2, sy / 2, sz / 2);
    const r = Math.max(4, Math.hypot(sx, sy, sz) / 2);
    const d = r / Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2)) * 0.95;
    this.controls.target.copy(c);
    this.camera.position.set(c.x + d * 0.45, c.y + d * 0.65, c.z + d * 0.85);
    this.camera.near = Math.max(0.1, d / 100);
    this.camera.far = d * 10;
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.requestRender();
  }

  _remove(key) {
    const e = this.entries.get(key);
    if (!e) return;
    if (e.pool) e.pool.release(e.idx);
    if (e.obj) this.objRoot.remove(e.obj);
    this.entries.delete(key);
  }

  _visible(e) {
    if (e.p[1] > this.maxY) return false;
    const r = this.order.get(e.key);
    return r === undefined || r < this.revealCount;
  }

  _applyVis(e) {
    const v = this._visible(e);
    if (v === e.visible) return;
    e.visible = v;
    if (e.pool) e.pool.set(e.idx, e.p[0], e.p[1], e.p[2], v);
    else e.obj.visible = v;
  }

  _setBlock(p, s) {
    const key = keyOf(p);
    const old = this.entries.get(key);
    if (isAir(s)) { if (old) this._remove(key); return; }
    if (old && old.s === s) return;
    if (old) this._remove(key);
    const st = parseState(s);
    const kind = classify(st);
    const e = { key, p, s, st, kind, pool: null, idx: -1, obj: null, visible: false };
    if (kind === 'obj') {
      const obj = buildObject(st);
      obj.position.set(p[0] + 0.5, p[1] + 0.5, p[2] + 0.5);
      obj.traverse((o) => { o.userData.key = key; });
      this.objRoot.add(obj);
      e.obj = obj;
    } else {
      e.pool = kind === 'glass' ? this.glass : this.cubes;
      e.idx = e.pool.alloc(key);
      const vis = this._visible(e);
      e.pool.set(e.idx, p[0], p[1], p[2], vis, baseColor(st.id, st.props).color);
      e.visible = vis;
      this.entries.set(key, e);
      return;
    }
    e.visible = undefined;
    this.entries.set(key, e);
    this._applyVis(e);
  }

  /** Replace the displayed world by a block list (diff-based, cheap for similar frames). */
  setBlocks(blocks, size, { fit = false } = {}) {
    if (size) this.setSize(size);
    const seen = new Set();
    for (const b of blocks) { seen.add(keyOf(b.p)); this._setBlock(b.p, b.s); }
    for (const k of [...this.entries.keys()]) if (!seen.has(k)) this._remove(k);
    if (fit) this.fit();
    this.requestRender();
  }

  applyChanges(blocks) {
    for (const b of blocks) this._setBlock(b.p, b.s);
    this.requestRender();
  }

  setReveal(orderPositions) {
    this.order = new Map();
    if (orderPositions) orderPositions.forEach((p, i) => this.order.set(keyOf(p), i));
    this.revealCount = Infinity;
    this._applyAllVis();
  }

  setRevealCount(n) { this.revealCount = n; this._applyAllVis(); }

  setMaxY(y) { this.maxY = y; this._syncIO(); this._applyAllVis(); }

  _applyAllVis() {
    for (const e of this.entries.values()) this._applyVis(e);
    this.requestRender();
  }

  setIO(inputs = [], outputs = []) {
    for (const s of this.ioSprites) { this.scene.remove(s); s.material.map.dispose(); s.material.dispose(); }
    this.ioSprites = [];
    const add = (io, color, bg) => {
      const s = makeLabel(io.name, color, bg, 0.9);
      s.position.set(io.p[0] + 0.5, io.p[1] + 1.35, io.p[2] + 0.5);
      s.userData.y = io.p[1];
      this.scene.add(s);
      this.ioSprites.push(s);
    };
    inputs.forEach((i) => add(i, '#fff', 'rgba(30,90,200,0.85)'));
    outputs.forEach((o) => add(o, '#fff', 'rgba(20,130,60,0.85)'));
    this._syncIO();
  }

  _syncIO() { for (const s of this.ioSprites) s.visible = s.userData.y <= this.maxY; }

  getEntry(key) { return this.entries.get(key); }

  // --- picking ------------------------------------------------------------------------------------------------------

  _pick(ev) {
    const r = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const hits = this.raycaster.intersectObjects([this.cubes.mesh, this.glass.mesh, this.objRoot], true);
    for (const h of hits) {
      let key = null;
      if (h.instanceId !== undefined && h.object.isInstancedMesh) {
        key = (h.object === this.cubes.mesh ? this.cubes : this.glass).keys[h.instanceId];
      } else key = h.object.userData.key;
      const e = key && this.entries.get(key);
      if (e && e.visible) return e;
    }
    return null;
  }

  _bindEvents() {
    const el = this.renderer.domElement;
    let down = null, raf = false, last = null;
    el.addEventListener('pointerdown', (ev) => { down = [ev.clientX, ev.clientY]; });
    el.addEventListener('pointerup', (ev) => {
      if (!down) return;
      const moved = Math.hypot(ev.clientX - down[0], ev.clientY - down[1]);
      down = null;
      if (moved > 4) return;
      const e = this._pick(ev);
      if (e && isInteractive(e.st)) this.cb.onUse?.(e.p);
    });
    el.addEventListener('pointermove', (ev) => {
      last = ev;
      if (raf) return;
      raf = true;
      requestAnimationFrame(() => {
        raf = false;
        if (!last || down) return;
        const e = this._pick(last);
        if (e) { this.hl.position.set(e.p[0] + 0.5, e.p[1] + 0.5, e.p[2] + 0.5); this.hl.visible = true; } else this.hl.visible = false;
        this.requestRender();
        this.cb.onHover?.(e ? { p: e.p, s: e.s } : null, last);
      });
    });
    el.addEventListener('pointerleave', () => { last = null; this.hl.visible = false; this.cb.onHover?.(null); this.requestRender(); });
  }
}
