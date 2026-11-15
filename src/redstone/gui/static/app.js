// Application glue. Layout: file library (left), views with the transport bar (middle), work panel with one tab
// per task (right): build, simulate, analyze, design. The "current circuit" is the loaded file or the best
// design of the last search; every task works on it.
import { api } from './api.js';
import { Scene3D } from './blocks3d.js';
import { LayerView } from './layers2d.js';
import { stacksText } from './blockstyle.js';
import { DocPane, renderMarkdown, svgImage, saveBlob } from './docs.js';
import { openSpecEditor } from './speceditor.js';
import { initWizard } from './wizard.js';
import { icon, applyIcons } from './icons.js';

applyIcons();

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const TASKS = { build: 'taskBuild', sim: 'taskSim', analyze: 'taskAnalyze', design: 'taskDesign', chat: 'taskChat' };
const GROUP_TITLES = { schematics: 'Schaltpläne', scenarios: 'Beispiele', specs: 'Vorgaben' };
// a few examples with plain names on top of the long list
const FEATURED = [
  ['scenarios/cmp-adder2.yaml', 'Addierer für zwei 2-Bit-Zahlen'],
  ['scenarios/tpl-xor2-comparator.yaml', 'Entweder-oder (XOR)'],
  ['scenarios/tpl-and2-torch.yaml', 'Beide Hebel nötig (UND)'],
  ['scenarios/seq-t-flip-flop-copper-bulb-button.yaml', 'Ein/Aus per Knopf'],
  ['scenarios/seq-monostable-comparator.yaml', 'Kurzer Impuls'],
  ['scenarios/seq-clock-repeater-ring.yaml', 'Blinker'],
  ['scenarios/seq-rs-latch-torch.yaml', 'An-Knopf und Aus-Knopf'],
  ['scenarios/cmp-cmp3.yaml', 'Vergleicher für zwei 3-Bit-Zahlen'],
  ['scenarios/cmp-mux8.yaml', 'Auswahlschalter 8 zu 1'],
];
const DIR_TITLES = {
  'tests/fixtures/external': 'Aus der Community', 'tests/fixtures/licensed': 'Weitere Schaltpläne', out: 'Eigene Ausgaben',
  'examples/specs': 'Logik', 'examples/specs/composed': 'Größere Logik', 'examples/behaviour': 'Zeitverhalten und Speicher',
};
const EXAMPLES = ['scenarios/cmp-adder2.yaml', 'scenarios/tpl-xor2-comparator.yaml'];

const S = {
  demo: params.get('demo') === '1',
  path: null, groups: {}, group: 'schematics',
  model: null, modelPath: null, modelGroup: null, fromJob: false,
  task: 'build', mode: 'build', goal: 'spec',
  playing: false,
  buildN: 0,
  job: null,
  simId: null, simTick: 0, simRunning: false, simStarting: false, busy: Promise.resolve(), simModel: null, simState: new Map(),
  lastSize: [1, 1, 1],
};

// --- helpers ---------------------------------------------------------------------------------------------------------

function setStatus(msg, err = false) {
  const el = $('status');
  el.textContent = msg || '';
  el.title = msg || '';
  el.classList.toggle('err', err);
}
const fail = (e) => setStatus(e && e.message ? e.message : String(e), true);
const setInfo = (t) => { $('info').textContent = t || ''; $('info').title = t || ''; };
const baseName = (p) => p.split('/').pop();
const stem = (p) => baseName(p).replace(/\.[^.]+$/, '');
const isOwn = (p) => p.startsWith('.cache/gui/'); // uploaded or written in the GUI
const store = {
  get(k) { try { return localStorage.getItem('rsx.' + k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem('rsx.' + k, v); } catch { /* private mode */ } },
};

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
  const m = S.mode === 'search' ? null : S.model;
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

// --- views and layout ------------------------------------------------------------------------------------------------

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
  if (!['split', '3d', '2d'].includes(l)) l = 'split';
  for (const x of $('layoutSeg').children) x.classList.toggle('on', x.dataset.layout === l);
  $('views').className = { split: 'split', '3d': 'only3d', '2d': 'only2d' }[l];
  store.set('layout', l);
  resizeViews();
}
$('layoutSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) setLayout(b.dataset.layout);
});

$('btnLib').addEventListener('click', () => {
  store.set('nolib', document.body.classList.toggle('nolib') ? '1' : '');
  resizeViews();
});

// splitter between the views and the work panel
(() => {
  const sp = $('splitter');
  const apply = (w) => {
    w = Math.max(320, Math.min(window.innerWidth * 0.7, w));
    document.documentElement.style.setProperty('--work-w', w + 'px');
    return w;
  };
  const saved = +store.get('workW');
  if (saved) apply(saved);
  sp.addEventListener('pointerdown', (e) => {
    sp.setPointerCapture(e.pointerId);
    sp.classList.add('drag');
    const move = (ev) => { store.set('workW', apply(window.innerWidth - ev.clientX)); v3.resize(); v2.resize(); };
    const up = () => { sp.classList.remove('drag'); sp.removeEventListener('pointermove', move); sp.removeEventListener('pointerup', up); };
    sp.addEventListener('pointermove', move);
    sp.addEventListener('pointerup', up);
  });
  window.addEventListener('resize', resizeViews);
})();

// close the settings menu on a click elsewhere
document.addEventListener('click', (e) => { if (!$('settings').contains(e.target)) $('settings').open = false; });

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
}

