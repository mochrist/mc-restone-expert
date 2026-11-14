// Application glue: sidebar, playback modes (build / design search / simulation), reports, status line.
import { api } from './api.js';
import { Scene3D } from './blocks3d.js';
import { LayerView } from './layers2d.js';
import { stacksText } from './blockstyle.js';
import { DocPane, renderMarkdown, svgImage, saveBlob } from './docs.js';
import { openSpecEditor } from './speceditor.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

const S = {
  demo: params.get('demo') === '1',
  files: null, path: null, pathGroup: null, groups: {},
  model: null, modelPath: null, modelGroup: null, fromJob: false,
  mode: 'build',
  playing: false,
  buildN: 0,
  job: null,
  simId: null, simTick: 0, simRunning: false, busy: Promise.resolve(), simModel: null, simState: new Map(),
  lastSize: [1, 1, 1],
  layout: 'split',
};

// --- helpers ---------------------------------------------------------------------------------------------------------

function setStatus(msg, err = false) {
  const el = $('status');
  el.textContent = msg || '';
  el.classList.toggle('err', err);
}
const fail = (e) => setStatus(e && e.message ? e.message : String(e), true);
const setInfo = (t) => { $('info').textContent = t || ''; };
const baseName = (p) => p.split('/').pop();
const stem = (p) => baseName(p).replace(/\.[^.]+$/, '');
const isOwn = (p) => p.startsWith('.cache/gui/'); // uploaded or written in the GUI

function node(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

/** Run a server action with a status line and a disabled button while it runs. */
async function busyWith(button, message, fn) {
  if (button) button.disabled = true;
  setStatus(message);
  try { return await fn(); } catch (e) { fail(e); return undefined; } finally { if (button) button.disabled = false; updateActions(); }
}

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
const resizeViews = () => setTimeout(() => { v3.resize(); v2.resize(); }, 0);

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

function setLayout(l) {
  if (l === 'doc' && !docs.show()) { setStatus('Noch kein Bericht: z. B. "Analysieren" oder "Neue Spezifikation" wählen.'); return; }
  S.layout = l;
  for (const x of $('layoutSeg').children) x.classList.toggle('on', x.dataset.layout === l);
  $('views').className = { split: 'split', '3d': 'only3d', '2d': 'only2d', doc: 'onlydoc' }[l] || 'split';
  resizeViews();
}
$('layoutSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) setLayout(b.dataset.layout);
});

const docs = new DocPane({
  pane: $('paneDoc'), tabs: $('docTabs'), body: $('docBody'), save: $('docSave'), close: $('docClose'),
  onToggle: (open) => { if (!open && S.layout === 'doc') setLayout('split'); else resizeViews(); },
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
      b.textContent = (isOwn(p) ? '✎ ' : '') + baseName(p);
      b.title = isOwn(p) ? `${p} (hochgeladen oder in der Oberfläche geschrieben)` : p;
      b.dataset.path = p; b.dataset.group = g;
      if (p === S.path) b.classList.add('sel');
      b.addEventListener('click', () => selectFile(p, g));
      box.appendChild(b);
    }
  }
  if (!box.children.length) box.innerHTML = '<div class="muted" style="padding:6px">Keine Dateien.</div>';
}
$('fileFilter').addEventListener('input', renderFiles);

async function refreshFiles() {
  S.groups = await api.files();
  renderFiles();
}

async function selectFile(path, group) {
  S.path = path; S.pathGroup = group;
  renderFiles();
  updateActions();
  if (group === 'specs') return editSpec(path);
  await loadModel(path, group);
}

async function loadModel(path, group = 'schematics') {
  stopAll();
  setStatus('Lade ' + path + ' ...');
  try {
    const m = S.demo ? await api.demo() : await api.model(path);
    S.model = m; S.modelPath = path; S.modelGroup = group; S.fromJob = false;
    endSim();
    renderMaterials(m);
    setMode('build', { fit: true });
    setStatus(`${m.blocks.length} Blöcke geladen.`);
  } catch (e) { fail(e); }
  updateActions();
}

