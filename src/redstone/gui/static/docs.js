// Document pane: reports (analysis, redesign report, text view, timing diagrams) and the spec editor as tabs
// next to the 3D/2D views, plus a small Markdown renderer for the reports the server writes.

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function inline(text) {
  return esc(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

export function svgImage(svg, alt = '') {
  const img = document.createElement('img');
  img.className = 'diagram';
  img.alt = alt;
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  const wrap = document.createElement('div'); // long diagrams keep their size and scroll sideways
  wrap.className = 'diagramwrap';
  wrap.appendChild(img);
  return wrap;
}

function el(tag, html, cls) {
  const e = document.createElement(tag);
  if (html !== undefined) e.innerHTML = html;
  if (cls) e.className = cls;
  return e;
}

/** The subset of Markdown that `rsx explain` and `rsx redesign` write: headings, lists, tables, fenced
 *  code, paragraphs, bold, inline code and images (looked up by file name in `svgs`). */
export function renderMarkdown(md, svgs = {}) {
  const root = el('div', undefined, 'md');
  const lines = md.split('\n');
  let i = 0, list = null, para = [];
  const flush = () => {
    if (para.length) { root.appendChild(el('p', inline(para.join(' ')))); para = []; }
    list = null;
  };
  const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('```')) {
      flush();
      const code = [];
      for (i++; i < lines.length && !lines[i].startsWith('```'); i++) code.push(lines[i]);
      i++;
      const pre = document.createElement('pre');
      pre.textContent = code.join('\n');
      root.appendChild(pre);
      continue;
    }
    const h = /^(#{1,4}) (.*)$/.exec(line);
    const img = /^!\[([^\]]*)\]\(([^)]+)\)\s*$/.exec(line);
    if (h) {
      flush();
      root.appendChild(el('h' + Math.min(4, h[1].length + 1), inline(h[2])));
    } else if (img) {
      flush();
      const svg = svgs[img[2].split('/').pop()];
      if (svg) root.appendChild(svgImage(svg, img[1]));
    } else if (line.startsWith('|') && i + 1 < lines.length && /^\|[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      flush();
      const table = el('table');
      table.appendChild(el('thead', '<tr>' + cells(line).map((c) => `<th>${inline(c)}</th>`).join('') + '</tr>'));
      const body = el('tbody');
      for (i += 2; i < lines.length && lines[i].startsWith('|'); i++) {
        body.appendChild(el('tr', cells(lines[i]).map((c) => `<td>${inline(c)}</td>`).join('')));
      }
      table.appendChild(body);
      const wrap = el('div', undefined, 'tablewrap');
      wrap.appendChild(table);
      root.appendChild(wrap);
      continue;
    } else if (/^\s*- /.test(line)) {
      if (para.length) flush();
      if (!list) { list = el('ul'); root.appendChild(list); }
      list.appendChild(el('li', inline(line.replace(/^\s*- /, ''))));
    } else if (!line.trim()) {
      flush();
    } else if (list && /^\s+\S/.test(line)) {
      list.lastChild.innerHTML += ' ' + inline(line.trim());
    } else {
      list = null;
      para.push(line.trim());
    }
    i++;
  }
  flush();
  return root;
}

export function saveBlob(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

/** A small set of reports shown as tabs inside one task of the work panel.
 *  A document: {title, node, download: {name, text, type}}. */
export class DocPane {
  constructor({ tabs, body, save }) {
    this.tabs = tabs; this.body = body; this.saveBtn = save;
    this.docs = new Map();
    this.current = null;
    save.addEventListener('click', () => {
      const d = this.docs.get(this.current);
      const dl = d && (typeof d.download === 'function' ? d.download() : d.download);
      if (dl) saveBlob(new Blob([dl.text], { type: dl.type || 'text/plain;charset=utf-8' }), dl.name);
    });
  }

  get(key) { return this.docs.get(key); }

  /** Add or replace a document and bring it to the front. */
  set(key, doc) {
    this.docs.set(key, doc);
    this.show(key);
  }

  remove(key) {
    if (!this.docs.delete(key)) return;
    if (this.current === key) this.current = this.docs.size ? [...this.docs.keys()].pop() : null;
    this.show(this.current);
  }

  clear() {
    this.docs.clear();
    this.current = null;
    this.show(null);
  }

  show(key) {
    const d = this.docs.get(key);
    this.current = d ? key : null;
    this.tabs.textContent = '';
    for (const [k, doc] of this.docs) {
      const b = document.createElement('button');
      b.textContent = doc.title;
      b.classList.toggle('on', k === this.current);
      b.addEventListener('click', () => this.show(k));
      this.tabs.appendChild(b);
    }
    this.body.textContent = '';
    if (d) this.body.appendChild(d.node);
    this.saveBtn.hidden = !(d && d.download);
  }
}