function renderMaterials(model) {
  const el = $('materials');
  el.textContent = '';
  const mats = (model && model.materials) || [];
  if (!mats.length) el.appendChild(node('span', model ? 'Kein Material.' : 'Keine Schaltung geladen.', 'muted'));
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
  for (const n of (model && model.notes) || []) notes.appendChild(node('div', n));
  $('buildHint').hidden = !!model;
}

// --- library ---------------------------------------------------------------------------------------------------------

function renderFiles() {
  const box = $('fileList');
  box.textContent = '';
  const filt = $('fileFilter').value.trim().toLowerCase();
  for (const b of $('groupSeg').children) {
    const n = (S.groups[b.dataset.group] || []).length;
    b.classList.toggle('on', !filt && b.dataset.group === S.group);
    b.textContent = GROUP_TITLES[b.dataset.group];
    b.title = `${b.title.replace(/ \(\d+ Dateien\)$/, '')} (${n} Dateien)`;
  }
  // without a filter: the chosen group; with one: matches from all groups
  for (const g of filt ? Object.keys(GROUP_TITLES) : [S.group]) {
    const list = (S.groups[g] || []).filter((p) => !filt || p.toLowerCase().includes(filt));
    if (!list.length) continue;
    if (filt) box.appendChild(node('h3', `${GROUP_TITLES[g]} (${list.length})`));
    const entry = (p, title) => {
      const b = document.createElement('button');
      b.textContent = title || baseName(p);
      if (title) b.appendChild(node('small', baseName(p)));
      b.title = p;
      if (p === S.path) b.classList.add('sel');
      b.addEventListener('click', () => selectFile(p, g));
      box.appendChild(b);
    };
    if (!filt && g === 'scenarios') {
      const featured = FEATURED.filter(([p]) => list.includes(p));
      if (featured.length) box.appendChild(node('h3', 'Zum Einstieg'));
      for (const [p, title] of featured) entry(p, title);
      box.appendChild(node('h3', `Alle Beispiele und Tests (${list.length})`));
    }
    let lastDir = null;
    for (const p of list) {
      const raw = p.split('/').slice(0, -1).join('/');
      const dir = isOwn(p) ? 'Eigene Dateien' : DIR_TITLES[raw] || raw;
      if (!filt && g !== 'scenarios' && dir !== lastDir) { box.appendChild(node('h3', dir || '.')); lastDir = dir; }
      entry(p);
    }
  }
  if (!box.children.length) box.appendChild(node('div', filt ? 'Nichts gefunden.' : 'Keine Dateien.', 'hint'));
  box.querySelector('.sel')?.scrollIntoView({ block: 'nearest' });
}
$('fileFilter').addEventListener('input', renderFiles);
$('groupSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  S.group = b.dataset.group;
  $('fileFilter').value = '';
  renderFiles();
});

async function refreshFiles() {
  S.groups = await api.files();
  renderFiles();
}

async function selectFile(path, group) {
  S.path = path;
  if (!$('fileFilter').value.trim()) S.group = group;
  renderFiles();
  if (group === 'specs') {
    setTask('design');
    setGoal('spec');
    return editSpec(path);
  }
  await loadModel(path, group);
  if (S.task === 'design' && S.modelPath === path) setGoal('file');
}

async function loadModel(path, group = 'schematics') {
  setPlaying(false);
  setStatus('Lade ' + path + ' ...');
  try {
    const m = S.demo ? await api.demo() : await api.model(path);
    S.model = m; S.modelPath = path; S.modelGroup = group; S.fromJob = false;
    circuitChanged();
    applyTask({ fit: true, forceModel: true });
    setStatus(`${m.name}: ${m.blocks.length} Blöcke geladen.`);
  } catch (e) { fail(e); }
}

/** The circuit all tasks work on: the shown result of a search or the loaded file. */
function currentRef() {
  if (S.fromJob && S.job && S.job.result && S.job.result.blocks) return { job: S.job.id };
  return S.modelPath ? { path: S.modelPath } : null;
}
const currentName = () => (S.model ? S.model.name : 'schaltung');

/** After the current circuit was replaced: drop everything that belonged to the old one. */
function circuitChanged() {
  endSim();
  anDocs.clear();
  simDocs.clear();
  renderMaterials(S.model);
  updateActions();
}