/** The circuit the sidebar actions work on: the shown result of a search or the loaded file. */
function currentRef() {
  if (S.fromJob && S.job && S.job.result && S.job.result.blocks) return { job: S.job.id };
  return S.modelPath ? { path: S.modelPath } : null;
}
const currentName = () => (S.fromJob && S.model ? S.model.name : S.modelPath ? stem(S.modelPath) : 'schaltung');

function updateActions() {
  const ref = S.demo ? null : currentRef();
  const scenario = !!ref && !ref.job && S.modelGroup === 'scenarios';
  const specSel = S.pathGroup === 'specs';
  $('selInfo').textContent = ref && ref.job ? `Entwurf der Suche: ${S.model.name}`
    : S.path ? S.path : 'Keine Datei gewählt.';
  $('btnExplain').disabled = $('btnDump').disabled = $('btnExport').disabled = !ref;
  $('btnScenario').hidden = $('oracleRow').hidden = !scenario;
  $('btnSpecEdit').hidden = !specSel;
  $('btnRedesign').disabled = S.demo || !S.path;
  $('btnShowResult').hidden = !(S.job && S.job.result && S.job.result.blocks) || S.fromJob;
  const sel = $('exportFmt');
  for (const o of sel.options) {
    o.hidden = o.disabled = (o.dataset.for === 'scenario' && !scenario) || (o.dataset.for === 'job' && !(ref && ref.job));
  }
  if (sel.selectedOptions[0] && sel.selectedOptions[0].disabled) sel.value = 'litematic';
}

// upload: button, file dialog, drag and drop
async function uploadFiles(fileList) {
  const files = [...fileList];
  if (!files.length || S.demo) return;
  let last = null;
  for (const f of files) {
    setStatus(`Lade ${f.name} hoch ...`);
    try { last = await api.upload(f); } catch (e) { fail(new Error(`${f.name}: ${e.message}`)); return; }
  }
  await refreshFiles().catch(fail);
  if (last) await selectFile(last.path, last.group);
}
$('btnOpen').addEventListener('click', () => $('fileInput').click());
$('fileInput').addEventListener('change', (e) => { uploadFiles(e.target.files); e.target.value = ''; });
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
window.addEventListener('dragenter', (e) => { if (hasFiles(e)) { dragDepth++; $('drop').hidden = false; } });
window.addEventListener('dragleave', (e) => { if (hasFiles(e) && --dragDepth <= 0) { dragDepth = 0; $('drop').hidden = true; } });
window.addEventListener('dragover', (e) => { if (hasFiles(e)) e.preventDefault(); });
window.addEventListener('drop', (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0; $('drop').hidden = true;
  uploadFiles(e.dataTransfer.files);
});

// --- reports: analysis, text view, scenario run, oracle, export ------------------------------------------------------

$('btnExplain').addEventListener('click', () => {
  const ref = currentRef(), name = currentName();
  if (!ref) return;
  busyWith($('btnExplain'), `Analysiere ${name} (Simulationsläufe) ...`, async () => {
    const r = await api.explain(ref);
    docs.set('explain', {
      title: 'Analyse', node: renderMarkdown(r.markdown, r.svgs),
      download: { name: `${name}-analyse.md`, text: r.markdown, type: 'text/markdown;charset=utf-8' },
    });
    setStatus('Analyse fertig.');
  });
});

$('btnDump').addEventListener('click', () => {
  const ref = currentRef(), name = currentName();
  if (!ref) return;
  busyWith($('btnDump'), 'Erzeuge Text-Ansicht ...', async () => {
    const r = await api.dump(ref, { states: true });
    const box = node('div');
    box.appendChild(node('h2', `Text-Ansicht: ${name}`));
    box.appendChild(node('pre', r.text));
    docs.set('dump', { title: 'Text', node: box, download: { name: `${name}-ebenen.txt`, text: r.text } });
    setStatus('Text-Ansicht fertig.');
  });
});

