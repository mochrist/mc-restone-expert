// Thin client for the JSON API (docs/gui-api.md). Errors are thrown as Error(<German text from the server>).
async function req(path, body) {
  let res;
  try {
    res = await fetch(path, body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
  } catch (e) {
    throw new Error('Server nicht erreichbar: ' + e.message);
  }
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok || (data && data.error && !('done' in data))) {
    throw new Error((data && data.error) || `HTTP ${res.status}`);
  }
  return data;
}

export const api = {
  files: () => req('/api/files'),
  model: (path) => req('/api/model?path=' + encodeURIComponent(path)),
  sim: (body) => req('/api/sim', body),
  use: (id, p) => req(`/api/sim/${id}/use`, { p }),
  tick: (id, n) => req(`/api/sim/${id}/tick`, { n }),
  redesign: (path, compact) => req('/api/redesign', { path, compact }),
  job: (id, since) => req(`/api/job/${id}?since=${since}`),
  demo: () => req('demo/model.json'),
};
