// "What should the circuit do?" as cards with a few plain settings instead of a spec file. Every wish writes
// the YAML that `rsx redesign` reads; the text editor below stays available for anything the cards cannot say.
import { icon } from './icons.js';

const LETTERS = ['a', 'b', 'c', 'd'];
const secs = (gt) => `${(gt / 20).toLocaleString('de-DE', { maximumFractionDigits: 2 })} s`;

const RULES = {
  and: { label: 'alle Hebel an sind', op: ' and ', text: 'nur, wenn alle Hebel an sind' },
  or: { label: 'mindestens ein Hebel an ist', op: ' or ', text: 'sobald mindestens ein Hebel an ist' },
  xor: { label: 'eine ungerade Zahl von Hebeln an ist', op: ' ^ ', text: 'wenn eine ungerade Zahl von Hebeln an ist (bei zwei Hebeln: genau einer)' },
  nor: { label: 'kein Hebel an ist', op: ' or ', not: true, text: 'nur, wenn kein Hebel an ist' },
  nand: { label: 'nicht alle Hebel an sind', op: ' and ', not: true, text: 'solange nicht alle Hebel an sind' },
};

function adder(bits) {
  const lines = [], ins = [];
  for (let i = bits - 1; i >= 0; i--) ins.push(`a${i}`);
  for (let i = bits - 1; i >= 0; i--) ins.push(`b${i}`);
  let carry = null;
  const fn = [];
  for (let i = 0; i < bits; i++) {
    const a = `a${i}`, b = `b${i}`;
    fn.push(`  s${i}: ${carry ? `${a} ^ ${b} ^ (${carry})` : `${a} ^ ${b}`}`);
    carry = carry ? `(${a} and ${b}) or ((${carry}) and (${a} ^ ${b}))` : `${a} and ${b}`;
  }
  fn.push(`  carry: ${carry}`);
  lines.push(`inputs: [${ins.join(', ')}]`, 'function:', ...fn);
  return lines.join('\n') + '\n';
}

// Only values the design search can build (measured with `rsx redesign` for every value; other lengths have no
// template yet). Clock: [period, on-time].
const PULSES = [2, 4, 6, 8, 12, 16, 20, 30, 40];
const EXTENDS = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 26, 30, 34, 40, 42, 50];
const CLOCKS = [[6, 2], [8, 2], [10, 4], [12, 6], [16, 4], [16, 8], [20, 10], [24, 6], [32, 8], [36, 18]];
const beat = (v) => v.beat.split('-').map(Number);