function goldenNote(box, cmp, what) {
  if (!cmp) return;
  box.appendChild(node('p', cmp.matches ? `✓ ${what}: identisch.` : `✗ ${what}: ${cmp.count} Abweichungen.`, cmp.matches ? 'good' : 'bad'));
  if (!cmp.matches) {
    box.appendChild(node('pre', cmp.mismatches.join('\n') + (cmp.count > cmp.mismatches.length ? `\n… ${cmp.count - cmp.mismatches.length} weitere` : '')));
  }
}

$('btnScenario').addEventListener('click', () => {
  const path = S.modelPath;
  if (!path) return;
  busyWith($('btnScenario'), `Szenario ${stem(path)} läuft im Simulator ...`, async () => {
    const r = await api.scenario(path);
    const box = node('div');
    box.appendChild(node('h2', `Szenario: ${r.name}`));
    if (r.description) box.appendChild(node('p', r.description));
    box.appendChild(node('p', `${r.ticks} Ticks im Simulator.`));
    if (r.golden) goldenNote(box, r.golden, 'Vergleich mit der Aufnahme aus dem Spiel (Golden Trace)');
    else box.appendChild(node('p', 'Zu diesem Szenario gibt es keine Aufnahme aus dem Spiel ("Im Spiel prüfen" nimmt eine auf).', 'muted'));
    for (const w of r.warnings) box.appendChild(node('p', 'Warnung: ' + w, 'bad'));
    box.appendChild(svgImage(r.svg, 'Zeitdiagramm'));
    box.appendChild(node('pre', r.diagram));
    docs.set('scenario', { title: 'Szenario', node: box, download: { name: `${r.name}.svg`, text: r.svg, type: 'image/svg+xml' } });
    setStatus(r.golden ? (r.golden.matches ? 'Szenario stimmt mit dem Spiel überein.' : 'Szenario weicht vom Spiel ab.') : 'Szenario fertig.', !!r.golden && !r.golden.matches);
  });
});

let oracle = null; // {id, timer, started}
$('btnOracle').addEventListener('click', async () => {
  const path = S.modelPath;
  if (!path || oracle) return;
  const golden = $('oracleGolden').checked;
  try {
    const { job } = await api.oracle(path, golden);
    const box = node('div');
    box.appendChild(node('h2', `Im Spiel: ${stem(path)}`));
    const state = node('p', '');
    box.appendChild(state);
    docs.set('oracle', { title: 'Im Spiel', node: box });
    oracle = { id: job, started: Date.now() };
    $('btnOracle').disabled = true;
    const poll = async () => {
      const secs = Math.round((Date.now() - oracle.started) / 1000);
      state.textContent = `Der Minecraft-Server läuft (${secs} s; üblich sind ein bis drei Minuten, beim ersten Mal länger) ...`;
      let d;
      try { d = await api.job(oracle.id, 0); } catch (e) { d = { done: true, error: e.message }; }
      if (!d.done) return;
      clearInterval(oracle.timer); oracle = null; $('btnOracle').disabled = false;
      if (d.error) { state.textContent = d.error; state.className = 'bad'; setStatus(d.error, true); return; }
      const r = d.result;
      state.textContent = `Aufnahme fertig nach ${secs} s: ${r.ticks} Ticks.`;
      goldenNote(box, r.simulator, 'Vergleich Spiel ↔ Simulator');
      if (r.written) box.appendChild(node('p', `Als Golden Trace gespeichert: ${r.written}`));
      box.appendChild(svgImage(r.svg, 'Zeitdiagramm'));
      box.appendChild(node('pre', r.diagram));
      docs.docs.get('oracle').download = { name: `${r.name}-spiel.svg`, text: r.svg, type: 'image/svg+xml' };
      if (docs.current === 'oracle') docs.show('oracle');
      setStatus(r.simulator.matches ? 'Spiel und Simulator stimmen überein.' : 'Spiel und Simulator weichen ab.', !r.simulator.matches);
    };
    oracle.timer = setInterval(poll, 2000);
    poll();
    setStatus('Aufnahme im Spiel gestartet.');
  } catch (e) { fail(e); }
});