function updateActions() {
  const ref = S.demo ? null : currentRef();
  const m = S.model;
  const scenario = !!ref && !ref.job && S.modelGroup === 'scenarios';
  $('curName').textContent = m ? m.name : 'Keine Schaltung geladen';
  $('curMeta').textContent = m ? `${m.size.join('×')} · ${m.blocks.length} Blöcke${S.fromJob ? ' · Entwurf der Suche' : ''}` : '';
  $('btnExplain').disabled = $('btnDump').disabled = $('btnExport').disabled = !ref;
  $('sStart').disabled = !ref;
  $('scenarioBox').hidden = !scenario;
  $('btnOracle').disabled = !!oracle;
  const sel = $('exportFmt');
  for (const o of sel.options) {
    o.hidden = o.disabled = (o.dataset.for === 'scenario' && !scenario) || (o.dataset.for === 'job' && !(ref && ref.job));
  }
  if (sel.selectedOptions[0] && sel.selectedOptions[0].disabled) sel.value = 'litematic';
  // design task
  const fileGoal = $('goalSeg').querySelector('[data-goal="file"]');
  fileGoal.disabled = !S.modelPath;
  if (!S.modelPath && S.goal === 'file') setGoal('spec');
  $('goalFileText').textContent = S.modelPath
    ? `Sucht eine kompaktere Schaltung mit demselben Verhalten wie „${stem(S.modelPath)}“. Das Verhalten wird zuerst im Simulator gemessen.`
    : '';
  $('btnRedesign').disabled = S.demo || (S.goal === 'file' && !S.modelPath) || !!(S.job && !S.job.done);
  $('btnRedesign').textContent = S.job && !S.job.done ? 'Suche läuft ...' : 'Entwurf suchen';
  const hasResult = !!(S.job && S.job.result && S.job.result.blocks);
  $('resultActions').hidden = !hasResult;
  $('btnShowResult').disabled = hasResult && S.fromJob && S.mode !== 'search';
  $('welcome').hidden = !!m || !!(S.job && (S.task === 'design' || S.task === 'chat'));
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
$('wOpen').addEventListener('click', () => $('fileInput').click());
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
$('wExample').addEventListener('click', () => {
  const p = EXAMPLES.find((x) => (S.groups.scenarios || []).includes(x)) || (S.groups.scenarios || [])[0];
  if (p) selectFile(p, 'scenarios').then(() => setTask('sim'));
});
$('wDesign').addEventListener('click', newSpec);
$('btnNewSpec').addEventListener('click', newSpec);

// --- tasks -----------------------------------------------------------------------------------------------------------

function setTask(task) {
  if (!TASKS[task]) return;
  S.task = task;
  for (const b of $('taskTabs').children) b.classList.toggle('on', b.dataset.task === task);
  for (const [t, id] of Object.entries(TASKS)) $(id).hidden = t !== task;
  applyTask();
}
$('taskTabs').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b && b.dataset.task !== S.task) setTask(b.dataset.task);
});

/** Bring views and transport bar in line with the task. forceModel: show the circuit even in the design task. */
function applyTask({ fit = false, forceModel = false } = {}) {
  if (S.task === 'sim') {
    setMode('sim', { fit });
    if (!S.simId && !S.simStarting && currentRef() && !S.demo) startSim();
  } else if ((S.task === 'design' || S.task === 'chat') && S.job && !forceModel && !(S.fromJob && S.job.finalShown)) setMode('search', { fit });
  else setMode('build', { fit });
  updateActions();
}

// --- playback: common ------------------------------------------------------------------------------------------------

function rate() { return 1.5 * Math.pow(1.045, +$('speed').value); }
function updateSpeedLabel() {
  const r = rate();
  $('speedVal').textContent = `${r < 10 ? r.toFixed(1) : Math.round(r)} ${S.mode === 'build' ? 'Blöcke' : 'Schritte'}/s`;
}
$('speed').addEventListener('input', updateSpeedLabel);

function setPlaying(p) {
  S.playing = p;
  $('bPlay').innerHTML = icon(p ? 'pause' : 'play');
}

function setMode(mode, { fit = false } = {}) {
  setPlaying(false);
  stopSimRun();
  const changed = S.mode !== mode;
  S.mode = mode;
  $('ctlBuild').hidden = mode === 'sim' || (mode === 'build' ? !S.model : !(S.job && S.job.frames.length));
  $('ctlSim').hidden = mode !== 'sim' || !S.model;
  $('ctlTitle').textContent = mode === 'build' ? 'Bauanleitung' : 'Suchverlauf';
  if (changed) $('speed').value = mode === 'build' ? 40 : 35;
  updateSpeedLabel();
  if (mode === 'build') {
    if (S.model) {
      showModel(S.model, { reveal: true, fit });
      const total = S.model.build_order.length;
      $('progress').max = total;
      setBuild(total);
    } else setInfo('');
  } else if (mode === 'search') {
    if (S.job && S.job.frames.length) showFrame(Math.max(0, Math.min(S.job.idx, S.job.frames.length - 1)));
    else setInfo(S.job ? 'Suche läuft, noch keine Zwischenschritte ...' : '');
  } else {
    if (S.simId && S.simModel) {
      showModel(S.simModel, { reveal: false, fit });
      const now = [...S.simState].filter(([, s]) => s !== 'air').map(([k, s]) => ({ p: k.split(',').map(Number), s }));
      v3.setBlocks(now, S.simModel.size, { fit: false });
      v2.setBlocks(now, S.simModel.size);
    } else if (S.model) showModel(S.model, { reveal: false, fit });
    $('sTick1').disabled = $('sRun').disabled = !S.simId;
    if (!S.simPaused) runSim();
    setInfo(S.simId ? 'Die Zeit läuft von selbst. Hebel und Knöpfe lassen sich in beiden Ansichten anklicken.' : '');
  }
  renderIO();
}

// --- build instructions ----------------------------------------------------------------------------------------------

function setBuild(n) {
  const order = S.model.build_order, total = order.length;
  n = Math.max(0, Math.min(total, n));
  S.buildN = n;
  for (const v of views) v.setRevealCount(n);
  $('progress').value = n;
  if (n >= total) setInfo(`Alle ${total} Blöcke gesetzt. ▶ spielt den Aufbau von vorn ab.`);
  else if (n > 0) {
    const p = order[n - 1];
    const st = S.model.blocks.find((b) => b.p[0] === p[0] && b.p[1] === p[1] && b.p[2] === p[2]);
    setInfo(`Block ${n} von ${total}: ${st ? st.s : ''} bei (${p.join(', ')})`);
  } else setInfo(`Block 0 von ${total}`);
}

