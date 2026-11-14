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

/** Tabs of documents. A document: {title, node | render(), download: {name, text, type} | () => {...}}. */
export class DocPane {
  constructor({ pane, tabs, body, save, close, onToggle }) {
    this.pane = pane; this.tabs = tabs; this.body = body; this.saveBtn = save; this.onToggle = onToggle;
    this.docs = new Map();
    this.current = null;
    close.addEventListener('click', () => this.hide());
    save.addEventListener('click', () => {
      const d = this.docs.get(this.current);
      const dl = d && (typeof d.download === 'function' ? d.download() : d.download);
      if (dl) saveBlob(new Blob([dl.text], { type: dl.type || 'text/plain;charset=utf-8' }), dl.name);
    });
  }

  get visible() { return !this.pane.hidden; }

  /** Add or replace a document and show it (unless `show` is false or another one should stay in front). */
  set(key, doc, { show = true } = {}) {
    this.docs.set(key, doc);
    if (show || this.current === key) this.show(key); else this.renderTabs();
  }

  has(key) { return this.docs.has(key); }

  remove(key) {
    this.docs.delete(key);
    if (this.current === key) {
      this.current = this.docs.size ? [...this.docs.keys()].pop() : null;
      if (this.current && this.visible) this.show(this.current); else if (!this.current) this.hide();
    }
    this.renderTabs();
  }

  renderTabs() {
    this.tabs.textContent = '';
    for (const [key, d] of this.docs) {
      const b = document.createElement('button');
      b.textContent = d.title;
      b.classList.toggle('on', key === this.current);
      b.addEventListener('click', () => this.show(key));
      this.tabs.appendChild(b);
    }
  }

  show(key = this.current || [...this.docs.keys()].pop()) {
    const d = this.docs.get(key);
    if (!d) return false;
    this.current = key;
    this.renderTabs();
    this.body.textContent = '';
    this.body.appendChild(d.node || d.render());
    this.body.scrollTop = 0;
    this.saveBtn.hidden = !d.download;
    const was = this.visible;
    this.pane.hidden = false;
    if (!was) this.onToggle?.(true);
    return true;
  }

  hide() {
    if (!this.visible) return;
    this.pane.hidden = true;
    this.onToggle?.(false);
  }
}