$('btnExport').addEventListener('click', () => {
  const ref = currentRef();
  if (!ref) return;
  busyWith($('btnExport'), 'Erzeuge Datei ...', async () => {
    const { blob, name } = await api.download(ref, $('exportFmt').value);
    saveBlob(blob, name);
    setStatus(`${name} heruntergeladen.`);
  });
});

// --- spec editor -----------------------------------------------------------------------------------------------------

const specEditor = openSpecEditor({
  docs, api, setStatus, fail,
  onSaved: async (path) => { await refreshFiles(); S.path = path; S.pathGroup = 'specs'; renderFiles(); updateActions(); },
  onSearch: (path) => startRedesign(path),
});
async function editSpec(path) {
  try {
    const r = await api.text(path);
    specEditor.open({ name: stem(path), text: r.text, path });
    setStatus('Spezifikation geladen: im Editor ändern oder gleich "Entwurf suchen".');
  } catch (e) { fail(e); }
}
$('btnNewSpec').addEventListener('click', () => { if (!S.demo) specEditor.open({ name: 'meine-schaltung', text: null, path: null }); });
$('btnSpecEdit').addEventListener('click', () => { if (S.path && S.pathGroup === 'specs') editSpec(S.path); });

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
    if (S.simId && S.simModel) {
      showModel(S.simModel, { reveal: false, fit });
      const now = [...S.simState].map(([k, s]) => ({ p: k.split(',').map(Number), s }));
      for (const v of views) { v.setBlocks(now.filter((b) => b.s !== 'air'), S.simModel.size, { fit: false }); v.setIO(S.simModel.inputs, S.simModel.outputs); }
    } else if (S.model) showModel(S.model, { reveal: false, fit });
    refreshSimSrc();
    $('sTick1').disabled = $('sRun').disabled = !S.simId;
    setInfo(S.simId ? 'Simulation läuft. Hebel und Knöpfe lassen sich anklicken.' : 'Quelle wählen und "Simulation starten" drücken.');
  }
  renderIO();
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

$('btnRedesign').addEventListener('click', async () => {
  if (!S.path) return;
  // a spec that is open in the editor is searched as edited
  if (S.pathGroup === 'specs' && specEditor.path === S.path) {
    const path = await specEditor.commit();
    if (path) startRedesign(path);
  } else startRedesign(S.path);
});

function searchOptions() {
  const num = (id) => ($(id).value.trim() === '' ? undefined : +$(id).value);
  const txt = (id) => $(id).value.trim() || undefined;
  return {
    compact: Math.max(0, Math.round(num('compact') ?? 100)), time: num('optTime') ?? 60, top: Math.max(1, Math.round(num('optTop') ?? 10)),
    max_size: txt('optSize'), max_delay: num('optDelay'), allow: txt('optAllow'), forbid: txt('optForbid'),
    outputs: txt('optOutputs'), no_qc: $('optNoQc').checked,
  };
}