$('btnExport').addEventListener('click', () => {
  const ref = currentRef();
  if (!ref) return;
  busyWith($('btnExport'), 'Erzeuge Datei ...', async () => {
    const { blob, name } = await api.download(ref, $('exportFmt').value);
    saveBlob(blob, name);
    setStatus(`${name} heruntergeladen.`);
  });
});

// --- analyze ---------------------------------------------------------------------------------------------------------

const anDocs = new DocPane({ tabs: $('anDocTabs'), body: $('anDocBody'), save: $('anDocSave') });

$('btnExplain').addEventListener('click', () => {
  const ref = currentRef(), name = currentName();
  if (!ref) return;
  busyWith($('btnExplain'), `Untersuche ${name} (bei großen Schaltungen dauert das einige Sekunden) ...`, async () => {
    const r = await api.explain(ref);
    anDocs.set('explain', {
      title: 'Erklärung', node: renderMarkdown(r.markdown, r.svgs),
      download: { name: `${name}-analyse.md`, text: r.markdown, type: 'text/markdown;charset=utf-8' },
    });
    setStatus('Erklärung fertig.');
  });
});

$('btnDump').addEventListener('click', () => {
  const ref = currentRef(), name = currentName();
  if (!ref) return;
  busyWith($('btnDump'), 'Erzeuge Text-Ansicht ...', async () => {
    const r = await api.dump(ref, { states: true });
    const box = node('div');
    box.appendChild(node('h2', `Als Text: ${name}`));
    box.appendChild(node('pre', r.text));
    anDocs.set('dump', { title: 'Text', node: box, download: { name: `${name}-ebenen.txt`, text: r.text } });
    setStatus('Text-Ansicht fertig.');
  });
});

// --- simulation ------------------------------------------------------------------------------------------------------

const simDocs = new DocPane({ tabs: $('simDocTabs'), body: $('simDocBody'), save: $('simDocSave') });

function endSim() {
  stopSimRun();
  S.simId = null; S.simModel = null; S.simState = new Map();
  $('sTick1').disabled = $('sRun').disabled = true;
  $('tickOut').textContent = 'Tick 0';
  renderIO();
}

async function startSim() {
  const ref = currentRef();
  if (!ref || S.simStarting) return;
  stopSimRun();
  S.simStarting = true;
  try {
    setStatus('Starte Simulation ...');
    const r = await api.sim(ref);
    if (JSON.stringify(ref) !== JSON.stringify(currentRef())) return; // another circuit was loaded meanwhile
    S.simId = r.sim; S.simTick = r.tick; S.simModel = r.model;
    S.simState = new Map(r.model.blocks.map((b) => [b.p.join(','), b.s]));
    $('tickOut').textContent = 'Tick ' + r.tick;
    S.simPaused = false;
    if (S.mode === 'sim') setMode('sim');
    setStatus('Die Schaltung läuft. Klicke einen Eingang an und sieh zu, was passiert.');
  } catch (e) { fail(e); } finally { S.simStarting = false; }
}
$('sStart').addEventListener('click', startSim);

const isOn = (s) => !!s && (/(?:powered|lit|extended|open)=true/.test(s) || /power=[1-9]/.test(s) || /\|output=[1-9]/.test(s));

/** Inputs as buttons and outputs as lights, by name: handy when the levers are hard to find in the view. */
function renderIO() {
  const m = S.simId ? S.simModel : null;
  const fill = (box, items, make) => {
    box.textContent = '';
    if (!items.length) { box.appendChild(node('span', m ? 'keine gefunden' : '–', 'none muted')); return; }
    for (const it of items) {
      const s = S.simState.get(it.p.join(','));
      const e = make(it);
      e.textContent = it.name;
      e.classList.toggle('on', isOn(s));
      e.title = `(${it.p.join(', ')}) ${s || ''}`;
      box.appendChild(e);
    }
  };
  fill($('ioIn'), m ? m.inputs : [], (it) => {
    const b = document.createElement('button');
    b.addEventListener('click', () => useBlock(it.p));
    return b;
  });
  fill($('ioOut'), m ? m.outputs : [], () => node('span', undefined, 'io'));
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
    if (S.mode === 'sim') for (const v of views) v.applyChanges(r.changed);
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
  if (S.mode !== 'sim' || !S.simId) {
    if (S.model && S.mode !== 'search') setStatus('Zum Schalten rechts auf „Ausprobieren“ wechseln.');
    return;
  }
  try {
    const r = await simCall(() => api.use(S.simId, p));
    applySim(r);
    const io = S.simModel.inputs.find((i) => i.p.join(',') === p.join(','));
    setStatus(`${io ? `Eingang „${io.name}“` : `Block (${p.join(', ')})`} betätigt.`);
    if (!S.simRunning) simTicks(1); // show the immediate reaction
  } catch (e) { fail(e); }
}
$('sTick1').addEventListener('click', () => simTicks(1));
$('simSpeed').addEventListener('input', (e) => { $('simSpeedVal').textContent = e.target.value; });

