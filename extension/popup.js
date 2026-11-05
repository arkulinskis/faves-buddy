/* Faves Buddy popup: connect with a code, save this tab (with a note, a list, or a category), save the whole window
   (optionally closing it), re-file what was just saved, and reopen a saved tab set. Work happens in background.js. */
'use strict';
const $ = (s) => document.querySelector(s);
const send = (m) => new Promise((res) => chrome.runtime.sendMessage(m, (r) => res(chrome.runtime.lastError ? { ok: false, error: chrome.runtime.lastError.message } : (r || {}))));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let st = null, tab = null, cats = [], lists = [], chosenCat = null, count = 0;

function connectView(error) {
  $('#open').hidden = true;
  $('#app').innerHTML = (error ? '<div class="err">' + esc(error) + '</div>' : '') +
    '<h2>Connect to your Faves Buddy</h2><p class="muted">In Faves Buddy, open <b>Tools → Browser extension</b> and copy your connection code. Paste it here.</p>' +
    '<textarea id="code" placeholder="FAVES1.…" spellcheck="false"></textarea><button class="primary big" id="connect">Connect</button>';
}

function mainView(msg) {
  $('#open').hidden = false;
  const web = tab && /^https?:/.test(tab.url || '');
  $('#app').innerHTML = (msg || '') +
    (web ? '<div class="card"><div class="page">' + (tab.favIconUrl && /^https:/.test(tab.favIconUrl) ? '<img src="' + esc(tab.favIconUrl) + '" alt="">' : '') +
      '<div style="min-width:0"><div class="t">' + esc(tab.title) + '</div><div class="d">' + esc(new URL(tab.url).hostname) + '</div></div></div>' +
      '<textarea id="note" placeholder="Note (optional): why you\'re saving it"></textarea>' +
      (lists.length ? '<select id="list"><option value="">No list</option>' + lists.map((l) => '<option value="' + esc(l.id) + '">' + esc(l.emoji + ' ' + l.name) + '</option>').join('') + '</select>' : '') +
      '<details><summary>Pick a category yourself (otherwise it\'s sorted for you)</summary><div class="chips" style="margin-top:8px">' +
      cats.filter((c) => c.id !== 'other').map((c) => '<button class="chip" data-cat="' + c.id + '">' + c.emoji + ' ' + esc(c.name) + '</button>').join('') + '</div></details>' +
      '<div class="row"><button class="primary" id="save">Save tab</button><button id="saveclose">Save &amp; close</button></div></div>'
      : '<p class="muted">This page can\'t be saved (browser pages and the Web Store are off-limits). You can still save the window\'s other tabs.</p>') +
    '<div class="card"><b>All ' + count + ' tabs in this window</b><p class="muted">Saved together as a tab set, each sorted on its own.</p>' +
    '<label class="chk"><input type="checkbox" id="closeall"> Close them after saving (pinned tabs stay)</label><button class="big" id="savewin">Save the whole window</button></div>' +
    '<details id="devbox"><summary>Tabs on your other devices (your phone…)</summary><div class="sets" id="devs"><p class="muted">Loading…</p></div></details>' +
    '<details id="setsbox"><summary>Reopen a tab set</summary><div class="sets" id="sets"><p class="muted">Loading…</p></div></details>' +
    '<p class="muted" style="text-align:center">Connected as <b>' + esc(st.ping.name) + '</b> · <button class="link" id="disconnect">Disconnect</button></p>';
}

function savedView(r, what) {
  const f = r.fave;
  return '<div class="card"><div class="ok">✓ ' + esc(what) + '</div>' +
    (f ? '<div><b>' + esc(f.title) + '</b></div><div>' + (r.created ? 'Filed under' : 'Already saved, in') + ' <b>' + f.emoji + ' ' + esc(f.cat_name) + '</b>' + (f.status === 'inbox' ? ' · in your inbox' : '') + '</div>' +
      (f.reasons && f.reasons.length ? '<div class="why">Because: ' + f.reasons.map((x) => '<span>' + esc(x) + '</span>').join('') + '</div>' : '') +
      '<details><summary>Wrong? Move it</summary><div class="chips" style="margin-top:8px">' + cats.filter((c) => c.id !== 'other').map((c) =>
        '<button class="chip' + (c.id === f.cat ? ' on' : '') + '" data-refile="' + c.id + '" data-id="' + esc(f.id) + '">' + c.emoji + ' ' + esc(c.name) + '</button>').join('') + '</div></details>'
      : '<div>' + r.added + ' new tabs saved' + (r.again ? ', ' + r.again + ' were already there' : '') + '. They\'re in your inbox as “' + esc(r.name || 'a tab set') + '”.</div>') + '</div>';
}

async function refresh(msg) {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  count = (await chrome.tabs.query({ currentWindow: true })).filter((t) => /^https?:/.test(t.url || '')).length;
  st = await send({ t: 'state' });
  if (!st.connected) return connectView();
  if (!st.ping || !st.ping.ok) return connectView(st.ping && st.ping.error || 'Couldn\'t reach Faves Buddy.');
  cats = st.ping.cats || []; lists = st.ping.lists || [];
  mainView(msg);
}