async function startRedesign(path) {
  if (S.job && S.job.timer) clearInterval(S.job.timer);
  stopAll();
  try {
    setStatus('Starte Entwurfssuche ...');
    const { job } = await api.redesign(path, searchOptions());
    S.job = { id: job, path, frames: [], done: false, result: null, idx: -1, since: 0, timer: null, finalShown: false, follow: true };
    if (S.fromJob) { S.fromJob = false; }
    $('frameLog').textContent = '';
    docs.remove('report');
    setMode('search');
    $('framesSec').hidden = false;
    S.job.timer = setInterval(pollJob, 500);
    pollJob();
  } catch (e) { fail(e); }
  updateActions();
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
        if (d.result.summary) {
          docs.set('report', {
            title: 'Entwurfsbericht', node: renderMarkdown(d.result.summary),
            download: { name: `${stem(j.path)}-redesign.md`, text: d.result.summary, type: 'text/markdown;charset=utf-8' },
          });
        }
        if (!d.error) setStatus(`Entwurfssuche fertig (${j.frames.length} Bilder).`);
        refreshSimSrc();
        if (d.result.blocks && S.mode === 'search' && !S.playing && j.idx === j.frames.length - 1 && !j.finalShown) showResult();
      } else if (!d.error) setStatus('Entwurfssuche beendet ohne Ergebnis.');
      updateActions();
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

/** Make the best design of the search the current circuit (materials, build guide, analysis, export ...). */
function showResult() {
  const j = S.job;
  if (!j || !j.result || !j.result.blocks) return;
  j.finalShown = true;
  S.model = j.result; S.modelPath = null; S.modelGroup = null; S.fromJob = true;
  endSim();
  showModel(j.result, { reveal: false, fit: true });
  renderMaterials(j.result);
  setInfo('Ergebnis der Entwurfssuche (bester Entwurf). Analysieren, simulieren, herunterladen oder unter "Bauanleitung" Block für Block nachbauen.');
  updateActions();
}
$('btnShowResult').addEventListener('click', () => { showResult(); setMode('build', { fit: true }); });

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
  if (S.modelPath) add('file', 'Datei: ' + baseName(S.modelPath));
  if (S.job && S.job.done && S.job.result && S.job.result.blocks) add('job', 'Entwurf der Suche');
  if (S.fromJob && [...sel.options].some((o) => o.value === 'job')) sel.value = 'job';
  else if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
  $('sStart').disabled = S.demo || !sel.options.length;
}

function endSim() {
  stopSimRun();
  S.simId = null; S.simModel = null; S.simState = new Map();
  $('sStart').textContent = 'Simulation starten';
  $('sTick1').disabled = $('sRun').disabled = true;
  renderIO();
}

$('sStart').addEventListener('click', async () => {
  const src = $('simSrc').value;
  if (!src) return;
  stopSimRun();
  try {
    setStatus('Starte Simulation ...');
    const body = src === 'job' ? { job: S.job.id } : { path: S.modelPath };
    const r = await api.sim(body);
    S.simId = r.sim; S.simTick = r.tick; S.simModel = r.model;
    S.simState = new Map(r.model.blocks.map((b) => [b.p.join(','), b.s]));
    showModel(r.model, { reveal: false, fit: false });
    $('tickOut').textContent = 'Tick ' + r.tick;
    $('sTick1').disabled = $('sRun').disabled = false;
    $('sStart').textContent = 'Neu starten';
    renderIO();
    setInfo('Simulation läuft. Hebel und Knöpfe lassen sich anklicken (3D, Ebenenansicht oder links unter "Ein- und Ausgänge").');
    setStatus('Simulation gestartet.');
  } catch (e) { fail(e); }
});

const isOn = (s) => !!s && (/(?:powered|lit|extended|open)=true/.test(s) || /power=[1-9]/.test(s) || /\|output=[1-9]/.test(s));

/** Inputs as buttons and outputs as lights, by name: handy when the levers are hard to find in the view. */
function renderIO() {
  const m = S.simModel;
  const show = S.mode === 'sim' && !!S.simId && !!m && (m.inputs.length + m.outputs.length) > 0;
  $('ioSec').hidden = !show;
  if (!show) return;
  const fill = (box, items, make) => {
    box.textContent = '';
    for (const it of items) {
      const s = S.simState.get(it.p.join(','));
      const e = make(it);
      e.textContent = it.name;
      e.classList.toggle('on', isOn(s));
      e.title = `(${it.p.join(', ')}) ${s || ''}`;
      box.appendChild(e);
    }
  };
  fill($('ioIn'), m.inputs, (it) => {
    const b = document.createElement('button');
    b.addEventListener('click', () => useBlock(it.p));
    return b;
  });
  fill($('ioOut'), m.outputs, () => document.createElement('span'));
}