function stopSimRun() {
  S.simRunning = false;
  clearTimeout(S.simTimer);
  const b = $('sRun');
  b.innerHTML = icon('play') + 'Weiter';
}
/** Let the time run: 10 steps a second, by default 2 ticks each (the speed of the game). */
function runSim() {
  if (S.simRunning || !S.simId || S.mode !== 'sim') return;
  S.simRunning = true;
  $('sRun').innerHTML = icon('pause') + 'Anhalten';
  const step = async () => {
    if (!S.simRunning) return;
    await simTicks(+$('simSpeed').value);
    if (S.simRunning) S.simTimer = setTimeout(step, 100);
  };
  step();
}
// The time runs by itself while "Ausprobieren" is open; `simPaused` remembers that the user stopped it.
$('sRun').addEventListener('click', () => {
  S.simPaused = S.simRunning;
  if (S.simRunning) { stopSimRun(); setStatus('Angehalten. „1 Tick“ geht einzeln weiter, „Weiter“ lässt die Zeit wieder laufen.'); }
  else runSim();
});
// no ticking in a hidden browser tab
document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopSimRun(); else if (!S.simPaused) runSim();
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
  busyWith($('btnScenario'), `Ablauf von ${stem(path)} läuft im Simulator ...`, async () => {
    const r = await api.scenario(path);
    const box = node('div');
    box.appendChild(node('h2', `Testablauf: ${r.name}`));
    if (r.golden) goldenNote(box, r.golden, 'Vergleich mit der Aufnahme aus dem echten Spiel');
    else box.appendChild(node('p', 'Zu diesem Szenario gibt es noch keine Aufnahme aus dem Spiel.', 'muted'));
    box.appendChild(node('p', `${r.ticks} Gameticks. Jede Zeile ist ein Messpunkt, # heißt „an“.`, 'muted'));
    for (const w of r.warnings) box.appendChild(node('p', 'Warnung: ' + w, 'bad'));
    box.appendChild(svgImage(r.svg, 'Zeitdiagramm'));
    const det = node('details');
    det.appendChild(node('summary', 'Zeitdiagramm als Text'));
    det.appendChild(node('pre', r.diagram));
    box.appendChild(det);
    simDocs.set('scenario', { title: 'Testablauf', node: box, download: { name: `${r.name}.svg`, text: r.svg, type: 'image/svg+xml' } });
    setStatus(r.golden ? (r.golden.matches ? 'Der Simulator stimmt mit dem Spiel überein.' : 'Der Simulator weicht vom Spiel ab.') : 'Ablauf fertig.', !!r.golden && !r.golden.matches);
  });
});

let oracle = null; // {id, timer, started}
$('btnOracle').addEventListener('click', async () => {
  const path = S.modelPath;
  if (!path || oracle) return;
  try {
    const { job } = await api.oracle(path, $('oracleGolden').checked);
    const box = node('div');
    box.appendChild(node('h2', `Im echten Spiel: ${stem(path)}`));
    const state = node('p', '');
    box.appendChild(state);
    const doc = { title: 'Im Spiel', node: box };
    simDocs.set('oracle', doc);
    oracle = { id: job, started: Date.now() };
    updateActions();
    const poll = async () => {
      const secs = Math.round((Date.now() - oracle.started) / 1000);
      state.textContent = `Der Minecraft-Server läuft seit ${secs} s (üblich sind ein bis drei Minuten, beim ersten Mal länger) ...`;
      let d;
      try { d = await api.job(oracle.id, 0); } catch (e) { d = { done: true, error: e.message }; }
      if (!d.done) return;
      clearInterval(oracle.timer); oracle = null; updateActions();
      if (d.error) { state.textContent = d.error; state.className = 'bad'; setStatus(d.error, true); return; }
      const r = d.result;
      state.textContent = `Aufnahme fertig nach ${secs} s: ${r.ticks} Gameticks.`;
      goldenNote(box, r.simulator, 'Vergleich Spiel ↔ Simulator');
      if (r.written) box.appendChild(node('p', `Als Referenz gespeichert: ${r.written}`));
      box.appendChild(svgImage(r.svg, 'Zeitdiagramm'));
      doc.download = { name: `${r.name}-spiel.svg`, text: r.svg, type: 'image/svg+xml' };
      if (simDocs.get('oracle') === doc && simDocs.current === 'oracle') simDocs.show('oracle');
      setStatus(r.simulator.matches ? 'Spiel und Simulator stimmen überein.' : 'Spiel und Simulator weichen ab.', !r.simulator.matches);
    };
    oracle.timer = setInterval(poll, 2000);
    poll();
    setStatus('Aufnahme im Spiel gestartet.');
  } catch (e) { fail(e); }
});

// --- design ----------------------------------------------------------------------------------------------------------

const deDocs = new DocPane({ tabs: $('deDocTabs'), body: $('deDocBody'), save: $('deDocSave') });
const specEditor = openSpecEditor({
  mount: $('specMount'), api, setStatus, fail,
  onSaved: () => refreshFiles(),
});
// the wish cards write the spec text; the editor below them shows it and takes over for "Eigene Vorgabe"
const wizard = initWizard({
  mount: $('wizard'),
  onSpec: ({ name, text }) => specEditor.open({ name, text, path: null }),
  onCustom: () => { $('specAdvanced').open = true; },
});
wizard.select('logic');

function setGoal(goal) {
  S.goal = goal;
  for (const b of $('goalSeg').children) b.classList.toggle('on', b.dataset.goal === goal);
  $('goalSpec').hidden = goal !== 'spec';
  $('goalFile').hidden = goal !== 'file';
  updateActions();
}
$('goalSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b && !b.disabled) setGoal(b.dataset.goal);
});

