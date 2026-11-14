// Application glue: sidebar, playback modes (build / design search / simulation), status line.
import { api } from './api.js';
import { Scene3D } from './blocks3d.js';
import { LayerView } from './layers2d.js';
import { stacksText, parseState } from './blockstyle.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

const S = {
  demo: params.get('demo') === '1',
  files: null, path: null, groups: {},
  model: null, modelPath: null,
  mode: 'build',
  playing: false,
  buildN: 0,
  job: null,
  simId: null, simTick: 0, simRunning: false, busy: Promise.resolve(),
  lastSize: [1, 1, 1],
};

// --- helpers ---------------------------------------------------------------------------------------------------------

function setStatus(msg, err = false) {
  const el = $('status');
  el.textContent = msg || '';
  el.classList.toggle('err', err);
}
const fail = (e) => setStatus(e && e.message ? e.message : String(e), true);
const setInfo = (t) => { $('info').textContent = t || ''; };

const tip = $('tip');
let hovered = null; // {info, ev} of the visible tooltip, so it can follow simulation changes
function onHover(info, ev) {
  if (!info || !ev) { tip.hidden = true; hovered = null; return; }
  hovered = { info, ev };
  const [x, y, z] = info.p;
  let name = '';
  const m = S.job && S.mode === 'search' ? null : S.model;
  if (m) {
    const io = [...(m.inputs || []).map((i) => ['Eingang', i]), ...(m.outputs || []).map((o) => ['Ausgang', o])]
      .find(([, i]) => i.p[0] === x && i.p[1] === y && i.p[2] === z);
    if (io) name = `${io[0]} "${io[1].name}"\n`;
  }
  tip.textContent = `${name}(${x}, ${y}, ${z}) ${info.s ? info.s : '(leer)'}`;
  tip.style.whiteSpace = 'pre-wrap';
  tip.hidden = false;
  tip.style.left = Math.min(window.innerWidth - 300, ev.clientX + 14) + 'px';
  tip.style.top = (ev.clientY + 16) + 'px';
}

// --- views -----------------------------------------------------------------------------------------------------------

const v3 = new Scene3D($('box3d'), { onHover, onUse: (p) => useBlock(p) });
const v2 = new LayerView($('box2d'), {
  onHover, onUse: (p) => useBlock(p),
  onLayer: (y) => { $('layerY').value = y; $('layerYVal').textContent = y; },
});
const views = [v3, v2];
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => setTimeout(() => views.forEach((v) => v.setTheme()), 50));

function syncSliders(size) {
  const maxEl = $('maxY'), layEl = $('layerY');
  const top = size[1] - 1;
  const wasTop = +maxEl.value >= +maxEl.max;
  maxEl.max = top; layEl.max = top;
  if (wasTop) maxEl.value = top;
  maxEl.value = Math.min(+maxEl.value, top);
  layEl.value = Math.min(+layEl.value, top);
  $('maxYVal').textContent = maxEl.value; $('layerYVal').textContent = layEl.value;
  v3.setMaxY(+maxEl.value);
  v2.setLayer(+layEl.value);
}

$('maxY').addEventListener('input', (e) => { $('maxYVal').textContent = e.target.value; v3.setMaxY(+e.target.value); });
$('layerY').addEventListener('input', (e) => { $('layerYVal').textContent = e.target.value; v2.setLayer(+e.target.value); });
$('btnFit').addEventListener('click', () => v3.fit());

$('layoutSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  for (const x of $('layoutSeg').children) x.classList.toggle('on', x === b);
  const l = b.dataset.layout;
  $('views').className = l === 'split' ? 'split' : l === '3d' ? 'only3d' : 'only2d';
  setTimeout(() => { v3.resize(); v2.resize(); }, 0);
});

/** Show a full model; `reveal` enables build-order hiding, `fit` re-fits the camera. */
function showModel(model, { reveal = false, fit = false, io = true } = {}) {
  onHover(null);
  v3.setBlocks(model.blocks, model.size, { fit });
  v2.setBlocks(model.blocks, model.size);
  v3.setIO(io ? model.inputs : [], io ? model.outputs : []);
  v2.setIO(io ? model.inputs : [], io ? model.outputs : []);
  for (const v of views) v.setReveal(reveal ? model.build_order : null);
  S.lastSize = model.size.slice();
  syncSliders(model.size);
  $('modelName').textContent = model.name ? `– ${model.name} (${model.size.join('×')})` : '';
}