// Serialise all sim requests so ticks and clicks never overlap.
function simCall(fn) {
  const p = S.busy.then(fn);
  S.busy = p.catch(() => {});
  return p;
}
function applySim(r) {
  S.simTick = r.tick;
  $('tickOut').textContent = 'Tick ' + r.tick;
  if (r.changed && r.changed.length) {
    for (const c of r.changed) S.simState.set(c.p.join(','), c.s);
    for (const v of views) v.applyChanges(r.changed);
    renderIO();
  }
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

// --- simulator core --------------------------------------------------------------------------------------------------

let core = 'rust';
$('coreSel').addEventListener('change', async (e) => {
  try {
    core = (await api.setCore(e.target.value)).core;
    setStatus(`Simulatorkern: ${core === 'rust' ? 'Rust' : 'Python (Referenz, deutlich langsamer)'}. Gilt für neue Simulationen, Analysen und Suchen.`);
  } catch (err) { fail(err); }
  e.target.value = core;
});

// --- start -----------------------------------------------------------------------------------------------------------

async function init() {
  updateSpeedLabel();
  updateActions();
  if (S.demo) {
    S.groups = { schematics: ['demo/model.json'] };
    renderFiles();
    for (const id of ['btnOpen', 'btnNewSpec', 'coreSel']) $(id).disabled = true;
    S.path = 'demo/model.json';
    await loadModel(S.path);
    setStatus('Demomodus: nur Modellansicht und Bauanleitung verfügbar.');
    return;
  }
  try {
    const f = await api.files();
    S.groups = f;
    renderFiles();
    setStatus('Bereit. Datei links wählen, eigene Datei öffnen oder eine neue Spezifikation schreiben.');
    api.info().then((i) => {
      core = i.core; $('coreSel').value = core;
      if (!i.rust) { const o = $('coreSel').querySelector('option[value="rust"]'); o.disabled = true; o.textContent = 'Rust (nicht gebaut)'; }
    }).catch(() => {});
    const initial = params.get('path');
    if (initial) {
      const g = ['schematics', 'scenarios', 'specs'].find((k) => (f[k] || []).includes(initial)) || 'schematics';
      await selectFile(initial, g);
    }
    // ?layout=3d|2d|split|doc and ?y=<layer> (handy for screenshots)
    const lay = params.get('layout');
    if (lay) setLayout(lay);
    const cam = (params.get('cam') || '').split(',').map(Number); // ?cam=px,py,pz,tx,ty,tz
    if (cam.length === 6 && cam.every(Number.isFinite)) {
      v3.camera.position.set(cam[0], cam[1], cam[2]); v3.controls.target.set(cam[3], cam[4], cam[5]);
      v3.controls.update(); v3.requestRender();
    }
    const yy = params.get('y');
    if (yy !== null && yy !== '') {
      const ly = Math.max(0, Math.min(S.lastSize[1] - 1, +yy || 0));
      $('layerY').value = ly; $('layerYVal').textContent = ly; v2.setLayer(ly);
    }
    // ?click=btnExplain,sStart,... presses these buttons one after the other (tests, screenshots);
    // mode:sim / mode:search / mode:build switch the mode, a number waits that many milliseconds
    for (const step of (params.get('click') || '').split(',').filter(Boolean)) {
      if (step.startsWith('mode:')) setMode(step.slice(5));
      else if (/^\d+$/.test(step)) await new Promise((r) => setTimeout(r, +step));
      else { $(step)?.click(); await new Promise((r) => setTimeout(r, 1200)); }
    }
  } catch (e) { fail(e); }
}
init();