// field: {key, label, type: 'range'|'select', ...}; a range with `steps` moves over those values only.
// yaml(values) and say(values) describe the wish
const WISHES = [
  {
    id: 'logic', icon: 'gate', title: 'Lampe nach Regel', sub: 'Mehrere Hebel entscheiden zusammen, ob die Lampe leuchtet.',
    fields: [
      { key: 'n', label: 'Anzahl Hebel', type: 'range', min: 2, max: 4, value: 2, show: (v) => `${v}` },
      { key: 'rule', label: 'Die Lampe leuchtet, wenn …', type: 'select', value: 'and', options: Object.entries(RULES).map(([k, r]) => [k, r.label]) },
    ],
    name: (v) => `${v.rule}${v.n}`,
    yaml: (v) => {
      const ins = LETTERS.slice(0, v.n), r = RULES[v.rule];
      const expr = ins.join(r.op);
      return `inputs: [${ins.join(', ')}]\nfunction:\n  lampe: ${r.not ? `not (${expr})` : expr}\n`;
    },
    say: (v) => `${v.n} Hebel und eine Lampe. Die Lampe leuchtet ${RULES[v.rule].text}.`,
  },
  {
    id: 'not', icon: 'invert', title: 'Umkehrer', sub: 'Die Lampe leuchtet, solange der Hebel aus ist.',
    fields: [], name: () => 'umkehrer',
    yaml: () => 'inputs: [a]\nfunction:\n  lampe: not a\n',
    say: () => 'Ein Hebel und eine Lampe. Hebel aus: Lampe an. Hebel an: Lampe aus.',
  },
  {
    id: 'pulse', icon: 'pulse', title: 'Kurzer Impuls', sub: 'Ein Druck gibt ein Signal von fester Länge, egal wie lange man drückt.',
    fields: [
      { key: 'length', label: 'Länge des Impulses', type: 'range', steps: PULSES, value: 8, show: (v) => `${v} Ticks = ${secs(v)}` },
      { key: 'kind', label: 'Ausgelöst durch', type: 'select', value: 'lever', options: [['lever', 'Hebel'], ['button', 'Knopf']] },
    ],
    name: (v) => `impuls-${v.length}`,
    yaml: (v) => `behaviour: monostable\nlength: ${v.length}\n${v.kind === 'button' ? 'kind: button\n' : ''}`,
    say: (v) => `Jedes Einschalten des ${v.kind === 'button' ? 'Knopfs' : 'Hebels'} lässt die Lampe genau ${secs(v.length)} leuchten.`,
  },
  {
    id: 'extend', icon: 'glow', title: 'Nachleuchten', sub: 'Das Signal bleibt nach dem Auslösen eine Mindestzeit an.',
    fields: [{ key: 'length', label: 'Mindestdauer', type: 'range', steps: EXTENDS, value: 12, show: (v) => `${v} Ticks = ${secs(v)}` }],
    name: (v) => `nachleuchten-${v.length}`,
    yaml: (v) => `behaviour: pulse-extender\nlength: ${v.length}\n`,
    say: (v) => `Auch ein kurzes Antippen des Hebels lässt die Lampe mindestens ${secs(v.length)} leuchten.`,
  },
  {
    id: 'toggle', icon: 'toggle', title: 'Ein/Aus per Knopf', sub: 'Jeder Druck schaltet um: an, aus, an …',
    fields: [{ key: 'kind', label: 'Bedient mit', type: 'select', value: 'button', options: [['button', 'Knopf'], ['lever', 'Hebel (jedes Einschalten zählt)']] }],
    name: () => 'umschalter',
    yaml: (v) => `behaviour: t-flip-flop\n${v.kind === 'button' ? 'kind: button\n' : ''}`,
    say: () => 'Der erste Druck schaltet die Lampe an, der nächste wieder aus (ein „T-Flip-Flop“).',
  },
  {
    id: 'latch', icon: 'latch', title: 'An-Knopf und Aus-Knopf', sub: 'Ein Knopf schaltet ein, ein zweiter wieder aus.',
    fields: [], name: () => 'speicher',
    yaml: () => 'behaviour: rs-latch\n',
    say: () => 'Zwei Knöpfe: Der eine schaltet die Lampe ein, sie bleibt an, bis der andere gedrückt wird (ein „RS-Latch“).',
  },
  {
    id: 'clock', icon: 'clock', title: 'Blinker', sub: 'Läuft von selbst und schaltet im Takt an und aus.',
    fields: [{
      key: 'beat', label: 'Takt', type: 'select', value: '8-2',
      options: CLOCKS.map(([p, o]) => [`${p}-${o}`, `alle ${secs(p)} für ${secs(o)} an (${p} / ${o} Ticks)`]),
    }],
    name: (v) => `blinker-${v.beat}`,
    yaml: (v) => `behaviour: clock\nperiod: ${beat(v)[0]}\non_ticks: ${beat(v)[1]}\n`,
    say: (v) => `Ein Taktgeber ohne Hebel: alle ${secs(beat(v)[0])} ein Signal von ${secs(beat(v)[1])}.`,
  },
  {
    id: 'delay', icon: 'delay', title: 'Verzögerung', sub: 'Das Signal kommt später an, sonst unverändert.',
    fields: [{ key: 'delay', label: 'Verzögerung', type: 'range', min: 2, max: 16, step: 2, value: 4, show: (v) => `${v} Ticks = ${secs(v)}` }],
    name: (v) => `verzoegerung-${v.delay}`,
    yaml: (v) => `behaviour: delay\ndelay: ${v.delay}\n`,
    say: (v) => `Die Lampe folgt dem Hebel, aber ${secs(v.delay)} später.`,
  },
  {
    id: 'adder', icon: 'calc', title: 'Addierer', sub: 'Rechnet zwei Binärzahlen zusammen.',
    fields: [{ key: 'bits', label: 'Stellen je Zahl', type: 'range', min: 1, max: 3, value: 1, show: (v) => `${v} Bit (${2 * v} Hebel)` }],
    name: (v) => `addierer-${v.bits}`,
    yaml: (v) => adder(v.bits),
    say: (v) => `${2 * v.bits} Hebel für zwei Zahlen von 0 bis ${2 ** v.bits - 1}; die Lampen zeigen die Summe binär${v.bits > 1 ? ' (die Suche dauert hier länger, bis zu einer Minute)' : ''}.`,
  },
  {
    id: 'custom', icon: 'code', title: 'Eigene Vorgabe', sub: 'Formeln oder Wahrheitstabelle als Text schreiben (für Fortgeschrittene).',
    fields: [], custom: true,
  },
];