function renderMaterials(model) {
  const el = $('materials');
  el.textContent = '';
  const mats = (model && model.materials) || [];
  if (!mats.length) { el.innerHTML = '<span class="muted">Kein Material.</span>'; }
  else {
    const t = document.createElement('table');
    t.className = 'mat';
    t.innerHTML = '<thead><tr><th>Gegenstand</th><th class="n">Anzahl</th><th class="n">Stacks</th></tr></thead>';
    const body = document.createElement('tbody');
    let total = 0, stacks = 0;
    for (const m of mats) {
      total += m.count; stacks += Math.ceil(m.count / 64);
      const tr = document.createElement('tr');
      for (const [txt, cls] of [[m.label || m.item, ''], [String(m.count), 'n'], [stacksText(m.count), 'n']]) {
        const td = document.createElement('td'); td.textContent = txt; if (cls) td.className = cls; tr.appendChild(td);
      }
      tr.title = m.item;
      body.appendChild(tr);
    }
    t.appendChild(body);
    const foot = document.createElement('tfoot');
    foot.innerHTML = `<tr><td>Summe</td><td class="n">${total}</td><td></td></tr>` +
      `<tr><td colspan="3" class="muted" style="font-weight:400">${stacks} belegte Plätze ≈ ${Math.ceil(stacks / 27)} Kisten (27 Plätze)</td></tr>`;
    t.appendChild(foot);
    el.appendChild(t);
  }
  const notes = $('notes');
  notes.textContent = '';
  for (const n of (model && model.notes) || []) { const d = document.createElement('div'); d.textContent = '• ' + n; notes.appendChild(d); }
}

// --- files -----------------------------------------------------------------------------------------------------------

function renderFiles() {
  const box = $('fileList');
  box.textContent = '';
  const filt = $('fileFilter').value.trim().toLowerCase();
  const titles = { schematics: 'Schaltpläne', scenarios: 'Szenarien', specs: 'Spezifikationen' };
  for (const g of ['schematics', 'scenarios', 'specs']) {
    const list = (S.groups[g] || []).filter((p) => !filt || p.toLowerCase().includes(filt));
    if (!list.length) continue;
    const h = document.createElement('h3'); h.textContent = `${titles[g]} (${list.length})`; box.appendChild(h);
    for (const p of list) {
      const b = document.createElement('button');
      b.textContent = p.split('/').pop(); b.title = p; b.dataset.path = p; b.dataset.group = g;
      if (p === S.path) b.classList.add('sel');
      b.addEventListener('click', () => selectFile(p, g));
      box.appendChild(b);
    }
  }
  if (!box.children.length) box.innerHTML = '<div class="muted" style="padding:6px">Keine Dateien.</div>';
}
$('fileFilter').addEventListener('input', renderFiles);

async function selectFile(path, group) {
  S.path = path; S.pathGroup = group;
  $('selInfo').textContent = path;
  $('btnRedesign').disabled = S.demo;
  renderFiles();
  if (group === 'specs') {
    setStatus('Spezifikation gewählt: "Entwurf suchen" startet die Suche.');
    return;
  }
  await loadModel(path);
}

async function loadModel(path) {
  stopAll();
  setStatus('Lade ' + path + ' ...');
  try {
    const m = S.demo ? await api.demo() : await api.model(path);
    S.model = m; S.modelPath = path; S.simId = null;
    $('summarySec').hidden = true;
    renderMaterials(m);
    setMode('build', { fit: true });
    setStatus(`${m.blocks.length} Blöcke geladen.`);
  } catch (e) { fail(e); }
}

// --- playback: common ------------------------------------------------------------------------------------------------

function rate() { return 1.5 * Math.pow(1.045, +$('speed').value); }
function updateSpeedLabel() {
  const r = rate();
  $('speedVal').textContent = `${r < 10 ? r.toFixed(1) : Math.round(r)} ${S.mode === 'build' ? 'Blöcke' : 'Bilder'}/s`;
}
$('speed').addEventListener('input', updateSpeedLabel);

function setPlaying(p) {
  S.playing = p;
  $('bPlay').innerHTML = p ? '&#9208;' : '&#9654;';
}

function stopAll() {
  setPlaying(false);
  stopSimRun();
  if (S.job && S.job.timer && S.mode !== 'search') { /* keep polling a running job in the background */ }
}

