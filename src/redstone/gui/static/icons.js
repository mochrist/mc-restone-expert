// Small line icons (24×24, stroke = currentColor). `<i data-icon="play"></i>` in the HTML is filled by applyIcons().
const P = {
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  cube: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
  layers: '<path d="M12 4l9 5-9 5-9-5 9-5z"/><path d="M3 14l9 5 9-5"/>',
  split: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M12 4.5v15"/>',
  play: '<path d="M8 5.5v13l10.5-6.5L8 5.5z"/>',
  pause: '<path d="M8.5 5v14M15.5 5v14"/>',
  back: '<path d="M18 6v12L9 12l9-6zM6 6v12"/>',
  forward: '<path d="M6 6v12l9-6-9-6zM18 6v12"/>',
  step: '<path d="M5 12h11M12 7l5 5-5 5M20 6v12"/>',
  reset: '<path d="M4 12a8 8 0 1 0 2.6-5.9"/><path d="M4 4.5V9h4.5"/>',
  hammer: '<path d="M14 4l6 6-2.5 2.5-6-6L14 4z"/><path d="M12.5 8.5L4 17l3 3 8.5-8.5"/>',
  zap: '<path d="M13 3L5 13.5h6L10 21l9-11h-6.5L13 3z"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
  sparkles: '<path d="M10 4l1.6 4.4L16 10l-4.4 1.6L10 16l-1.6-4.4L4 10l4.4-1.6L10 4z"/><path d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8L18 14z"/>',
  sliders: '<path d="M5 6h8M17 6h2M5 12h2M11 12h8M5 18h10M19 18h0"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  folder: '<path d="M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7z"/>',
  focus: '<path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15"/><circle cx="12" cy="12" r="2"/>',
  chat: '<path d="M4.5 5.5h15a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H10l-4.5 3.5v-3.5h-1a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  // design wishes
  gate: '<path d="M4 7h5M4 17h5M15.5 12H20"/><path d="M9 5h3a7 7 0 0 1 0 14H9V5z"/>',
  invert: '<path d="M4 12h3M17.5 12H20"/><path d="M7 6v12l8-6-8-6z"/><circle cx="16.2" cy="12" r="1.3"/>',
  pulse: '<path d="M3 16h5V8h5v8h8"/>',
  glow: '<path d="M3 16h4V8h10l4 8"/>',
  toggle: '<rect x="3" y="7.5" width="18" height="9" rx="4.5"/><circle cx="16.5" cy="12" r="2.5"/>',
  latch: '<rect x="4" y="5" width="16" height="14" rx="3"/><path d="M9 10v4M15 10v4"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  delay: '<path d="M3 12h4M17 12h4"/><rect x="7" y="8" width="10" height="8" rx="2"/><path d="M11 10.5v3M13.5 10.5v3"/>',
  calc: '<path d="M12 5v14M5 12h14"/><rect x="3.5" y="3.5" width="17" height="17" rx="3"/>',
  code: '<path d="M8.5 7.5L4 12l4.5 4.5M15.5 7.5L20 12l-4.5 4.5M13.5 5l-3 14"/>',
};

export function icon(name) {
  return `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ''}</svg>`;
}

export function applyIcons(root = document) {
  for (const el of root.querySelectorAll('i[data-icon]')) el.outerHTML = icon(el.dataset.icon);
}