async function editSpec(path) {
  try {
    const r = await api.text(path);
    wizard.select('custom');
    specEditor.open({ name: stem(path), text: r.text, path });
    setStatus('Vorgabe geladen. Bei Bedarf den Text ändern, dann „Entwurf suchen“.');
  } catch (e) { fail(e); }
}
function newSpec() {
  if (S.demo) return;
  setTask('design');
  setGoal('spec');
  if (wizard.current === 'custom') wizard.select('logic');
  setStatus('Wähle, was die Schaltung tun soll, dann „Entwurf suchen“.');
}

function searchOptions() {
  const num = (id) => ($(id).value.trim() === '' ? undefined : +$(id).value);
  const txt = (id) => $(id).value.trim() || undefined;
  return {
    compact: Math.max(0, Math.round(num('compact') ?? 100)), time: num('optTime') ?? 60, top: Math.max(1, Math.round(num('optTop') ?? 10)),
    max_size: txt('optSize'), max_delay: num('optDelay'), allow: txt('optAllow'), forbid: txt('optForbid'),
    outputs: S.goal === 'file' ? txt('optOutputs') : undefined, no_qc: $('optNoQc').checked,
  };
}

$('btnRedesign').addEventListener('click', async () => {
  const path = S.goal === 'file' ? S.modelPath : await specEditor.commit();
  if (path) startRedesign(path);
});

async function startRedesign(path) {
  if (S.job && S.job.timer) clearInterval(S.job.timer);
  setPlaying(false);
  try {
    setStatus('Starte Entwurfssuche ...');
    const { job } = await api.redesign(path, searchOptions());
    followJob(job, path);
  } catch (e) { fail(e); }
  updateActions();
}

/** Show a running design search (started here or by the assistant); its result becomes the current circuit. */
function followJob(job, path, task = 'design') {
  if (S.job && S.job.timer) clearInterval(S.job.timer);
  setPlaying(false);
  try {
    if (S.fromJob) { // the old result is gone: back to the file, or to nothing
      S.fromJob = false;
      if (!S.modelPath) S.model = null;
      circuitChanged();
    }
    S.job = { id: job, path, frames: [], done: false, result: null, idx: -1, since: 0, timer: null, finalShown: false, follow: true };
    $('frameLog').textContent = '';
    $('frameCount').textContent = '0';
    $('framesSec').hidden = false;
    $('designState').textContent = `Suche für „${stem(path)}“ läuft ...`;
    $('designState').className = 'hint';
    if (task === 'design') setTimeout(() => $('btnRedesign').scrollIntoView({ block: 'start', behavior: 'smooth' }), 50);
    deDocs.clear();
    if (S.task !== task) setTask(task); else applyTask();
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
    const hadFrames = j.frames.length > 0;
    for (const f of d.frames || []) {
      j.frames.push(f);
      j.since = f.i + 1;
      addFrameLog(f, j.frames.length - 1);
    }
    $('frameCount').textContent = j.frames.length;
    if (S.mode === 'search') {
      if (!hadFrames && j.frames.length) { $('ctlBuild').hidden = false; updateActions(); }
      $('progress').max = Math.max(0, j.frames.length - 1);
      if (j.frames.length && (j.idx < 0 || (wasLast && j.follow && !S.playing))) showFrame(j.frames.length - 1);
    }
    if (d.done) {
      clearInterval(j.timer); j.timer = null; j.done = true;
      const st = $('designState');
      if (d.result) {
        j.result = d.result;
        if (d.result.summary) {
          deDocs.set('report', {
            title: 'Bericht', node: renderMarkdown(d.result.summary),
            download: { name: `${stem(j.path)}-redesign.md`, text: d.result.summary, type: 'text/markdown;charset=utf-8' },
          });
        }
      }
      if (d.error) {
        st.textContent = d.error; st.className = 'bad';
        setStatus('Entwurfssuche ohne Erfolg: ' + d.error, true);
      } else if (d.result && d.result.blocks) {
        const r = d.result;
        st.textContent = `Bester Entwurf: „${r.name}“, ${r.size.join('×')}, ${r.blocks.length} Blöcke. Er ist jetzt die aktuelle Schaltung.`;
        st.className = 'good';
        setStatus(`Entwurfssuche fertig: ${r.name}, ${r.blocks.length} Blöcke.`);
        if (S.mode === 'search' && !S.playing && (j.idx === j.frames.length - 1 || !j.frames.length)) showResult();
      } else { st.textContent = 'Die Suche endete ohne Ergebnis.'; st.className = 'bad'; }
      updateActions();
    } else setStatus(`Suche läuft ... ${j.frames.length} Zwischenschritte`);
  } catch (e) {
    if (j === S.job) { clearInterval(j.timer); j.timer = null; j.done = true; fail(e); updateActions(); }
  } finally { polling = false; }
}

function addFrameLog(f, i) {
  const d = document.createElement('div');
  d.dataset.i = i;
  const mark = f.phase === 'compact' ? (f.accepted ? '<span class="ok">✓</span> ' : '<span class="no">✗</span> ') : '<span class="ok">●</span> ';
  d.innerHTML = mark;
  d.appendChild(document.createTextNode(`${i + 1} ${f.phase === 'compose' ? 'zusammengesetzt' : 'verkleinert'}: ${f.label}`));
  d.addEventListener('click', () => { setPlaying(false); if (S.mode !== 'search') setMode('search'); S.job.follow = false; showFrame(i); updateActions(); });
  $('frameLog').appendChild(d);
}