function setMode(mode, { fit = false } = {}) {
  setPlaying(false);
  stopSimRun();
  S.mode = mode;
  for (const b of $('modeSeg').children) b.classList.toggle('on', b.dataset.mode === mode);
  $('ctlBuild').hidden = mode === 'sim';
  $('ctlSim').hidden = mode !== 'sim';
  $('framesSec').hidden = !(mode === 'search' && S.job);
  $('speedLbl').textContent = mode === 'build' ? 'Blöcke/s' : 'Bilder/s';
  $('speed').value = mode === 'build' ? 40 : 35;
  updateSpeedLabel();
  if (mode === 'build') {
    if (S.model) {
      showModel(S.model, { reveal: true, fit });
      const total = S.model.build_order.length;
      $('progress').max = total;
      setBuild(total);
    } else { setInfo('Bitte eine Datei wählen.'); $('progress').max = 0; }
  } else if (mode === 'search') {
    if (S.job && S.job.frames.length) showFrame(Math.max(0, Math.min(S.job.idx, S.job.frames.length - 1)));
    else { $('progress').max = 0; setInfo(S.job ? 'Suche läuft, noch keine Einzelbilder ...' : 'Keine Entwurfssuche gestartet: links eine Datei wählen und "Entwurf suchen" drücken.'); }
  } else {
    if (S.model && !S.simId) showModel(S.model, { reveal: false, fit });
    refreshSimSrc();
    $('sTick1').disabled = $('sRun').disabled = !S.simId;
    setInfo(S.simId ? 'Simulation läuft. Hebel und Knöpfe lassen sich anklicken.' : 'Quelle wählen und "Simulation starten" drücken.');
  }
}
$('modeSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b && b.dataset.mode !== S.mode) setMode(b.dataset.mode);
});

// --- build instructions ----------------------------------------------------------------------------------------------

function setBuild(n) {
  const order = S.model.build_order, total = order.length;
  n = Math.max(0, Math.min(total, n));
  S.buildN = n;
  for (const v of views) v.setRevealCount(n);
  $('progress').value = n;
  if (n > 0 && n <= total) {
    const p = order[n - 1];
    const st = S.model.blocks.find((b) => b.p[0] === p[0] && b.p[1] === p[1] && b.p[2] === p[2]);
    setInfo(`Block ${n}/${total}: (${p.join(', ')}) ${st ? st.s : ''}`);
  } else setInfo(`Block 0/${total}`);
}

// --- design search ---------------------------------------------------------------------------------------------------

$('btnRedesign').addEventListener('click', startRedesign);

async function startRedesign() {
  if (!S.path) return;
  if (S.job && S.job.timer) clearInterval(S.job.timer);
  stopAll();
  try {
    setStatus('Starte Entwurfssuche ...');
    const { job } = await api.redesign(S.path, Math.max(0, +$('compact').value || 0));
    S.job = { id: job, frames: [], done: false, result: null, idx: -1, since: 0, timer: null, finalShown: false, follow: true };
    $('frameLog').textContent = '';
    $('summarySec').hidden = true;
    setMode('search');
    $('framesSec').hidden = false;
    S.job.timer = setInterval(pollJob, 500);
    pollJob();
  } catch (e) { fail(e); }
}

let polling = false;
async function pollJob() {
  const j = S.job;
  if (!j || polling) return;
  polling = true;
  try {
    const d = await api.job(j.id, j.since);
    if (j !== S.job) return;
    const wasLast = j.idx === j.frames.length - 1;
    for (const f of d.frames || []) {
      j.frames.push(f);
      j.since = f.i + 1;
      addFrameLog(f, j.frames.length - 1);
    }
    if (S.mode === 'search') {
      $('progress').max = Math.max(0, j.frames.length - 1);
      if (j.frames.length && (j.idx < 0 || (wasLast && j.follow && !S.playing))) showFrame(j.frames.length - 1);
    }
    if (d.done) {
      clearInterval(j.timer); j.timer = null; j.done = true;
      if (d.error) { setStatus('Entwurfssuche fehlgeschlagen: ' + d.error, true); }
      if (d.result) {
        j.result = d.result;
        $('summary').textContent = d.result.summary || '';
        $('summarySec').hidden = !d.result.summary;
        setStatus(`Entwurfssuche fertig (${j.frames.length} Bilder).`);
        refreshSimSrc();
        if (S.mode === 'search' && !S.playing && j.idx === j.frames.length - 1 && !j.finalShown) showResult();
      } else if (!d.error) setStatus('Entwurfssuche beendet ohne Ergebnis.');
    } else if (S.mode === 'search') setStatus(`Suche läuft ... ${j.frames.length} Bilder`);
  } catch (e) {
    if (j === S.job) { clearInterval(j.timer); j.timer = null; fail(e); }
  } finally { polling = false; }
}

