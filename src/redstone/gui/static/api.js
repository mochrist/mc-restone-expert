// Thin client for the JSON API (docs/gui-api.md). Errors are thrown as Error(<German text from the server>).
async function send(path, init) {
  try {
    return await fetch(path, init);
  } catch (e) {
    throw new Error('Server nicht erreichbar: ' + e.message);
  }
}

async function req(path, body) {
  const res = await send(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok || (data && data.error && !('done' in data))) {
    throw new Error((data && data.error) || `HTTP ${res.status}`);
  }
  return data;
}

const query = (o) => Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')
  .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

export const api = {
  files: () => req('/api/files'),
  info: () => req('/api/info'),
  setCore: (core) => req('/api/core', { core }),
  model: (path) => req('/api/model?path=' + encodeURIComponent(path)),
  text: (path) => req('/api/text?path=' + encodeURIComponent(path)),
  sim: (body) => req('/api/sim', body),
  use: (id, p) => req(`/api/sim/${id}/use`, { p }),
  tick: (id, n) => req(`/api/sim/${id}/tick`, { n }),
  redesign: (path, options = {}) => req('/api/redesign', { path, ...options }),
  job: (id, since) => req(`/api/job/${id}?since=${since}`),
  // ref: {path} or {job} (the result of a design search)
  explain: (ref) => req('/api/explain', ref),
  dump: (ref, options = {}) => req('/api/dump', { ...ref, ...options }),
  scenario: (path) => req('/api/scenario', { path }),
  oracle: (path, golden) => req('/api/oracle', { path, golden }),
  saveSpec: (name, text) => req('/api/spec', { name, text }),
  async upload(file) {
    const res = await send('/api/upload?name=' + encodeURIComponent(file.name), { method: 'POST', body: file });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
    return data;
  },
  /** A file from the server: {blob, name}. */
  async download(ref, format) {
    const res = await send('/api/export?' + query({ ...ref, format }));
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error((data && data.error) || `HTTP ${res.status}`);
    }
    const m = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '');
    return { blob: await res.blob(), name: m ? m[1] : 'download' };
  },
  assistant: () => req('/api/assistant'),
  saveKey: (key) => req('/api/assistant/key', { key }),
  chat: (chat, message, current) => req('/api/chat', { chat, message, current }),
  chatEvents: (id, since) => req(`/api/chat/${id}?since=${since}`),
  demo: () => req('demo/model.json'),
};
