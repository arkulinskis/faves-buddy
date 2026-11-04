/* Faves Buddy extension: background service worker.
   - Talks to the app: POST <api>/clip with JSON as text/plain (no CORS preflight); the token is in the body.
     The connection code (FAVES1.<base64 {a: api origin, t: token}>) comes from Faves Buddy -> Tools -> Browser extension.
   - Right-click menus: save this page, a link, a picture, or selected text (as a note).
   - Shortcuts: Alt+Shift+S saves this tab, Alt+Shift+W saves the whole window as a tab set.
   - Reads the page the person is on (title, description, picture, schema.org types, place, event date) with
     chrome.scripting on their click (activeTab), so the app doesn't need to fetch it again. */
'use strict';

const get = (k) => new Promise((res) => chrome.storage.local.get(k, (v) => res(v[k])));
const set = (o) => new Promise((res) => chrome.storage.local.set(o, res));

function parseCode(code) {
  const m = String(code || '').trim().match(/^FAVES1\.([A-Za-z0-9_-]+)$/);
  if (!m) return null;
  try {
    const b64 = m[1].replace(/-/g, '+').replace(/_/g, '/');
    const j = JSON.parse(atob(b64 + '==='.slice((b64.length + 3) % 4)));
    if (!/^https?:\/\//.test(j.a) || !j.t) return null;
    return { api: j.a.replace(/\/$/, ''), token: j.t };
  } catch (e) { return null; }
}

async function call(action, payload) {
  const conn = await get('conn');
  if (!conn) return { ok: false, error: 'Not connected yet. Open the extension and paste your code.', notConnected: true };
  try {
    const r = await fetch(conn.api + '/clip', { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
                                                body: JSON.stringify(Object.assign({ token: conn.token, action }, payload || {})) });
    const j = await r.json().catch(() => ({ ok: false, error: 'Faves Buddy answered strangely (HTTP ' + r.status + ').' }));
    if (r.status === 401) j.notConnected = true;
    return j;
  } catch (e) {
    return { ok: false, error: 'Couldn\'t reach Faves Buddy. Check your connection.' };
  }
}

/* Runs inside the page (chrome.scripting). Plain function: no outside variables. */
function readPage() {
  const meta = (n) => { const el = document.querySelector('meta[property="' + n + '"],meta[name="' + n + '"]'); return el ? (el.getAttribute('content') || '').trim() : ''; };
  const out = { description: meta('og:description') || meta('description') || meta('twitter:description'), image: meta('og:image') || meta('twitter:image'),
                site_name: meta('og:site_name'), og_type: (meta('og:type') || '').toLowerCase(), lang: (document.documentElement.lang || '').slice(0, 8), schema: [] };
  const title = meta('og:title') || document.title || '';
  try { if (out.image) out.image = new URL(out.image, location.href).href; } catch (e) { out.image = ''; }
  const walk = (n) => {
    if (Array.isArray(n)) return n.forEach(walk);
    if (!n || typeof n !== 'object') return;
    const t = n['@type']; (Array.isArray(t) ? t : t ? [t] : []).forEach((x) => { if (typeof x === 'string') out.schema.push(x.split('/').pop()); });
    if (n.geo && n.geo.latitude && out.lat == null) { out.lat = +n.geo.latitude; out.lng = +n.geo.longitude; }
    if (n.startDate && !out.startDate) out.startDate = String(n.startDate);
    if (n.address && !out.address) { const a = n.address; out.address = typeof a === 'string' ? a : [a.streetAddress, a.addressLocality, a.addressRegion].filter(Boolean).join(', '); }
    ['@graph', 'mainEntity', 'location'].forEach((k) => n[k] && walk(n[k]));
  };
  document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => { try { walk(JSON.parse(s.textContent)); } catch (e) {} });
  out.schema = Array.from(new Set(out.schema)).slice(0, 12);
  const words = (document.body && document.body.innerText || '').split(/\s+/).length;
  if (words > 350) out.read_min = Math.max(1, Math.round(words / 230));
  const sel = String(window.getSelection ? window.getSelection() : '').trim();
  if (sel) out.selection = sel.slice(0, 600);
  Object.keys(out).forEach((k) => { if (out[k] === '' || out[k] == null || (Array.isArray(out[k]) && !out[k].length)) delete out[k]; });
  return { title: title.slice(0, 200), meta: out };
}

async function pageInfo(tab) {
  if (!tab || !/^https?:/.test(tab.url || '')) return { title: tab && tab.title || '', meta: {} };
  try {
    const [r] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: readPage });
    return r && r.result || { title: tab.title, meta: {} };
  } catch (e) {
    return { title: tab.title || '', meta: {} };  // some pages (the Web Store, PDFs) can't be read
  }
}

async function saveTab(tab, extra) {
  const info = await pageInfo(tab);
  const item = Object.assign({ url: tab.url, title: info.title || tab.title, meta: info.meta }, extra || {});
  return call('save', { item });
}