function addFrameLog(f, i) {
  const d = document.createElement('div');
  d.dataset.i = i;
  const mark = f.phase === 'compact' ? (f.accepted ? '<span class="ok">✓</span> ' : '<span class="no">✗</span> ') : '<span class="ok">●</span> ';
  d.innerHTML = mark;
  d.appendChild(document.createTextNode(`${i + 1} ${f.phase}: ${f.label}`));
  d.addEventListener('click', () => { setPlaying(false); S.job.follow = false; showFrame(i); });
  $('frameLog').appendChild(d);
}

function showFrame(i) {
  const j = S.job;
  if (!j || !j.frames.length) return;
  i = Math.max(0, Math.min(j.frames.length - 1, i));
  const first = j.idx < 0 || !j.shownFrame;
  const f = j.frames[i];
  j.idx = i; j.shownFrame = true;
  v3.setBlocks(f.blocks, f.size, { fit: first });
  v2.setBlocks(f.blocks, f.size);
  for (const v of views) { v.setReveal(null); v.setIO([], []); }
  syncSliders(f.size);
  $('progress').max = j.frames.length - 1;
  $('progress').value = i;
  const mark = f.phase === 'compact' ? (f.accepted ? ' ✓ übernommen' : ' ✗ verworfen') : '';
  setInfo(`Bild ${i + 1}/${j.frames.length} · ${f.phase === 'compose' ? 'Zusammensetzen' : 'Kompaktieren'}${mark} · ${f.label} · ${f.blocks.length} Blöcke`);
  const log = $('frameLog');
  log.querySelector('.cur')?.classList.remove('cur');
  const row = log.children[i];
  if (row) { row.classList.add('cur'); row.scrollIntoView({ block: 'nearest' }); }
  j.follow = i === j.frames.length - 1;
}

function showResult() {
  const j = S.job;
  if (!j || !j.result) return;
  j.finalShown = true;
  S.model = j.result; S.modelPath = null; S.fromJob = true;
  showModel(j.result, { reveal: false, fit: true });
  renderMaterials(j.result);
  $('summarySec').hidden = !j.result.summary;
  setInfo('Ergebnis der Entwurfssuche (bester Entwurf). Unter "Bauanleitung" lässt er sich Block für Block nachbauen.');
}

// --- playback buttons ------------------------------------------------------------------------------------------------

function seek(delta) {
  if (S.mode === 'build' && S.model) setBuild(S.buildN + delta);
  else if (S.mode === 'search' && S.job) { S.job.follow = false; showFrame(S.job.idx + delta); }
}
$('bBack').addEventListener('click', () => { setPlaying(false); seek(-1); });
$('bStep').addEventListener('click', () => { setPlaying(false); seek(1); });
$('bPlay').addEventListener('click', () => {
  if (S.playing) return setPlaying(false);
  if (S.mode === 'build') {
    if (!S.model) return;
    if (S.buildN >= S.model.build_order.length) setBuild(0);
  } else if (S.mode === 'search') {
    if (!S.job || !S.job.frames.length) return;
    if (S.job.idx >= S.job.frames.length - 1 && S.job.done) { S.job.finalShown = false; showFrame(0); }
  }
  setPlaying(true);
});
$('progress').addEventListener('input', (e) => {
  setPlaying(false);
  const v = +e.target.value;
  if (S.mode === 'build' && S.model) setBuild(v);
  else if (S.mode === 'search' && S.job) { S.job.follow = false; showFrame(v); }
});

let acc = 0, lastT = 0;
function loop(now) {
  requestAnimationFrame(loop);
  const dt = Math.min(0.25, (now - lastT) / 1000);
  lastT = now;
  if (!S.playing) { acc = 0; return; }
  acc += dt * rate();
  const k = Math.floor(acc);
  if (k < 1) return;
  acc -= k;
  if (S.mode === 'build' && S.model) {
    setBuild(S.buildN + k);
    if (S.buildN >= S.model.build_order.length) setPlaying(false);
  } else if (S.mode === 'search' && S.job) {
    const j = S.job, last = j.frames.length - 1;
    if (j.idx + k >= last) {
      showFrame(last);
      if (j.done) { setPlaying(false); if (j.result && !j.finalShown) showResult(); }
      // else: live job, keep waiting for new frames
    } else showFrame(j.idx + k);
  }
}
requestAnimationFrame(loop);