function showFrame(i) {
  const j = S.job;
  if (!j || !j.frames.length) return;
  i = Math.max(0, Math.min(j.frames.length - 1, i));
  const first = j.idx < 0 || !j.shownFrame;
  const f = j.frames[i];
  j.idx = i; j.shownFrame = true;
  onHover(null);
  v3.setBlocks(f.blocks, f.size, { fit: first });
  v2.setBlocks(f.blocks, f.size);
  for (const v of views) { v.setReveal(null); v.setIO([], []); }
  syncSliders(f.size);
  $('progress').max = j.frames.length - 1;
  $('progress').value = i;
  const mark = f.phase === 'compact' ? (f.accepted ? ' ✓ übernommen' : ' ✗ verworfen') : '';
  setInfo(`Schritt ${i + 1} von ${j.frames.length} · ${f.phase === 'compose' ? 'Zusammensetzen' : 'Verkleinern'}${mark} · ${f.label} · ${f.blocks.length} Blöcke`);
  const log = $('frameLog');
  log.querySelector('.cur')?.classList.remove('cur');
  const row = log.children[i];
  if (row) { row.classList.add('cur'); if ($('framesSec').open) row.scrollIntoView({ block: 'nearest' }); }
  j.follow = i === j.frames.length - 1;
}

/** Make the best design of the search the current circuit (materials, build guide, analysis, export ...). */
function showResult() {
  const j = S.job;
  if (!j || !j.result || !j.result.blocks) return;
  setPlaying(false);
  j.finalShown = true;
  S.model = j.result; S.modelPath = null; S.modelGroup = null; S.fromJob = true;
  S.path = null;
  renderFiles();
  circuitChanged();
  setMode('build', { fit: true });
  updateActions();
}
$('btnShowResult').addEventListener('click', showResult);
for (const [id, task] of [['rBuild', 'build'], ['rSim', 'sim'], ['rAnalyze', 'analyze']]) {
  $(id).addEventListener('click', () => { if (!S.fromJob) showResult(); setTask(task); });
}

// --- transport buttons -----------------------------------------------------------------------------------------------

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
    if (S.job.idx >= S.job.frames.length - 1 && S.job.done) showFrame(0);
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
      if (j.done) setPlaying(false);
      // else: live job, keep waiting for new frames
    } else showFrame(j.idx + k);
  }
}
requestAnimationFrame(loop);

// --- simulator core --------------------------------------------------------------------------------------------------

let core = 'rust';
$('coreSel').addEventListener('change', async (e) => {
  try {
    core = (await api.setCore(e.target.value)).core;
    setStatus(`Simulatorkern: ${core === 'rust' ? 'Rust' : 'Python (Referenz, deutlich langsamer)'}.`);
  } catch (err) { fail(err); }
  e.target.value = core;
});

// --- start -----------------------------------------------------------------------------------------------------------

async function init() {
  updateSpeedLabel();
  setLayout(params.get('layout') || store.get('layout') || 'split');
  if (store.get('nolib')) document.body.classList.add('nolib');
  renderMaterials(null);
  setGoal('spec');
  setMode('build');
  updateActions();
  if (S.demo) {
    S.groups = { schematics: ['demo/model.json'] };
    for (const id of ['btnOpen', 'btnNewSpec', 'coreSel', 'wOpen', 'wExample', 'wDesign']) $(id).disabled = true;
    S.path = 'demo/model.json';
    renderFiles();
    await loadModel(S.path);
    setStatus('Demomodus: nur Ansicht, Material und Bauanleitung.');
    return;
  }
  try {
    const f = await api.files();
    S.groups = f;
    renderFiles();
    setStatus('Bereit.');
    api.info().then((i) => {
      core = i.core; $('coreSel').value = core;
      if (!i.rust) { const o = $('coreSel').querySelector('option[value="rust"]'); o.disabled = true; o.textContent = 'Rust (nicht gebaut)'; }
    }).catch(() => {});
    const initial = params.get('path');
    if (initial) {
      const g = Object.keys(GROUP_TITLES).find((k) => (f[k] || []).includes(initial)) || 'schematics';
      await selectFile(initial, g);
    }
    if (params.get('task')) setTask(params.get('task'));
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
    // ?click=btnExplain,sRun,... presses these buttons one after the other (tests, screenshots);
    // task:sim / task:design ... switch the task, a number waits that many milliseconds
    for (const step of (params.get('click') || '').split(',').filter(Boolean)) {
      if (step.startsWith('task:')) setTask(step.slice(5));
      else if (/^\d+$/.test(step)) await new Promise((r) => setTimeout(r, +step));
      else { $(step)?.click(); await new Promise((r) => setTimeout(r, 1200)); }
    }
  } catch (e) { fail(e); }
}
// --- assistant ---------------------------------------------------------------------------------------------------------

const IDEAS = [
  ['Codeschloss-Tür', 'Ich möchte eine Eisentür, die nur aufgeht, wenn von vier Hebeln genau der erste und der dritte an sind.'],
  ['Türklingel', 'Eine Türklingel: Wenn man einen Knopf drückt, soll ein Notenblock einen Ton spielen.'],
  ['Alarmanlage mit Reset', 'Eine Alarmanlage: Ein Knopf löst den Alarm aus, eine Lampe bleibt an, bis man einen zweiten Knopf zum Zurücksetzen drückt.'],
  ['Leuchtturm-Blinker', 'Ein Leuchtturm: Eine Lampe soll von selbst blinken, etwa jede Sekunde kurz aufleuchten.'],
];
const chat = { id: null, since: 0, timer: null, busy: false, note: null, live: new Map() };

