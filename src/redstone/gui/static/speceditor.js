// Spec editor: write what a circuit should do (YAML as in examples/specs and examples/behaviour) and start a
// design search for it. Lives as the "Spezifikation" tab of the document pane.

const TEMPLATES = [
  ['Logik als Formel', `# Ausgänge als Formeln der Eingänge: and, or, not, ^ (XOR), != und == sind erlaubt.
inputs: [a, b]
function:
  y: a != b
`],
  ['Logik mit mehreren Ausgängen (Volladdierer)', `inputs: [a, b, c]
function:
  sum: a ^ b ^ c
  carry: (a and b) or (c and (a ^ b))
`],
  ['Wahrheitstabelle', `# Jede Zeile: Stellung der Eingänge -> Zustand der Ausgänge (in der Reihenfolge von inputs/outputs).
inputs: [a, b]
outputs: [y]
table:
  "00": "0"
  "01": "1"
  "10": "1"
  "11": "0"
`],
  ['Teil-Wahrheitstabelle (Rest egal)', `# Nur die genannten Zeilen sind verlangt, alle anderen Kombinationen sind egal.
inputs: [h1, h2, h3]
outputs: [b1, b0]
others: dont_care
table:
  "000": "00"
  "100": "01"
  "010": "10"
  "001": "11"
`],
  ['Monoflop (fester Puls je Flanke)', `# Bei jeder steigenden Flanke am Hebel ein Puls von 8 Gameticks.
behaviour: monostable
length: 8
`],
  ['Pulsverlängerer', `# Der Ausgang bleibt mindestens 12 Gameticks an.
behaviour: pulse-extender
length: 12
`],
  ['T-Flip-Flop', `# Jeder Hebelpuls schaltet den Ausgang um.
behaviour: t-flip-flop
`],
  ['T-Flip-Flop hinter Logik', `# Schaltet um, wenn (a and b) einschaltet.
behaviour: t-flip-flop
inputs: [a, b]
gate: a and b
`],
  ['Clock', `# Dauerläufer: Periode 8 Gameticks, davon 2 an.
behaviour: clock
period: 8
on_ticks: 2
`],
];

const HELP = [
  'Logik: inputs (Namen der Hebel) und function (je Ausgang eine Formel) oder table (Wahrheitstabelle).',
  'Zeitverhalten und Speicher: behaviour mit monostable, pulse-extender, delay, t-flip-flop, rs-latch oder clock; dazu die Parameter aus den Vorlagen.',
  'max_delay: N begrenzt die Verzögerung in Gameticks. Größe, erlaubte Blöcke usw. stehen links unter Entwurfssuche → Optionen.',
  'Bis 8 Eingänge geht jede Funktion; größere nur, wenn sie sich zerlegen lässt (Addierer, Komparator, Multiplexer).',
];

export function openSpecEditor({ docs, api, setStatus, fail, onSaved, onSearch }) {
  const box = document.createElement('div');
  box.className = 'spec';
  const row = document.createElement('div');
  row.className = 'row';
  const nameLabel = document.createElement('label');
  nameLabel.textContent = 'Name ';
  const name = document.createElement('input');
  name.type = 'text';
  name.spellcheck = false;
  nameLabel.appendChild(name);
  const tpl = document.createElement('select');
  tpl.innerHTML = '<option value="">Vorlage einfügen …</option>' + TEMPLATES.map(([t], i) => `<option value="${i}">${t}</option>`).join('');
  row.append(nameLabel, tpl);
  const area = document.createElement('textarea');
  area.spellcheck = false;
  const actions = document.createElement('div');
  actions.className = 'row';
  const search = document.createElement('button');
  search.className = 'primary';
  search.textContent = 'Entwurf suchen';
  const save = document.createElement('button');
  save.textContent = 'Speichern';
  save.title = 'In der Dateiliste unter Spezifikationen ablegen (Ordner .cache/gui/specs)';
  const origin = document.createElement('span');
  origin.className = 'muted';
  actions.append(search, save, origin);
  const help = document.createElement('details');
  help.innerHTML = '<summary>Kurzanleitung</summary>';
  const ul = document.createElement('ul');
  for (const h of HELP) { const li = document.createElement('li'); li.textContent = h; ul.appendChild(li); }
  help.appendChild(ul);
  box.append(row, area, actions, help);

  const ed = { path: null, orig: null };
  const doc = { title: 'Spezifikation', node: box, download: () => ({ name: `${name.value.trim() || 'spezifikation'}.yaml`, text: area.value }) };

  tpl.addEventListener('change', () => {
    if (tpl.value === '') return;
    const text = TEMPLATES[+tpl.value][1];
    if (!area.value.trim() || area.value === ed.orig || TEMPLATES.some(([, t]) => t === area.value) || confirmReplace()) area.value = text;
    tpl.value = '';
    area.focus();
  });
  // no browser dialog: a second pick of a template replaces edited text
  let armed = false;
  function confirmReplace() {
    if (armed) { armed = false; return true; }
    armed = true;
    setStatus('Der Text wurde geändert: Vorlage noch einmal wählen, um ihn zu ersetzen.');
    return false;
  }
  area.addEventListener('keydown', (e) => { // Tab indents (YAML needs spaces)
    if (e.key !== 'Tab' || e.shiftKey || e.ctrlKey || e.altKey) return;
    e.preventDefault();
    area.setRangeText('  ', area.selectionStart, area.selectionEnd, 'end');
  });

  /** Path of a file with the editor's text: the opened file if unchanged, otherwise saved under the name. */
  ed.commit = async () => {
    const text = area.value;
    if (!text.trim()) { fail(new Error('Die Spezifikation ist leer.')); return null; }
    if (ed.path && text === ed.orig) return ed.path;
    try {
      const r = await api.saveSpec(name.value.trim() || 'spezifikation', text);
      ed.path = r.path; ed.orig = text;
      origin.textContent = r.path;
      await onSaved(r.path);
      return r.path;
    } catch (e) { fail(e); return null; }
  };
  ed.open = ({ name: n, text, path }) => {
    name.value = n;
    area.value = text === null ? TEMPLATES[0][1] : text;
    ed.path = path; ed.orig = text;
    origin.textContent = path || 'neu, noch nicht gespeichert';
    docs.set('spec', doc);
    if (text === null) area.focus();
  };
  search.addEventListener('click', async () => { const p = await ed.commit(); if (p) onSearch(p); });
  save.addEventListener('click', async () => { const p = await ed.commit(); if (p) setStatus(`Gespeichert: ${p}`); });
  return ed;
}