// --- simulation ------------------------------------------------------------------------------------------------------

function refreshSimSrc() {
  const sel = $('simSrc'), prev = sel.value;
  sel.textContent = '';
  const add = (v, t) => { const o = document.createElement('option'); o.value = v; o.textContent = t; sel.appendChild(o); };
  if (S.modelPath) add('file', 'Datei: ' + S.modelPath.split('/').pop());
  if (S.job && S.job.done && S.job.result) add('job', 'Entwurf der Suche');
  if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
  else if (S.fromJob && S.job?.result) sel.value = 'job';
  $('sStart').disabled = S.demo || !sel.options.length;
}

$('sStart').addEventListener('click', async () => {
  const src = $('simSrc').value;
  if (!src) return;
  stopSimRun();
  try {
    setStatus('Starte Simulation ...');
    const body = src === 'job' ? { job: S.job.id } : { path: S.modelPath };
    const r = await api.sim(body);
    S.simId = r.sim; S.simTick = r.tick;
    showModel(r.model, { reveal: false, fit: false });
    $('tickOut').textContent = 'Tick ' + r.tick;
    $('sTick1').disabled = $('sRun').disabled = false;
    setInfo('Simulation läuft. Hebel und Knöpfe lassen sich anklicken (3D oder Ebenenansicht).');
    setStatus('Simulation gestartet.');
  } catch (e) { fail(e); }
});

// Serialise all sim requests so ticks and clicks never overlap.
function simCall(fn) {
  const p = S.busy.then(fn);
  S.busy = p.catch(() => {});
  return p;
}
function applySim(r) {
  S.simTick = r.tick;
  $('tickOut').textContent = 'Tick ' + r.tick;
  if (r.changed && r.changed.length) for (const v of views) v.applyChanges(r.changed);
  if (hovered) {
    const [x, y, z] = hovered.info.p;
    const c = (r.changed || []).find((b) => b.p[0] === x && b.p[1] === y && b.p[2] === z);
    if (c) onHover({ p: hovered.info.p, s: c.s === 'air' ? null : c.s }, hovered.ev);
  }
}
async function simTicks(n) {
  if (!S.simId) return;
  try { applySim(await simCall(() => api.tick(S.simId, n))); } catch (e) { stopSimRun(); fail(e); }
}
async function useBlock(p) {
  if (!S.simId || S.mode !== 'sim') { setStatus('Zum Schalten zuerst die Simulation starten (Modus "Simulation").'); return; }
  try {
    const r = await simCall(() => api.use(S.simId, p));
    applySim(r);
    setStatus(`Bedient: (${p.join(', ')})`);
  } catch (e) { fail(e); }
}
$('sTick1').addEventListener('click', () => simTicks(1));
$('simSpeed').addEventListener('input', (e) => { $('simSpeedVal').textContent = e.target.value; });

function stopSimRun() {
  S.simRunning = false;
  clearTimeout(S.simTimer);
  const b = $('sRun');
  if (b) b.classList.remove('primary');
}
$('sRun').addEventListener('click', () => {
  if (S.simRunning) return stopSimRun();
  S.simRunning = true;
  $('sRun').classList.add('primary');
  const step = async () => {
    if (!S.simRunning) return;
    await simTicks(+$('simSpeed').value);
    if (S.simRunning) S.simTimer = setTimeout(step, 100);
  };
  step();
});

// --- start -----------------------------------------------------------------------------------------------------------

async function init() {
  updateSpeedLabel();
  if (S.demo) {
    S.groups = { schematics: ['demo/model.json'] };
    renderFiles();
    setStatus('Demomodus: nur Modellansicht und Bauanleitung verfügbar.');
    $('btnRedesign').disabled = true;
    $('selInfo').textContent = 'demo/model.json';
    S.path = 'demo/model.json';
    await loadModel(S.path);
    return;
  }
  try {
    const f = await api.files();
    S.groups = f;
    renderFiles();
    setStatus('Bereit. Datei links wählen.');
    const initial = params.get('path');
    if (initial) {
      const g = ['schematics', 'scenarios', 'specs'].find((k) => (f[k] || []).includes(initial)) || 'schematics';
      await selectFile(initial, g);
    }
  } catch (e) { fail(e); }
}
init();