async function saveWindow(windowId, close) {
  const tabs = await chrome.tabs.query({ windowId });
  const items = tabs.filter((t) => /^https?:/.test(t.url || '')).map((t) => ({ url: t.url, title: t.title, favicon: t.favIconUrl && /^https:/.test(t.favIconUrl) ? t.favIconUrl : undefined }));
  if (!items.length) return { ok: false, error: 'No web pages in this window.' };
  const d = new Date();
  const r = await call('save_many', { items, group: 'Window · ' + d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) + ' ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) });
  if (r.ok && close) {
    const keep = await chrome.tabs.create({ windowId, url: (await get('conn')).api.replace(/\/_\/api$/, '') + '/#tabs', active: true });
    const ids = tabs.filter((t) => /^https?:/.test(t.url || '') && !t.pinned && t.id !== keep.id).map((t) => t.id);
    if (ids.length) await chrome.tabs.remove(ids);
  }
  return r;
}

function notify(title, message) {
  try { chrome.notifications.create({ type: 'basic', iconUrl: 'icons/icon-128.png', title, message: message || '' }); } catch (e) {}
}
function told(r, what) {
  if (r.ok) {
    const f = r.fave;
    if (f) notify((r.created ? 'Saved ' : 'Already saved: ') + f.emoji + ' ' + f.cat_name, f.title + (f.status === 'inbox' ? ' · in your inbox' : ''));
    else notify('Saved ' + r.added + ' tabs', (r.again ? r.again + ' were already saved. ' : '') + 'They\'re in your inbox, as a tab set.');
  } else notify('Couldn\'t save ' + what, r.error);
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: 'fb-page', title: 'Save this page to Faves Buddy', contexts: ['page'] });
    chrome.contextMenus.create({ id: 'fb-link', title: 'Save this link to Faves Buddy', contexts: ['link'] });
    chrome.contextMenus.create({ id: 'fb-image', title: 'Save this picture to Faves Buddy', contexts: ['image'] });
    chrome.contextMenus.create({ id: 'fb-note', title: 'Save “%s” as a note', contexts: ['selection'] });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  let r;
  if (info.menuItemId === 'fb-page') r = await saveTab(tab);
  else if (info.menuItemId === 'fb-link') r = await call('save', { item: { url: info.linkUrl, title: info.selectionText || '', meta: {} } });
  else if (info.menuItemId === 'fb-image') r = await call('save', { item: { kind: 'image', url: info.srcUrl, page_url: tab && tab.url, title: (tab && tab.title ? 'Picture from ' + tab.title : 'Picture'), meta: {} } });
  else if (info.menuItemId === 'fb-note') r = await call('note', { text: info.selectionText, page_url: tab && tab.url, page_title: tab && tab.title });
  if (r) told(r, 'that');
});

chrome.commands.onCommand.addListener(async (cmd, tab) => {
  if (!tab) [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (cmd === 'save-tab') told(await saveTab(tab), 'this tab');
  if (cmd === 'save-window') told(await saveWindow(tab.windowId, false), 'this window');
});

/* The popup asks the worker to do things (it closes when it loses focus; the worker keeps going). */
chrome.runtime.onMessage.addListener((m, sender, reply) => {
  (async () => {
    if (m.t === 'state') {
      const conn = await get('conn');
      reply({ connected: !!conn, api: conn && conn.api, ping: conn ? await call('ping') : null });
    } else if (m.t === 'connect') {
      const c = parseCode(m.code);
      if (!c) return reply({ ok: false, error: 'That doesn\'t look like a Faves Buddy code. It starts with FAVES1.' });
      await set({ conn: c });
      const p = await call('ping');
      if (!p.ok) { await chrome.storage.local.remove('conn'); return reply(p); }
      reply(p);
    } else if (m.t === 'disconnect') {
      await chrome.storage.local.remove('conn'); reply({ ok: true });
    } else if (m.t === 'save-tab') {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const r = await saveTab(tab, { note: m.note || '', list_id: m.list_id || null, category: m.category || null });
      if (r.ok && m.close) chrome.tabs.remove(tab.id);
      reply(r);
    } else if (m.t === 'save-window') {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      reply(await saveWindow(tab.windowId, !!m.close));
    } else if (m.t === 'call') {
      reply(await call(m.action, m.payload));
    } else if (m.t === 'reopen') {
      const r = await call('tabset_urls', { id: m.id });
      if (r.ok) { const w = await chrome.windows.create({ url: r.urls[0] }); for (const u of r.urls.slice(1)) await chrome.tabs.create({ windowId: w.id, url: u, active: false }); }
      reply(r);
    } else if (m.t === 'open-app') {
      const conn = await get('conn');
      if (conn) chrome.tabs.create({ url: conn.api.replace(/\/_\/api$/, '') + '/' + (m.hash || '') });
      reply({ ok: true });
    }
  })();
  return true;
});