function chatAdd(cls, content) {
  const d = node('div', undefined, 'msg ' + cls);
  if (content instanceof Node) d.appendChild(content); else d.textContent = content;
  $('chatLog').insertBefore(d, chat.note && chat.note.isConnected ? chat.note : null);
  d.scrollIntoView({ block: 'nearest' });
  return d;
}
function chatNote(t) {
  if (!chat.note) chat.note = chatAdd('note', t); else chat.note.textContent = t;
}
function chatBusy(b) {
  chat.busy = b;
  $('chatSend').disabled = b;
  $('chatStop').hidden = !b;
  $('chatNew').disabled = b;
  for (const x of $('chatIdeas').children) x.disabled = b;
  if (!b && chat.note) { chat.note.remove(); chat.note = null; }
}
function chatReset() {
  if (chat.timer) clearInterval(chat.timer);
  Object.assign(chat, { id: null, since: 0, timer: null, note: null, live: new Map() });
  $('chatLog').replaceChildren();
  store.set('chat', '');
  chatBusy(false);
}
async function chatKeyState() {
  try {
    const a = await api.assistant();
    $('chatKey').hidden = a.configured;
    $('chatKeyFile').textContent = a.key_file || '~/.rsx';
  } catch (e) { fail(e); }
}
$('chatKeySave').addEventListener('click', () => busyWith($('chatKeySave'), 'Speichere den Schlüssel ...', async () => {
  const r = await api.saveKey($('chatKeyIn').value);
  $('chatKeyIn').value = '';
  $('chatKey').hidden = r.configured;
  setStatus(r.configured ? 'Schlüssel gespeichert. Der Assistent ist bereit.' : 'Schlüssel entfernt.');
}));
async function chatSend(text) {
  text = (text || '').trim();
  if (!text || chat.busy || S.demo) return;
  $('chatIn').value = '';
  chatBusy(true);
  try {
    const r = await api.chat(chat.id, text, currentRef());
    chat.id = r.chat; chat.since = r.since;
    store.set('chat', chat.id);
    chatNote('Der Assistent denkt nach …');
    chat.timer = setInterval(chatPoll, 500);
  } catch (e) { chatAdd('user', text); chatAdd('err', e.message); chatBusy(false); }
}
/** One chat event. `replay`: shown again after reloading the page (no new searches or files are opened). */
async function chatEvent(ev, replay) {
  if (ev.type === 'user') chatAdd('user', ev.text);
  else if (ev.type === 'delta') {
    let d = chat.live.get(ev.key);
    if (!d) { d = chatAdd('bot live', ''); d._raw = ''; chat.live.set(ev.key, d); }
    d._raw += ev.text;
    d.textContent = d._raw;
    d.scrollIntoView({ block: 'nearest' });
  } else if (ev.type === 'text') {
    const d = chat.live.get(ev.key);
    const md = renderMarkdown(ev.text);
    if (d) { d.classList.remove('live'); d.replaceChildren(md); chat.live.delete(ev.key); } else chatAdd('bot', md);
  } else if (ev.type === 'status') { if (!replay) chatNote(ev.text); }
  else if (ev.type === 'error') { chatAdd('err', ev.text); if (!replay && /API-Schlüssel/.test(ev.text)) chatKeyState(); }
  else if (ev.type === 'cancelled') chatAdd('note', ev.text);
  else if (ev.type === 'job') { if (!replay) followJob(ev.job, ev.path, 'chat'); }
  else if (ev.type === 'load') {
    if (!replay) { await refreshFiles().catch(() => {}); await selectFile(ev.path, ev.group || 'scenarios'); }
  }
}
function chatDropLive() { // deltas of an answer that never finished (cancelled or failed)
  for (const d of chat.live.values()) d.classList.remove('live');
  chat.live.clear();
}
let chatPolling = false;
async function chatPoll() {
  if (chatPolling || !chat.id) return;
  chatPolling = true;
  try {
    const d = await api.chatEvents(chat.id, chat.since);
    for (const ev of d.events) { chat.since = ev.i + 1; await chatEvent(ev, false); }
    if (!d.busy) { clearInterval(chat.timer); chat.timer = null; chatDropLive(); chatBusy(false); }
  } catch (e) {
    clearInterval(chat.timer); chat.timer = null; chatAdd('err', e.message); chatBusy(false);
  } finally { chatPolling = false; }
}
async function chatRestore() {
  const id = store.get('chat');
  if (!id) return;
  try {
    const d = await api.chatEvents(id, 0);
    chat.id = id;
    for (const ev of d.events) { chat.since = ev.i + 1; await chatEvent(ev, true); }
    if (d.busy) { chatBusy(true); chatNote('Der Assistent arbeitet noch …'); chat.timer = setInterval(chatPoll, 500); }
    else chatDropLive();
  } catch { store.set('chat', ''); } // the app was restarted: the conversation is gone
}
$('chatStop').addEventListener('click', async () => {
  if (!chat.id) return;
  chatNote('Breche ab …');
  try { await api.chatCancel(chat.id); } catch (e) { fail(e); }
});
$('chatNew').addEventListener('click', () => { if (!chat.busy) chatReset(); });
for (const [title, text] of IDEAS) {
  const b = node('button', title);
  b.type = 'button';
  b.title = text;
  b.addEventListener('click', () => chatSend(text));
  $('chatIdeas').appendChild(b);
}
$('chatSend').addEventListener('click', () => chatSend($('chatIn').value));
$('chatIn').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatSend($('chatIn').value); }
});
if (!S.demo) { chatKeyState(); chatRestore(); }

init();