/** onSpec({name, text}) is called whenever the chosen wish or one of its settings changes; onCustom() when
 *  the text editor should take over. Returns {select(id)}. */
export function initWizard({ mount, onSpec, onCustom }) {
  const grid = document.createElement('div');
  grid.className = 'wishes';
  const detail = document.createElement('div');
  detail.className = 'wishdetail';
  mount.append(grid, detail);
  const values = Object.fromEntries(WISHES.map((w) => [w.id, Object.fromEntries(w.fields.map((f) => [f.key, f.value]))]));
  let current = null;

  function emit() {
    const w = current, v = values[w.id];
    detail.querySelector('.say').textContent = w.say(v);
    for (const f of w.fields) {
      const out = detail.querySelector(`[data-out="${f.key}"]`);
      if (out) out.textContent = f.show(v[f.key]);
    }
    onSpec({ name: w.name(v), text: `# ${w.title}: ${w.say(v)}\n${w.yaml(v)}` });
  }

  function select(id) {
    const w = WISHES.find((x) => x.id === id) || WISHES[0];
    current = w;
    for (const b of grid.children) b.classList.toggle('on', b.dataset.id === w.id);
    detail.textContent = '';
    if (w.custom) { onCustom(); return; }
    for (const f of w.fields) {
      const label = document.createElement('label');
      label.className = 'field';
      const head = document.createElement('span');
      head.textContent = f.label;
      label.appendChild(head);
      let inp;
      if (f.type === 'select') {
        inp = document.createElement('select');
        for (const [val, text] of f.options) { const o = document.createElement('option'); o.value = val; o.textContent = text; inp.appendChild(o); }
      } else {
        inp = document.createElement('input');
        inp.type = 'range';
        if (f.steps) { inp.min = 0; inp.max = f.steps.length - 1; inp.step = 1; }
        else { inp.min = f.min; inp.max = f.max; inp.step = f.step || 1; }
        const out = document.createElement('output');
        out.dataset.out = f.key;
        head.appendChild(out);
      }
      inp.dataset.key = f.key;
      inp.value = f.steps ? f.steps.indexOf(values[w.id][f.key]) : values[w.id][f.key];
      inp.addEventListener('input', () => {
        values[w.id][f.key] = f.steps ? f.steps[+inp.value] : f.type === 'range' ? +inp.value : inp.value;
        emit();
      });
      label.appendChild(inp);
      detail.appendChild(label);
    }
    const say = document.createElement('p');
    say.className = 'say';
    detail.appendChild(say);
    emit();
  }

  for (const w of WISHES) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.id = w.id;
    b.innerHTML = `<span class="tile">${icon(w.icon)}</span><span class="txt"><strong></strong><span></span></span>`;
    b.querySelector('strong').textContent = w.title;
    b.querySelector('.txt > span').textContent = w.sub;
    b.addEventListener('click', () => select(w.id));
    grid.appendChild(b);
  }
  return { select, get current() { return current && current.id; } };
}