document.addEventListener('click', async (e) => {
  const b = e.target.closest('button, a'); if (!b) return;
  if (b.id === 'shortcuts') { e.preventDefault(); chrome.tabs.create({ url: 'chrome://extensions/shortcuts' }); return; }
  if (b.id === 'open') { await send({ t: 'open-app', hash: '#inbox' }); window.close(); return; }
  if (b.id === 'connect') {
    b.disabled = true; b.textContent = 'Connecting…';
    const r = await send({ t: 'connect', code: $('#code').value });
    if (!r.ok) return connectView(r.error);
    return refresh('<div class="card"><div class="ok">✓ Connected. Hello ' + esc(r.name) + '!</div></div>');
  }
  if (b.id === 'disconnect') { await send({ t: 'disconnect' }); return connectView(); }
  if (b.dataset.cat) { chosenCat = chosenCat === b.dataset.cat ? null : b.dataset.cat; document.querySelectorAll('[data-cat]').forEach((x) => x.classList.toggle('on', x.dataset.cat === chosenCat)); return; }
  if (b.id === 'save' || b.id === 'saveclose') {
    b.disabled = true; b.textContent = 'Saving…';
    const r = await send({ t: 'save-tab', note: ($('#note') || {}).value, list_id: ($('#list') || {}).value, category: chosenCat, close: b.id === 'saveclose' });
    if (!r.ok) return r.notConnected ? connectView(r.error) : mainView('<div class="err">' + esc(r.error) + '</div>');
    $('#app').innerHTML = savedView(r, 'Saved');
    return;
  }
  if (b.id === 'savewin') {
    b.disabled = true; b.textContent = 'Saving ' + count + ' tabs…';
    const close = $('#closeall').checked;
    const r = await send({ t: 'save-window', close });
    if (!r.ok) return mainView('<div class="err">' + esc(r.error) + '</div>');
    if (close) { window.close(); return; }
    $('#app').innerHTML = savedView(r, 'Window saved');
    return;
  }
  if (b.dataset.refile) {
    const r = await send({ t: 'call', action: 'set_category', payload: { id: b.dataset.id, category: b.dataset.refile } });
    if (r.ok) $('#app').innerHTML = savedView(Object.assign(r, { created: true }), 'Moved and kept. Faves Buddy will remember.');
    return;
  }
  if (b.dataset.set) { b.disabled = true; await send({ t: 'reopen', id: b.dataset.set }); window.close(); }
  if (b.dataset.dev != null) {
    const d = devices[+b.dataset.dev]; if (!d) return;
    b.disabled = true; b.textContent = 'Sending ' + d.tabs.length + ' tabs…';
    const r = await send({ t: 'call', action: 'drop_links', payload: { items: d.tabs, group: 'Tabs from ' + d.name } });
    if (!r.ok) { $('#devs').innerHTML = '<div class="err">' + esc(r.error || "That didn't work.") + '</div>'; return; }
    await send({ t: 'open-app', hash: '#share/' + r.code }); window.close();
  }
});
/* Tabs open on this person's other devices (Chrome sync). Sent to the app's tab sorter as one pile per device. */
let devices = [];
async function loadDevices() {
  let list = [];
  try { list = await chrome.sessions.getDevices({ maxResults: 25 }); } catch (e) { list = []; }
  devices = list.map((dev) => {
    const tabs = [];
    (dev.sessions || []).forEach((s) => ((s.window && s.window.tabs) || (s.tab ? [s.tab] : [])).forEach((t) => {
      if (/^https?:/.test(t.url || '') && !tabs.some((x) => x.url === t.url)) tabs.push({ url: t.url, title: t.title || '' });
    }));
    return { name: dev.deviceName || 'another device', tabs, when: Math.max(0, ...(dev.sessions || []).map((s) => s.lastModified || 0)) };
  }).filter((d) => d.tabs.length);
  $('#devs').innerHTML = devices.length ? devices.map((d, i) => '<button data-dev="' + i + '"><span>' + esc(d.name) + '</span><span class="muted">Sort ' + d.tabs.length + ' tabs →</span></button>').join('') +
    '<p class="muted">Opens Faves Buddy with them as a pile to swipe through: keep, move or skip. Close them on the device afterwards.</p>'
    : '<p class="muted">No other devices found. Sign in to Chrome on your phone with the same Google account and turn on sync for open tabs (Settings → You and Google → Sync). Tabs show up here a minute later.</p>';
}
document.addEventListener('toggle', async (e) => {
  if (e.target.id === 'devbox' && e.target.open) { loadDevices(); return; }
  if (e.target.id !== 'setsbox' || !e.target.open) return;
  const r = await send({ t: 'call', action: 'tabsets' });
  $('#sets').innerHTML = r.ok && r.tabsets.length ? r.tabsets.map((s) => '<button data-set="' + esc(s.id) + '"><span>' + esc(s.name) + '</span><span class="muted">' + s.count + ' tabs</span></button>').join('')
    : '<p class="muted">No tab sets yet.</p>';
}, true);

$('#ver').textContent = 'v' + chrome.runtime.getManifest().version;
refresh();
