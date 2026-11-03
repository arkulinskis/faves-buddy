/* core.js: the shared front-end engine (window.UI). Same in every app made from APP_MAKER/template;
   app-specific things live in web/app.js (brand, nav, footer) and web/pages/*.html (the pages).

   Pages:   UI.page(name, {title, nav, icon, auth, order, chrome}, mount)
              auth: null (anyone) | 'guest' (signed-out only) | 'user' | 'admin'
              nav: label for the header / phone tab bar (omit to keep it out of the menus)
              mount(view, ctx) draws into `view`; ctx = {args, me, go, api}. Return a Promise (the page
              is "ready" when it resolves) or {ready, destroy}. URLs are #name/arg1/arg2.
   Server:  UI.api(fn, ...args) -> Promise of the server function's return value. A reply of
              {ok: false, error} rejects with that message (shown as a toast unless you .catch it).
            UI.apiQuiet(fn, ...args) is the same without Anvil's loading spinner.
   Auth:    UI.auth('login'|'signup'|'reset'|'logout', {...}) -> Promise of {ok, me, message}
   Helpers: UI.esc, UI.icon, UI.toast, UI.modal, UI.confirm, UI.busy, UI.formData, UI.fmtDate, UI.ago,
            UI.store, UI.setTheme, UI.feedback, UI.go, UI.refresh
   Tests:   window.UI_READY is true when the current page has finished loading. */
(function () {
  'use strict';
  if (window.UI && window.UI.__v) return;
  var UI = window.UI = { __v: 1, pages: {}, me: null, config: { name: 'App', key: 'app', home: 'home', landing: 'landing' } };
  window.UI_READY = false;

  // The saved theme lives under the app's key ('<key>.theme'), which is only known once the app configures UI:
  // apply it again then, or a saved Light/Dark choice is ignored after every reload.
  UI.configure = function (cfg) { Object.keys(cfg).forEach(function (k) { UI.config[k] = cfg[k]; }); if (cfg.key && UI.applyTheme) UI.applyTheme(UI.theme()); };

  /* ------------------------------------------------------------------ small helpers */
  UI.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  UI.plural = function (n, one, many) { return n + ' ' + (n === 1 ? one : (many || one + 's')); };
  UI.initials = function (name) {
    var p = String(name || '?').trim().split(/\s+/);
    return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase();
  };
  UI.fmtDate = function (iso, opts) {
    if (!iso) return '';
    var d = iso.length <= 10 ? new Date(iso + 'T12:00:00') : new Date(iso);
    return d.toLocaleDateString(undefined, opts || { day: 'numeric', month: 'short', year: 'numeric' });
  };
  UI.fmtDateTime = function (iso) {
    return iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
  };
  UI.ago = function (iso) {
    if (!iso) return '';
    var s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return 'just now';
    var steps = [[60, 'minute'], [24, 'hour'], [7, 'day'], [4.35, 'week'], [12, 'month'], [Infinity, 'year']], n = s / 60;
    for (var i = 0; i < steps.length; i++) {
      if (n < steps[i][0]) { n = Math.floor(n); return UI.plural(n, steps[i][1]) + ' ago'; }
      n = n / steps[i][0];
    }
    return '';
  };
  UI.store = {
    get: function (k, dflt) { try { var v = localStorage.getItem(UI.config.key + '.' + k); return v == null ? dflt : JSON.parse(v); } catch (e) { return dflt; } },
    set: function (k, v) { try { localStorage.setItem(UI.config.key + '.' + k, JSON.stringify(v)); } catch (e) {} }
  };
  UI.formData = function (form) {
    var out = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled) return;
      if (el.type === 'checkbox') out[el.name] = el.checked;
      else if (el.type === 'radio') { if (el.checked) out[el.name] = el.value; }
      else out[el.name] = el.value;
    });
    return out;
  };
  /* Disable a button while a Promise runs; returns the Promise. */
  UI.busy = function (btn, promise) {
    if (!btn) return promise;
    btn.disabled = true; btn.classList.add('is-busy');
    var done = function () { btn.disabled = false; btn.classList.remove('is-busy'); };
    promise.then(done, done);
    return promise;
  };

  var ICONS = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.5 3-5.5 6.5-5.5s6.5 2 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18 14.7c2.2.6 3.5 2.4 3.5 5.3"/>',
    sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z"/>',
    bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    back: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    bug: '<rect x="7" y="8" width="10" height="12" rx="5"/><path d="M12 8V5M9 5.5 7.5 4M15 5.5 16.5 4M7 13H3M21 13h-4M7.5 18l-3 2M16.5 18l3 2M7.5 9.5l-3-2M16.5 9.5l3-2"/>',
    bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    heart: '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    inbox: '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5 5h14l2 8v6H3v-6z"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    database: '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.5"/><path d="M4.5 5.5v13c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-13"/><path d="M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    pin: '<path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/>',
    camera: '<path d="M4 8h3l2-3h6l2 3h3v12H4z"/><circle cx="12" cy="13.5" r="3.5"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    filter: '<path d="M4 5h16l-6 7.5V19l-4 1.5v-8z"/>',
    more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
    tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.5"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7L11.5 7"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.5-1.5"/>',
    note: '<path d="M5 3h10l4 4v14H5z"/><path d="M15 3v4h4M8 12h8M8 16h6"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
    locate: '<circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="8"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>',
    archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9M10 13h4"/>',
    share: '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.5M8.2 13.2l7.6 4.5"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v4h16v-4"/>',
    download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 16v4h16v-4"/>',
    wand: '<path d="m4 20 11-11M14 4v3M18.5 5.5l-2 2M20 10h-3M17 3l1 1"/><path d="m13 8 3 3"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l2 2M15 8l2 2"/>',
    puzzle: '<path d="M9 4h3a2 2 0 1 1 4 0h3v5a2 2 0 1 0 0 4v6H4v-6a2 2 0 1 0 0-4V4z"/>',
    tabs: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M3 11h18M7 7V4h6v3M15 7V5h4v2"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    sort: '<path d="M7 4v16M3 16l4 4 4-4M17 20V4M13 8l4-4 4 4"/>',
    text: '<path d="M4 6V4h16v2M12 4v16M8 20h8"/>',
    phone: '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
    snooze: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2.5M5 3 2 6M19 3l3 3"/>',
    play: '<path d="M7 4v16l13-8z"/>',
    book: '<path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4z"/><path d="M20 4h-5a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h5z"/>',
    ticket: '<path d="M3 8a2 2 0 0 0 0 4 2 2 0 0 0 0 4v2h18v-2a2 2 0 0 1 0-4 2 2 0 0 1 0-4V6H3z"/><path d="M14 6v12"/>'
  };
  UI.ICONS = ICONS;
  UI.icon = function (name, cls) {
    return '<svg class="ui-ic ' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || ICONS.sparkle) + '</svg>';
  };

  /* ------------------------------------------------------------------ toasts, modals */
  UI.toast = function (msg, kind) {
    var box = document.querySelector('.ui-toasts');
    if (!box) { box = document.createElement('div'); box.className = 'ui ui-toasts'; box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
    var t = document.createElement('div');
    t.className = 'ui-toast' + (kind ? ' ' + kind : '');
    t.innerHTML = (kind === 'error' ? UI.icon('info') : kind === 'ok' ? UI.icon('check') : '') + '<span>' + UI.esc(msg) + '</span>';
    box.appendChild(t);
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 300); }, kind === 'error' ? 6500 : 3200);
  };
  UI.modal = function (html, opts) {
    opts = opts || {};
    var prev = document.activeElement;
    var wrap = document.createElement('div');
    wrap.className = 'ui ui-modal-wrap';
    wrap.innerHTML = '<div class="ui-modal' + (opts.wide ? ' wide' : '') + '" role="dialog" aria-modal="true">' +
      '<button class="ui-btn ghost icon ui-modal-x" data-close aria-label="Close">' + UI.icon('x') + '</button>' + html + '</div>';
    document.body.appendChild(wrap);
    document.documentElement.classList.add('ui-modal-open');
    function key(e) { if (e.key === 'Escape') close(); }
    function close() {
      if (!wrap.parentNode) return;
      wrap.remove(); document.removeEventListener('keydown', key);
      if (!document.querySelector('.ui-modal-wrap')) document.documentElement.classList.remove('ui-modal-open');
      if (opts.onclose) opts.onclose();
      if (prev && prev.focus) prev.focus();
    }
    document.addEventListener('keydown', key);
    wrap.addEventListener('mousedown', function (e) { if (e.target === wrap) close(); });
    wrap.addEventListener('click', function (e) { if (e.target.closest('[data-close]')) close(); });
    var first = wrap.querySelector('input, textarea, select');
    setTimeout(function () { (first || wrap.querySelector('.ui-modal')).focus && (first || wrap.querySelector('.ui-modal')).focus(); }, 30);
    return { el: wrap.querySelector('.ui-modal'), close: close };
  };
  UI.confirm = function (o) {
    o = typeof o === 'string' ? { title: o } : (o || {});
    return new Promise(function (resolve) {
      var answered = false;
      var m = UI.modal('<h2>' + UI.esc(o.title || 'Are you sure?') + '</h2>' + (o.text ? '<p class="muted">' + UI.esc(o.text) + '</p>' : '') +
        '<div class="ui-row end" style="margin-top:20px"><button class="ui-btn ghost" data-close>' + UI.esc(o.cancel || 'Cancel') + '</button>' +
        '<button class="ui-btn ' + (o.danger ? 'danger solid' : 'primary') + '" data-ok>' + UI.esc(o.ok || 'OK') + '</button></div>',
      { onclose: function () { if (!answered) resolve(false); } });
      m.el.querySelector('[data-ok]').onclick = function () { answered = true; m.close(); resolve(true); };
    });
  };

  /* ------------------------------------------------------------------ theme */
  UI.theme = function () { return UI.store.get('theme', 'auto'); };
  UI.applyTheme = function (t) {
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
    else document.documentElement.removeAttribute('data-theme');
    var dark = t === 'dark' || (t !== 'light' && window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('ui-dark', !!dark);
  };
  UI.setTheme = function (t) { UI.store.set('theme', t); UI.applyTheme(t); };
  UI.applyTheme(UI.theme());
  if (window.matchMedia) {
    try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { UI.applyTheme(UI.theme()); }); } catch (e) {}
  }

  /* ------------------------------------------------------------------ server bridge */
  var bridge = null;
  function send(kind, payload) {
    if (!bridge) return Promise.reject(new Error('The app is still starting.'));
    var out;
    try { out = bridge(kind, JSON.stringify(payload || {})); } catch (e) { return Promise.reject(e); }
    return Promise.resolve(out).then(function (r) {
      r = typeof r === 'string' ? JSON.parse(r) : (r || {});
      if (r.error) {
        var err = new Error(r.error); err.uiApi = true; err.denied = !!r.denied;
        if (r.detail) console.error(kind, payload && payload.fn, r.detail);
        if (r.reload) setTimeout(function () { location.reload(); }, 2500);
        throw err;
      }
      return r.result;
    });
  }
  function apiCall(quiet, fn, args) {
    return send('call', { fn: fn, args: args, quiet: quiet }).then(function (res) {
      if (res && typeof res === 'object' && res.ok === false) {
        var err = new Error(res.error || 'That didn\'t work.'); err.uiApi = true; err.expected = true; err.result = res;
        throw err;
      }
      return res;
    });
  }
  UI.api = function (fn) { return apiCall(false, fn, Array.prototype.slice.call(arguments, 1)); };
  UI.apiQuiet = function (fn) { return apiCall(true, fn, Array.prototype.slice.call(arguments, 1)); };
  /* Errors nobody caught become a toast, so a failed action is never silent. */
  window.addEventListener('unhandledrejection', function (e) {
    if (e.reason && e.reason.uiApi) { e.preventDefault(); UI.toast(e.reason.message, 'error'); }
  });

  /* Sign in / up / out. On success it navigates: to where the visitor was heading (UI.after) or home
     after signing in, to the landing page after signing out. */
  UI.auth = function (kind, payload) {
    return send(kind, payload || {}).then(function (r) {
      if (r && r.ok === false) { var err = new Error(r.error); err.uiApi = true; err.expected = true; throw err; }
      if (r && 'me' in r && (r.me || kind === 'logout')) {
        UI.me = r.me || null;
        var target = r.me ? (UI.after || '#' + UI.config.home) : '#' + UI.config.landing;
        UI.after = null;
        if (location.hash === target) route(); else location.hash = target;
      }
      return r;
    });
  };
  /* Update the signed-in user's details (e.g. a new name) and redraw the header, without reloading the page. */
  UI.setMe = function (me) {
    UI.me = me || null;
    if (shellRoot) renderChrome(current.name);
  };

  /* ------------------------------------------------------------------ pages and routing */
  UI.page = function (name, opts, mount) {
    if (typeof opts === 'function') { mount = opts; opts = {}; }
    opts.name = name; opts.mount = mount;
    UI.pages[name] = opts;
  };
  UI.allowed = function (p) {
    if (!p) return false;
    if (p.auth === 'user') return !!UI.me;
    if (p.auth === 'admin') return !!(UI.me && UI.me.is_admin);
    if (p.auth === 'guest') return !UI.me;
    return true;
  };
  UI.navPages = function () {
    return Object.keys(UI.pages).map(function (k) { return UI.pages[k]; })
      .filter(function (p) { return p.nav && UI.allowed(p) && (!p.when || p.when()); })
      .sort(function (a, b) { return (a.order || 50) - (b.order || 50); });
  };
  UI.parseHash = function () {
    var h = (location.hash || '').replace(/^#!?\/?/, '');
    var parts = h.split('?')[0].split('/').filter(function (x) { return x !== ''; }).map(decodeURIComponent);
    return { name: parts[0] || '', args: parts.slice(1) };
  };
  UI.hashFor = function (name) {
    var args = Array.prototype.slice.call(arguments, 1).filter(function (a) { return a != null && a !== ''; });
    return '#' + [name].concat(args.map(encodeURIComponent)).join('/');
  };
  UI.go = function (name) {
    var h = UI.hashFor.apply(null, arguments);
    if (location.hash === h) route(); else location.hash = h;
  };
  UI.refresh = function () { route(); };
  UI.after = null;  // where to go after signing in

  var shellRoot = null, view = null, current = { name: null, destroy: null }, routeSeq = 0;

  function defaultPage() { return UI.me ? UI.config.home : UI.config.landing; }

  function route() {
    var r = UI.parseHash(), name = r.name || defaultPage(), p = UI.pages[name];
    if (!p) { name = defaultPage(); p = UI.pages[name]; r.args = []; }
    if (p.auth === 'guest' && UI.me) { p = UI.pages[UI.config.home]; name = UI.config.home; r.args = []; }
    if ((p.auth === 'user' || p.auth === 'admin') && !UI.me) {
      UI.after = location.hash && location.hash !== '#' ? location.hash : null;
      p = UI.pages.auth; name = 'auth'; r.args = [];
    }
    if (p.auth === 'admin' && !(UI.me && UI.me.is_admin)) {
      UI.toast('That page is for admins only.', 'error');
      p = UI.pages[UI.config.home]; name = UI.config.home; r.args = [];
    }
    var seq = ++routeSeq;
    window.UI_READY = false;
    if (current.destroy) { try { current.destroy(); } catch (e) { console.error(e); } }
    current = { name: name, args: r.args, destroy: null };
    if (shellRoot) {
      shellRoot.className = 'ui ui-shell page-' + name + (UI.me ? ' signed-in' : ' signed-out') + (p.chrome === false ? ' no-chrome' : '');
      renderChrome(name);
    }
    // A fresh element for every page, so listeners a page adds to `view` never pile up.
    var fresh = view.cloneNode(false);
    view.parentNode.replaceChild(fresh, view);
    view = fresh;
    window.scrollTo(0, 0);
    document.title = (p.title ? (typeof p.title === 'function' ? p.title(r.args) : p.title) + ' · ' : '') + UI.config.name;
    var ctx = { name: name, args: r.args, me: UI.me, go: UI.go, api: UI.api, page: p };
    var out;
    try { out = p.mount(view, ctx); } catch (e) { console.error(e); out = Promise.reject(e); }
    var ready = out && typeof out.then === 'function' ? out : (out && out.ready) || Promise.resolve();
    if (out && out.destroy) current.destroy = out.destroy;
    Promise.resolve(ready).then(function () { if (seq === routeSeq) window.UI_READY = true; },
      function (e) {
        if (seq !== routeSeq) return;
        console.error(e);
        if (!view.innerHTML) view.innerHTML = '<div class="ui-wrap"><div class="ui-empty">' + UI.icon('info') +
          '<h3>This page didn\'t load</h3><p class="muted">' + UI.esc(e && e.message || 'Something went wrong.') + '</p>' +
          '<button class="ui-btn" onclick="UI.refresh()">Try again</button></div></div>';
        window.UI_READY = true;
      });
  }
  UI.current = function () { return current; };

  /* The shell's parts come from web/app.js: UI.shell = {header(me, active), footer(me), tabbar(me, active)} */
  function renderChrome(active) {
    var S = UI.shell || {};
    var hd = shellRoot.querySelector('[data-ui-header]'), ft = shellRoot.querySelector('[data-ui-footer]'), tb = shellRoot.querySelector('[data-ui-tabbar]');
    if (hd) hd.innerHTML = S.header ? S.header(UI.me, active) : '';
    if (ft) ft.innerHTML = S.footer ? S.footer(UI.me, active) : '';
    if (tb) tb.innerHTML = S.tabbar ? S.tabbar(UI.me, active) : '';
  }
  UI.renderChrome = function () { if (shellRoot) renderChrome(current.name); };

  /* Called by client_code/Main.py (and by the local harness) once the page is up. */
  UI.start = function (node, bridgeFn, bootJson) {
    bridge = bridgeFn;
    var boot = typeof bootJson === 'string' ? JSON.parse(bootJson || '{}') : (bootJson || {});
    UI.me = boot.me || null;
    var host = node && node.matches && node.matches('[data-ui-app]') ? node : (node && node.querySelector('[data-ui-app]')) || node || document.body;
    host.innerHTML = '<div class="ui ui-shell">' +
      '<header class="ui-header" data-ui-header></header>' +
      '<main class="ui-main" data-ui-view></main>' +
      '<footer class="ui-footer" data-ui-footer></footer>' +
      '<nav class="ui-tabbar" data-ui-tabbar aria-label="Main"></nav></div>';
    shellRoot = host.firstChild;
    view = host.querySelector('[data-ui-view]');
    if (UI.shell && UI.shell.wire) UI.shell.wire(shellRoot);
    window.addEventListener('hashchange', route);
    route();
  };

  /* ------------------------------------------------------------------ feedback (footer + menu)
     All feedback goes to Prepsto. The widget tag in head.html (data-prepsto="CODE") slides its panel in;
     any [data-feedback] or [data-prepsto-open] element opens it. If the widget hasn't loaded, the panel opens in a new tab.
     There is no in-app feedback form any more: Admin -> Feedback only lists older messages (and app requests). */
  UI.feedback = function () {
    if (window.Prepsto && window.Prepsto.open) { window.Prepsto.open(); return; }
    var tag = document.querySelector('script[data-prepsto]');
    var code = tag && tag.getAttribute('data-prepsto');
    if (code && code.indexOf('__') !== 0) window.open('https://prepsto.com/#f/' + encodeURIComponent(code), '_blank', 'noopener');
    else UI.toast('Feedback is not set up yet.', 'error');
  };

  /* Shared clicks: [data-go="page/arg"], [data-feedback], [data-theme-set] anywhere in the app. */
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[data-go],[data-feedback],[data-theme-set]');
    if (!el) return;
    if (el.hasAttribute('data-go')) { e.preventDefault(); UI.go.apply(null, el.getAttribute('data-go').split('/')); }
    else if (el.hasAttribute('data-feedback')) { e.preventDefault(); UI.feedback(el.getAttribute('data-feedback') || null); }
    else if (el.hasAttribute('data-theme-set')) { e.preventDefault(); UI.setTheme(el.getAttribute('data-theme-set')); if (UI.shell && UI.shell.onTheme) UI.shell.onTheme(); }
  });
})();


/* app.js: this app's identity and frame: name, header, footer, phone tab bar.
   Pages live in web/pages/*.html (shared pieces in _fb, _fbmap, _fbmedia). The engine (window.UI) is web/core.js. */
(function () {
  'use strict';
  UI.configure({
    name: 'Faves Buddy',
    key: 'favesbuddy',          // prefix for this app's browser storage
    tagline: 'Tabs, pins, screenshots and ideas: sorted, mapped and shared.',
    home: 'home',                // first page after signing in
    landing: 'landing'           // first page for visitors who aren't signed in
  });

  var esc = UI.esc;
  UI.inboxCount = 0;  // set by the Faves and Inbox pages; shown as a dot on "Inbox"

  function brand() {
    return '<a class="ui-brand" href="#" data-go="' + (UI.me ? UI.config.home : UI.config.landing) + '" aria-label="' + esc(UI.config.name) + ' home">' +
      '<img src="_/theme/icon.svg" alt="" width="32" height="32"><span>' + esc(UI.config.name) + '</span></a>';
  }

  function themeSwitch() {
    var t = UI.theme();
    return '<div class="ui-seg" role="group" aria-label="Appearance">' + [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']].map(function (o) {
      return '<button type="button" data-theme-set="' + o[0] + '" class="' + (t === o[0] ? 'on' : '') + '">' + o[1] + '</button>';
    }).join('') + '</div>';
  }

  function userMenu(me) {
    return '<div class="ui-menu" data-menu hidden>' +
      '<div class="ui-menu-head"><strong>' + esc(me.name) + '</strong><span class="muted small">' + esc(me.email) + '</span></div>' +
      '<a href="#lists" data-go="lists">' + UI.icon('grid') + 'Your lists</a>' +
      '<a href="#tidy" data-go="tidy">' + UI.icon('wand') + 'Tidy tabs &amp; screenshots</a>' +
      '<a href="#tabs" data-go="tabs">' + UI.icon('tabs') + 'Saved tab sets</a>' +
      '<a href="#tools" data-go="tools">' + UI.icon('puzzle') + 'Extension, import &amp; tools</a>' +
      '<a href="#profile" data-go="profile">' + UI.icon('user') + 'Your profile</a>' +
      (me.is_admin ? '<a href="#admin" data-go="admin">' + UI.icon('shield') + 'Admin</a>' : '') +
      '<div class="ui-menu-block"><span class="small muted">Appearance</span>' + themeSwitch() + '</div>' +
      '<button type="button" data-feedback>' + UI.icon('chat') + 'Submit feedback</button>' +
      '<button type="button" data-lk-open="overview">' + UI.icon('lock') + 'Privacy &amp; Terms</button>' +
      '<button type="button" data-signout>' + UI.icon('logout') + 'Sign out</button></div>';
  }

  function navLabel(p) {
    return '<span>' + esc(p.nav) + '</span>' + (p.name === 'inbox' && UI.inboxCount ? '<span class="fb-count">' + UI.inboxCount + '</span>' : '');
  }

  UI.shell = {
    header: function (me, active) {
      var nav = UI.navPages();
      return '<div class="ui-header-in">' + brand() +
        (me ? '<nav class="ui-nav" aria-label="Main">' + nav.map(function (p) {
          return '<a href="#' + p.name + '" class="' + (p.name === active ? 'on' : '') + '">' + UI.icon(p.icon) + navLabel(p) + '</a>';
        }).join('') + '</nav>' : '') +
        '<div class="ui-header-right">' +
        (me ? '<a class="ui-btn primary fb-save-btn" href="#add" data-go="add">' + UI.icon('plus') + '<span>Save</span></a>' +
              '<button type="button" class="ui-avatar-btn" data-menu-toggle aria-label="Your account" aria-haspopup="true">' + esc(UI.initials(me.name)) + '</button>' + userMenu(me)
          : (active === 'auth' ? '' : '<a class="ui-btn ghost" href="#auth" data-go="auth">Sign in</a><a class="ui-btn primary" href="#auth/signup" data-go="auth/signup">Get started</a>')) +
        '</div></div>';
    },
    footer: function (me) {
      return '<div class="ui-footer-in"><div class="ui-footer-brand">' + brand() + '<p class="muted small">' + esc(UI.config.tagline) + '</p></div>' +
        '<div class="ui-footer-links">' +
        '<a href="#landing" data-go="landing">About</a>' +
        (me ? '<a href="#tools" data-go="tools">Browser extension</a>' : '') +
        '<a href="https://prepsto.com/#f/vef7qyr" target="_blank" rel="noopener" data-prepsto-open>Submit feedback</a>' +
        '<button type="button" data-lk-open="overview">Privacy &amp; Terms</button>' +
        '</div><p class="ui-footer-legal small muted">© ' + new Date().getFullYear() + ' ' + esc(UI.config.name) +
        ' · Map data © OpenStreetMap contributors</p></div>';
    },
    tabbar: function (me, active) {
      if (!me) return '';
      var tab = function (name, icon, label) {
        return '<a href="#' + name + '" class="' + (name === active ? 'on' : '') + '">' + UI.icon(icon) + '<span>' + label + '</span>' +
          (name === 'inbox' && UI.inboxCount ? '<i class="fb-tab-dot"></i>' : '') + '</a>';
      };
      return tab('home', 'heart', 'Faves') + tab('inbox', 'inbox', 'Inbox') +
        '<a href="#add" class="fb-tab-add' + (active === 'add' ? ' on' : '') + '" aria-label="Save something">' + UI.icon('plus') + '</a>' +
        tab('map', 'map', 'Map') + tab('discover', 'compass', 'Discover');
    },
    wire: function (root) {
      root.addEventListener('click', function (e) {
        var t = e.target.closest('[data-menu-toggle]');
        var menu = root.querySelector('[data-menu]');
        if (t && menu) { menu.hidden = !menu.hidden; t.setAttribute('aria-expanded', String(!menu.hidden)); return; }
        if (e.target.closest('[data-signout]')) { UI.auth('logout').then(function () { UI.toast('Signed out. See you soon!'); }); }
        if (menu && !menu.hidden && !e.target.closest('[data-menu] .ui-seg')) menu.hidden = true;
      });
      document.addEventListener('keydown', function (e) {
        var menu = root.querySelector('[data-menu]');
        if (e.key === 'Escape' && menu) menu.hidden = true;
      });
    },
    onTheme: function () {  // redraw the menu's Auto/Light/Dark buttons and keep the menu open
      var menu = document.querySelector('[data-menu]'), open = menu && !menu.hidden;
      UI.renderChrome();
      if (open) document.querySelector('[data-menu]').hidden = false;
      if (window.FB && FB.onTheme) FB.onTheme();
    }
  };
  UI.setInbox = function (n) {
    if (UI.inboxCount === (n || 0)) return;
    UI.inboxCount = n || 0;
    UI.renderChrome();
  };
})();


/* ===== _fb.html ===== */
(function () {
  'use strict';
  var FB = window.FB = window.FB || {}, esc = UI.esc;
  FB.CATS = []; FB.CAT = {};

  var bootP = null;
  FB.boot = function (force) {
    if (!bootP || force) {
      bootP = UI.apiQuiet('fb_boot').then(function (b) {
        FB.setCats(b.cats);
        FB.prefs = { home: b.home, settings: b.settings || {} }; FB.API = b.api || '';
        FB.aiSort = b.ai || { available: false, on: false };   // AI second opinion for sorting (in progress, AISort.py)
        return b;
      }, function (e) { bootP = null; throw e; });
    }
    return bootP;
  };
  FB.setCats = function (cats) { if (!cats) return; FB.CATS = cats; FB.CAT = {}; cats.forEach(function (c) { FB.CAT[c.id] = c; }); };
  FB.cat = function (id) { return FB.CAT[id] || FB.CAT.other || { id: 'other', name: 'Unsorted', emoji: '📌', color: '#90a4ae' }; };
  FB.catChip = function (id, cls) {
    var c = FB.cat(id);
    return '<span class="fb-cat ' + (cls || '') + '"><span class="dot" style="background:' + esc(c.color) + '"></span>' + esc(c.emoji) + ' ' + esc(c.name) + '</span>';
  };
  FB.catPicker = function (current, attr) {
    attr = attr || 'data-cat';
    return '<div class="fb-picker">' + FB.CATS.map(function (c) {
      return '<button type="button" class="fb-chip' + (c.id === current ? ' on' : '') + '" ' + attr + '="' + c.id + '">' + c.emoji + ' ' + esc(c.name) + '</button>';
    }).join('') + '</div>';
  };
  FB.KIND_ICON = { link: 'link', place: 'pin', photo: 'image', note: 'note', idea: 'bulb', event: 'calendar' };
  FB.STAGES = [['', 'No status'], ['want', 'Want to go'], ['been', 'Been there'], ['loved', 'Loved it']];
  /* The same three stages, worded for what the fave is. */
  FB.stages = function (f) {
    if (f.kind === 'place' || f.kind === 'event' || f.lat != null) return FB.STAGES.slice(1);
    var later = { read: 'To read', watch: 'To watch', listen: 'To listen', recipes: 'To cook', learn: 'To learn', shop: 'Want it', gifts: 'To give' }[f.cat] || 'Later';
    return [['want', later], ['been', 'Done'], ['loved', 'Loved it']];
  };
  FB.stageBadge = function (s, f) {
    var label = {}; (f ? FB.stages(f) : FB.STAGES).forEach(function (x) { label[x[0]] = x[1]; });
    if (s === 'loved') return '<span class="ui-badge" style="background:var(--c-accent-soft);color:var(--c-accent)">' + UI.icon('heart') + 'Loved</span>';
    if (s === 'been') return '<span class="ui-badge good">' + UI.icon('check') + esc(label.been) + '</span>';
    if (s === 'want') return '<span class="ui-badge brand">' + UI.icon('star') + esc(label.want) + '</span>';
    return '';
  };

  /* A soft gradient tile in the category's colour, for faves without a picture. */
  function hash(s) { var h = 0; s = String(s || ''); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); }
  FB.tile = function (f) {
    var c = FB.cat(f.cat), h = hash(f.id || f.title), a = 120 + (h % 120), r1 = 60 + (h % 50), r2 = 30 + (h % 40);
    var showText = f.kind === 'note' || f.kind === 'idea';
    var rgb = (c.color || '#888888').match(/\w\w/g).map(function (x) { return parseInt(x, 16); });
    var light = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 175;
    return '<div class="fb-tile" style="background:linear-gradient(' + a + 'deg,' + c.color + ',color-mix(in srgb,' + c.color + ' 55%,#fff))">' +
      '<span class="ring" style="width:' + (r1 * 2) + 'px;height:' + (r1 * 2) + 'px;left:' + (h % 70) + '%;top:' + (h % 50 - 20) + '%"></span>' +
      '<span class="ring" style="width:' + (r2 * 2) + 'px;height:' + (r2 * 2) + 'px;left:' + (h % 30) + '%;top:' + (40 + h % 40) + '%"></span>' +
      (showText && (f.note || f.desc) ? '<span class="txt"' + (light ? ' style="color:#3b3000"' : '') + '>' + esc((f.note || f.desc || '').slice(0, 160)) + '</span>' : '<span class="em">' + esc(c.emoji) + '</span>') +
      '<span class="kind">' + UI.icon(FB.KIND_ICON[f.kind] || 'link') + '</span></div>';
  };
  FB.cover = function (f, extra) {
    var img = f.image ? '<img src="' + esc(f.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : '';
    return '<div class="fb-cover">' + FB.tile(f) + img + (extra || '') + '</div>';
  };

  FB.card = function (f, o) {
    o = o || {};
    var c = FB.cat(f.cat), sub = '';
    if (f.kind === 'place' || (f.lat != null && !f.url)) sub = UI.icon('pin') + '<span>' + esc(f.address || 'On the map') + '</span>';
    else if (f.domain) sub = UI.icon('globe') + '<span>' + esc(f.domain) + '</span>';
    else if (f.kind === 'photo') sub = UI.icon('image') + '<span>Picture</span>';
    else sub = UI.icon(FB.KIND_ICON[f.kind] || 'note') + '<span>' + (f.kind === 'idea' ? 'Idea' : 'Note') + '</span>';
    var pills = '<span class="fb-pill">' + esc(c.emoji) + ' ' + esc(c.name) + '</span>';
    if (f.event_at) pills += '<span class="fb-pill accent">' + UI.icon('calendar') + esc(FB.when(f.event_at, true)) + '</span>';
    else if (f.read_min) pills += '<span class="fb-pill dark">' + f.read_min + ' min</span>';
    var meta = [];
    if (o.from && f.lat != null) meta.push(FB.fmtDist(FB.dist(o.from, f)));
    var oh = f.osm && f.osm.opening_hours ? FB.openNow(f.osm.opening_hours) : null;
    if (oh === true) meta.push('<span class="fb-open">Open now</span>'); else if (oh === false) meta.push('<span class="fb-closed">Closed now</span>');
    if (f.owner) meta.push('from ' + esc(f.owner));
    if (f.saves > 1) meta.push('saved ' + f.saves + '×');
    var tags = (f.tags || []).slice(0, 3);
    var href = o.href || ('#fave/' + encodeURIComponent(f.id));
    return '<article class="fb-card" data-fave="' + esc(f.id) + '">' +
      (o.noStage || !f.mine && f.mine !== undefined ? '' : '<button type="button" class="fb-stage' + (f.stage === 'loved' ? ' loved' : '') + '" data-love aria-label="' + (f.stage === 'loved' ? 'Loved' : 'Love it') + '" title="Love it">' + UI.icon('heart') + '</button>') +
      '<a href="' + esc(href) + '" style="color:inherit;text-decoration:none;display:contents">' +
      FB.cover(f, '<div class="fb-on-img">' + pills + '</div>') +
      '<div class="fb-card-body"><h3>' + esc(f.title || 'Untitled') + '</h3><div class="fb-sub">' + sub + '</div>' +
      (meta.length ? '<div class="fb-sub small">' + meta.join(' · ') + '</div>' : '') +
      (tags.length ? '<div class="fb-tags">' + tags.map(function (t) { return '<span class="fb-tag">#' + esc(t) + '</span>'; }).join('') + '</div>' : '') +
      '</div></a>' + (o.actions ? '<div class="fb-actions">' + o.actions(f) + '</div>' : '') + '</article>';
  };
  FB.grid = function (faves, o) { return '<div class="fb-grid">' + faves.map(function (f) { return FB.card(f, o); }).join('') + '</div>'; };

  /* Hearts on cards: toggles "Loved". Pages call FB.wireCards(view, onChange). */
  FB.wireCards = function (root, onChange) {
    root.addEventListener('click', function (e) {
      var b = e.target.closest('[data-love]');
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      var id = b.closest('[data-fave]').getAttribute('data-fave'), loved = b.classList.contains('loved');
      b.classList.toggle('loved', !loved);
      UI.apiQuiet('update_fave', id, { stage: loved ? '' : 'loved' }).then(function (r) {
        UI.toast(loved ? 'Unloved' : 'Loved it ♥', 'ok'); if (onChange) onChange(r.fave);
      }, function (err) { b.classList.toggle('loved', loved); UI.toast(err.message, 'error'); });
    });
  };

  /* ---------------------------------------------------------------- time + distance */
  FB.when = function (iso, short) {
    if (!iso) return '';
    var d = new Date(iso), now = new Date(), days = Math.round((new Date(d.toDateString()) - new Date(now.toDateString())) / 864e5);
    var t = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    var day = days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : days > 1 && days < 7 ? d.toLocaleDateString(undefined, { weekday: short ? 'short' : 'long' })
      : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
    return day + (short && days > 6 ? '' : ' ' + t);
  };
  FB.dist = function (a, b) {
    if (!a || !b || a.lat == null || b.lat == null) return null;
    var R = 6371, dLat = (b.lat - a.lat) * Math.PI / 180, dLng = (b.lng - a.lng) * Math.PI / 180;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  };
  FB.fmtDist = function (km) {
    if (km == null) return '';
    if (km < 1) return Math.round(km * 1000 / 10) * 10 + ' m';
    return (km < 10 ? km.toFixed(1) : Math.round(km)) + ' km';
  };

  /* OpenStreetMap opening_hours, the common shapes: "Mo-Fr 09:00-17:00; Sa,Su 10:00-16:00", "24/7",
     "Mo-Su 17:00-03:00" (past midnight), "Tu-Sa 11:00-14:00,17:00-22:00", "Su off". Anything fancier
     (holidays, months, weeks) -> null (we don't guess). */
  var DAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
  FB.openNow = function (spec, when) {
    if (!spec) return null;
    spec = String(spec).trim();
    if (spec === '24/7') return true;
    if (/PH|SH|week|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|sunrise|sunset|\|\|/.test(spec)) return null;
    var now = when || new Date(), dow = (now.getDay() + 6) % 7, mins = now.getHours() * 60 + now.getMinutes();
    var open = false, known = false;
    var rules = spec.split(';');
    for (var i = 0; i < rules.length; i++) {
      var r = rules[i].trim(); if (!r) continue;
      var m = r.match(/^((?:[A-Z][a-z](?:-[A-Z][a-z])?,?)+)\s+(.+)$/);
      var days = [0, 1, 2, 3, 4, 5, 6], times = r;
      if (m) { days = expandDays(m[1]); times = m[2]; } else if (!/^\d/.test(r)) return null;
      if (!days) return null;
      var prevDay = (dow + 6) % 7;
      if (/^off|closed$/i.test(times.trim())) { if (days.indexOf(dow) >= 0) { open = false; known = true; } continue; }
      var spans = times.split(',');
      for (var j = 0; j < spans.length; j++) {
        var t = spans[j].trim().match(/^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\+?$/);
        if (!t) return null;
        var a = +t[1] * 60 + +t[2], b = +t[3] * 60 + +t[4];
        if (days.indexOf(dow) >= 0) { known = true; if (b > a ? mins >= a && mins < b : mins >= a) open = true; }
        if (b <= a && days.indexOf(prevDay) >= 0 && mins < b) { known = true; open = true; }
      }
    }
    return known ? open : false;
  };
  function expandDays(s) {
    var out = [];
    var parts = s.replace(/,$/, '').split(',');
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].split('-'), a = DAYS.indexOf(p[0]), b = p[1] ? DAYS.indexOf(p[1]) : a;
      if (a < 0 || b < 0) return null;
      for (var d = a; ; d = (d + 1) % 7) { out.push(d); if (d === b) break; }
    }
    return out;
  }

  /* ---------------------------------------------------------------- location */
  var geoP = null;
  FB.geo = function (ask) {
    var cached = null;
    try { cached = JSON.parse(sessionStorage.getItem('fb.geo') || 'null'); } catch (e) {}
    if (cached && Date.now() - cached.t < 10 * 60e3) return Promise.resolve(cached);
    if (!ask) return Promise.resolve(FB.prefs && FB.prefs.home ? Object.assign({ home: true }, FB.prefs.home) : null);
    if (!geoP) {
      geoP = new Promise(function (resolve) {
        if (!navigator.geolocation) return resolve(null);
        navigator.geolocation.getCurrentPosition(function (p) {
          var g = { lat: p.coords.latitude, lng: p.coords.longitude, t: Date.now(), label: 'You are here' };
          try { sessionStorage.setItem('fb.geo', JSON.stringify(g)); } catch (e) {}
          resolve(g);
        }, function () { resolve(null); }, { enableHighAccuracy: false, timeout: 9000, maximumAge: 300000 });
      }).then(function (g) { geoP = null; return g || (FB.prefs && FB.prefs.home ? Object.assign({ home: true }, FB.prefs.home) : null); });
    }
    return geoP;
  };

  /* ---------------------------------------------------------------- snooze + lists */
  FB.snoozeChoices = function () {
    var now = new Date(), out = [];
    var tonight = new Date(now); tonight.setHours(19, 0, 0, 0); if (tonight <= now) tonight.setDate(tonight.getDate() + 1);
    var sat = new Date(now); sat.setDate(now.getDate() + ((6 - now.getDay() + 7) % 7 || 7)); sat.setHours(9, 0, 0, 0);
    var week = new Date(now); week.setDate(now.getDate() + ((8 - now.getDay()) % 7 || 7)); week.setHours(9, 0, 0, 0);
    var month = new Date(now); month.setMonth(now.getMonth() + 1); month.setHours(9, 0, 0, 0);
    out.push(['Tonight', tonight], ['This weekend', sat], ['Next week', week], ['In a month', month]);
    return out.map(function (x) { return [x[0], x[1].toISOString(), x[1].toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })]; });
  };
  FB.snoozeModal = function (id) {
    return new Promise(function (resolve) {
      var m = UI.modal('<h2>Remind me later</h2><p class="muted">It leaves your inbox and comes back when you choose.</p><div class="fb-sheet-list">' +
        FB.snoozeChoices().map(function (c) { return '<button class="ui-btn block" data-until="' + c[1] + '">' + UI.icon('snooze') + esc(c[0]) + '<span class="ui-spacer"></span><span class="muted small">' + esc(c[2]) + '</span></button>'; }).join('') +
        '</div>', { onclose: function () { resolve(null); } });
      m.el.addEventListener('click', function (e) {
        var b = e.target.closest('[data-until]'); if (!b) return;
        UI.busy(b, UI.api('triage', id, 'snooze', null, b.getAttribute('data-until'))).then(function (r) { m.close(); UI.toast('Snoozed until ' + b.querySelector('.muted').textContent, 'ok'); resolve(r); });
      });
    });
  };
  /* Pick the lists a fave is in. lists: [{id,name,emoji,role}]; current: ids. Resolves with the new ids or null. */
  FB.listsModal = function (fave, lists, current) {
    return new Promise(function (resolve) {
      var editable = lists.filter(function (l) { return l.role === 'owner' || l.role === 'editor'; });
      var done = false;
      var m = UI.modal('<h2>Add to lists</h2>' +
        (editable.length ? '<div class="fb-lists-pick">' + editable.map(function (l) {
          return '<label><input type="checkbox" value="' + esc(l.id) + '"' + (current.indexOf(l.id) >= 0 ? ' checked' : '') + '><span class="em">' + esc(l.emoji || '⭐') + '</span><span>' + esc(l.name) +
            (l.role === 'editor' ? ' <span class="muted small">· ' + esc(l.owner || 'shared') + '</span>' : '') + '</span></label>';
        }).join('') + '</div>' : '<p class="muted">No lists yet. Make one below.</p>') +
        '<form class="ui-row" data-new style="margin-top:14px"><input type="text" name="name" placeholder="New list, e.g. Brunch spots" maxlength="60" style="flex:1;min-width:160px"><button class="ui-btn" type="submit">' + UI.icon('plus') + 'Create</button></form>' +
        '<div class="ui-row end" style="margin-top:18px"><button class="ui-btn ghost" data-close>Cancel</button><button class="ui-btn primary" data-save>Save</button></div>',
        { onclose: function () { if (!done) resolve(null); } });
      m.el.querySelector('[data-new]').addEventListener('submit', function (e) {
        e.preventDefault();
        var name = e.target.name.value.trim(); if (!name) return;
        UI.busy(e.target.querySelector('button'), UI.api('save_list', null, { name: name })).then(function (r) {
          var box = m.el.querySelector('.fb-lists-pick');
          if (!box) { box = document.createElement('div'); box.className = 'fb-lists-pick'; var p = m.el.querySelector('p.muted'); p.replaceWith(box); }
          box.insertAdjacentHTML('afterbegin', '<label><input type="checkbox" value="' + esc(r.list.id) + '" checked><span class="em">' + esc(r.list.emoji) + '</span><span>' + esc(r.list.name) + '</span></label>');
          e.target.name.value = '';
        });
      });
      m.el.querySelector('[data-save]').addEventListener('click', function (e) {
        var ids = Array.prototype.map.call(m.el.querySelectorAll('.fb-lists-pick input:checked'), function (i) { return i.value; });
        UI.busy(e.target.closest('button'), UI.api('update_fave', fave.id, { lists: ids })).then(function (r) { done = true; m.close(); UI.toast('Lists updated', 'ok'); resolve(r.fave); });
      });
    });
  };

  FB.copy = function (text, msg) {
    var ok = function () { UI.toast(msg || 'Copied', 'ok'); };
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text).then(ok, function () { fallback(); });
    fallback();
    function fallback() { var t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); ok(); } catch (e) {} t.remove(); }
  };
  FB.appUrl = function (hash) { return location.origin + location.pathname + hash; };
  FB.download = function (name, text, type) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: type || 'text/plain' }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  };
})();

/* ===== _fbmap.html ===== */
(function () {
  'use strict';
  var FB = window.FB = window.FB || {}, esc = UI.esc;
  var map = FB.map = {};
  var LIB = 'https://unpkg.com/maplibre-gl@4.7.1/dist/';
  var libP = null;
  map.load = function () {
    if (window.maplibregl) return Promise.resolve(window.maplibregl);
    if (!libP) libP = new Promise(function (resolve, reject) {
      var css = document.createElement('link'); css.rel = 'stylesheet'; css.href = LIB + 'maplibre-gl.css'; document.head.appendChild(css);
      var s = document.createElement('script'); s.src = LIB + 'maplibre-gl.js';
      s.onload = function () { resolve(window.maplibregl); };
      s.onerror = function () { libP = null; reject(new Error('The map couldn\'t load. Check your connection.')); };
      document.head.appendChild(s);
    });
    return libP;
  };
  map.style = function () {
    return 'https://tiles.openfreemap.org/styles/' + (document.documentElement.classList.contains('ui-dark') ? 'dark' : 'positron');
  };
  /* Maps follow the app's light/dark switch (and the system's, in Auto). */
  var live = [];
  map.restyle = function () {
    live = live.filter(function (m) { return m._container && document.body.contains(m._container); });
    live.forEach(function (m) { try { m.setStyle(map.style()); } catch (e) {} });
  };
  var wasDark = document.documentElement.classList.contains('ui-dark');
  new MutationObserver(function () {
    var dark = document.documentElement.classList.contains('ui-dark');
    if (dark !== wasDark) { wasDark = dark; map.restyle(); }
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  map.webgl = function () {
    try { var c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
  };
  /* Make a map in `el`. Resolves with the MapLibre map once its style has loaded (or null without WebGL). */
  map.make = function (el, o) {
    o = o || {};
    el.classList.add('fb-map');
    if (!map.webgl()) {
      el.innerHTML = '<div class="fb-map-off"><div>' + UI.icon('map') + '<p>This browser can\'t draw the map (WebGL is off).<br>Your places are listed below.</p></div></div>';
      return Promise.resolve(null);
    }
    return map.load().then(function (ml) {
      var m = new ml.Map({ container: el, style: map.style(), center: o.center ? [o.center.lng, o.center.lat] : [-73.58, 45.52], zoom: o.zoom || 12,
                           attributionControl: { compact: true }, cooperativeGestures: !!o.cooperative, maxZoom: 18 });
      m.addControl(new ml.NavigationControl({ showCompass: false }), 'top-right');
      live.push(m);
      return new Promise(function (resolve) {
        var done = false;
        var fin = function () { if (!done) { done = true; resolve(m); } };
        m.once('load', fin);
        setTimeout(fin, 6000);  // a slow tile server shouldn't block the page
      });
    }, function (err) {
      el.innerHTML = '<div class="fb-map-off"><div>' + UI.icon('map') + '<p>' + esc(err.message) + '</p></div></div>';
      return null;
    });
  };
  map.pinEl = function (f, o) {
    var c = FB.cat(f.cat), el = document.createElement('div');
    el.className = 'fb-pin' + (f.stage === 'loved' ? ' loved' : '') + (o && o.suggestion ? ' sug' : '');
    el.style.setProperty('--pin', c.color);
    el.innerHTML = '<span>' + esc(o && o.emoji || c.emoji) + '</span>';
    el.title = f.title || '';
    return el;
  };
  map.meEl = function () { var el = document.createElement('div'); el.className = 'fb-me'; el.title = 'You'; return el; };
  map.fit = function (m, pts, pad) {
    pts = pts.filter(function (p) { return p && p.lat != null; });
    if (!m || !pts.length) return;
    if (pts.length === 1) { m.jumpTo({ center: [pts[0].lng, pts[0].lat], zoom: 14 }); return; }
    var b = new window.maplibregl.LngLatBounds();
    pts.forEach(function (p) { b.extend([p.lng, p.lat]); });
    m.fitBounds(b, { padding: pad || 60, maxZoom: 15, animate: false });
  };
  map.popup = function (f, actions) {
    return '<div class="fb-pop">' + (f.image ? '<img src="' + esc(f.image) + '" alt="" referrerpolicy="no-referrer" onerror="this.remove()">' : '') +
      '<b>' + esc(f.title) + '</b><div class="muted">' + FB.catChip(f.cat) + '</div>' + (f.address ? '<div class="muted">' + esc(f.address) + '</div>' : '') +
      (actions ? '<div class="ui-row">' + actions + '</div>' : '') + '</div>';
  };

  /* ------------------------------------------------------------------ open data */
  var data = FB.data = {};
  var OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://maps.mail.ru/osm/tools/overpass/api/interpreter'];
  function timeout(p, ms) { return Promise.race([p, new Promise(function (_, rej) { setTimeout(function () { rej(new Error('timeout')); }, ms); })]); }
  data.overpass = function (q) {
    var i = 0;
    function next() {
      if (i >= OVERPASS.length) return Promise.reject(new Error('OpenStreetMap search is busy right now.'));
      var url = OVERPASS[i++];
      return timeout(fetch(url, { method: 'POST', body: 'data=' + encodeURIComponent(q), headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }), 22000)
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (j) { return j.elements || []; }, next);
    }
    return next();
  };
  function osmFilter(pair) {
    var k = pair[0], v = pair[1];
    if (v === '*' || v == null) return '["' + k + '"]';
    if (v.indexOf('|') >= 0) return '["' + k + '"~"^(' + v + ')$"]';
    if (k === 'cuisine') return '["cuisine"~"(^|;)' + v + '($|;)"]';
    return '["' + k + '"="' + v + '"]';
  }
  /* A recipe from Discover.taste(): {filters: [[k, v]...], prefer: [[k, v]]}. Returns ranked, deduped places. */
  data.placesLike = function (recipe, center, km, saved) {
    var r = Math.round((km || 2) * 1000);
    var f = recipe.filters.map(osmFilter).join('');
    var q = '[out:json][timeout:20];(nwr(around:' + r + ',' + center.lat.toFixed(5) + ',' + center.lng.toFixed(5) + ')' + f + '["name"];);out center tags 80;';
    return data.overpass(q).then(function (els) { return rank(els.map(fromOsm), recipe, center, km, saved); });
  };
  function fromOsm(e) {
    var t = e.tags || {}, lat = e.lat != null ? e.lat : e.center && e.center.lat, lng = e.lon != null ? e.lon : e.center && e.center.lon;
    var addr = [t['addr:housenumber'], t['addr:street']].filter(Boolean).join(' ');
    return { title: t.name, lat: lat, lng: lng, osm: t, address: addr ? addr + (t['addr:city'] ? ', ' + t['addr:city'] : '') : '',
             website: t.website || t['contact:website'] || '', ref: e.type + '/' + e.id };
  }
  function rank(items, recipe, center, km, saved) {
    saved = saved || [];
    var seen = {};
    return items.filter(function (p) {
      if (!p.title || p.lat == null) return false;
      var key = p.title.toLowerCase();
      if (seen[key]) return false; seen[key] = 1;
      return !saved.some(function (s) { return s[0] === key || (Math.abs(s[1] - p.lat) < 0.0004 && Math.abs(s[2] - p.lng) < 0.0006 && s[0].slice(0, 4) === key.slice(0, 4)); });
    }).map(function (p) {
      var score = 1, why = [];
      (recipe.prefer || []).forEach(function (pr) {
        var v = p.osm && p.osm[pr[0]];
        if (v && new RegExp('^(' + pr[1] + ')$').test(v)) { score += 2; why.push(pr[0].replace('diet:', '').replace('_', ' ') + ': ' + v); }
      });
      if (p.osm && p.osm.opening_hours) score += 0.4;
      if (p.website) score += 0.4;
      if (p.osm && (p.osm.wikidata || p.osm.wikipedia)) { score += 0.6; why.push('on Wikipedia'); }
      var d = FB.dist(center, p); p.km = d;
      score -= (d || 0) / Math.max(0.5, km || 2);
      p.score = score; p.why = why;
      return p;
    }).sort(function (a, b) { return b.score - a.score; });
  }
  /* The map tiles' own points of interest (OpenMapTiles "poi" layer: name, class, subclass). Needs a map showing the area. */
  var TILE_CLASS = { cafe: 'cafe', restaurant: 'restaurant', fast_food: 'fast_food', bar: 'bar', pub: 'beer', park: 'park', museum: 'museum',
                     gallery: 'art_gallery', bakery: 'bakery', books: 'library', hotel: 'lodging', fitness_centre: 'sports_centre', ice_cream: 'ice_cream' };
  data.tilePois = function (m, recipe, center, km, saved) {
    if (!m) return [];
    var want = recipe.filters[0][1], sub = TILE_CLASS[want] || want, out = [];
    try {
      m.querySourceFeatures('openmaptiles', { sourceLayer: 'poi' }).forEach(function (f) {
        var p = f.properties || {};
        if (!p.name || (p.subclass !== want && p.class !== sub && p.subclass !== sub)) return;
        var g = f.geometry && f.geometry.coordinates;
        if (!g) return;
        out.push({ title: p['name:latin'] || p.name, lat: g[1], lng: g[0], osm: {}, address: '', ref: 'tile/' + (f.id || p.name) });
      });
    } catch (e) {}
    return rank(out, { prefer: [] }, center, km, saved).filter(function (p) { return p.km <= (km || 2) * 1.3; });
  };
  data.photon = function (q, near, limit) {
    var u = 'https://photon.komoot.io/api/?q=' + encodeURIComponent(q) + '&limit=' + (limit || 6) + (near ? '&lat=' + near.lat + '&lon=' + near.lng : '');
    return timeout(fetch(u), 12000).then(function (r) { return r.json(); }).then(function (j) {
      return (j.features || []).map(function (f) {
        var p = f.properties || {}, g = f.geometry.coordinates;
        var addr = [[p.housenumber, p.street].filter(Boolean).join(' '), p.city || p.district, p.state].filter(Boolean).join(', ');
        var osm = {}; if (p.osm_key) osm[p.osm_key] = p.osm_value;
        return { title: p.name || addr || q, lat: g[1], lng: g[0], address: addr, osm: osm, kind: p.osm_value ? p.osm_value.replace(/_/g, ' ') : '' };
      });
    });
  };
  var WIKI = 'https://en.wikipedia.org/w/api.php?format=json&origin=*&formatversion=2&';
  function wikiPages(j) {
    return ((j.query && j.query.pages) || []).map(function (p) {
      return { title: p.title, desc: p.description || '', image: p.thumbnail && p.thumbnail.source, url: 'https://en.wikipedia.org/wiki/' + encodeURIComponent(p.title.replace(/ /g, '_')),
               lat: p.coordinates && p.coordinates[0].lat, lng: p.coordinates && p.coordinates[0].lon, index: p.index || 0 };
    }).sort(function (a, b) { return a.index - b.index; });
  }
  data.wikiNearby = function (c, radiusM) {
    return timeout(fetch(WIKI + 'action=query&generator=geosearch&ggscoord=' + c.lat + '%7C' + c.lng + '&ggsradius=' + (radiusM || 5000) + '&ggslimit=30' +
      '&prop=coordinates%7Cpageimages%7Cdescription&piprop=thumbnail&pithumbsize=480'), 12000).then(function (r) { return r.json(); }).then(wikiPages);
  };
  data.wikiLike = function (seed) {
    return timeout(fetch(WIKI + 'action=query&list=search&srlimit=1&srsearch=' + encodeURIComponent(seed)), 12000).then(function (r) { return r.json(); }).then(function (j) {
      var hit = j.query && j.query.search && j.query.search[0];
      if (!hit) return [];
      return fetch(WIKI + 'action=query&generator=search&gsrlimit=6&gsrsearch=' + encodeURIComponent('morelike:' + hit.title) +
        '&prop=pageimages%7Cdescription&piprop=thumbnail&pithumbsize=480').then(function (r) { return r.json(); }).then(function (j2) {
          return wikiPages(j2).map(function (p) { p.from = hit.title; return p; });
        });
    });
  };
  data.wikidataEvents = function (c, km) {
    var q = 'SELECT ?e ?eLabel ?desc ?coord ?img ?site ?start WHERE { SERVICE wikibase:around { ?e wdt:P625 ?coord . ' +
      'bd:serviceParam wikibase:center "Point(' + c.lng + ' ' + c.lat + ')"^^geo:wktLiteral . bd:serviceParam wikibase:radius "' + (km || 25) + '" . } ' +
      '?e wdt:P31/wdt:P279* wd:Q132241 . OPTIONAL { ?e wdt:P18 ?img } OPTIONAL { ?e wdt:P856 ?site } OPTIONAL { ?e wdt:P580 ?start } ' +
      'OPTIONAL { ?e schema:description ?desc FILTER(lang(?desc) = "en") } SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr". } } LIMIT 40';
    return timeout(fetch('https://query.wikidata.org/sparql?format=json&query=' + encodeURIComponent(q), { headers: { Accept: 'application/sparql-results+json' } }), 20000)
      .then(function (r) { return r.json(); }).then(function (j) {
        var seen = {};
        return (j.results.bindings || []).map(function (b) {
          var pt = (b.coord && b.coord.value || '').match(/Point\(([-\d.]+) ([-\d.]+)\)/);
          return { title: b.eLabel && b.eLabel.value, desc: b.desc && b.desc.value || 'Festival', url: b.site ? b.site.value : b.e.value.replace('http:', 'https:'),
                   image: b.img ? b.img.value.replace('http:', 'https:') + '?width=480' : null, lat: pt ? +pt[2] : null, lng: pt ? +pt[1] : null, wikidata: b.e.value };
        }).filter(function (e) { if (!e.title || /^Q\d+$/.test(e.title) || seen[e.title]) return false; seen[e.title] = 1; return true; });
      });
  };
  /* Geohash (Ticketmaster's geoPoint). */
  data.geohash = function (lat, lng, prec) {
    var B = '0123456789bcdefghjkmnpqrstuvwxyz', la = [-90, 90], lo = [-180, 180], h = '', bit = 0, ch = 0, even = true;
    while (h.length < (prec || 7)) {
      var r = even ? lo : la, v = even ? lng : lat, mid = (r[0] + r[1]) / 2;
      if (v >= mid) { ch = ch * 2 + 1; r[0] = mid; } else { ch = ch * 2; r[1] = mid; }
      even = !even;
      if (++bit === 5) { h += B[ch]; bit = 0; ch = 0; }
    }
    return h;
  };
  data.ticketmaster = function (key, c, km, classification) {
    var start = new Date(); start.setMinutes(0, 0, 0);
    var u = 'https://app.ticketmaster.com/discovery/v2/events.json?apikey=' + encodeURIComponent(key) + '&geoPoint=' + data.geohash(c.lat, c.lng, 7) +
      '&radius=' + Math.round(km || 25) + '&unit=km&sort=date,asc&size=24&startDateTime=' + start.toISOString().replace(/\.\d{3}Z$/, 'Z') +
      (classification ? '&classificationName=' + encodeURIComponent(classification) : '');
    return timeout(fetch(u), 15000).then(function (r) {
      if (r.status === 401) throw Object.assign(new Error('That Ticketmaster key didn\'t work. Check it in Tools → Events.'), { uiApi: true });
      if (!r.ok) throw Object.assign(new Error('Ticketmaster said HTTP ' + r.status + '.'), { uiApi: true });
      return r.json();
    }).then(function (j) {
      return ((j._embedded && j._embedded.events) || []).map(function (e) {
        var v = e._embedded && e._embedded.venues && e._embedded.venues[0] || {}, img = (e.images || []).filter(function (i) { return i.ratio === '16_9' && i.width < 800; })[0] || (e.images || [])[0];
        var when = e.dates && e.dates.start && (e.dates.start.dateTime || e.dates.start.localDate);
        var seg = e.classifications && e.classifications[0] && (e.classifications[0].genre || e.classifications[0].segment || {}).name;
        return { title: e.name, url: e.url, image: img && img.url, start: when, venue: v.name || '', address: [v.address && v.address.line1, v.city && v.city.name].filter(Boolean).join(', '),
                 lat: v.location ? +v.location.latitude : null, lng: v.location ? +v.location.longitude : null, genre: seg && seg !== 'Undefined' ? seg : '' };
      });
    });
  };
})();

/* ===== _fbmedia.html ===== */
(function () {
  'use strict';
  var FB = window.FB = window.FB || {}, esc = UI.esc;
  var media = FB.media = {};

  media.shrink = function (file, max) {
    max = max || 1600;
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file), img = new Image();
      img.onload = function () {
        var s = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
        var c = document.createElement('canvas');
        c.width = Math.round(img.naturalWidth * s); c.height = Math.round(img.naturalHeight * s);
        var g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        var q = 0.84, out = c.toDataURL('image/jpeg', q);
        while (out.length > 2.6e6 && q > 0.45) { q -= 0.12; out = c.toDataURL('image/jpeg', q); }
        resolve({ dataUrl: out, w: c.width, h: c.height });
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(Object.assign(new Error('That file isn\'t a picture this browser can open.'), { uiApi: true })); };
      img.src = url;
    });
  };

  /* Minimal EXIF reader (JPEG APP1): GPS position, date taken, camera model. */
  media.exif = function (file) {
    if (!file || !/jpe?g/i.test(file.type || file.name || '')) return Promise.resolve(null);
    return file.slice(0, 256 * 1024).arrayBuffer().then(function (buf) {
      var v = new DataView(buf);
      if (v.getUint16(0) !== 0xFFD8) return null;
      var off = 2;
      while (off < v.byteLength - 4) {
        var mk = v.getUint16(off), len = v.getUint16(off + 2);
        if (mk === 0xFFE1 && v.getUint32(off + 4) === 0x45786966) return parseTiff(v, off + 10);
        off += 2 + len;
      }
      return null;
    }).catch(function () { return null; });
  };
  function parseTiff(v, t) {
    var le = v.getUint16(t) === 0x4949;
    var u16 = function (o) { return v.getUint16(o, le); }, u32 = function (o) { return v.getUint32(o, le); };
    function ifd(o) {
      var n = u16(t + o), out = {};
      for (var i = 0; i < n; i++) {
        var e = t + o + 2 + i * 12, tag = u16(e), type = u16(e + 2), cnt = u32(e + 4), valOff = e + 8;
        out[tag] = { type: type, cnt: cnt, off: (type === 2 && cnt > 4) || (type === 5) || (type === 3 && cnt > 2) ? t + u32(valOff) : valOff };
      }
      return out;
    }
    function str(x) { var s = ''; for (var i = 0; i < x.cnt - 1; i++) s += String.fromCharCode(v.getUint8(x.off + i)); return s.trim(); }
    function rats(x) { var a = []; for (var i = 0; i < x.cnt; i++) a.push(u32(x.off + i * 8) / (u32(x.off + i * 8 + 4) || 1)); return a; }
    var out = {};
    try {
      var main = ifd(u32(t + 4));
      if (main[0x0110]) out.camera = str(main[0x0110]);
      if (main[0x8769]) { var ex = ifd(u32(main[0x8769].off)); if (ex[0x9003]) out.taken = str(ex[0x9003]); }
      if (main[0x8825]) {
        var g = ifd(u32(main[0x8825].off));
        if (g[2] && g[4]) {
          var la = rats(g[2]), lo = rats(g[4]);
          var lat = la[0] + la[1] / 60 + la[2] / 3600, lng = lo[0] + lo[1] / 60 + lo[2] / 3600;
          if (g[1] && String.fromCharCode(v.getUint8(g[1].off)) === 'S') lat = -lat;
          if (g[3] && String.fromCharCode(v.getUint8(g[3].off)) === 'W') lng = -lng;
          if (isFinite(lat) && isFinite(lng) && (lat || lng)) { out.lat = +lat.toFixed(6); out.lng = +lng.toFixed(6); }
        }
      }
    } catch (e) {}
    return Object.keys(out).length ? out : null;
  }

  /* On-device OCR. Loaded on first use from jsDelivr (tesseract.js 5.1.1); language data from its default CDN. */
  var tessP = null;
  function loadTess() {
    if (window.Tesseract) return Promise.resolve(window.Tesseract);
    if (!tessP) tessP = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
      s.onload = function () { resolve(window.Tesseract); };
      s.onerror = function () { tessP = null; reject(Object.assign(new Error('Couldn\'t load the text reader. Check your connection.'), { uiApi: true })); };
      document.head.appendChild(s);
    });
    return tessP;
  }
  media.ocr = function (dataUrl, onProgress) {
    return loadTess().then(function (T) {
      return T.recognize(dataUrl, 'eng+fra', { logger: function (m) { if (onProgress && m && m.progress != null) onProgress(m.status, m.progress); } });
    }).then(function (r) {
      var text = (r && r.data && r.data.text || '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
      return text;
    });
  };

  /* Useful bits in free text (OCR, notes): links, emails, phone numbers, dates, times, street addresses, @handles, prices. */
  var MONTHS = 'jan(?:uary|vier)?|feb(?:ruary)?|f[ée]v(?:rier)?|mar(?:ch|s)?|apr(?:il)?|avr(?:il)?|may|mai|june?|juin|july?|juil(?:let)?|aug(?:ust)?|ao[uû]t|sept?(?:ember|embre)?|oct(?:ober|obre)?|nov(?:ember|embre)?|dec(?:ember)?|d[ée]c(?:embre)?';
  media.extract = function (text) {
    text = String(text || '');
    var uniq = function (a) { return a.filter(function (x, i) { return x && a.indexOf(x) === i; }).slice(0, 8); };
    var all = function (re, fix) { var out = [], m; re.lastIndex = 0; while ((m = re.exec(text))) out.push(fix ? fix(m) : m[0].trim()); return uniq(out); };
    return {
      urls: all(/\b(?:https?:\/\/|www\.)[^\s<>"')]+[^\s<>"').,;:!?]/gi),
      emails: all(/\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g),
      phones: all(/(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b/g),
      dates: all(new RegExp('\\b(?:\\d{1,2}(?:er)?\\s+(?:' + MONTHS + ')\\.?(?:\\s+\\d{4})?|(?:' + MONTHS + ')\\.?\\s+\\d{1,2}(?:st|nd|rd|th)?(?:,?\\s+\\d{4})?|\\d{4}-\\d{2}-\\d{2}|\\d{1,2}/\\d{1,2}/\\d{2,4})\\b', 'gi')),
      times: all(/\b\d{1,2}(?::\d{2})?\s?(?:am|pm|AM|PM)\b|\b\d{1,2}\s?h\s?\d{0,2}\b|\b\d{1,2}:\d{2}\b/g),
      addresses: all(/\b\d{1,5}[\s,]+(?:rue|avenue|av\.?|boul(?:evard)?\.?|chemin|place|ch\.?)\s+[A-ZÀ-Ý][\wÀ-ÿ'-]+(?:[\s-][A-ZÀ-Ý][\wÀ-ÿ'-]+)*|\b\d{1,5}\s+[A-Z][\w'-]+(?:\s[A-Z][\w'-]+)*\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Place|Pl)\b\.?|\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b/g),
      handles: all(/(^|\s)@[A-Za-z0-9_.]{2,30}\b/g, function (m) { return m[0].trim(); }),
      prices: all(/(?:\$|€|£)\s?\d+(?:[.,]\d{2})?|\b\d+(?:[.,]\d{2})?\s?(?:\$|€|£)/g)
    };
  };
  media.foundCount = function (f) { var n = 0; Object.keys(f || {}).forEach(function (k) { n += (f[k] || []).length; }); return n; };
  media.foundHtml = function (f) {
    var LABEL = { urls: ['link', 'Links'], emails: ['mail', 'Emails'], phones: ['phone', 'Phone numbers'], dates: ['calendar', 'Dates'], times: ['clock', 'Times'],
      addresses: ['pin', 'Addresses'], handles: ['user', 'Handles'], prices: ['tag', 'Prices'] };
    return Object.keys(LABEL).filter(function (k) { return f && f[k] && f[k].length; }).map(function (k) {
      return '<div class="fb-found"><span class="muted small">' + UI.icon(LABEL[k][0]) + LABEL[k][1] + '</span><div class="fb-tags">' + f[k].map(function (x) {
        if (k === 'urls') return '<a class="fb-tag" target="_blank" rel="noopener" href="' + esc(/^https?:/i.test(x) ? x : 'https://' + x) + '">' + esc(x) + '</a>';
        if (k === 'addresses') return '<a class="fb-tag" href="#map/find/' + encodeURIComponent(x) + '">' + esc(x) + '</a>';
        if (k === 'phones') return '<a class="fb-tag" href="tel:' + esc(x.replace(/[^\d+]/g, '')) + '">' + esc(x) + '</a>';
        if (k === 'emails') return '<a class="fb-tag" href="mailto:' + esc(x) + '">' + esc(x) + '</a>';
        return '<span class="fb-tag">' + esc(x) + '</span>';
      }).join('') + '</div></div>';
    }).join('');
  };

  /* ------------------------------------------------------------------ bring-your-own-key Claude */
  var API = 'https://api.anthropic.com/v1/messages', VERSION = '2026-10-21', KEY = 'favesbuddy.ai';
  var MODELS = [['claude-haiku-5-5', 'Claude Haiku 5.5', 'Quick and cheapest: about $0.10 per million tokens in. Great for pictures.'],
                ['claude-sonnet-5-5', 'Claude Sonnet 5.5', 'Sharper reading of busy screenshots.'],
                ['claude-opus-5-5', 'Claude Opus 5.5', 'The most careful. Costs the most.']];
  var ai = FB.ai = {
    MODELS: MODELS,
    get: function () { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } },
    set: function (v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) {} },
    clear: function () { try { localStorage.removeItem(KEY); } catch (e) {} },
    has: function () { return !!ai.get().key; },
    model: function () { var m = ai.get().model; return MODELS.some(function (x) { return x[0] === m; }) ? m : MODELS[0][0]; }
  };
  function friendly(status, body) {
    var msg = body && body.error && body.error.message || '';
    if (status === 401) return 'That Anthropic API key didn\'t work. Check it in Tools → AI.';
    if (status === 402) return 'Your Anthropic account needs credit (Billing in the Claude Console).';
    if (status === 404 || status === 403) return 'That model isn\'t available to your key. Pick another in Tools → AI.';
    if (status === 413) return 'That picture is too big for the AI. Try a smaller one.';
    if (status === 429) return 'Anthropic is rate-limiting this key. Wait a minute and try again.';
    if (status >= 500) return 'Anthropic is busy right now. Try again in a moment.';
    return msg ? 'Anthropic said: ' + msg : 'The AI request failed (HTTP ' + status + ').';
  }
  ai.call = function (o, _noFallback) {
    if (!ai.has()) return Promise.reject(Object.assign(new Error('Add your Anthropic API key first (Tools → AI).'), { uiApi: true }));
    var model = ai.model(), fb = model !== 'claude-haiku-5-5' && !_noFallback;
    var h = { 'content-type': 'application/json', 'x-api-key': ai.get().key, 'anthropic-version': VERSION, 'anthropic-dangerous-direct-browser-access': 'true' };
    if (fb) h['anthropic-beta'] = 'server-side-fallback-2026-07-01';
    var body = { model: model, max_tokens: o.max_tokens || 1500, system: o.system, messages: o.messages, output_config: { effort: o.effort || 'low' } };
    if (fb) body.fallbacks = 'default';
    if (o.schema) body.output_config.format = { type: 'json_schema', schema: o.schema };
    return fetch(API, { method: 'POST', headers: h, body: JSON.stringify(body) }).then(function (res) {
      if (!res.ok) return res.json().catch(function () { return null; }).then(function (b) {
        var m = b && b.error && b.error.message || '';
        if (fb && res.status === 400 && /fallback|beta/i.test(m)) return ai.call(o, true);
        throw Object.assign(new Error(friendly(res.status, b)), { uiApi: true });
      });
      return res.json().then(function (msg) {
        if (msg.stop_reason === 'refusal') throw Object.assign(new Error('The AI declined to describe this picture.'), { uiApi: true });
        var text = (msg.content || []).filter(function (b) { return b.type === 'text'; }).map(function (b) { return b.text; }).join('');
        if (!o.schema) return text;
        try { return JSON.parse(text); } catch (e) { throw Object.assign(new Error('The AI answer was cut off. Try again.'), { uiApi: true }); }
      });
    }, function () { throw Object.assign(new Error('Couldn\'t reach Anthropic. Check your connection (or an ad blocker).'), { uiApi: true }); });
  };
  ai.test = function () { return ai.call({ system: 'Reply in five words.', messages: [{ role: 'user', content: 'Say hello to a tidy collector.' }], max_tokens: 50 }); };
  ai.analyseImage = function (dataUrl, ocrText) {
    var cats = (FB.CATS || []).map(function (c) { return c.id; });
    var schema = { type: 'object', additionalProperties: false, required: ['title', 'summary', 'category', 'tags', 'text', 'places', 'when'],
      properties: { title: { type: 'string' }, summary: { type: 'string' }, category: { type: 'string', enum: cats.length ? cats : ['other'] },
        tags: { type: 'array', items: { type: 'string' } }, text: { type: 'string' },
        places: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['name', 'address'], properties: { name: { type: 'string' }, address: { type: 'string' } } } },
        when: { type: 'string' } } };
    var m = dataUrl.match(/^data:(image\/\w+);base64,(.+)$/);
    return ai.call({ schema: schema, effort: 'low', max_tokens: 1200,
      system: 'You help someone file a saved picture or screenshot in their personal collection. Be factual: only describe what is visible. Never invent places, dates or prices.',
      messages: [{ role: 'user', content: [
        { type: 'image', source: { type: 'base64', media_type: m[1], data: m[2] } },
        { type: 'text', text: 'Describe this saved picture for the person\'s collection.\n' +
          '- title: a short, specific name (max 8 words), e.g. "Jazz in the park poster" or "Ramen shop menu"\n' +
          '- summary: 1-2 sentences on what it is and why someone might have saved it\n' +
          '- category: the best fit from the list\n- tags: up to 5 short lowercase tags\n' +
          '- text: the important text visible in the picture (names, dates, prices), max 400 characters\n' +
          '- places: any businesses or venues named, with an address if visible (else "")\n' +
          '- when: a date/time if one is shown, as written, else ""' +
          (ocrText ? '\n\nText already read from it on the device (may have errors):\n"""' + ocrText.slice(0, 2000) + '"""' : '') }
      ] }] });
  };
  ai.nudge = function (what) {
    return '<div class="fb-ai-nudge">' + UI.icon('key') + '<span><b>Bring your own AI key</b> to ' + esc(what) + '. It stays in this browser; you pay Anthropic directly (cents). ' +
      'Everything else works without it.</span><a class="ui-btn sm" href="#tools/ai" data-go="tools/ai">Add key</a></div>';
  };
})();

/* ===== add.html ===== */
(function () {
  var esc = UI.esc;
  var TABS = [['link', 'Link', 'link'], ['place', 'Place', 'pin'], ['photo', 'Pictures', 'image'], ['note', 'Note or idea', 'note']];

  UI.page('add', { title: 'Save something', auth: 'user' }, function (view, ctx) {
    var tab = TABS.some(function (t) { return t[0] === ctx.args[0]; }) ? ctx.args[0] : 'link';
    var prefill = tab === 'link' ? (ctx.args.slice(1).join('/') || '') : '';
    var lists = [], chosen = { cat: null, lists: [] }, preview = null;

    function frame(inner) {
      view.innerHTML = '<div class="ui-wrap ad-box"><div class="ui-page-head"><div><h1>Save something</h1><p class="muted">It\'s sorted for you. You can always change where it goes.</p></div></div>' +
        '<div class="ad-tidy"><a class="ui-btn sm" href="#tidy/tabs" data-go="tidy/tabs">' + UI.icon('tabs') + 'A pile of tabs</a><a class="ui-btn sm" href="#tidy/shots" data-go="tidy/shots">' + UI.icon('wand') + 'Sweep screenshots</a></div>' +
        '<nav class="ui-tabs ad-tabs">' + TABS.map(function (t) { return '<a href="#add/' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '">' + UI.icon(t[2]) + t[1] + '</a>'; }).join('') + '</nav>' +
        '<div data-body>' + inner + '</div></div>';
    }
    function listPicker() {
      if (!lists.length) return '';
      return '<div class="fv-sec"><span class="lbl">Add to lists</span><div class="fb-chips">' + lists.filter(function (l) { return l.role !== 'viewer'; }).map(function (l) {
        return '<button type="button" class="fb-chip sm' + (chosen.lists.indexOf(l.id) >= 0 ? ' on' : '') + '" data-list="' + esc(l.id) + '">' + esc((l.emoji || '⭐') + ' ' + l.name) + '</button>';
      }).join('') + '</div></div>';
    }
    /* ------------------------------------------------------------- link */
    function linkTab() {
      frame('<form class="ui-row" data-link><input type="url" name="url" placeholder="https://… (a page, a video, a Google Maps link…)" value="' + esc(prefill) + '" required style="flex:1;min-width:220px">' +
        '<button class="ui-btn primary" type="submit">' + UI.icon('eye') + 'Preview</button></form><div data-preview></div>' +
        '<div class="fb-panel" style="margin-top:28px"><h3>Save from any browser</h3><p class="muted small">Drag this button to your bookmarks bar. On any page, click it to send the page here. (In Chrome, the <a href="#tools" data-go="tools">extension</a> does more: whole windows of tabs at once.)</p>' +
        '<a class="ad-bookmarklet" data-bookmarklet href="#" onclick="return false">' + UI.icon('heart') + '+ Faves Buddy</a></div>');
      var bm = view.querySelector('[data-bookmarklet]');
      bm.setAttribute('href', "javascript:(function(){window.open('" + FB.appUrl('#add/link/') + "'+encodeURIComponent(location.href),'_blank');})();");
      if (prefill) doPreview(prefill);
    }
    function doPreview(url, btn) {
      var box = view.querySelector('[data-preview]');
      box.innerHTML = '<div class="ui-skel" style="height:180px;margin-top:18px"></div>';
      chosen = { cat: null, lists: [] };
      return UI.busy(btn, UI.api('preview_link', url)).then(function (r) {
        var p = r.page, s = r.sort;
        preview = { url: url, page: p, sort: s };
        chosen.cat = s.category;
        var f = { id: url, title: p.title || p.final_url || url, cat: s.category, kind: p.kind || 'link', image: p.image, address: p.address, desc: p.description, tags: s.tags };
        box.innerHTML = '<div class="fb-panel ad-preview">' + FB.cover(f) + '<div><h2>' + esc(f.title) + '</h2>' +
          '<div class="fb-sub">' + (p.kind === 'place' ? UI.icon('pin') + '<span>' + esc(p.address || (p.lat != null ? 'Pinned on the map' : 'Place')) + '</span>' : UI.icon('globe') + '<span>' + esc(p.site_name || url.replace(/^https?:\/\//, '').split('/')[0]) + '</span>') + '</div>' +
          (p.description ? '<p class="muted small" style="margin-top:8px">' + esc(p.description.slice(0, 220)) + '</p>' : '') +
          (r.error ? '<p class="ui-hint">' + UI.icon('info') + ' Couldn\'t read the page itself (' + esc(r.error) + '), so this is sorted from the link alone.</p>' : '') +
          (r.already ? '<div class="ui-note" style="margin-top:10px">You saved this before. Saving again adds your note to it. <a href="#fave/' + esc(r.already) + '">Open it</a></div>' : '') +
          '<div class="fv-sec"><span class="lbl">Goes in</span><div class="fb-why">' + (s.category !== 'other' ? Math.round(s.confidence * 100) + '% sure because: ' + s.reasons.map(function (x) { return '<span class="fb-tag">' + esc(x) + '</span>'; }).join('') : 'Not sure: pick a category') + '</div>' +
          '<div style="margin-top:10px" data-cats>' + FB.catPicker(chosen.cat) + '</div></div>' + listPicker() +
          '<div class="fv-sec"><span class="lbl">Note</span><textarea data-note rows="2" placeholder="Optional: why you\'re saving it"></textarea></div>' +
          '<div class="ui-row" style="margin-top:14px"><button class="ui-btn primary lg" data-save-link>' + UI.icon('heart') + 'Save</button><button class="ui-btn" data-save-inbox>Save to inbox for later</button></div></div></div>';
      });
    }
    /* ------------------------------------------------------------- place */
    function placeTab() {
      frame('<form class="ui-row" data-psearch><input type="search" name="q" placeholder="Name of a café, park, shop, address…" required style="flex:1;min-width:220px">' +
        '<button class="ui-btn primary" type="submit">' + UI.icon('search') + 'Search</button></form>' +
        '<div class="ui-row" style="margin-top:12px"><button class="ui-btn" data-here>' + UI.icon('locate') + 'Pin where I am now</button>' +
        '<span class="muted small">Or paste a Google Maps link on the Link tab.</span></div><div class="ad-results" data-results></div>');
    }
    function placeRow(p) {
      return '<div class="ad-place"><span class="fb-pill">' + UI.icon('pin') + '</span><div class="grow"><b>' + esc(p.title) + '</b><span class="muted small">' + esc([p.kind, p.address].filter(Boolean).join(' · ')) +
        (p.km != null ? ' · ' + FB.fmtDist(p.km) : '') + '</span></div><button class="ui-btn sm primary" data-save-place=\'' + esc(JSON.stringify(p)) + '\'>' + UI.icon('heart') + 'Save</button></div>';
    }
    /* ------------------------------------------------------------- photos */
    function photoTab() {
      frame('<label class="ad-drop" data-drop>' + UI.icon('image') + '<b>Drop screenshots and photos here</b><span class="muted small">or tap to choose (several at once is fine). On a phone you can take a photo.</span>' +
        '<input type="file" accept="image/*" multiple hidden data-files></label>' +
        '<label class="ui-check small" style="margin-top:12px"><input type="checkbox" data-auto-ocr ' + (UI.store.get('add.ocr', true) ? 'checked' : '') + '> Read the text in them (on this device, free; the first time downloads about 10 MB)</label>' +
        (FB.ai.has() ? '<label class="ui-check small" style="margin-top:6px"><input type="checkbox" data-auto-ai ' + (UI.store.get('add.ai', false) ? 'checked' : '') + '> Also describe them with AI (your key, a fraction of a cent each)</label>' : '<div style="margin-top:12px">' + FB.ai.nudge('describe pictures and spot places in them') + '</div>') +
        '<div class="ad-photos" data-photos></div>');
      var drop = view.querySelector('[data-drop]');
      drop.addEventListener('dragover', function (e) { e.preventDefault(); drop.classList.add('over'); });
      drop.addEventListener('dragleave', function () { drop.classList.remove('over'); });
      drop.addEventListener('drop', function (e) { e.preventDefault(); drop.classList.remove('over'); handleFiles(e.dataTransfer.files); });
    }
    var queue = Promise.resolve();
    function handleFiles(files) {
      Array.prototype.slice.call(files || []).filter(function (f) { return /^image\//.test(f.type); }).forEach(function (file, i) {
        var key = 'p' + Date.now() + i, box = view.querySelector('[data-photos]');
        box.insertAdjacentHTML('afterbegin', '<div class="ad-photo" data-p="' + key + '"><img alt=""><div><b data-t>' + esc(file.name) + '</b><div class="st" data-st>Shrinking…</div><div class="fv-progress"><i></i></div></div></div>');
        var row = box.querySelector('[data-p="' + key + '"]');
        queue = queue.then(function () { return onePhoto(file, row); }).catch(function (err) { row.querySelector('[data-st]').textContent = err.message || 'That didn\'t work.'; });
      });
    }
    function onePhoto(file, row) {
      var st = row.querySelector('[data-st]'), bar = row.querySelector('.fv-progress i'), fave = null, shot = null;
      var title = file.name.replace(/\.[a-z0-9]+$/i, '').replace(/[_-]+/g, ' ').trim() || 'Picture';
      return Promise.all([FB.media.shrink(file), FB.media.exif(file)]).then(function (r) {
        shot = r[0]; var ex = r[1];
        row.querySelector('img').src = shot.dataUrl;
        st.textContent = 'Saving…'; bar.style.width = '15%';
        var f = { title: title, kind: 'photo', photo: shot.dataUrl, source: 'app' };
        if (ex && ex.lat != null) { f.lat = ex.lat; f.lng = ex.lng; }
        return UI.apiQuiet('save_fave', f).then(function (res) {
          fave = res.fave;
          if (ex) return UI.apiQuiet('save_photo_ocr', fave.id, null, null, null, ex).then(function (x) { fave = x.fave; });
        });
      }).then(function () {
        if (!view.querySelector('[data-auto-ocr]') || !view.querySelector('[data-auto-ocr]').checked) return;
        st.textContent = 'Reading the text…';
        return FB.media.ocr(shot.dataUrl, function (s, p) { bar.style.width = (20 + p * 60) + '%'; st.textContent = s === 'recognizing text' ? 'Reading the text…' : 'Getting the reader ready…'; })
          .then(function (text) { return UI.apiQuiet('save_photo_ocr', fave.id, text, FB.media.extract(text)); }).then(function (r) { fave = r.fave; });
      }).then(function () {
        var ai = view.querySelector('[data-auto-ai]');
        if (!ai || !ai.checked) return;
        st.textContent = 'Asking the AI…'; bar.style.width = '85%';
        return FB.ai.analyseImage(shot.dataUrl, (fave.meta || {}).ocr).then(function (a) {
          return UI.apiQuiet('save_photo_ocr', fave.id, null, null, a);
        }).then(function (r) { fave = r.fave; }, function (err) { UI.toast(err.message, 'error'); });
      }).then(function () {
        bar.style.width = '100%';
        var c = FB.cat(fave.cat), found = FB.media.foundCount((fave.meta || {}).found);
        row.querySelector('[data-t]').innerHTML = '<a href="#fave/' + esc(fave.id) + '">' + esc(fave.title) + '</a>';
        st.innerHTML = 'In your inbox as <b>' + esc(c.emoji + ' ' + c.name) + '</b>' + (found ? ' · found ' + UI.plural(found, 'useful bit') : '') + (fave.lat != null ? ' · 📍 on the map' : '') +
          ((fave.reasons || []).length ? '<br><span class="faint">' + esc(fave.reasons.slice(0, 2).join(' · ')) + '</span>' : '');
      });
    }
    /* ------------------------------------------------------------- note */
    function noteTab() {
      frame('<form class="fb-panel ui-stack" data-noteform><div class="ui-seg" role="group"><button type="button" class="on" data-kind="note">Note</button><button type="button" data-kind="idea">Idea</button></div>' +
        '<label class="ui-field"><span>Title</span><input type="text" name="title" maxlength="200" required placeholder="e.g. Gift for Sam: a good pocket knife"></label>' +
        '<label class="ui-field"><span>Details <em>(optional)</em></span><textarea name="note" rows="5" maxlength="4000" placeholder="Links, who recommended it, what to try…"></textarea></label>' +
        listPicker() + '<div class="ui-row end"><button class="ui-btn primary" type="submit">' + UI.icon('heart') + 'Save</button></div></form>');
    }

    view.addEventListener('submit', function (e) {
      if (e.target.matches('[data-link]')) { e.preventDefault(); doPreview(e.target.url.value.trim(), e.target.querySelector('button')); }
      if (e.target.matches('[data-psearch]')) {
        e.preventDefault();
        var q = e.target.q.value.trim(), btn = e.target.querySelector('button');
        FB.geo(false).then(function (g) {
          return UI.busy(btn, FB.data.photon(q, g, 8)).then(function (res) {
            res.forEach(function (p) { p.km = g ? FB.dist(g, p) : null; });
            view.querySelector('[data-results]').innerHTML = res.length ? res.map(placeRow).join('') : '<p class="muted">Nothing found. Try adding the city.</p>';
          });
        }).catch(function () { UI.toast('Place search is unavailable right now.', 'error'); });
      }
      if (e.target.matches('[data-noteform]')) {
        e.preventDefault();
        var v = UI.formData(e.target), kind = view.querySelector('[data-kind].on').getAttribute('data-kind');
        UI.busy(e.target.querySelector('[type=submit]'), UI.api('save_fave', { title: v.title, note: v.note, kind: kind, list_id: chosen.lists[0] || null })).then(function (r) {
          addOtherLists(r.fave).then(function () { var c = FB.cat(r.fave.cat); UI.toast('Saved to your inbox as ' + c.emoji + ' ' + c.name, 'ok'); UI.go('fave', r.fave.id); });
        });
      }
    });
    function addOtherLists(f) {
      if (chosen.lists.length < 2) return Promise.resolve();
      return UI.apiQuiet('update_fave', f.id, { lists: chosen.lists });
    }
    view.addEventListener('click', function (e) {
      var c = e.target.closest('[data-cat]');
      if (c && view.querySelector('[data-cats]')) { chosen.cat = c.getAttribute('data-cat'); view.querySelectorAll('[data-cats] [data-cat]').forEach(function (b) { b.classList.toggle('on', b === c); }); return; }
      var l = e.target.closest('[data-list]');
      if (l) { var id = l.getAttribute('data-list'), i = chosen.lists.indexOf(id); if (i >= 0) chosen.lists.splice(i, 1); else chosen.lists.push(id); l.classList.toggle('on', i < 0); return; }
      var k = e.target.closest('[data-kind]');
      if (k) { view.querySelectorAll('[data-kind]').forEach(function (b) { b.classList.toggle('on', b === k); }); return; }
      var sl = e.target.closest('[data-save-link]'), si = e.target.closest('[data-save-inbox]');
      if ((sl || si) && preview) {
        var p = preview.page, f = { url: preview.url, title: p.title || '', note: (view.querySelector('[data-note]') || {}).value || '', enriched: !!p.title,
          meta: { description: p.description, image: p.image, site_name: p.site_name, og_type: p.og_type, schema: p.schema, lang: p.lang, read_min: p.read_min,
                  startDate: p.startDate, endDate: p.endDate, priceRange: p.priceRange, servesCuisine: p.servesCuisine, recipeYield: p.recipeYield, totalTime: p.totalTime, entity: p.entity },
          lat: p.lat, lng: p.lng, address: p.address, osm: p.osm || {}, kind: p.kind === 'place' ? 'place' : null, list_id: chosen.lists[0] || null, event_at: p.startDate || null };
        if (sl) f.category = chosen.cat; else f.status = 'inbox';
        UI.busy(sl || si, UI.api('save_fave', f)).then(function (r) {
          addOtherLists(r.fave).then(function () {
            var cc = FB.cat(r.fave.cat);
            UI.toast((r.created ? (sl ? 'Saved in ' : 'In your inbox as ') : 'Already saved: added to ') + cc.emoji + ' ' + cc.name, 'ok');
            UI.go('fave', r.fave.id);
          });
        });
        return;
      }
      var sp = e.target.closest('[data-save-place]');
      if (sp) {
        var pl = JSON.parse(sp.getAttribute('data-save-place'));
        UI.busy(sp, UI.api('save_fave', { title: pl.title, lat: pl.lat, lng: pl.lng, address: pl.address, osm: pl.osm, kind: 'place' })).then(function (r) {
          var cc = FB.cat(r.fave.cat); sp.disabled = true; sp.innerHTML = UI.icon('check') + 'Saved';
          UI.toast((r.created ? 'Saved to your inbox as ' : 'Already saved as ') + cc.emoji + ' ' + cc.name, 'ok');
        });
        return;
      }
      var here = e.target.closest('[data-here]');
      if (here) {
        UI.busy(here, FB.geo(true)).then(function (g) {
          if (!g || g.home) { UI.toast('Location isn\'t available here. Search for the place instead.', 'error'); return; }
          return UI.api('save_fave', { title: '', lat: g.lat, lng: g.lng, kind: 'place' }).then(function (r) { UI.toast('Pinned: ' + r.fave.title, 'ok'); UI.go('fave', r.fave.id); });
        });
      }
    });
    view.addEventListener('change', function (e) {
      if (e.target.matches('[data-files]')) { handleFiles(e.target.files); e.target.value = ''; }
      if (e.target.matches('[data-auto-ocr]')) UI.store.set('add.ocr', e.target.checked);
      if (e.target.matches('[data-auto-ai]')) UI.store.set('add.ai', e.target.checked);
    });
    return Promise.all([FB.boot(), UI.apiQuiet('my_lists')]).then(function (r) {
      lists = r[1].mine.concat(r[1].shared.filter(function (l) { return l.role === 'editor'; }));
      ({ link: linkTab, place: placeTab, photo: photoTab, note: noteTab })[tab]();
    });
  });
})();

/* ===== admin.html ===== */
(function () {
  var esc = UI.esc;
  var TABS = [['overview', 'Overview', 'grid'], ['feedback', 'Feedback', 'inbox'], ['users', 'Users', 'users'], ['sorting', 'Sorting', 'sparkle'], ['ai', 'AI sorting', 'wand'], ['demo', 'Demo data', 'database']];

  UI.page('admin', { title: 'Admin', auth: 'admin' }, function (view, ctx) {
    var tab = TABS.some(function (t) { return t[0] === ctx.args[0]; }) ? ctx.args[0] : 'overview';
    var fbFilter = 'new';
    view.innerHTML = '<div class="ui-wrap"><div class="ui-page-head"><div><h1>Admin</h1><p class="muted">Only admins see this page.</p></div></div>' +
      '<nav class="ui-tabs">' + TABS.map(function (t) {
        return '<a href="#admin/' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '">' + UI.icon(t[2]) + t[1] + '</a>';
      }).join('') + '</nav><div data-body><div class="ui-skel"></div></div></div>';
    var body = view.querySelector('[data-body]');

    function overview() {
      return UI.api('admin_overview').then(function (d) {
        var stat = function (n, label, go) { return '<a class="ui-card ui-stat" href="#admin/' + go + '" style="text-decoration:none;color:inherit"><b>' + n + '</b><span>' + label + '</span></a>'; };
        body.innerHTML = '<div class="ad-stats">' + stat(d.users, 'people signed up', 'users') + stat(d.admins, UI.plural(d.admins, 'admin').replace(/^\d+ /, ''), 'users') +
          stat(d.feedback_new, 'new feedback', 'feedback') + stat(d.faves, 'faves saved (' + d.faves_week + ' this week)', 'sorting') +
          stat(d.from_extension, 'saved from the extension', 'overview') + stat(d.connected, 'people using the extension', 'overview') +
          stat(d.lists, 'lists (' + d.shared + ' public)', 'overview') + '</div>' +
          '<p class="muted small" style="margin-top:18px">Demo data is <b>' + esc(d.demo.state) + '</b> (' + d.demo.counts.users + ' demo people). Manage it in the Demo data tab.</p>';
      });
    }

    function feedback() {
      return UI.api('list_feedback', null).then(function (d) {
        var items = d.items.filter(function (i) { return fbFilter === 'all' || i.status === fbFilter; });
        body.innerHTML = '<div class="ui-row" style="margin-bottom:16px"><div class="ui-seg">' + [['new', 'New'], ['read', 'Read'], ['done', 'Done'], ['all', 'All']].map(function (f) {
          var n = f[0] === 'all' ? d.items.length : d.counts[f[0]];
          return '<button data-filter="' + f[0] + '" class="' + (fbFilter === f[0] ? 'on' : '') + '">' + f[1] + ' (' + n + ')</button>';
        }).join('') + '</div></div>' +
          (items.length ? '<div class="ad-fb">' + items.map(function (i) {
            var c = i.context || {};
            return '<div class="ui-item" data-id="' + esc(i.id) + '"><div class="meta"><span class="ui-badge ' + (i.kind === 'bug' ? 'bad' : i.kind === 'idea' ? 'brand' : '') + '">' + esc(i.kind_label) + '</span>' +
              '<b>' + esc(i.name) + '</b>' + (i.email ? '<a href="mailto:' + esc(i.email) + '">' + esc(i.email) + '</a>' : '') + '<span>' + esc(UI.fmtDateTime(i.created)) + '</span></div>' +
              '<p class="msg">' + esc(i.message) + '</p>' +
              '<div class="ctx">' + esc([c.page, c.screen, c.theme, c.browser].filter(Boolean).join(' · ')) + '</div>' +
              '<textarea data-note placeholder="Private note (only admins see it)">' + esc(i.note) + '</textarea>' +
              '<div class="ui-row" style="margin-top:10px">' + ['new', 'read', 'done'].map(function (s) {
                return '<button class="ui-btn sm' + (i.status === s ? ' primary' : '') + '" data-status="' + s + '">' + s[0].toUpperCase() + s.slice(1) + '</button>';
              }).join('') + '<span class="ui-spacer"></span><button class="ui-btn sm danger" data-del-fb>' + UI.icon('trash') + 'Delete</button></div></div>';
          }).join('') + '</div>'
            : '<div class="ui-empty">' + UI.icon('inbox') + '<h3>No ' + (fbFilter === 'all' ? '' : fbFilter + ' ') + 'messages</h3><p>New feedback goes to Prepsto (prepsto.com). Older messages and requests from the app show up here.</p></div>');
      });
    }

    function users(query) {
      return UI.api('list_users', query || null).then(function (d) {
        body.innerHTML = '<form class="ui-row" data-search style="margin-bottom:14px"><input type="search" name="q" placeholder="Search by name or email" value="' + esc(query || '') + '" style="max-width:360px">' +
          '<button class="ui-btn" type="submit">' + UI.icon('search') + 'Search</button><span class="muted small">' + UI.plural(d.total, 'person', 'people') + '</span></form>' +
          '<table class="ad-users"><thead><tr><th>Name</th><th>Email</th><th>Joined</th><th>Admin</th><th>Active</th></tr></thead><tbody>' +
          d.users.map(function (u) {
            return '<tr data-id="' + esc(u.id) + '"><td><b>' + esc(u.name) + '</b></td><td class="email">' + esc(u.email) + '</td><td class="joined muted">' + esc(UI.fmtDate(u.joined)) + '</td>' +
              '<td><label class="ui-check"><input type="checkbox" data-admin' + (u.is_admin ? ' checked' : '') + '> Admin</label></td>' +
              '<td><label class="ui-check"><input type="checkbox" data-enabled' + (u.enabled ? ' checked' : '') + '> Active</label></td></tr>';
          }).join('') + '</tbody></table>';
      });
    }

    function demo() {
      return UI.api('admin_overview').then(function (d) {
        var c = d.demo.counts;
        body.innerHTML = '<div class="ui-card ui-narrow" style="margin:0"><h3>Demo data</h3>' +
          '<p class="muted">Example people and content, so the app never looks empty for the first visitors. Demo rows are flagged, so removing them never touches real data. Once removed, it stays removed until you load it again.</p>' +
          '<p>Status: <b>' + esc(d.demo.state) + '</b> · ' + Object.keys(c).map(function (k) { return c[k] + ' ' + esc(k); }).join(', ') + '</p>' +
          '<div class="ui-row"><button class="ui-btn primary" data-demo="load">' + UI.icon('refresh') + (d.demo.state === 'loaded' ? 'Reload demo data' : 'Load demo data') + '</button>' +
          '<button class="ui-btn danger" data-demo="remove">' + UI.icon('trash') + 'Remove demo data</button></div></div>';
      });
    }

    function sorting() {
      return UI.api('admin_sorting').then(function (d) {
        var pct = d.total ? Math.round(d.right / d.total * 100) : 0;
        body.innerHTML = '<div class="ad-stats"><div class="ui-card ui-stat"><b>' + (d.total ? pct + '%' : '–') + '</b><span>first guesses people kept (' + d.right + ' of ' + d.total + ')</span></div>' +
          '<div class="ui-card ui-stat"><b>' + d.categories + '</b><span>categories</span></div></div>' +
          '<div class="ui-grid two" style="margin-top:16px"><div class="ui-card"><h3>Per suggested category</h3>' + (d.per.length ? '<table class="ad-users"><tbody>' + d.per.map(function (r) {
            return '<tr><td>' + esc(r.name) + '</td><td>' + r.right + ' / ' + r.total + '</td><td>' + Math.round(r.right / r.total * 100) + '%</td></tr>'; }).join('') + '</tbody></table>' : '<p class="muted">No sorted faves yet.</p>') + '</div>' +
          '<div class="ui-card"><h3>Most common corrections</h3><p class="muted small">Suggested → what people chose. Tune server_code/Taxonomy.py with these.</p>' +
          (d.fixes.length ? '<table class="ad-users"><tbody>' + d.fixes.map(function (f) { return '<tr><td>' + esc(f[0]) + '</td><td>' + f[1] + '</td></tr>'; }).join('') + '</tbody></table>' : '<p class="muted">None yet.</p>') + '</div></div>' +
          '<div class="ui-card" style="margin-top:16px"><h3>Try the sorter</h3><form class="ui-stack" data-try><textarea name="text" rows="3" placeholder="A link (https://…) or any text: a note, OCR from a poster…"></textarea>' +
          '<label class="ui-check"><input type="checkbox" name="fetch"> Read the link live</label><button class="ui-btn primary" type="submit">Sort it</button></form><div data-try-out style="margin-top:12px"></div></div>';
      });
    }

    function ai() {
      return UI.api('admin_ai_status').then(function (d) {
        var c = d.config;
        body.innerHTML = '<div class="ui-card"><div class="ui-row" style="justify-content:space-between"><h3 style="margin:0">AI second opinion for sorting</h3><span class="ui-badge brand">In progress</span></div>' +
          '<p class="muted">The rules sort everything first, without AI. When this is on, people who opt in (Tools → AI) get Claude’s suggestion on the inbox items the rules aren’t sure about. It only suggests; nothing is re-filed by itself. ' +
          'Sent per item: title, website, link path, up to 300 characters of text. Never pictures.</p>' +
          '<div class="ui-grid two" style="margin-top:14px"><div><p><b>1. Key:</b> ' + (d.has_key ? '<span class="ui-badge brand">' + UI.icon('check') + ' found in App Secrets</span>'
            : 'not added yet. In the Anvil editor, open <b>App Secrets</b> and add a secret named <code>' + esc(d.secret) + '</code> holding your Anthropic API key.') + '</p>' +
          '<p><b>2. Switch:</b> ' + (d.available ? 'on' : 'off') + ' · <b>' + d.opted_in + '</b> people opted in · ' + d.suggestions_waiting + ' suggestions in inboxes</p></div>' +
          '<form class="ui-stack" data-aiset><label class="ui-check"><input type="checkbox" name="enabled"' + (c.enabled ? ' checked' : '') + (d.has_key ? '' : ' disabled') + '> Turn it on for everyone who opts in</label>' +
          '<label class="ui-field"><span>Model</span><select name="model">' + d.models.map(function (m) { return '<option value="' + m[0] + '"' + (m[0] === c.model ? ' selected' : '') + '>' + esc(m[1] + ': ' + m[2]) + '</option>'; }).join('') + '</select></label>' +
          '<div class="ui-row"><label class="ui-field" style="flex:1"><span>Ask when the rules are under (confidence)</span><input type="number" name="threshold" min="0.2" max="0.95" step="0.05" value="' + c.threshold + '"></label>' +
          '<label class="ui-field" style="flex:1"><span>Items per person per day</span><input type="number" name="daily" min="10" max="2000" step="10" value="' + c.daily + '"></label></div>' +
          '<div class="ui-row"><button class="ui-btn primary" type="submit">Save</button><button class="ui-btn" type="button" data-aitest' + (d.has_key ? '' : ' disabled') + '>' + UI.icon('play') + 'Test on my least-sure faves</button></div></form></div>' +
          '<div data-aiout style="margin-top:14px"></div></div>';
      });
    }

    var DRAW = { overview: overview, feedback: feedback, users: users, sorting: sorting, ai: ai, demo: demo };

    view.addEventListener('click', function (e) {
      var f = e.target.closest('[data-filter]');
      if (f) { fbFilter = f.getAttribute('data-filter'); feedback(); return; }
      var st = e.target.closest('[data-status]');
      if (st) {
        var card = st.closest('[data-id]');
        UI.api('set_feedback_status', card.getAttribute('data-id'), st.getAttribute('data-status'), card.querySelector('[data-note]').value).then(function () { UI.toast('Saved', 'ok'); feedback(); });
        return;
      }
      var del = e.target.closest('[data-del-fb]');
      if (del) {
        UI.confirm({ title: 'Delete this message?', ok: 'Delete', danger: true }).then(function (yes) {
          if (yes) UI.api('delete_feedback', del.closest('[data-id]').getAttribute('data-id')).then(feedback);
        });
        return;
      }
      var at = e.target.closest('[data-aitest]');
      if (at) {
        var model = view.querySelector('[data-aiset] [name=model]').value;
        UI.busy(at, UI.api('admin_ai_test', model)).then(function (r) {
          view.querySelector('[data-aiout]').innerHTML = '<p class="small muted">' + esc(r.model) + ' · ' + r.ms + ' ms' + (r.usage.input_tokens ? ' · ' + r.usage.input_tokens + ' tokens in, ' + r.usage.output_tokens + ' out' : '') + '</p>' +
            '<table class="ad-users"><thead><tr><th>Fave</th><th>Rules</th><th>AI</th><th>Why</th></tr></thead><tbody>' + r.rows.map(function (x) {
              return '<tr><td>' + esc(x.title) + '</td><td>' + esc(x.rules) + ' (' + Math.round(x.rules_conf * 100) + '%)</td><td><b>' + esc(x.ai || '-') + '</b> ' + esc(x.sure || '') + '</td><td class="small">' + esc(x.why || '') + '</td></tr>';
            }).join('') + '</tbody></table>';
        });
        return;
      }
      var dm = e.target.closest('[data-demo]');
      if (dm) {
        var load = dm.getAttribute('data-demo') === 'load';
        UI.confirm({ title: load ? 'Load the demo data?' : 'Remove the demo data?', text: load ? 'Demo people and content are added (any old demo rows are replaced).' : 'Every demo row is deleted. Real data stays.', ok: load ? 'Load' : 'Remove', danger: !load })
          .then(function (yes) { if (yes) UI.busy(dm, UI.api(load ? 'demo_load' : 'demo_remove')).then(function () { UI.toast('Done', 'ok'); demo(); }); });
      }
    });
    view.addEventListener('change', function (e) {
      var row = e.target.closest('tr[data-id]');
      if (!row) return;
      var id = row.getAttribute('data-id'), box = e.target;
      var fn = box.hasAttribute('data-admin') ? 'set_admin' : box.hasAttribute('data-enabled') ? 'set_enabled' : null;
      if (fn) UI.api(fn, id, box.checked).then(function () { UI.toast('Saved', 'ok'); }, function (err) { box.checked = !box.checked; UI.toast(err.message, 'error'); });
    });
    view.addEventListener('submit', function (e) {
      if (e.target.matches('[data-search]')) { e.preventDefault(); users(UI.formData(e.target).q); }
      if (e.target.matches('[data-aiset]')) {
        e.preventDefault();
        var v = UI.formData(e.target);
        UI.busy(e.target.querySelector('[type=submit]'), UI.api('admin_ai_save', { enabled: !!v.enabled, model: v.model, threshold: v.threshold, daily: v.daily })).then(function () { UI.toast('Saved', 'ok'); ai(); });
      }
      if (e.target.matches('[data-try]')) {
        e.preventDefault();
        var v = UI.formData(e.target);
        UI.busy(e.target.querySelector('[type=submit]'), UI.api('admin_classify', v.text, v.fetch)).then(function (r) {
          var x = r.result;
          e.target.parentNode.querySelector('[data-try-out]').innerHTML = '<p><b>' + esc(x.category) + '</b> (' + Math.round(x.confidence * 100) + '% sure)</p>' +
            '<p class="small muted">Why: ' + esc(x.reasons.join(' · ') || 'nothing matched') + '</p><p class="small muted">Scores: ' + esc(Object.keys(x.scores).map(function (k) { return k + ' ' + x.scores[k]; }).join(', ')) + '</p>' +
            (x.tags.length ? '<p class="small muted">Tags: ' + esc(x.tags.join(', ')) + '</p>' : '') + (r.page && r.page.title ? '<p class="small muted">Page title: ' + esc(r.page.title) + '</p>' : '');
        });
      }
    });
    return DRAW[tab]();
  });
})();

/* ===== auth.html ===== */
(function () {
  var esc = UI.esc;
  var GOOGLE_G = '<svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>' +
    '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>' +
    '<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>' +
    '<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';
  function pw(name, auto) {
    return '<div class="au-pw"><input type="password" name="' + name + '" autocomplete="' + auto + '" required minlength="8">' +
      '<button type="button" data-show>Show</button></div>';
  }
  UI.page('auth', { title: 'Sign in', auth: 'guest' }, function (view, ctx) {
    var mode = ['signup', 'reset'].indexOf(ctx.args[0]) >= 0 ? ctx.args[0] : 'login';
    function draw(msg, isErr) {
      var heading = { login: 'Welcome back', signup: 'Create your account', reset: 'Reset your password' }[mode];
      var sub = { login: 'Sign in to continue to ' + esc(UI.config.name) + '.', signup: 'It\'s free and takes a few seconds.',
        reset: 'We\'ll email you a link to choose a new password.' }[mode];
      view.innerHTML = '<div class="au-wrap"><div class="ui-card au-card">' +
        '<h1>' + heading + '</h1><p class="muted">' + sub + '</p>' +
        (mode !== 'reset' ? '<div class="ui-seg" role="tablist"><button type="button" data-mode="login" class="' + (mode === 'login' ? 'on' : '') + '">Sign in</button>' +
          '<button type="button" data-mode="signup" class="' + (mode === 'signup' ? 'on' : '') + '">Create account</button></div>' : '<div style="height:14px"></div>') +
        '<form class="ui-stack" data-form="' + mode + '" novalidate>' +
        (mode === 'signup' ? '<label class="ui-field"><span>Your name</span><input type="text" name="name" autocomplete="name" required maxlength="60"></label>' : '') +
        '<label class="ui-field"><span>Email</span><input type="email" name="email" autocomplete="email" required></label>' +
        (mode === 'login' ? '<label class="ui-field"><span>Password</span>' + pw('password', 'current-password') + '</label>' : '') +
        (mode === 'signup' ? '<label class="ui-field"><span>Password <em>(at least 8 characters)</em></span>' + pw('password', 'new-password') + '</label>' +
          (window.LegalKit ? '<div>' + LegalKit.consentField() + '</div>' : '') : '') +
        '<div data-msg role="alert"' + (msg ? ' class="' + (isErr ? 'ui-error' : 'ui-note') + '">' + esc(msg) : ' hidden>') + '</div>' +
        '<button class="ui-btn primary block" type="submit">' + { login: 'Sign in', signup: 'Create account', reset: 'Send the link' }[mode] + '</button></form>' +
        (mode !== 'reset' ? '<div class="au-or">or</div><button type="button" class="ui-btn block au-google" data-google>' + GOOGLE_G + 'Continue with Google</button>' : '') +
        '<div class="au-links">' + (mode === 'login' ? '<a data-mode="reset">Forgot your password?</a>' : '<a data-mode="login">' + UI.icon('back') + ' Back to sign in</a>') +
        '<a href="#landing" data-go="landing">About ' + esc(UI.config.name) + '</a></div></div></div>';
      var first = view.querySelector('input');
      if (first && !msg) first.focus();
    }
    view.addEventListener('click', function (e) {
      var m = e.target.closest('[data-mode]');
      if (m) { e.preventDefault(); mode = m.getAttribute('data-mode'); history.replaceState(null, '', '#auth' + (mode === 'login' ? '' : '/' + mode)); draw(); return; }
      var g = e.target.closest('[data-google]');
      if (g) { google(g); return; }
      var s = e.target.closest('[data-show]');
      if (s) { var i = s.parentNode.querySelector('input'); i.type = i.type === 'password' ? 'text' : 'password'; s.textContent = i.type === 'password' ? 'Show' : 'Hide'; }
    });
    view.addEventListener('submit', function (e) {
      e.preventDefault();
      var form = e.target, v = UI.formData(form);
      var problem = !/^\S+@\S+\.\S+$/.test(v.email || '') ? 'Please enter a valid email address.'
        : mode !== 'reset' && (v.password || '').length < (mode === 'signup' ? 8 : 1) ? (mode === 'signup' ? 'Please choose a password of at least 8 characters.' : 'Please enter your password.')
        : mode === 'signup' && (v.name || '').trim().length < 2 ? 'Please tell us your name.' : null;
      if (problem) { say(problem, true); return; }
      if (mode === 'signup' && window.LegalKit && !LegalKit.consentChecked(form)) return;  // the kit shows its own message
      UI.busy(form.querySelector('[type=submit]'), UI.auth(mode, v)).then(function (r) {
        if (mode === 'reset' || (r && !r.me)) { mode = 'login'; draw(r && r.message, false); restore({ email: v.email }); }
        else UI.toast(mode === 'signup' ? 'Welcome to ' + UI.config.name + '!' : 'Welcome back!', 'ok');
      }, function (err) { say(err.message, true); });
    });
    // Sign-up asks for the Privacy & Terms tick here too (ticking it is remembered for the new account).
    function google(btn) {
      var form = view.querySelector('form'), v = mode === 'signup' ? UI.formData(form) : {};
      if (mode === 'signup' && window.LegalKit && !LegalKit.consentChecked(form)) return;
      UI.busy(btn, UI.auth('google', { name: (v.name || '').trim() })).then(function () {
        UI.toast(mode === 'signup' ? 'Welcome to ' + UI.config.name + '!' : 'Welcome back!', 'ok');
      }, function (err) { say(err.message, true); });
    }
    function say(msg, isErr) {
      var box = view.querySelector('[data-msg]');
      box.className = isErr ? 'ui-error' : 'ui-note'; box.textContent = msg; box.hidden = false;
    }
    function restore(v) {
      ['name', 'email'].forEach(function (k) { var i = view.querySelector('[name=' + k + ']'); if (i && v[k]) i.value = v[k]; });
    }
    draw();
  });
})();

/* ===== discover.html ===== */
(function () {
  var esc = UI.esc, TM_KEY = 'favesbuddy.tm';
  var TABS = [['places', 'Places like yours', 'pin'], ['events', 'Events', 'ticket'], ['ideas', 'Ideas & reads', 'book']];

  function tmKey() { try { return localStorage.getItem(TM_KEY) || ''; } catch (e) { return ''; } }

  UI.page('discover', { title: 'Discover', nav: 'Discover', icon: 'compass', auth: 'user', order: 40 }, function (view, ctx) {
    var tab = TABS.some(function (t) { return t[0] === ctx.args[0]; }) ? ctx.args[0] : 'places';
    var taste = null, center = null, km = UI.store.get('dc.km', 2), results = {}, savedUrls = {};
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:80px"></div><div class="ui-skel" style="height:260px;margin-top:16px"></div></div>';

    function where() { return !center ? 'near you' : center.home ? 'around ' + center.label : center.label; }
    function centersHtml() {
      var cs = taste.centers.slice();
      return '<div class="dc-where"><span class="muted small">Around</span>' + cs.map(function (c, i) {
        return '<button class="fb-chip sm' + (center && center.lat === c.lat && center.lng === c.lng ? ' on' : '') + '" data-center="' + i + '">' + (c.home ? '🏠 ' : '📍 ') + esc(c.label) + '</button>';
      }).join('') + '<button class="fb-chip sm' + (center && center.me ? ' on' : '') + '" data-me>' + UI.icon('locate') + 'Near me</button>' +
        '<span class="muted small" style="margin-left:6px">within</span>' + [1, 2, 5, 15].map(function (k) { return '<button class="fb-chip sm' + (km === k ? ' on' : '') + '" data-km="' + k + '">' + k + ' km</button>'; }).join('') + '</div>';
    }
    function draw() {
      view.innerHTML = '<div class="ui-wrap"><div class="dc-head"><div><h1>Discover</h1><p class="muted" style="margin:4px 0 0">More of what you love, found in open data on demand. ' +
        (taste.kept ? 'Based on your ' + UI.plural(taste.kept, 'kept fave') + '.' : 'Save a few faves and this gets personal.') + '</p></div></div>' +
        centersHtml() +
        '<nav class="ui-tabs dc-tabs">' + TABS.map(function (t) { return '<a href="#discover/' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '">' + UI.icon(t[2]) + t[1] + '</a>'; }).join('') + '</nav>' +
        '<div data-body></div>' +
        '<div class="fb-panel" style="margin-top:34px"><h3>How suggestions work</h3><div class="dc-how">' +
        '<div><b>1. Your taste</b>We look at what you kept: kinds of places (café, park…), cuisines, tags like “terrace” or “vegan”, and where your faves are.</div>' +
        '<div><b>2. A precise search</b>Each card shows the exact filter we send to OpenStreetMap, Wikipedia or Wikidata. Nothing runs until you tap.</div>' +
        '<div><b>3. You decide</b>Results you already saved are hidden. Saving one puts it in your inbox, sorted, so it teaches the next search.</div></div></div></div>';
      body();
    }
    function body() {
      var b = view.querySelector('[data-body]');
      if (tab === 'places') {
        b.innerHTML = '<div class="dc-recipes">' + taste.recipes.map(function (r, i) {
          return '<button class="dc-recipe" data-recipe="' + i + '"><span class="em">' + esc(r.emoji) + '</span><b>' + esc(r.label) + '</b><span class="muted small">' + esc(r.because) + '</span>' +
            '<span class="q">' + esc(r.filters.concat(r.prefer).map(function (f) { return f[0] + '=' + f[1]; }).join(' + ')) + '</span></button>';
        }).join('') + '</div><div class="dc-results" data-results>' + (results.places || '<p class="muted" style="margin-top:16px">' + UI.icon('info') + ' Tap a search to look ' + esc(where()) + '.</p>') + '</div>';
      } else if (tab === 'events') {
        var key = tmKey();
        b.innerHTML = '<div class="dc-recipes">' +
          '<button class="dc-recipe" data-ev="wikidata"><span class="em">🎪</span><b>Festivals around here</b><span class="muted small">Recurring festivals and events listed on Wikidata within ' + Math.max(km, 15) + ' km.</span><span class="q">wikidata: instance of festival, near</span></button>' +
          (key ? taste.event_classes.concat(['']).slice(0, 4).map(function (c) {
            return '<button class="dc-recipe" data-ev="tm" data-class="' + esc(c) + '"><span class="em">🎟️</span><b>' + (c ? esc(c) + ' events' : 'Everything coming up') + '</b><span class="muted small">Dated events from Ticketmaster, soonest first.</span><span class="q">ticketmaster: ' + (c ? 'classificationName=' + esc(c) + ' + ' : '') + 'radius=' + Math.max(km, 10) + 'km</span></button>';
          }).join('') : '') + '</div>' +
          (key ? '' : '<div class="fb-ai-nudge" style="margin-top:16px">' + UI.icon('ticket') + '<span><b>Want concerts, shows and games with dates?</b> Add a free Ticketmaster Discovery API key (5,000 searches a day). It stays in this browser.</span><a class="ui-btn sm" href="#tools/events" data-go="tools/events">Add key</a></div>') +
          '<div class="dc-results" data-results>' + (results.events || '') + '</div>';
      } else {
        b.innerHTML = (taste.seeds.length ? '<p class="muted small">More like your favourite reads and videos (Wikipedia “more like this”):</p><div class="dc-seeds">' +
          taste.seeds.map(function (s, i) { return '<button class="fb-chip" data-seed="' + i + '">' + UI.icon('book') + esc(s.length > 40 ? s.slice(0, 40) + '…' : s) + '</button>'; }).join('') + '</div>' :
          '<p class="muted">Keep a few articles, videos or courses and you\'ll get “more like this” ideas here.</p>') +
          '<div class="dc-recipes" style="margin-top:8px"><button class="dc-recipe" data-wiki-near><span class="em">🏛️</span><b>Stories ' + esc(where()) + '</b><span class="muted small">Wikipedia articles about places within ' + km + ' km: history, architecture, oddities.</span><span class="q">wikipedia: geosearch radius=' + Math.min(10, km) + 'km</span></button></div>' +
          '<div class="dc-results" data-results>' + (results.ideas || '') + '</div>';
      }
    }
    function resultsBox(html) { var el = view.querySelector('[data-results]'); if (el) el.innerHTML = html; results[tab] = html; }
    function sugCard(s, i, kind) {
      var f = { id: 'sug' + i + kind, title: s.title, cat: s.cat || 'other', kind: s.kind || 'place', image: s.image, lat: s.lat, lng: s.lng, address: s.address || s.venue || '',
                osm: s.osm || {}, desc: s.desc, event_at: s.start || null, tags: [] };
      var saved = s.url && savedUrls[s.url];
      return '<article class="fb-card dc-card">' + FB.cover(f, '<div class="fb-on-img"><span class="fb-pill">' + esc(FB.cat(f.cat).emoji + ' ' + FB.cat(f.cat).name) + '</span>' +
        (s.start ? '<span class="fb-pill accent">' + esc(FB.when(s.start, true)) + '</span>' : '') + '</div>') +
        '<div class="fb-card-body"><h3>' + esc(s.title) + '</h3>' +
        (s.desc || s.address || s.venue ? '<div class="fb-sub"><span>' + esc(s.desc || s.venue || s.address) + '</span></div>' : '') +
        '<div class="fb-sub small">' + (s.km != null ? FB.fmtDist(s.km) + ' away' : '') + (s.genre ? ' · ' + esc(s.genre) : '') + '</div>' +
        (s.why && s.why.length ? '<div class="dc-why">✓ ' + esc(s.why.join(' · ')) + '</div>' : '') + '</div>' +
        '<div class="fb-actions"><button class="ui-btn sm primary" data-save-sug="' + i + '"' + (saved ? ' disabled' : '') + '>' + UI.icon('heart') + (saved ? 'Saved' : 'Save') + '</button>' +
        (s.url || s.website ? '<a class="ui-btn sm" target="_blank" rel="noopener" href="' + esc(s.url || s.website) + '">' + UI.icon('external') + 'Look</a>' : '') +
        (s.lat != null && !s.url ? '<a class="ui-btn sm" target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=' + s.lat + '&mlon=' + s.lng + '#map=18/' + s.lat + '/' + s.lng + '">' + UI.icon('map') + 'Map</a>' : '') +
        '</div></article>';
    }
    var current = [];
    function show(list, head, kind) {
      current = list;
      resultsBox('<div class="dc-res-head"><b>' + head + '</b><span class="muted small">' + UI.plural(list.length, 'result') + '</span></div>' +
        (list.length ? '<div class="fb-grid">' + list.map(function (s, i) { return sugCard(s, i, kind); }).join('') + '</div>'
          : '<div class="ui-empty">' + UI.icon('search') + '<h3>Nothing new found</h3><p>Try a bigger distance or another spot.</p></div>'));
    }
    function loading(msg) { resultsBox('<div class="ib-progress" style="display:flex;gap:10px;align-items:center;padding:14px;border-radius:14px;background:var(--c-surface)">' + UI.icon('refresh') + esc(msg) + '</div>'); }

    function runRecipe(i, btn) {
      var r = taste.recipes[i];
      view.querySelectorAll('.dc-recipe').forEach(function (b) { b.classList.toggle('on', b === btn); });
      loading('Searching OpenStreetMap for ' + r.label.toLowerCase() + ' within ' + km + ' km, ' + where() + '…');
      return FB.data.placesLike(r, center, km, taste.saved).then(function (list) {
        show(list.slice(0, 24).map(function (p) { p.cat = r.cat; return p; }), esc(r.emoji + ' ' + r.label) + ' ' + esc(where()), 'p');
      }, function () {
        // Overpass busy: read the map tiles' points of interest around the centre instead.
        loading('OpenStreetMap search is busy; reading the map ' + where() + ' instead…');
        var tmp = document.createElement('div'); tmp.style.cssText = 'position:fixed;left:-9999px;top:0;width:600px;height:600px';
        document.body.appendChild(tmp);
        return FB.map.make(tmp, { center: center, zoom: 15 }).then(function (m) {
          return new Promise(function (res) { setTimeout(res, 1800); }).then(function () {
            var list = FB.data.tilePois(m, r, center, km, taste.saved);
            if (m) m.remove(); tmp.remove();
            show(list.slice(0, 24).map(function (p) { p.cat = r.cat; p.why = ['from the map']; return p; }), esc(r.emoji + ' ' + r.label) + ' ' + esc(where()) + ' <span class="muted small">(from the map; fewer details)</span>', 'p');
          });
        });
      });
    }
    view.addEventListener('click', function (e) {
      var rb = e.target.closest('[data-recipe]');
      if (rb) { UI.busy(rb, runRecipe(+rb.getAttribute('data-recipe'), rb)); return; }
      var cb = e.target.closest('[data-center]');
      if (cb) { var c = taste.centers[+cb.getAttribute('data-center')]; center = c; results = {}; draw(); return; }
      if (e.target.closest('[data-me]')) {
        UI.busy(e.target.closest('[data-me]'), FB.geo(true)).then(function (g) {
          if (!g || g.home) { UI.toast('Location isn\'t available. Pick one of your spots instead.', 'error'); return; }
          center = { lat: g.lat, lng: g.lng, label: 'near you', me: true }; results = {}; draw();
        });
        return;
      }
      var kb = e.target.closest('[data-km]');
      if (kb) { km = +kb.getAttribute('data-km'); UI.store.set('dc.km', km); results = {}; draw(); return; }
      var ev = e.target.closest('[data-ev]');
      if (ev) {
        view.querySelectorAll('.dc-recipe').forEach(function (b) { b.classList.toggle('on', b === ev); });
        if (ev.getAttribute('data-ev') === 'wikidata') {
          loading('Looking up festivals ' + where() + ' on Wikidata…');
          UI.busy(ev, FB.data.wikidataEvents(center, Math.max(km, 15)).then(function (list) {
            show(list.map(function (x) { x.cat = 'events'; x.kind = 'event'; x.km = FB.dist(center, x); return x; }), '🎪 Festivals ' + esc(where()), 'w');
          }, function () { resultsBox('<div class="ui-error">Wikidata didn\'t answer. Try again in a minute.</div>'); }));
        } else {
          var cls = ev.getAttribute('data-class');
          loading('Asking Ticketmaster for events ' + where() + '…');
          UI.busy(ev, FB.data.ticketmaster(tmKey(), center, Math.max(km, 10), cls).then(function (list) {
            show(list.map(function (x) { x.cat = 'events'; x.kind = 'event'; x.km = FB.dist(center, x); return x; }), '🎟️ ' + (cls ? esc(cls) + ' events' : 'Coming up') + ' ' + esc(where()), 't');
          }, function (err) { resultsBox('<div class="ui-error">' + esc(err.message) + '</div>'); }));
        }
        return;
      }
      var sd = e.target.closest('[data-seed]');
      if (sd) {
        var seed = taste.seeds[+sd.getAttribute('data-seed')];
        view.querySelectorAll('[data-seed]').forEach(function (b) { b.classList.toggle('on', b === sd); });
        loading('Finding Wikipedia articles like “' + seed + '”…');
        UI.busy(sd, FB.data.wikiLike(seed).then(function (list) {
          show(list.map(function (x) { x.cat = 'read'; x.kind = 'link'; x.why = x.from ? ['like ' + x.from] : []; return x; }), '📖 More like “' + esc(seed) + '”', 'k');
        }, function () { resultsBox('<div class="ui-error">Wikipedia didn\'t answer. Try again.</div>'); }));
        return;
      }
      var wn = e.target.closest('[data-wiki-near]');
      if (wn) {
        loading('Reading Wikipedia ' + where() + '…');
        UI.busy(wn, FB.data.wikiNearby(center, Math.min(10000, km * 1000)).then(function (list) {
          show(list.map(function (x) { x.cat = 'culture'; x.kind = 'link'; x.km = FB.dist(center, x); return x; }), '🏛️ Stories ' + esc(where()), 'n');
        }, function () { resultsBox('<div class="ui-error">Wikipedia didn\'t answer. Try again.</div>'); }));
        return;
      }
      var sv = e.target.closest('[data-save-sug]');
      if (sv) {
        var s = current[+sv.getAttribute('data-save-sug')];
        var f = { title: s.title, source: 'suggested', url: s.url || null, lat: s.lat, lng: s.lng, address: s.address || '', osm: s.osm || {},
                  kind: s.kind === 'event' ? (s.start ? 'event' : 'link') : (s.url ? 'link' : 'place'), event_at: s.start || null,
                  meta: { description: s.desc || '', image: s.image || '', suggested_by: tab }, enriched: !!s.url };
        if (!f.url && f.lat == null) f.kind = 'note';
        UI.busy(sv, UI.api('save_fave', f)).then(function (r) {
          if (s.url) savedUrls[s.url] = 1;
          taste.saved.push([s.title.toLowerCase(), s.lat, s.lng]);
          sv.innerHTML = UI.icon('check') + 'Saved'; sv.disabled = true;
          var c = FB.cat(r.fave.cat); UI.toast('In your inbox as ' + c.emoji + ' ' + c.name, 'ok');
        });
      }
    });
    return Promise.all([FB.boot(), UI.api('taste'), FB.geo(false)]).then(function (r) {
      taste = r[1];
      if (!taste.centers.length) taste.centers.push({ lat: 45.5165, lng: -73.5795, label: 'in Montréal', n: 0 });
      center = taste.centers[0];
      draw();
    });
  });
})();

/* ===== fave.html ===== */
(function () {
  var esc = UI.esc;

  UI.page('fave', { title: 'Fave', auth: 'user' }, function (view, ctx) {
    var id = ctx.args[0], F = null, mine = false, lists = [], m = null, alive = true, here = null;
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:360px"></div></div>';

    function facts() {
      var o = F.osm || {}, out = [];
      if (F.address) out.push(['pin', esc(F.address)]);
      if (o.opening_hours) {
        var on = FB.openNow(o.opening_hours);
        out.push(['clock', (on === true ? '<span class="fb-open">Open now</span> · ' : on === false ? '<span class="fb-closed">Closed now</span> · ' : '') + esc(o.opening_hours)]);
      }
      if (o.website || o['contact:website']) out.push(['globe', '<a href="' + esc(o.website || o['contact:website']) + '" target="_blank" rel="noopener">' + esc((o.website || o['contact:website']).replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')) + '</a>']);
      if (o.phone || o['contact:phone']) out.push(['phone', '<a href="tel:' + esc((o.phone || o['contact:phone']).replace(/[^\d+]/g, '')) + '">' + esc(o.phone || o['contact:phone']) + '</a>']);
      if (o.cuisine) out.push(['tag', 'Cuisine: ' + esc(o.cuisine.replace(/_/g, ' ').replace(/;/g, ', '))]);
      if (o.wheelchair === 'yes') out.push(['check', 'Wheelchair accessible']);
      if (F.event_at) out.push(['calendar', '<b>' + esc(FB.when(F.event_at)) + '</b> · ' + esc(UI.fmtDate(F.event_at))]);
      var md = F.meta || {};
      if (md.priceRange) out.push(['tag', esc(md.priceRange)]);
      if (md.totalTime) out.push(['clock', 'Total time ' + esc(md.totalTime.replace(/^PT/, '').toLowerCase())]);
      if (F.read_min) out.push(['book', F.read_min + ' minute read']);
      return out.length ? '<div class="fv-facts">' + out.map(function (x) { return '<div>' + UI.icon(x[0]) + '<span>' + x[1] + '</span></div>'; }).join('') + '</div>' : '';
    }
    function draw() {
      var c = FB.cat(F.cat), md = F.meta || {}, conf = Math.round((F.conf || 0) * 100);
      var myLists = lists.filter(function (l) { return (F.lists || []).indexOf(l.id) >= 0; });
      var html = '<div class="ui-wrap"><a href="#' + (F.status === 'inbox' ? 'inbox' : 'home') + '" class="small">' + UI.icon('back') + (F.status === 'inbox' ? ' Inbox' : ' Your faves') + '</a>' +
        '<div class="fv-top" style="margin-top:14px"><div><div class="fv-pic">' + FB.cover(F) + '</div>' +
        (mine && F.kind === 'photo' ? '<div class="ui-row" style="margin-top:10px"><label class="ui-btn sm">' + UI.icon('camera') + 'Replace picture<input type="file" accept="image/*" data-repic hidden></label></div>' : '') + '</div>' +
        '<div><div class="ui-row">' + FB.catChip(F.cat) + (F.status === 'inbox' ? '<span class="ui-badge warn">In your inbox</span>' : F.status === 'archived' ? '<span class="ui-badge">Archived</span>' : '') +
        (F.owner ? '<span class="ui-badge">by ' + esc(F.owner) + '</span>' : '') + FB.stageBadge(F.stage, F) + '</div>' +
        '<h1 class="fv-title" ' + (mine ? 'contenteditable="true" data-title spellcheck="false"' : '') + '>' + esc(F.title) + '</h1>' +
        (F.url ? '<div class="ui-row"><a class="ui-btn primary" href="' + esc(F.url) + '" target="_blank" rel="noopener" data-open>' + UI.icon('external') + 'Open ' + esc(F.domain || 'link') + '</a>' +
          (F.lat != null ? '<a class="ui-btn" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + F.lat + ',' + F.lng + '">' + UI.icon('compass') + 'Directions</a>' : '') + '</div>'
          : F.lat != null ? '<div class="ui-row"><a class="ui-btn primary" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + F.lat + ',' + F.lng + '">' + UI.icon('compass') + 'Directions</a>' +
          '<a class="ui-btn" target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=' + F.lat + '&mlon=' + F.lng + '#map=18/' + F.lat + '/' + F.lng + '">' + UI.icon('map') + 'OpenStreetMap</a></div>' : '') +
        (F.desc ? '<p class="muted" style="margin-top:14px">' + esc(F.desc) + '</p>' : '') +
        (facts() ? '<div class="fv-sec">' + facts() + '</div>' : '');
      if (mine) {
        html += '<div class="fv-sec"><span class="lbl">Status</span><div class="ui-row"><div class="ui-seg">' + FB.stages(F).map(function (s) {
          return '<button data-stage="' + s[0] + '" class="' + (F.stage === s[0] ? 'on' : '') + '">' + s[1] + '</button>'; }).join('') + '</div>' +
          '<div class="fv-stars" aria-label="Rating">' + [1, 2, 3, 4, 5].map(function (n) { return '<button data-star="' + n + '" class="' + ((F.rating || 0) >= n ? 'on' : '') + '" aria-label="' + n + ' stars">' + UI.icon('star') + '</button>'; }).join('') + '</div></div></div>' +
          '<div class="fv-sec"><span class="lbl">Category</span><div class="fb-why">' + (F.confirmed ? 'You filed it here.' : 'Suggested' + (F.cat !== 'other' ? ' (' + conf + '% sure)' : '') + (F.reasons.length ? ' because:' : '')) +
          (F.confirmed ? '' : F.reasons.map(function (r) { return '<span class="fb-tag">' + esc(r) + '</span>'; }).join('')) + '</div>' +
          '<div style="margin-top:10px">' + FB.catPicker(F.cat) + '</div>' +
          (F.confirmed ? '<button class="ui-btn sm ghost" data-resort style="margin-top:8px">' + UI.icon('refresh') + 'Let Faves Buddy sort it again</button>' : '') + '</div>' +
          '<div class="fv-sec"><span class="lbl">Tags</span><div class="fv-tags">' + (F.tags || []).map(function (t) { return '<span class="fb-tag">#' + esc(t) + '<button data-untag="' + esc(t) + '" aria-label="Remove tag">×</button></span>'; }).join('') +
          '<form data-tagform style="display:inline"><input type="text" name="tag" placeholder="+ tag" maxlength="30"></form></div></div>' +
          '<div class="fv-sec"><span class="lbl">Lists</span><div class="ui-row">' + myLists.map(function (l) { return '<a class="fb-chip sm" href="#list/' + esc(l.id) + '">' + esc(l.emoji + ' ' + l.name) + '</a>'; }).join('') +
          '<button class="ui-btn sm" data-lists>' + UI.icon('plus') + (myLists.length ? 'Change' : 'Add to a list') + '</button></div></div>' +
          '<div class="fv-sec"><span class="lbl">Note</span><textarea data-note rows="4" placeholder="Why you saved it, who told you, what to order…">' + esc(F.note) + '</textarea></div>' +
          (F.status === 'inbox' ? '<div class="fv-sec"><button class="ui-btn primary" data-keep>' + UI.icon('check') + 'Keep as ' + esc(c.name) + '</button></div>' : '');
      } else {
        if (F.note) html += '<div class="fv-sec"><span class="lbl">Note</span><p>' + esc(F.note) + '</p></div>';
        html += '<div class="fv-sec"><button class="ui-btn primary" data-copy-mine>' + UI.icon('heart') + 'Save to my faves</button></div>';
      }
      html += '</div></div>';
      if (F.lat != null) html += '<div class="fb-section"><h2>On the map</h2>' + (mine ? '<button class="ui-btn sm" data-similar>' + UI.icon('sparkle') + 'More like this nearby</button>' : '') + '</div><div class="fv-map" data-map></div><div data-similar-out></div>';
      else if (mine && FB.cat(F.cat).place) html += '<div class="fb-section"><h2>Where is it?</h2></div><form class="ui-row" data-locate><input type="text" name="q" placeholder="Search for the place, e.g. ' + esc(F.title) + '" value="' + esc(F.title) + '" style="flex:1;min-width:200px"><button class="ui-btn" type="submit">' + UI.icon('search') + 'Find</button></form><div data-locate-out style="margin-top:10px"></div>';
      if (F.kind === 'photo' || md.ocr) html += photoSection();
      if (md.selection) html += '<div class="fb-section"><h2>Saved from</h2></div><p class="muted">' + esc(md.selection) + '</p>';
      if (mine) html += '<div class="fb-section"><h2>More</h2></div><div class="fv-actions">' +
        (F.status !== 'archived' ? '<button class="ui-btn" data-archive>' + UI.icon('archive') + 'Archive</button>' : '<button class="ui-btn" data-unarchive>' + UI.icon('inbox') + 'Back to inbox</button>') +
        '<button class="ui-btn" data-snooze>' + UI.icon('snooze') + 'Remind me later</button>' +
        '<button class="ui-btn danger" data-delete>' + UI.icon('trash') + 'Delete</button></div>';
      html += '<p class="fv-meta">Saved ' + esc(UI.ago(F.created)) + (F.source ? ' from ' + esc({ extension: 'the browser extension', app: 'the app', import: 'an import', onetab: 'OneTab', suggested: 'Discover', shared: 'a shared list', sample: 'the samples', map: 'the map' }[F.source] || F.source) : '') +
        (F.saves > 1 ? ' · saved ' + F.saves + ' times' : '') + (F.tabset_name ? ' · tab set <a href="#tabs">' + esc(F.tabset_name) + '</a>' : '') +
        (md.fetch_error ? ' · couldn\'t read the page: ' + esc(md.fetch_error) : '') + '</p></div>';
      view.innerHTML = html;
      if (F.lat != null) drawMap();
    }
    function photoSection() {
      var md = F.meta || {}, found = md.found || {};
      return '<div class="fb-section"><h2>In the picture</h2></div><div class="fb-panel ui-stack">' +
        (md.ocr ? '<div><b>Text read from it</b><div class="fv-ocr">' + esc(md.ocr) + '</div></div>' : '<p class="muted">The text in this picture hasn\'t been read yet.</p>') +
        (FB.media.foundCount(found) ? '<div><b>Found in it</b>' + FB.media.foundHtml(found) + '</div>' : '') +
        (md.ai ? '<div><b>AI description</b><p>' + esc(md.ai) + '</p></div>' : '') +
        (mine && F.photo ? '<div class="ui-row"><button class="ui-btn" data-ocr>' + UI.icon('text') + (md.ocr ? 'Read the text again' : 'Read the text (on this device, free)') + '</button>' +
          (FB.ai.has() ? '<button class="ui-btn" data-ai>' + UI.icon('wand') + 'Describe with AI</button>' : '') + '</div><div data-ocr-progress></div>' +
          (FB.ai.has() ? '' : FB.ai.nudge('describe pictures, spot places and dates in them')) : '') + '</div>';
    }
    function drawMap() {
      FB.map.make(view.querySelector('[data-map]'), { center: F, zoom: 15, cooperative: true }).then(function (map) {
        if (!map || !alive) return;
        m = map;
        new maplibregl.Marker({ element: FB.map.pinEl(F), anchor: 'bottom' }).setLngLat([F.lng, F.lat]).addTo(m);
        if (mine) {
          m.on('click', function (e) {
            UI.confirm({ title: 'Move the pin here?', text: 'The place\'s location becomes the spot you clicked.', ok: 'Move pin' }).then(function (y) {
              if (y) save({ lat: +e.lngLat.lat.toFixed(6), lng: +e.lngLat.lng.toFixed(6) }).then(function () { UI.toast('Pin moved', 'ok'); });
            });
          });
        }
      });
    }
    function save(fields, redraw) {
      return UI.api('update_fave', F.id, fields).then(function (r) { F = r.fave; if (redraw !== false) draw(); return r; });
    }
    function readText(btn) {
      var prog = view.querySelector('[data-ocr-progress]');
      prog.innerHTML = '<div class="muted small" data-st>Loading the text reader (first time: about 10 MB)…</div><div class="fv-progress"><i></i></div>';
      var bar = prog.querySelector('i'), st = prog.querySelector('[data-st]');
      return UI.busy(btn, FB.media.ocr(F.image, function (status, p) { st.textContent = status === 'recognizing text' ? 'Reading the text…' : 'Getting ready…'; bar.style.width = Math.round(p * 100) + '%'; })
        .then(function (text) { return UI.api('save_photo_ocr', F.id, text, FB.media.extract(text)); })
        .then(function (r) { F = r.fave; draw(); UI.toast('Text read. Category: ' + FB.cat(F.cat).emoji + ' ' + FB.cat(F.cat).name, 'ok'); }));
    }
    function describe(btn) {
      return UI.busy(btn, fetch(F.image).then(function (r) { return r.blob(); }).then(function (b) { return FB.media.shrink(b, 1200); })
        .then(function (s) { return FB.ai.analyseImage(s.dataUrl, (F.meta || {}).ocr); })
        .then(function (a) {
          var found = Object.assign({}, (F.meta || {}).found || {});
          if (a.places && a.places.length) found.addresses = (found.addresses || []).concat(a.places.map(function (p) { return p.address || p.name; }).filter(Boolean));
          if (a.when) found.dates = (found.dates || []).concat([a.when]);
          return UI.api('save_photo_ocr', F.id, (F.meta || {}).ocr || a.text || null, found, a);
        }).then(function (r) { F = r.fave; draw(); UI.toast('Described by AI', 'ok'); }));
    }
    view.addEventListener('click', function (e) {
      var t = e.target;
      if (t.closest('[data-open]')) { UI.apiQuiet('opened', F.id); return; }
      var st = t.closest('[data-stage]'); if (st) { var v = st.getAttribute('data-stage'); save({ stage: F.stage === v ? '' : v }); return; }
      var sr = t.closest('[data-star]'); if (sr) { var n = +sr.getAttribute('data-star'); save({ rating: F.rating === n ? 0 : n }); return; }
      var ct = t.closest('[data-cat]');
      if (ct) { save({ category: ct.getAttribute('data-cat') }).then(function () { UI.toast('Filed under ' + FB.cat(F.cat).emoji + ' ' + FB.cat(F.cat).name + '. Noted for next time.', 'ok'); }); return; }
      if (t.closest('[data-resort]')) { UI.api('resort_fave', F.id).then(function (r) { F = r.fave; draw(); UI.toast('Sorted again: ' + FB.cat(F.cat).name, 'ok'); }); return; }
      var ut = t.closest('[data-untag]'); if (ut) { save({ tags: F.tags.filter(function (x) { return x !== ut.getAttribute('data-untag'); }) }); return; }
      if (t.closest('[data-lists]')) { FB.listsModal(F, lists, F.lists || []).then(function (nf) { if (nf) { F = nf; draw(); } }); return; }
      if (t.closest('[data-keep]')) { UI.api('triage', F.id, 'keep').then(function () { UI.toast('Kept', 'ok'); load(); }); return; }
      if (t.closest('[data-archive]')) { UI.api('triage', F.id, 'archive').then(function () { UI.toast('Archived', 'ok'); load(); }); return; }
      if (t.closest('[data-unarchive]')) { UI.api('triage', F.id, 'inbox').then(function () { UI.toast('Back in your inbox', 'ok'); load(); }); return; }
      if (t.closest('[data-snooze]')) { FB.snoozeModal(F.id).then(function (r) { if (r) load(); }); return; }
      if (t.closest('[data-delete]')) {
        UI.confirm({ title: 'Delete this fave?', text: 'It disappears from your lists too. This can\'t be undone.', ok: 'Delete', danger: true })
          .then(function (y) { if (y) UI.api('delete_fave', F.id).then(function () { UI.toast('Deleted', 'ok'); UI.go('home'); }); });
        return;
      }
      if (t.closest('[data-ocr]')) { readText(t.closest('[data-ocr]')); return; }
      if (t.closest('[data-ai]')) { describe(t.closest('[data-ai]')); return; }
      if (t.closest('[data-copy-mine]')) {
        var lid = (F.lists || [])[0];
        UI.busy(t.closest('button'), UI.api('copy_member_item', lid, F.id)).then(function (r) { UI.toast(r.created ? 'Saved to your inbox' : 'Already in your faves', 'ok'); });
        return;
      }
      if (t.closest('[data-similar]')) { similar(t.closest('[data-similar]')); return; }
      var lp = t.closest('[data-loc-pick]');
      if (lp) { var p = JSON.parse(lp.getAttribute('data-loc-pick')); save({ lat: p.lat, lng: p.lng, address: p.address, osm: p.osm }).then(function () { UI.toast('Pinned on your map', 'ok'); }); }
    });
    function similar(btn) {
      var o = F.osm || {}, key = ['amenity', 'shop', 'tourism', 'leisure', 'craft', 'historic'].filter(function (k) { return o[k]; })[0];
      var recipe = key ? { filters: [[key, o[key]]].concat(o.cuisine ? [['cuisine', o.cuisine.split(';')[0]]] : []), prefer: [], cat: F.cat, label: 'Similar places' } : null;
      if (!recipe) { UI.toast('We don\'t know this place\'s type yet. Try Discover instead.', 'error'); return; }
      UI.busy(btn, UI.apiQuiet('taste').then(function (t) { return FB.data.placesLike(recipe, F, 1.5, t.saved); })).then(function (list) {
        var out = view.querySelector('[data-similar-out]');
        out.innerHTML = '<p class="muted small" style="margin-top:14px">' + UI.plural(list.length, 'place') + ' with ' + esc(recipe.filters.map(function (f) { return f[0] + '=' + f[1]; }).join(' + ')) + ' within 1.5 km (OpenStreetMap):</p>' +
          '<div class="fb-chips">' + list.slice(0, 12).map(function (p) { return '<button class="fb-chip" data-sim=\'' + esc(JSON.stringify({ title: p.title, lat: p.lat, lng: p.lng, address: p.address, osm: p.osm })) + '\'>' + UI.icon('plus') + esc(p.title) + ' <span class="n">' + FB.fmtDist(p.km) + '</span></button>'; }).join('') + '</div>';
        if (m) list.slice(0, 12).forEach(function (p) { new maplibregl.Marker({ element: FB.map.pinEl({ cat: F.cat, title: p.title }, { suggestion: true }), anchor: 'bottom' }).setLngLat([p.lng, p.lat]).addTo(m); });
        if (m && list.length) FB.map.fit(m, [F].concat(list.slice(0, 12)), 40);
      }, function () { UI.toast('OpenStreetMap search is busy right now. Try again in a minute.', 'error'); });
    }
    view.addEventListener('click', function (e) {
      var b = e.target.closest('[data-sim]'); if (!b) return;
      var p = JSON.parse(b.getAttribute('data-sim'));
      UI.busy(b, UI.api('save_fave', Object.assign({ kind: 'place', source: 'suggested' }, p))).then(function (r) { b.disabled = true; b.innerHTML = UI.icon('check') + esc(p.title); UI.toast((r.created ? 'Saved: ' : 'Already saved: ') + p.title, 'ok'); });
    });
    view.addEventListener('submit', function (e) {
      if (e.target.matches('[data-tagform]')) {
        e.preventDefault();
        var tag = e.target.tag.value.trim().replace(/^#/, '').toLowerCase(); if (!tag) return;
        save({ tags: (F.tags || []).concat([tag]) }).then(function () { var i = view.querySelector('[data-tagform] input'); if (i) i.focus(); });
      }
      if (e.target.matches('[data-locate]')) {
        e.preventDefault();
        FB.geo(false).then(function (g) { return UI.busy(e.target.querySelector('button'), FB.data.photon(e.target.q.value, g || { lat: 45.52, lng: -73.58 }, 6)); }).then(function (res) {
          view.querySelector('[data-locate-out]').innerHTML = res.length ? '<div class="fb-chips">' + res.map(function (p) {
            return '<button class="fb-chip" data-loc-pick=\'' + esc(JSON.stringify(p)) + '\'>' + UI.icon('pin') + esc(p.title) + ' <span class="n">' + esc(p.address) + '</span></button>'; }).join('') + '</div>' : '<p class="muted">No match. Try the street or neighbourhood.</p>';
        });
      }
    });
    view.addEventListener('focusout', function (e) {
      if (e.target.matches('[data-title]')) { var t = e.target.textContent.trim(); if (t && t !== F.title) save({ title: t }, false).then(function () { UI.toast('Renamed', 'ok'); }); }
      if (e.target.matches('[data-note]')) { var n = e.target.value; if (n !== (F.note || '')) save({ note: n }, false).then(function () { UI.toast('Note saved', 'ok'); }); }
    });
    view.addEventListener('keydown', function (e) { if (e.target.matches('[data-title]') && e.key === 'Enter') { e.preventDefault(); e.target.blur(); } });
    view.addEventListener('change', function (e) {
      if (!e.target.matches('[data-repic]') || !e.target.files[0]) return;
      FB.media.shrink(e.target.files[0]).then(function (s) { return UI.api('set_photo', F.id, s.dataUrl); }).then(function (r) { F = r.fave; draw(); UI.toast('Picture replaced', 'ok'); });
    });
    function load() {
      return Promise.all([FB.boot(), UI.api('get_fave', id)]).then(function (r) {
        F = r[1].fave; mine = r[1].mine; lists = r[1].lists || [];
        document.title = F.title + ' · ' + UI.config.name;
        draw();
      });
    }
    return { ready: load(), destroy: function () { alive = false; if (m) try { m.remove(); } catch (e) {} } };
  });
})();

/* ===== home.html ===== */
(function () {
  var esc = UI.esc;
  var KINDS = [['', 'Everything'], ['place', 'Places'], ['link', 'Links'], ['photo', 'Pictures'], ['note', 'Notes'], ['idea', 'Ideas']];
  var SORTS = [['new', 'Newest first'], ['old', 'Oldest first'], ['az', 'A to Z'], ['loved', 'Most loved'], ['soon', 'Coming up']];

  UI.page('home', { title: 'Your faves', nav: 'Faves', icon: 'heart', auth: 'user', order: 10 }, function (view, ctx) {
    var f = UI.store.get('home.filters', { status: 'kept' }), data = null, offset = 0, here = null;
    if (ctx.args[0] === 'cat' && ctx.args[1]) f = { status: 'kept', cat: ctx.args[1] };
    if (ctx.args[0] === 'tag' && ctx.args[1]) f = { status: 'kept', tag: ctx.args[1] };
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:90px"></div><div class="ui-skel" style="height:300px;margin-top:20px"></div></div>';

    function lists(d) {
      return '<div class="fb-section"><h2>Your lists</h2><a href="#lists" class="small">All lists →</a></div><div class="hm-row">' +
        d.lists.slice(0, 8).map(function (l) {
          return '<a class="hm-list" href="#list/' + esc(l.id) + '"><div class="top"><span class="em" style="background:color-mix(in srgb,' + esc(l.color || '#5b5bf0') + ' 18%,transparent)">' + esc(l.emoji || '⭐') + '</span>' +
            '<div><b>' + esc(l.name) + '</b><span class="muted small">' + UI.plural(l.count, 'fave') + (l.role !== 'owner' ? ' · shared by ' + esc(l.owner) : l.public ? ' · public link' : '') + '</span></div></div></a>';
        }).join('') + '<a class="hm-list new" href="#lists/new">' + UI.icon('plus') + '<span>New list</span></a></div>';
    }
    function filters(d) {
      var cats = FB.CATS.filter(function (c) { return d.counts[c.id]; });
      return '<div class="hm-filters">' +
        '<div class="hm-filter-row"><input type="search" data-q placeholder="Search titles, notes, text in pictures…" value="' + esc(f.q || '') + '">' +
        '<select data-kind aria-label="Kind">' + KINDS.map(function (k) { return '<option value="' + k[0] + '"' + ((f.kind || '') === k[0] ? ' selected' : '') + '>' + k[1] + '</option>'; }).join('') + '</select>' +
        '<select data-status aria-label="Status"><option value="kept"' + (f.status === 'kept' ? ' selected' : '') + '>Kept</option><option value="all"' + (f.status === 'all' ? ' selected' : '') + '>Kept + inbox</option><option value="archived"' + (f.status === 'archived' ? ' selected' : '') + '>Archived</option></select>' +
        '<select data-sort aria-label="Sort">' + SORTS.map(function (s) { return '<option value="' + s[0] + '"' + ((f.sort || 'new') === s[0] ? ' selected' : '') + '>' + s[1] + '</option>'; }).join('') + '</select></div>' +
        '<div class="fb-chips scroll" role="group" aria-label="Categories"><button class="fb-chip' + (!f.cat ? ' on' : '') + '" data-fcat="">All <span class="n">' + d.total_kept + '</span></button>' +
        cats.map(function (c) { return '<button class="fb-chip' + (f.cat === c.id ? ' on' : '') + '" data-fcat="' + c.id + '">' + c.emoji + ' ' + esc(c.name) + ' <span class="n">' + d.counts[c.id] + '</span></button>'; }).join('') + '</div>' +
        (d.tags.length ? '<div class="hm-tagcloud">' + d.tags.map(function (t) { return '<button class="fb-chip sm' + (f.tag === t[0] ? ' on' : ' flat') + '" data-ftag="' + esc(t[0]) + '">#' + esc(t[0]) + ' <span class="n">' + t[1] + '</span></button>'; }).join('') + '</div>' : '') +
        '</div>';
    }
    function welcome() {
      return '<div class="fb-panel hm-welcome" style="margin-top:22px"><div><h2>Let\'s gather your favourite things</h2>' +
        '<p class="muted">Everything you save lands in your inbox, already sorted into a category with the reason why. You confirm with one tap, and Faves Buddy learns how you like things filed.</p>' +
        '<div class="ui-row" style="margin-top:16px"><button class="ui-btn primary" data-samples>' + UI.icon('sparkle') + 'Load sample faves to explore</button>' +
        '<a class="ui-btn" href="#tools/import" data-go="tools/import">' + UI.icon('upload') + 'Import bookmarks</a></div></div>' +
        '<div class="hm-ways">' +
        '<div class="hm-way">' + UI.icon('puzzle') + '<div><b>Save tabs from Chrome</b><div class="muted small">One click for this tab, or the whole window at once. <a href="#tools" data-go="tools">Get the extension</a></div></div></div>' +
        '<div class="hm-way">' + UI.icon('pin') + '<div><b>Paste a Google Maps link</b><div class="muted small">It becomes a pin on your map, with the place\'s type and hours.</div></div></div>' +
        '<div class="hm-way">' + UI.icon('image') + '<div><b>Drop in screenshots</b><div class="muted small">The text in them is read on your device, so a poster becomes an event.</div></div></div>' +
        '<div class="hm-way">' + UI.icon('phone') + '<div><b>Tidy up on your phone</b><div class="muted small">Share a pile of tabs or screenshots from your phone and swipe through them. <a href="#tidy" data-go="tidy">How</a></div></div></div></div></div>';
    }
    function draw(d) {
      data = d;
      UI.setInbox(d.inbox);
      var first = esc(ctx.me.name.split(' ')[0]);
      var html = '<div class="ui-wrap"><div class="hm-hello"><div><h1>Hi ' + first + ' 👋</h1><p class="muted">' +
        (d.count_all ? UI.plural(d.total_kept, 'fave') + ' kept · ' + UI.plural(d.places, 'place') + ' on your map' + (d.week ? ' · ' + d.week + ' saved this week' : '') : 'Your collection starts here.') +
        '</p></div><div class="ui-row"><a class="ui-btn" href="#map" data-go="map">' + UI.icon('map') + 'Map</a><a class="ui-btn" href="#discover" data-go="discover">' + UI.icon('compass') + 'Discover</a></div></div>' +
        '<form class="hm-quick" data-quick><input type="text" name="q" placeholder="Paste a link or a Maps pin, or jot an idea…" data-ph-short="Link, Maps pin or idea…" autocomplete="off" aria-label="Save something">' +
        '<a class="ui-btn icon" href="#add/photo" data-go="add/photo" title="Add pictures" aria-label="Add pictures">' + UI.icon('camera') + '</a>' +
        '<button class="ui-btn primary" type="submit">' + UI.icon('plus') + 'Save</button></form>' +
        '<p class="hm-hint">Links are read and sorted for you. Plain text becomes a note (start with “idea:” for an idea).</p>' +
        '<div class="hm-tidy"><a class="ui-btn sm" href="#tidy/tabs" data-go="tidy/tabs">' + UI.icon('tabs') + 'Tidy my open tabs</a>' +
        '<a class="ui-btn sm" href="#tidy/shots" data-go="tidy/shots">' + UI.icon('image') + 'Sweep my screenshots</a></div>';
      if (d.inbox) html += '<a class="hm-inbox" href="#inbox"><span class="big">' + d.inbox + '</span><div class="grow"><b>' + (d.inbox === 1 ? 'thing is' : 'things are') + ' waiting in your inbox</b>' +
        '<div class="muted small">Already sorted with a suggestion each. Confirm them in a minute.</div></div><span class="ui-btn sm primary">Sort now ' + UI.icon('arrow') + '</span></a>';
      if (!d.count_all) { html += welcome() + '</div>'; view.innerHTML = html; return; }
      if (d.soon.length) html += '<div class="fb-section"><h2>Coming up</h2></div><div class="hm-row">' + d.soon.map(function (x) { return FB.card(x, { from: here }); }).join('') + '</div>';
      if (d.rediscover) html += '<div class="fb-section"><h2>Rediscover</h2><span class="muted small">Something you saved a while ago</span></div>' +
        '<div class="fb-panel hm-redis">' + FB.cover(d.rediscover) + '<div><h3 style="font-size:1.3rem">' + esc(d.rediscover.title) + '</h3><p class="muted">' + FB.catChip(d.rediscover.cat) +
        ' · saved ' + esc(UI.ago(d.rediscover.created)) + '</p>' + (d.rediscover.desc ? '<p>' + esc(d.rediscover.desc) + '</p>' : '') +
        '<div class="ui-row"><a class="ui-btn primary" href="#fave/' + esc(d.rediscover.id) + '">Open it</a><button class="ui-btn" data-archive-redis="' + esc(d.rediscover.id) + '">' + UI.icon('archive') + 'Not anymore</button></div></div></div>';
      html += lists(d);
      html += '<div class="fb-section"><h2>Everything you kept</h2><span class="muted small" data-total></span></div>' + filters(d) + '<div data-grid></div>';
      if (d.has_samples) html += '<p class="muted small" style="margin-top:24px">' + UI.icon('info') + ' Some faves are samples. Remove them anytime in <a href="#tools" data-go="tools">Tools</a>.</p>';
      html += '</div>';
      view.innerHTML = html;
      var qi = view.querySelector('[data-ph-short]'); if (qi && innerWidth < 520) qi.placeholder = qi.getAttribute('data-ph-short');
      grid(d.faves, d.total, d.more, false);
    }
    function grid(faves, total, more, append) {
      var g = view.querySelector('[data-grid]'); if (!g) return;
      var t = view.querySelector('[data-total]'); if (t) t.textContent = UI.plural(total, 'fave');
      if (!append) g.innerHTML = '';
      if (!faves.length && !append) {
        g.innerHTML = '<div class="ui-empty">' + UI.icon('search') + '<h3>Nothing matches</h3><p>Try another category or clear the search.</p></div>'; return;
      }
      var old = g.querySelector('[data-more]'); if (old) old.remove();
      var box = g.querySelector('.fb-grid');
      if (!box) { g.innerHTML = FB.grid(faves, { from: here }); box = g.querySelector('.fb-grid'); }
      else box.insertAdjacentHTML('beforeend', faves.map(function (x) { return FB.card(x, { from: here }); }).join(''));
      if (more) g.insertAdjacentHTML('beforeend', '<div class="ui-row" style="justify-content:center;margin-top:20px" data-more><button class="ui-btn" data-load-more>Show more</button></div>');
    }
    function refilter() {
      UI.store.set('home.filters', f); offset = 0;
      return UI.apiQuiet('list_faves', f, 0).then(function (r) { grid(r.faves, r.total, r.more, false); });
    }
    var qTimer = 0;
    view.addEventListener('input', function (e) {
      if (e.target.matches('[data-q]')) { clearTimeout(qTimer); qTimer = setTimeout(function () { f.q = e.target.value.trim(); refilter(); }, 300); }
    });
    view.addEventListener('change', function (e) {
      if (e.target.matches('[data-kind]')) { f.kind = e.target.value || null; refilter(); }
      if (e.target.matches('[data-status]')) { f.status = e.target.value; refilter(); }
      if (e.target.matches('[data-sort]')) { f.sort = e.target.value; refilter(); }
    });
    view.addEventListener('click', function (e) {
      var c = e.target.closest('[data-fcat]');
      if (c) { f.cat = c.getAttribute('data-fcat') || null; view.querySelectorAll('[data-fcat]').forEach(function (b) { b.classList.toggle('on', b === c); }); refilter(); return; }
      var t = e.target.closest('[data-ftag]');
      if (t) { var tag = t.getAttribute('data-ftag'); f.tag = f.tag === tag ? null : tag;
        view.querySelectorAll('[data-ftag]').forEach(function (b) { var on = b.getAttribute('data-ftag') === f.tag; b.classList.toggle('on', on); b.classList.toggle('flat', !on); }); refilter(); return; }
      if (e.target.closest('[data-load-more]')) {
        offset += 60;
        UI.busy(e.target.closest('button'), UI.apiQuiet('list_faves', f, offset)).then(function (r) { grid(r.faves, r.total, r.more, true); });
        return;
      }
      var s = e.target.closest('[data-samples]');
      if (s) { UI.busy(s, UI.api('load_samples')).then(function (r) { UI.toast(r.added + ' sample faves added. Have a look around!', 'ok'); load(); }); return; }
      var a = e.target.closest('[data-archive-redis]');
      if (a) { UI.api('triage', a.getAttribute('data-archive-redis'), 'archive').then(function () { UI.toast('Archived', 'ok'); load(); }); }
    });
    view.addEventListener('submit', function (e) {
      if (!e.target.matches('[data-quick]')) return;
      e.preventDefault();
      var v = e.target.q.value.trim();
      if (!v) return;
      if (/^(https?:\/\/|www\.)\S+$/i.test(v) || /^[\w-]+(\.[\w-]+)+\/\S*$/.test(v)) { UI.go('add', 'link', v); return; }
      var idea = /^idea\s*:/i.test(v), text = v.replace(/^(idea|note)\s*:\s*/i, '');
      UI.busy(e.target.querySelector('[type=submit]'), UI.api('save_fave', { title: text.slice(0, 120), note: text.length > 120 ? text : '', kind: idea ? 'idea' : 'note' }))
        .then(function (r) {
          var c = FB.cat(r.fave.cat);
          UI.toast('Saved to your inbox as ' + c.emoji + ' ' + c.name, 'ok');
          e.target.q.value = ''; load();
        });
    });
    FB.wireCards(view);
    function load() { return Promise.all([FB.boot(), UI.api('faves_home', f), FB.geo(false)]).then(function (r) { here = r[2]; draw(r[1]); }); }
    return load();
  });
})();

/* ===== inbox.html ===== */
(function () {
  var esc = UI.esc;

  UI.page('inbox', { title: 'Inbox', nav: 'Inbox', icon: 'inbox', auth: 'user', order: 20 }, function (view) {
    var items = [], focus = 0, pending = 0, startPending = 0, alive = true, lists = [];
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:70px"></div><div class="ui-skel" style="height:160px;margin-top:14px"></div></div>';

    function itemHtml(f) {
      var c = FB.cat(f.cat), conf = Math.round((f.conf || 0) * 100);
      var sub = f.domain ? UI.icon('globe') + '<span>' + esc(f.domain) + '</span>' : f.address ? UI.icon('pin') + '<span>' + esc(f.address) + '</span>' : UI.icon(FB.KIND_ICON[f.kind] || 'note') + '<span>' + esc(f.kind) + '</span>';
      return '<article class="ib-item" data-id="' + esc(f.id) + '" tabindex="-1">' + FB.cover(f) +
        '<div class="ib-main"><h3><a href="#fave/' + esc(f.id) + '">' + esc(f.title || 'Untitled') + '</a></h3><div class="fb-sub">' + sub +
        (f.tabset_name ? ' · <span>' + UI.icon('tabs') + esc(f.tabset_name) + '</span>' : '') + (f.saves > 1 ? ' · saved ' + f.saves + '×' : '') + '</div>' +
        (f.enriched ? '<div class="ib-sug"><span class="fb-chip on sm" style="pointer-events:none">' + c.emoji + ' ' + esc(c.name) + '</span>' +
          (f.cat !== 'other' ? '<span class="fb-conf" title="How sure: ' + conf + '%"><i style="width:' + conf + '%"></i></span><span class="muted small">' + (conf >= 70 ? 'Pretty sure' : conf >= 45 ? 'Likely' : 'A guess') + '</span>' : '<span class="muted small">Not sure yet: pick one</span>') + '</div>' +
          ((f.reasons || []).length ? '<div class="fb-why">Why: ' + f.reasons.slice(0, 3).map(function (r) { return '<span class="fb-tag">' + esc(r) + '</span>'; }).join('') + '</div>' : '')
          : '<div class="fb-why">' + UI.icon('refresh') + ' Reading this page…</div>') +
        aiHtml(f) +
        ((f.tags || []).length ? '<div class="fb-tags">' + f.tags.slice(0, 5).map(function (t) { return '<span class="fb-tag">#' + esc(t) + '</span>'; }).join('') + '</div>' : '') +
        '<div class="ib-actions"><button class="ui-btn primary sm" data-keep>' + UI.icon('check') + '<span class="lbl">Keep' + (f.cat !== 'other' ? ' as ' + esc(c.name) : '') + '</span></button>' +
        '<button class="ui-btn sm" data-change>' + UI.icon('tag') + '<span class="lbl">Change</span></button>' +
        '<button class="ui-btn sm icon" data-lists title="Add to lists" aria-label="Add to lists">' + UI.icon('grid') + '</button>' +
        '<button class="ui-btn sm icon" data-snooze title="Remind me later" aria-label="Remind me later">' + UI.icon('snooze') + '</button>' +
        '<button class="ui-btn sm icon" data-archive title="Archive" aria-label="Archive">' + UI.icon('archive') + '</button>' +
        '<button class="ui-btn sm icon danger" data-delete title="Delete" aria-label="Delete">' + UI.icon('trash') + '</button>' +
        (f.url ? '<a class="ui-btn sm ghost" href="' + esc(f.url) + '" target="_blank" rel="noopener">' + UI.icon('external') + '<span class="lbl">Open</span></a>' : '') +
        '</div><div data-picker hidden></div></div></article>';
    }
    function aiHtml(f) {
      var a = f.meta && f.meta.ai_sort;
      if (!a || !a.cat || a.cat === f.cat) return '';
      var c = FB.cat(a.cat);
      return '<div class="ib-ai">' + UI.icon('sparkle') + '<span><b>AI suggests ' + esc(c.emoji + ' ' + c.name) + '</b>' + (a.why ? ': ' + esc(a.why) : '') + '</span>' +
        '<button class="ui-btn sm" data-ai-use>Use this</button></div>';
    }
    function askAI() {
      if (!alive || !(FB.aiSort && FB.aiSort.available && FB.aiSort.on)) return;
      var unsure = items.filter(function (f) { return f.enriched && !f.confirmed && f.conf < 0.55 && !(f.meta && f.meta.ai_sort); });
      if (!unsure.length || pending) return;
      UI.apiQuiet('ai_second_opinion').then(function (r) {
        if (!alive) return;
        r.faves.forEach(function (f) {
          var i = items.findIndex(function (x) { return x.id === f.id; });
          var el = view.querySelector('.ib-item[data-id="' + CSS.escape(f.id) + '"]');
          if (i >= 0 && el) { items[i] = f; el.outerHTML = itemHtml(f); }
        });
      }).catch(function (err) { console.warn('AI second opinion:', err && err.message); });
    }
    function draw(d) {
      items = d.faves; lists = d.lists || []; pending = d.pending; startPending = Math.max(startPending, d.pending);
      UI.setInbox(d.total);
      var confident = items.filter(function (f) { return f.enriched && f.conf >= 0.6 && f.cat !== 'other'; }).length;
      view.innerHTML = '<div class="ui-wrap"><div class="ib-head"><div><h1>Inbox</h1><p class="muted" style="margin:4px 0 0">' +
        (d.total ? UI.plural(d.total, 'thing') + ' to sort' : 'Nothing to sort') + (d.snoozed ? ' · ' + d.snoozed + ' snoozed' : '') + '</p></div>' +
        (confident > 1 ? '<button class="ui-btn primary" data-accept>' + UI.icon('sparkle') + 'Keep the ' + confident + ' sure ones</button>' : '') + '</div>' +
        '<div data-progress></div>' +
        (items.length ? '<p class="ib-keys">Keys: <kbd>J</kbd>/<kbd>K</kbd> move · <kbd>Enter</kbd> keep · <kbd>A</kbd> archive · <kbd>S</kbd> snooze · <kbd>Del</kbd> delete</p>' +
          '<div class="ib-list">' + items.map(itemHtml).join('') + '</div>'
          : '<div class="ib-zero fb-panel"><div class="big">🎉</div><h2>Inbox zero</h2><p class="muted">Everything is sorted. New tabs, pins and screenshots you save will show up here.</p>' +
            '<div class="ui-row" style="justify-content:center"><a class="ui-btn primary" href="#add" data-go="add">' + UI.icon('plus') + 'Save something</a><a class="ui-btn" href="#home" data-go="home">See your faves</a></div></div>') + '</div>';
      setFocus(0, true);
      progress();
      if (pending) enrichLoop(); else askAI();
    }
    function progress() {
      var el = view.querySelector('[data-progress]'); if (!el) return;
      if (!pending) { el.innerHTML = ''; return; }
      var done = startPending - pending, pct = startPending ? Math.round(done / startPending * 100) : 0;
      el.innerHTML = '<div class="ib-progress">' + UI.icon('refresh') + '<span>Reading ' + UI.plural(pending, 'saved page') + '…</span><span class="bar"><i style="width:' + pct + '%"></i></span></div>';
    }
    function enrichLoop() {
      if (!alive || !pending) return;
      UI.apiQuiet('enrich_pending', 4).then(function (r) {
        if (!alive) return;
        pending = r.left;
        r.done.forEach(function (f) {
          var i = items.findIndex(function (x) { return x.id === f.id; });
          var el = view.querySelector('.ib-item[data-id="' + CSS.escape(f.id) + '"]');
          if (i >= 0 && el) { items[i] = f; el.outerHTML = itemHtml(f); }
        });
        progress();
        if (pending) setTimeout(enrichLoop, 300); else askAI();
      }, function () { pending = 0; progress(); });
    }
    function setFocus(i, quiet) {
      var els = view.querySelectorAll('.ib-item');
      if (!els.length) return;
      focus = Math.max(0, Math.min(els.length - 1, i));
      els.forEach(function (el, j) { el.classList.toggle('focus', j === focus && !quiet); });
      if (!quiet) { els[focus].focus({ preventScroll: true }); els[focus].scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
    }
    function remove(id, msg) {
      var el = view.querySelector('.ib-item[data-id="' + CSS.escape(id) + '"]');
      items = items.filter(function (x) { return x.id !== id; });
      UI.setInbox(items.length);
      if (msg) UI.toast(msg, 'ok');
      if (!el) return;
      el.classList.add('gone');
      setTimeout(function () {
        el.remove();
        if (!view.querySelector('.ib-item')) { confetti(); load(); }
        else setFocus(focus, true);
      }, 260);
    }
    function confetti() {
      var box = document.createElement('div'); box.className = 'ib-confetti';
      var colors = ['#5b5bf0', '#ff6f61', '#ffb300', '#26a69a', '#ec407a', '#42a5f5'];
      for (var i = 0; i < 70; i++) {
        var p = document.createElement('i');
        p.style.left = Math.random() * 100 + 'vw'; p.style.background = colors[i % colors.length];
        p.style.animationDelay = Math.random() * .6 + 's'; p.style.animationDuration = 1.8 + Math.random() * 1.4 + 's';
        box.appendChild(p);
      }
      document.body.appendChild(box); setTimeout(function () { box.remove(); }, 3600);
    }
    function act(id, action, cat) {
      var f = items.filter(function (x) { return x.id === id; })[0];
      if (action === 'keep') return UI.api('triage', id, 'keep', cat || null).then(function () { var c = FB.cat(cat || f.cat); remove(id, 'Kept in ' + c.emoji + ' ' + c.name); });
      if (action === 'archive') return UI.api('triage', id, 'archive').then(function () { remove(id, 'Archived'); });
      if (action === 'delete') return UI.api('triage', id, 'delete').then(function () { remove(id, 'Deleted'); });
      if (action === 'snooze') return FB.snoozeModal(id).then(function (r) { if (r) remove(id); });
    }
    view.addEventListener('click', function (e) {
      if (e.target.closest('[data-accept]')) {
        var b = e.target.closest('[data-accept]');
        UI.busy(b, UI.api('accept_confident', 0.6)).then(function (r) { UI.toast(UI.plural(r.kept, 'fave') + ' kept with their suggested category', 'ok'); if (r.kept) confetti(); load(); });
        return;
      }
      var card = e.target.closest('.ib-item'); if (!card) return;
      var id = card.getAttribute('data-id');
      focus = Array.prototype.indexOf.call(view.querySelectorAll('.ib-item'), card);
      var pickCat = e.target.closest('[data-cat]');
      if (pickCat) { act(id, 'keep', pickCat.getAttribute('data-cat')); return; }
      if (e.target.closest('[data-ai-use]')) {
        UI.busy(e.target.closest('button'), UI.api('ai_use', id)).then(function (r) { var c = FB.cat(r.fave.cat); remove(id, 'Kept in ' + c.emoji + ' ' + c.name); });
        return;
      }
      if (e.target.closest('[data-keep]')) { UI.busy(e.target.closest('button'), act(id, 'keep')); return; }
      if (e.target.closest('[data-archive]')) { act(id, 'archive'); return; }
      if (e.target.closest('[data-snooze]')) { act(id, 'snooze'); return; }
      if (e.target.closest('[data-delete]')) { act(id, 'delete'); return; }
      if (e.target.closest('[data-change]')) {
        var p = card.querySelector('[data-picker]'), f = items.filter(function (x) { return x.id === id; })[0];
        p.hidden = !p.hidden;
        if (!p.hidden) p.innerHTML = '<div class="ib-pick"><p class="small muted" style="margin:0 0 10px">Where does it belong? Faves Buddy will remember for next time.</p>' + FB.catPicker(f.cat) + '</div>';
        return;
      }
      if (e.target.closest('[data-lists]')) {
        var fv = items.filter(function (x) { return x.id === id; })[0];
        FB.listsModal(fv, lists, []).then(function (nf) { if (nf && nf.status === 'kept') remove(id); });
      }
    });
    function onKey(e) {
      if (UI.current().name !== 'inbox' || document.querySelector('.ui-modal-wrap') || /input|textarea|select/i.test(e.target.tagName)) return;
      var els = view.querySelectorAll('.ib-item'); if (!els.length) return;
      var id = els[focus] && els[focus].getAttribute('data-id');
      var k = e.key.toLowerCase();
      if (k === 'j' || k === 'arrowdown') { e.preventDefault(); setFocus(focus + 1); }
      else if (k === 'k' || k === 'arrowup') { e.preventDefault(); setFocus(focus - 1); }
      else if (k === 'enter' && id) { e.preventDefault(); act(id, 'keep'); }
      else if (k === 'a' && id) act(id, 'archive');
      else if (k === 's' && id) act(id, 'snooze');
      else if ((k === 'delete' || k === 'backspace') && id) act(id, 'delete');
    }
    document.addEventListener('keydown', onKey);
    function load() { return Promise.all([FB.boot(), UI.api('inbox')]).then(function (r) { draw(r[1]); }); }
    return { ready: load(), destroy: function () { alive = false; document.removeEventListener('keydown', onKey); } };
  });
})();

/* ===== landing.html ===== */
// Watch section: swap the video's cover for YouTube's player (privacy-enhanced) only when it's pressed.
  if (!window.__ytFilm) {
    window.__ytFilm = true;
    document.addEventListener('click', function (e) {
      var b = e.target && e.target.closest ? e.target.closest('[data-yt-film]') : null;
      if (!b) return;
      var f = document.createElement('iframe');
      f.src = 'https://www.youtube-nocookie.com/embed/' + b.getAttribute('data-yt-film') + '?autoplay=1&rel=0&playsinline=1';
      f.title = b.getAttribute('data-yt-title') || 'Video';
      f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
      f.allowFullscreen = true;
      f.referrerPolicy = 'strict-origin-when-cross-origin';
      b.parentNode.replaceChild(f, b);
    });
  }
(function () {
  var COPY = {
    eyebrow: 'Your favourite things, sorted',
    title: 'Tame the tabs, pins and <em>screenshots</em> you swore you’d come back to',
    lead: 'Save from anywhere: a Chrome tab (or forty), a Google Maps pin, a poster you snapped, a passing idea. Faves Buddy files each one for you, shows what’s near you on a map, and finds more of what you love.',
    cta: 'Start my collection, free',
    proof: ['Sorts without AI', 'Your data stays yours', 'Works on your phone'],
    stepsTitle: 'From chaos to “oh, that place!”',
    stepsLead: 'Three moves. The middle one happens by itself.',
    steps: [['💾', 'Save from anywhere', 'The Chrome extension saves this tab or the whole window. Paste a Maps link, drop screenshots, or jot an idea. Import your old bookmarks, OneTab or Pocket.'],
            ['🗂️', 'It sorts itself, and says why', 'Each fave lands in your inbox already filed: “Recipe, because the page is a recipe”, “Café, because OpenStreetMap says so”. Confirm with one tap. It learns how you file things.'],
            ['📍', 'Find it when it matters', 'See what’s around you and open now, what’s coming up this weekend, and fresh suggestions like your favourites. Share a list with a link.']],
    featuresTitle: 'Everything your favourites need',
    features: [['puzzle', 'One-click Chrome extension', 'Save a tab, a link, a picture or selected text. Save a whole window as a tab set and close it with peace of mind.'],
               ['inbox', 'An inbox that sorts itself', 'Twenty categories, from cafés to recipes to gift ideas. Every suggestion shows its reasons and a confidence bar.'],
               ['map', 'Your map, near you', 'Every place on one map, nearest first, with “open now” from real opening hours. Directions in a tap.'],
               ['image', 'Screenshots that read themselves', 'Text in pictures is read right on your device. A poster becomes an event, a menu becomes a restaurant.'],
               ['compass', 'Discover more of what you love', 'Precise searches in OpenStreetMap, Wikipedia and Wikidata, built from your taste. You see exactly what was searched.'],
               ['share', 'Lists you can share', 'A public link for anyone, or invite friends by email to view or add their own finds.'],
               ['wand', 'Bring your own AI (optional)', 'Add your own Anthropic key to have pictures described. The key stays in your browser.'],
               ['upload', 'Bring everything in, take it out', 'Import bookmarks, OneTab, Pocket and Google Maps saved places. Export to JSON, CSV, GeoJSON or bookmarks anytime.'],
               ['lock', 'Private by default', 'Your faves are only yours until you share a list. No ads, no selling data, no tracking.']],
    faq: [['Is it free?', 'Yes. Faves Buddy is free. The optional extras that cost money are paid by you directly to those services (an Anthropic API key for AI descriptions, usually a fraction of a cent per picture). Ticketmaster’s event key is free.'],
          ['Do you use AI to sort my things?', 'No. Sorting uses clear rules: what the page says about itself (schema.org, page type), the website, OpenStreetMap’s description of a place, and keywords in English and French. Then it learns from the choices you make. AI is optional, only for describing pictures, and only with your own key.'],
          ['What happens to my screenshots?', 'They’re shrunk on your device and stored in your account. The text in them is read on your device with an open-source reader (Tesseract). Nothing goes to an AI unless you add your own key and ask for it.'],
          ['Where do suggestions come from?', 'From open data: OpenStreetMap (places), Wikipedia (articles, places nearby) and Wikidata (festivals). With your own free key, Ticketmaster for dated events. Searches run only when you tap.'],
          ['Do you track my location?', 'No. Your browser asks before sharing your location, and it’s only used on the page you’re on to show distances. If you choose a home spot, only that spot is saved.'],
          ['Which browsers does the extension work in?', 'Chrome and Chromium browsers (Edge, Brave, Arc, Opera). On other browsers and phones, use the bookmarklet, paste links, or share screenshots into the app.'],
          ['Can I get my data out?', 'Anytime, in four formats: JSON (everything), CSV, GeoJSON (your places) and a bookmarks file any browser can import.']],
    bandTitle: 'Close those 40 tabs tonight.',
    bandLead: 'They’ll be waiting for you, sorted, on your map.'
  };

  // The hero map: a made-up city corner (gentle street grid, a park, a river) with your faves pinned by kind.
  // Pins sit right of the card on desktop, across the top on phones.
  function heroArt() {
    var streets = '', i;
    for (i = -6; i < 22; i++) streets += '<path d="M' + (i * 130) + ' -200 L' + (i * 130 + 240) + ' 900"/>';
    for (i = -4; i < 14; i++) streets += '<path d="M-300 ' + (i * 96) + ' L1600 ' + (i * 96 - 120) + '"/>';
    var map = '<div class="lh-mapbg" aria-hidden="true"><svg viewBox="0 0 1280 640" preserveAspectRatio="xMidYMid slice">' +
      '<rect width="1280" height="640" fill="var(--land)"/>' +
      '<path d="M1140 -20 C1100 160 1210 300 1150 460 S1180 600 1220 680 L1300 680 L1300 -20 Z" fill="var(--water)"/>' +
      '<path d="M800 380 C860 340 960 350 990 410 C1010 470 940 520 860 510 C800 500 760 430 800 380 Z" fill="var(--park)"/>' +
      '<g stroke="var(--casing)" stroke-width="15" fill="none">' + streets + '</g>' +
      '<g stroke="var(--street)" stroke-width="10" fill="none">' + streets + '</g>' +
      '<path d="M500 -40 C700 200 900 260 1300 300" stroke="var(--casing)" stroke-width="24" fill="none"/><path d="M500 -40 C700 200 900 260 1300 300" stroke="var(--street)" stroke-width="18" fill="none"/>' +
      '<g fill="var(--label)" font-family="inherit" font-size="13" font-weight="700" letter-spacing="2"><text x="836" y="450">PARK</text><text x="1180" y="120" transform="rotate(80 1180 120)">RIVER</text></g>' +
      '</svg></div>';
    var pins = [['☕', '#b08968', 64, 30, 1], ['🍜', '#ff8a65', 78, 22, 0], ['🌳', '#66bb6a', 69, 66, 0], ['🎟️', '#ffb300', 90, 38, 0], ['📖', '#42a5f5', 86, 70, 1],
                ['🧑‍🍳', '#ef5350', 58, 52, 0], ['🖼️', '#ab47bc', 95, 18, 0]];
    return map + '<div class="lh-pins" aria-hidden="true"><span class="lh-me" style="left:76%;top:46%"></span>' +
      pins.map(function (p, n) { return '<span class="lh-pin' + (p[4] ? ' open' : '') + '" style="--p:' + p[1] + ';left:' + p[2] + '%;top:' + p[3] + '%;animation-delay:' + (n * .1) + 's"><span>' + p[0] + '</span></span>'; }).join('') +
      '<div class="lh-pop" style="left:64%;top:30%"><b>Café Olimpico</b><span class="ok">● Open now</span> · 300 m · saved from a tab in March</div></div>' +
      '<div class="lh-saved" aria-hidden="true"><span class="ic">🗂️</span><span>maps.app.goo.gl/x7…<small>Filed as <b>Restaurant</b>, because OpenStreetMap says so</small></span></div>';
  }

  UI.page('landing', { title: 'Your favourite things, sorted' }, function (view, ctx) {
    var me = ctx.me, C = COPY, esc = UI.esc;
    var primary = me ? '<a class="ui-btn primary lg" href="#home" data-go="home">Open my faves ' + UI.icon('arrow') + '</a>'
      : '<a class="ui-btn primary lg" href="#auth/signup" data-go="auth/signup">' + esc(C.cta) + ' ' + UI.icon('arrow') + '</a>' +
        '<a class="ui-btn lg" href="#auth" data-go="auth">I have an account</a>';
    view.innerHTML =
      '<section class="lp-hero">' + heroArt() + '<div class="ui-wrap"><div class="lh-card">' +
        '<div class="eyebrow">' + esc(C.eyebrow) + '</div><h1>' + C.title + '</h1><p class="lp-lead">' + esc(C.lead) + '</p>' +
        '<div class="lp-cta">' + primary + '</div>' +
        '<div class="lp-proof">' + C.proof.map(function (p) { return '<span>' + UI.icon('check') + esc(p) + '</span>'; }).join('') + '</div>' +
      '</div></div></section>' +
      '<section class="lp-section ytf" id="watch"><div class="ui-wrap"><div class="ytf-in"><div class="ytf-copy"><div class="eyebrow"><svg viewBox="0 0 28 20" width="20" height="14" aria-hidden="true"><rect width="28" height="20" rx="5" fill="#FF0033"/><path d="M11.2 5.8v8.4l7.3-4.2z" fill="#fff"/></svg>Watch</div><h2>See Faves Buddy in about a minute</h2><p>A short video tour of what Faves Buddy does and how it works.</p><a class="ytf-link" href="https://www.youtube.com/watch?v=LKq6NHGjgdc" target="_blank" rel="noopener">Watch on YouTube &#8599;</a></div><div><div class="ytf-frame"><button type="button" class="ytf-cover" data-yt-film="LKq6NHGjgdc" data-yt-title="Faves Buddy video" aria-label="Play the Faves Buddy video (1:15)"><img src="_/theme/yt-cover.jpg" alt="" loading="lazy" decoding="async" width="960" height="540"><span class="ytf-play" aria-hidden="true"><svg viewBox="0 0 68 48" width="68" height="48"><path d="M66.5 7.7a8.5 8.5 0 0 0-6-6C55.3.3 34 .3 34 .3s-21.3 0-26.5 1.4a8.5 8.5 0 0 0-6 6C.1 13 .1 24 .1 24s0 11 1.4 16.3a8.5 8.5 0 0 0 6 6c5.2 1.4 26.5 1.4 26.5 1.4s21.3 0 26.5-1.4a8.5 8.5 0 0 0 6-6C67.9 35 67.9 24 67.9 24s0-11-1.4-16.3z" fill="#FF0033"/><path d="M45 24 27 14v20z" fill="#fff"/></svg></span><span class="ytf-len">1:15</span></button></div><p class="ytf-note">The video loads from YouTube when you press play.</p></div></div></div></section>' +
      '<section class="lp-section" id="how"><div class="ui-wrap"><div class="lp-head"><h2>' + esc(C.stepsTitle) + '</h2><p>' + esc(C.stepsLead) + '</p></div>' +
        '<div class="lp-steps">' + C.steps.map(function (s) { return '<div class="ui-card lp-step"><span class="em">' + s[0] + '</span><h3>' + esc(s[1]) + '</h3><p class="muted">' + esc(s[2]) + '</p></div>'; }).join('') + '</div></div></section>' +
      '<section class="lp-section"><div class="ui-wrap"><div class="lp-head"><h2>' + esc(C.featuresTitle) + '</h2></div>' +
        '<div class="ui-grid lp-feats">' + C.features.map(function (f) { return '<div class="ui-card lp-feature"><span class="fi">' + UI.icon(f[0]) + '</span><h3>' + esc(f[1]) + '</h3><p>' + esc(f[2]) + '</p></div>'; }).join('') + '</div></div></section>' +
      '<section class="lp-section" data-peek hidden><div class="ui-wrap"><div class="lp-head"><h2>Peek at a shared list</h2><p>This is what a list looks like when someone shares it with a link. (Made-up places, real map.)</p></div><div class="lp-lists" data-peek-lists></div></div></section>' +
      '<section class="lp-section"><div class="ui-wrap"><div class="lp-head"><h2>Questions</h2></div><div class="lp-faq">' +
        C.faq.map(function (q) { return '<details><summary>' + esc(q[0]) + '</summary><p>' + esc(q[1]) + '</p></details>'; }).join('') + '</div></div></section>' +
      '<section class="lp-section"><div class="ui-wrap"><div class="lp-band"><div><h2>' + esc(C.bandTitle) + '</h2><p>' + esc(C.bandLead) + '</p></div>' +
        (me ? '<a class="ui-btn lg" href="#home" data-go="home">Open my faves</a>' : '<a class="ui-btn lg" href="#auth/signup" data-go="auth/signup">' + esc(C.cta) + '</a>') +
      '</div></div></section>';
    return UI.apiQuiet('featured_lists').then(function (d) {
      FB.setCats(d.cats);
      if (!d.lists.length) return;
      view.querySelector('[data-peek]').hidden = false;
      view.querySelector('[data-peek-lists]').innerHTML = d.lists.map(function (l) {
        return '<a class="lp-list" href="#s/' + esc(l.token) + '"><span class="em" style="background:color-mix(in srgb,' + esc(l.color) + ' 20%,var(--c-bg))">' + esc(l.emoji) + '</span>' +
          '<div><b>' + esc(l.name) + '</b><span class="muted small">' + UI.plural(l.count, 'fave') + ' · by ' + esc(l.owner) + '</span></div><span class="ui-spacer"></span>' + UI.icon('arrow') + '</a>';
      }).join('');
    }, function () {});
  });
})();

/* ===== lists.html ===== */
(function () {
  var esc = UI.esc;

  function mosaic(l) {
    var p = (l.preview || []).slice(0, 3), tint = 'color-mix(in srgb,' + esc(l.color) + ' 22%,var(--c-surface-2))';
    var cells = [0, 1, 2].map(function (i) {
      return p[i] ? '<div style="background-image:url(\'' + esc(p[i]) + '\')"></div>'
        : '<div class="ph" style="background:' + tint + '">' + (i === 0 ? esc(l.emoji) : '') + '</div>';
    });
    return '<div class="ls-mosaic">' + cells.join('') + '</div>';
  }
  function tile(l) {
    return '<a class="ls-tile" href="#list/' + esc(l.id) + '">' + mosaic(l) + '<div class="top"><span class="em" style="background:color-mix(in srgb,' + esc(l.color) + ' 18%,transparent)">' + esc(l.emoji) + '</span>' +
      '<div style="min-width:0"><b>' + esc(l.name) + '</b><span class="muted small">' + UI.plural(l.count, 'fave') +
      (l.role !== 'owner' ? ' · by ' + esc(l.owner) + ' · ' + (l.role === 'editor' ? 'you can add' : 'view only') : (l.public ? ' · 🔗 public' : '') + (l.members_n ? ' · shared with ' + l.members_n : '')) + '</span></div></div></a>';
  }
  /* Create / edit a list. Resolves with the saved list or null. */
  function editModal(l, emojis, colors) {
    l = l || { name: '', emoji: emojis[0], color: colors[0], description: '' };
    var st = { emoji: l.emoji, color: l.color };
    return new Promise(function (resolve) {
      var done = false;
      var m = UI.modal('<h2>' + (l.id ? 'Edit list' : 'New list') + '</h2><form class="ui-stack" data-f>' +
        '<label class="ui-field"><span>Name</span><input type="text" name="name" maxlength="60" required value="' + esc(l.name) + '" placeholder="e.g. Brunch spots, Rainy day ideas"></label>' +
        '<div class="ui-field"><span>Emoji</span><div class="ls-emojis">' + emojis.map(function (e) { return '<button type="button" data-e="' + esc(e) + '" class="' + (e === st.emoji ? 'on' : '') + '">' + esc(e) + '</button>'; }).join('') + '</div></div>' +
        '<div class="ui-field"><span>Colour</span><div class="ls-colors">' + colors.map(function (c) { return '<button type="button" data-c="' + c + '" class="' + (c === st.color ? 'on' : '') + '" style="background:' + c + '" aria-label="' + c + '"></button>'; }).join('') + '</div></div>' +
        '<label class="ui-field"><span>Description <em>(optional)</em></span><textarea name="description" maxlength="400" rows="3">' + esc(l.description || '') + '</textarea></label>' +
        '<div class="ui-row end"><button type="button" class="ui-btn ghost" data-close>Cancel</button><button class="ui-btn primary" type="submit">' + (l.id ? 'Save' : 'Create list') + '</button></div></form>',
        { onclose: function () { if (!done) resolve(null); } });
      m.el.addEventListener('click', function (e) {
        var b = e.target.closest('[data-e]'); if (b) { st.emoji = b.getAttribute('data-e'); m.el.querySelectorAll('[data-e]').forEach(function (x) { x.classList.toggle('on', x === b); }); }
        var c = e.target.closest('[data-c]'); if (c) { st.color = c.getAttribute('data-c'); m.el.querySelectorAll('[data-c]').forEach(function (x) { x.classList.toggle('on', x === c); }); }
      });
      m.el.querySelector('[data-f]').addEventListener('submit', function (e) {
        e.preventDefault();
        var v = UI.formData(e.target);
        UI.busy(e.target.querySelector('[type=submit]'), UI.api('save_list', l.id || null, { name: v.name, description: v.description, emoji: st.emoji, color: st.color }))
          .then(function (r) { done = true; m.close(); resolve(r.list); });
      });
    });
  }

  UI.page('lists', { title: 'Lists', nav: 'Lists', icon: 'grid', auth: 'user', order: 50 }, function (view, ctx) {
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:240px"></div></div>';
    var data = null;
    function draw(d) {
      data = d;
      view.innerHTML = '<div class="ui-wrap"><div class="ui-page-head"><div><h1>Lists</h1><p class="muted">Group faves your way, then share them with a link or with people.</p></div>' +
        '<button class="ui-btn primary" data-new>' + UI.icon('plus') + 'New list</button></div>' +
        '<div class="ls-grid">' + d.mine.map(tile).join('') + '<button class="ls-tile ls-new" data-new>' + UI.icon('plus') + '<span>New list</span></button></div>' +
        (d.shared.length ? '<div class="fb-section"><h2>Shared with you</h2></div><div class="ls-grid">' + d.shared.map(tile).join('') + '</div>' : '') + '</div>';
    }
    view.addEventListener('click', function (e) {
      if (e.target.closest('[data-new]')) editModal(null, data.emojis, data.colors).then(function (l) { if (l) UI.go('list', l.id); });
    });
    return UI.api('my_lists').then(function (d) {
      draw(d);
      if (ctx.args[0] === 'new') editModal(null, d.emojis, d.colors).then(function (l) { if (l) UI.go('list', l.id); });
    });
  });

  UI.page('list', { title: 'List', auth: 'user' }, function (view, ctx) {
    var id = ctx.args[0], L = null, addable = [], emojis = [], colors = [], m = null, alive = true;
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:120px"></div><div class="ui-skel" style="height:300px;margin-top:16px"></div></div>';

    function draw() {
      var own = L.role === 'owner', edit = own || L.role === 'editor', places = L.items.filter(function (f) { return f.lat != null; });
      view.innerHTML = '<div class="ui-wrap"><a href="#lists" class="small">' + UI.icon('back') + ' All lists</a>' +
        '<div class="lv-head" style="margin-top:14px"><span class="em" style="background:color-mix(in srgb,' + esc(L.color) + ' 20%,var(--c-bg))">' + esc(L.emoji) + '</span>' +
        '<div><h1>' + esc(L.name) + '</h1><p class="muted" style="margin:4px 0 0">' + UI.plural(L.count, 'fave') + (own ? '' : ' · by ' + esc(L.owner) + ' · you can ' + (edit ? 'add and remove' : 'view')) +
        (L.public ? ' · 🔗 anyone with the link can view' : '') + '</p>' + (L.description ? '<p style="margin:8px 0 0">' + esc(L.description) + '</p>' : '') + '</div>' +
        '<div class="ui-row acts">' + (edit ? '<button class="ui-btn primary" data-add>' + UI.icon('plus') + 'Add faves</button>' : '') +
        (own ? '<button class="ui-btn" data-share>' + UI.icon('share') + 'Share</button><button class="ui-btn icon" data-edit title="Edit" aria-label="Edit list">' + UI.icon('edit') + '</button>' +
          '<button class="ui-btn icon danger" data-delete title="Delete list" aria-label="Delete list">' + UI.icon('trash') + '</button>'
          : '<button class="ui-btn" data-leave>' + UI.icon('logout') + 'Leave</button>') + '</div></div>' +
        (places.length ? '<div class="lv-map" data-map></div>' : '') +
        (L.items.length ? FB.grid(L.items, { actions: function (f) {
          return (!f.mine ? '<button class="ui-btn sm" data-copy="' + esc(f.id) + '">' + UI.icon('heart') + 'Save to mine</button>' : '') +
            (f.can_remove ? '<button class="ui-btn sm ghost" data-remove="' + esc(f.id) + '">' + UI.icon('x') + 'Remove</button>' : '');
        }, noStage: true }) : '<div class="ui-empty">' + UI.icon('grid') + '<h3>This list is empty</h3><p>' + (edit ? 'Add faves to it here, or from any fave\'s page.' : 'Nothing here yet.') + '</p></div>') + '</div>';
      if (places.length) {
        FB.map.make(view.querySelector('[data-map]'), { center: places[0], zoom: 13, cooperative: true }).then(function (map) {
          if (!map || !alive) return;
          m = map;
          places.forEach(function (f) {
            new maplibregl.Marker({ element: FB.map.pinEl(f), anchor: 'bottom' }).setLngLat([f.lng, f.lat])
              .setPopup(new maplibregl.Popup({ offset: 26 }).setHTML(FB.map.popup(f, '<a class="ui-btn sm primary" href="#fave/' + esc(f.id) + '">Open</a>'))).addTo(m);
          });
          FB.map.fit(m, places, 40);
        });
      }
    }
    function shareModal() {
      var mm = UI.modal('<h2>Share “' + esc(L.name) + '”</h2><div data-share-body></div>', { wide: true });
      function body() {
        var link = L.public && L.token ? FB.appUrl('#s/' + L.token) : '';
        mm.el.querySelector('[data-share-body]').innerHTML =
          '<div class="ui-card flat" style="--neu-bg:var(--c-surface)"><div class="ui-row between"><div><b>Public link</b><div class="muted small">Anyone with the link can see this list. No sign-in needed. Notes and emails stay private.</div></div>' +
          '<label class="ui-check"><input type="checkbox" data-public' + (L.public ? ' checked' : '') + '> On</label></div>' +
          (link ? '<div class="ui-row" style="margin-top:12px"><input type="text" readonly value="' + esc(link) + '" style="flex:1;min-width:0"><button class="ui-btn" data-copy-link>' + UI.icon('copy') + 'Copy</button></div>' : '') + '</div>' +
          '<div class="ui-card flat" style="margin-top:14px;--neu-bg:var(--c-surface)"><b>Invite people</b><div class="muted small">They\'ll see it under “Shared with you” when they sign in with that email. Editors can add their own faves.</div>' +
          '<form class="ui-row" data-invite style="margin-top:12px"><input type="email" name="email" placeholder="friend@example.com" required style="flex:1;min-width:180px">' +
          '<select name="role" style="width:auto"><option value="viewer">Can view</option><option value="editor">Can add</option></select><button class="ui-btn primary" type="submit">Invite</button></form>' +
          '<div class="lv-members" style="margin-top:14px">' + (L.members.length ? L.members.map(function (p) {
            return '<div class="lv-member" data-mid="' + esc(p.id) + '"><span class="ui-avatar" style="width:34px;height:34px">' + esc(UI.initials(p.name || p.email || '?')) + '</span>' +
              '<div class="grow"><b>' + esc(p.name || p.email) + '</b><div class="muted small">' + esc(p.email || '') + (p.joined ? '' : ' · hasn\'t signed up yet') + '</div></div>' +
              '<select data-role style="width:auto"><option value="viewer"' + (p.role === 'viewer' ? ' selected' : '') + '>Can view</option><option value="editor"' + (p.role === 'editor' ? ' selected' : '') + '>Can add</option></select>' +
              '<button class="ui-btn sm icon ghost" data-unshare aria-label="Remove">' + UI.icon('x') + '</button></div>';
          }).join('') : '<p class="muted small">Not shared with anyone yet.</p>') + '</div></div>';
      }
      body();
      mm.el.addEventListener('change', function (e) {
        if (e.target.matches('[data-public]')) UI.api('set_public', L.id, e.target.checked).then(function (r) { L.public = !!r.token; L.token = r.token; body(); if (r.token) FB.copy(FB.appUrl('#s/' + r.token), 'Link copied'); });
        if (e.target.matches('[data-role]')) UI.api('set_member', L.id, e.target.closest('[data-mid]').getAttribute('data-mid'), e.target.value).then(function () { UI.toast('Updated', 'ok'); });
      });
      mm.el.addEventListener('click', function (e) {
        if (e.target.closest('[data-copy-link]')) FB.copy(FB.appUrl('#s/' + L.token), 'Link copied');
        var u = e.target.closest('[data-unshare]');
        if (u) UI.api('set_member', L.id, u.closest('[data-mid]').getAttribute('data-mid')).then(function () { return reload(); }).then(body);
      });
      mm.el.addEventListener('submit', function (e) {
        if (!e.target.matches('[data-invite]')) return;
        e.preventDefault();
        var v = UI.formData(e.target);
        UI.busy(e.target.querySelector('[type=submit]'), UI.api('invite', L.id, v.email, v.role)).then(function (r) {
          L.members = r.list.members; body();
          UI.toast(r.has_account ? 'Shared. They\'ll see it in their lists.' : 'Invite saved. Tell them to sign up with ' + v.email + '.', 'ok');
        });
      });
    }
    function addModal() {
      var mm = UI.modal('<h2>Add faves to “' + esc(L.name) + '”</h2><input type="search" data-filter placeholder="Filter your faves" style="margin-bottom:10px">' +
        '<div class="lv-add-list">' + (addable.length ? addable.map(function (f) {
          var c = FB.cat(f.cat);
          return '<label data-t="' + esc((f.title || '').toLowerCase()) + '"><input type="checkbox" value="' + esc(f.id) + '"><span>' + esc(c.emoji) + '</span><span>' + esc(f.title) + '</span></label>';
        }).join('') : '<p class="muted">All your faves are already on this list.</p>') + '</div>' +
        '<div class="ui-row end" style="margin-top:16px"><button class="ui-btn ghost" data-close>Cancel</button><button class="ui-btn primary" data-do-add>Add</button></div>');
      mm.el.querySelector('[data-filter]').addEventListener('input', function (e) {
        var q = e.target.value.toLowerCase();
        mm.el.querySelectorAll('.lv-add-list label').forEach(function (l) { l.hidden = q && l.getAttribute('data-t').indexOf(q) < 0; });
      });
      mm.el.querySelector('[data-do-add]').addEventListener('click', function (e) {
        var ids = Array.prototype.map.call(mm.el.querySelectorAll('.lv-add-list input:checked'), function (i) { return i.value; });
        if (!ids.length) { mm.close(); return; }
        UI.busy(e.target.closest('button'), UI.api('list_add', L.id, ids)).then(function (r) { mm.close(); UI.toast(UI.plural(r.added, 'fave') + ' added', 'ok'); reload().then(draw); });
      });
    }
    view.addEventListener('click', function (e) {
      if (e.target.closest('[data-share]')) { shareModal(); return; }
      if (e.target.closest('[data-add]')) { addModal(); return; }
      if (e.target.closest('[data-edit]')) { editModal(L, emojis, colors).then(function (l) { if (l) reload().then(draw); }); return; }
      if (e.target.closest('[data-delete]')) {
        UI.confirm({ title: 'Delete this list?', text: 'The faves stay in your collection; only the list goes. People it was shared with lose access.', ok: 'Delete list', danger: true })
          .then(function (y) { if (y) UI.api('delete_list', L.id).then(function () { UI.toast('List deleted', 'ok'); UI.go('lists'); }); });
        return;
      }
      if (e.target.closest('[data-leave]')) {
        var meM = L.members.filter(function (x) { return x.me; })[0];
        UI.confirm({ title: 'Leave this list?', text: 'You won\'t see it any more unless ' + L.owner + ' shares it again.', ok: 'Leave' })
          .then(function (y) { if (y && meM) UI.api('set_member', L.id, meM.id).then(function () { UI.go('lists'); }); });
        return;
      }
      var rm = e.target.closest('[data-remove]');
      if (rm) { UI.api('list_remove', L.id, rm.getAttribute('data-remove')).then(function () { UI.toast('Removed from the list', 'ok'); reload().then(draw); }); return; }
      var cp = e.target.closest('[data-copy]');
      if (cp) UI.busy(cp, UI.api('copy_member_item', L.id, cp.getAttribute('data-copy'))).then(function (r) { UI.toast(r.created ? 'Saved to your inbox' : 'Already in your faves', 'ok'); });
    });
    function reload() { return UI.api('get_list', id).then(function (r) { L = r.list; addable = r.addable; emojis = r.emojis; colors = r.colors; }); }
    return { ready: Promise.all([FB.boot(), reload()]).then(draw), destroy: function () { alive = false; if (m) try { m.remove(); } catch (e) {} } };
  });
})();

/* ===== map.html ===== */
(function () {
  var esc = UI.esc;
  var RADII = [[1, '1 km'], [3, '3 km'], [10, '10 km'], [0, 'Anywhere']];

  UI.page('map', { title: 'Map', nav: 'Map', icon: 'map', auth: 'user', order: 30 }, function (view, ctx) {
    var all = [], here = null, m = null, markers = [], sugMarkers = [], st = UI.store.get('map.state', { radius: 0, cat: '', open: false }), lists = [], listFilter = null, listIds = null;
    var alive = true;
    if (ctx.args[0] === 'list' && ctx.args[1]) listFilter = ctx.args[1];
    view.innerHTML = '<div class="ui-wrap mp-wrap"><div class="mp-layout"><div class="mp-map"><div data-map></div>' +
      '<div class="mp-tools"><form class="mp-search" data-search><input type="search" name="q" placeholder="Find a place to save…" aria-label="Find a place"><button class="ui-btn sm icon" type="submit" aria-label="Search">' + UI.icon('search') + '</button></form>' +
      '<button class="ui-btn sm" data-near>' + UI.icon('locate') + 'Near me</button><button class="ui-btn sm" data-suggest>' + UI.icon('sparkle') + 'Suggest nearby</button></div>' +
      '<div data-results></div></div>' +
      '<aside class="mp-side"><div class="fb-panel mp-filters" data-filters></div><div class="mp-list" data-list><div class="ui-skel"></div></div></aside></div></div>';
    var mapEl = view.querySelector('[data-map]');

    function visible() {
      return all.filter(function (f) {
        if (f.lat == null) return false;
        if (st.cat && f.cat !== st.cat) return false;
        if (listIds && listIds.indexOf(f.id) < 0) return false;
        if (st.open && FB.openNow(f.osm && f.osm.opening_hours) !== true) return false;
        if (st.radius && here && FB.dist(here, f) > st.radius) return false;
        return true;
      }).sort(function (a, b) { return here ? FB.dist(here, a) - FB.dist(here, b) : (a.title || '').localeCompare(b.title || ''); });
    }
    function drawFilters() {
      var cats = {}; all.forEach(function (f) { if (f.lat != null) cats[f.cat] = (cats[f.cat] || 0) + 1; });
      view.querySelector('[data-filters]').innerHTML =
        '<div class="ui-row between"><b>' + (here ? (here.home ? esc(here.label || 'Home base') : 'Near you') : 'Your places') + '</b>' +
        '<label class="ui-check small"><input type="checkbox" data-open' + (st.open ? ' checked' : '') + '> Open now</label></div>' +
        '<div class="fb-chips">' + RADII.map(function (r) { return '<button class="fb-chip sm' + (st.radius === r[0] ? ' on' : '') + '" data-radius="' + r[0] + '"' + (!here && r[0] ? ' disabled title="Use Near me first"' : '') + '>' + r[1] + '</button>'; }).join('') + '</div>' +
        '<div class="fb-chips scroll"><button class="fb-chip sm' + (!st.cat ? ' on' : '') + '" data-mcat="">All</button>' +
        FB.CATS.filter(function (c) { return cats[c.id]; }).map(function (c) { return '<button class="fb-chip sm' + (st.cat === c.id ? ' on' : '') + '" data-mcat="' + c.id + '">' + c.emoji + ' ' + esc(c.name) + ' <span class="n">' + cats[c.id] + '</span></button>'; }).join('') + '</div>' +
        (lists.length ? '<select data-mlist aria-label="List"><option value="">All lists</option>' + lists.map(function (l) { return '<option value="' + esc(l.id) + '"' + (listFilter === l.id ? ' selected' : '') + '>' + esc((l.emoji || '') + ' ' + l.name) + '</option>'; }).join('') + '</select>' : '');
    }
    function drawList() {
      var v = visible(), box = view.querySelector('[data-list]');
      box.innerHTML = v.length ? v.map(function (f) {
        var oh = FB.openNow(f.osm && f.osm.opening_hours);
        return '<a class="mp-row" href="#fave/' + esc(f.id) + '" data-row="' + esc(f.id) + '">' + FB.cover(f) + '<div style="min-width:0"><b>' + esc(f.title) + '</b><div class="muted">' +
          esc(FB.cat(f.cat).emoji + ' ' + FB.cat(f.cat).name) + (oh === true ? ' · <span class="fb-open">Open</span>' : oh === false ? ' · Closed' : '') + '</div></div>' +
          '<span class="d">' + (here ? FB.fmtDist(FB.dist(here, f)) : '') + '</span></a>';
      }).join('') : '<div class="ui-empty" style="padding:30px 16px">' + UI.icon('pin') + '<h3>No places here</h3><p class="small">' +
        (all.some(function (f) { return f.lat != null; }) ? 'Try a bigger radius or another category.' : 'Paste a Google Maps link or search for a place to pin your first one.') + '</p></div>';
      drawPins(v);
    }
    function drawPins(v) {
      if (!m) return;
      markers.forEach(function (mk) { mk.remove(); }); markers = [];
      v.forEach(function (f) {
        var el = FB.map.pinEl(f);
        var mk = new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([f.lng, f.lat])
          .setPopup(new maplibregl.Popup({ offset: 26, closeButton: true }).setHTML(FB.map.popup(f,
            '<a class="ui-btn sm primary" href="#fave/' + esc(f.id) + '">Open</a><a class="ui-btn sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + f.lat + ',' + f.lng + '">Directions</a>')))
          .addTo(m);
        el.addEventListener('click', function () { var r = view.querySelector('[data-row="' + CSS.escape(f.id) + '"]'); view.querySelectorAll('.mp-row.on').forEach(function (x) { x.classList.remove('on'); }); if (r) { r.classList.add('on'); r.scrollIntoView({ block: 'nearest' }); } });
        markers.push(mk);
      });
    }
    function fitAll() { var v = visible(); FB.map.fit(m, here && st.radius ? v.concat([here]) : (v.length ? v : (here ? [here] : []))); }
    var meMarker = null;
    function showMe() {
      if (!m || !here) return;
      if (meMarker) meMarker.remove();
      meMarker = new maplibregl.Marker({ element: FB.map.meEl() }).setLngLat([here.lng, here.lat]).addTo(m);
    }

    view.addEventListener('click', function (e) {
      var r = e.target.closest('[data-radius]');
      if (r && !r.disabled) { st.radius = +r.getAttribute('data-radius'); save(); drawFilters(); drawList(); fitAll(); return; }
      var c = e.target.closest('[data-mcat]');
      if (c) { st.cat = c.getAttribute('data-mcat'); save(); drawFilters(); drawList(); fitAll(); return; }
      var near = e.target.closest('[data-near]');
      if (near) {
        UI.busy(near, FB.geo(true)).then(function (g) {
          if (!g) { UI.toast('Location is off. Set a home spot in Tools instead.', 'error'); return; }
          here = g; if (!st.radius) st.radius = 3; save(); showMe(); drawFilters(); drawList(); fitAll();
          if (g.home) UI.toast('Using your home spot (location wasn\'t shared).');
        });
        return;
      }
      if (e.target.closest('[data-suggest]')) { suggest(e.target.closest('[data-suggest]')); return; }
      var pick = e.target.closest('[data-pick]');
      if (pick) {
        var p = JSON.parse(pick.getAttribute('data-pick'));
        view.querySelector('[data-results]').innerHTML = '';
        if (m) {
          m.jumpTo({ center: [p.lng, p.lat], zoom: 16 });
          var el = FB.map.pinEl({ cat: 'other', title: p.title }, { suggestion: true, emoji: '📍' });
          var mk = new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([p.lng, p.lat])
            .setPopup(new maplibregl.Popup({ offset: 26 }).setHTML('<div class="fb-pop"><b>' + esc(p.title) + '</b><div class="muted">' + esc(p.address || p.kind || '') + '</div><div class="ui-row"><button class="ui-btn sm primary" data-save-place=\'' + esc(JSON.stringify(p)) + '\'>' + UI.icon('heart') + 'Save</button></div></div>')).addTo(m);
          sugMarkers.push(mk); mk.togglePopup();
        } else saveSuggestion(p);
        return;
      }
    });
    document.addEventListener('click', onDocClick);
    function onDocClick(e) {
      var b = e.target.closest && e.target.closest('[data-save-place]');
      if (!b || UI.current().name !== 'map') return;
      saveSuggestion(JSON.parse(b.getAttribute('data-save-place')), b);
    }
    function saveSuggestion(p, btn) {
      var pr = UI.api('save_fave', { title: p.title, lat: p.lat, lng: p.lng, address: p.address, osm: p.osm || {}, kind: 'place', source: 'map' });
      UI.busy(btn, pr).then(function (r) {
        var c = FB.cat(r.fave.cat);
        UI.toast((r.created ? 'Saved to your inbox: ' : 'Already saved: ') + c.emoji + ' ' + c.name, 'ok');
        if (r.created) { all.push(r.fave); drawFilters(); drawList(); }
      });
    }
    view.addEventListener('change', function (e) {
      if (e.target.matches('[data-open]')) { st.open = e.target.checked; save(); drawList(); }
      if (e.target.matches('[data-mlist]')) { listFilter = e.target.value || null; loadList().then(function () { drawList(); fitAll(); }); }
    });
    view.addEventListener('submit', function (e) {
      if (!e.target.matches('[data-search]')) return;
      e.preventDefault();
      var q = e.target.q.value.trim(); if (!q) return;
      find(q, e.target.querySelector('button'));
    });
    function find(q, btn) {
      var center = m ? { lat: m.getCenter().lat, lng: m.getCenter().lng } : here;
      UI.busy(btn, FB.data.photon(q, center, 8)).then(function (res) {
        var box = view.querySelector('[data-results]');
        box.innerHTML = res.length ? '<div class="mp-results">' + res.map(function (p) {
          return '<button data-pick=\'' + esc(JSON.stringify(p)) + '\'>' + UI.icon('pin') + '<span><b>' + esc(p.title) + '</b><br><span class="muted small">' + esc([p.kind, p.address].filter(Boolean).join(' · ')) + '</span></span></button>';
        }).join('') + '<button data-close-results class="muted small" style="justify-content:center" onclick="this.parentNode.remove()">Close</button></div>' : '';
        if (!res.length) UI.toast('No place found for "' + q + '"', 'error');
      }, function () { UI.toast('Place search is unavailable right now.', 'error'); });
    }
    function suggest(btn) {
      if (!m) { UI.toast('The map needs to be showing for suggestions.', 'error'); return; }
      var c = m.getCenter(), center = { lat: c.lat, lng: c.lng };
      UI.busy(btn, UI.apiQuiet('taste').then(function (t) {
        var recipe = t.recipes[0];
        return FB.data.placesLike(recipe, center, 1.5, t.saved).catch(function () {
          return FB.data.tilePois(m, recipe, center, 1.5, t.saved);
        }).then(function (list) { return { recipe: recipe, list: list }; });
      })).then(function (r) {
        sugMarkers.forEach(function (mk) { mk.remove(); }); sugMarkers = [];
        r.list.slice(0, 12).forEach(function (p) {
          var el = FB.map.pinEl({ cat: r.recipe.cat, title: p.title }, { suggestion: true, emoji: r.recipe.emoji });
          sugMarkers.push(new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([p.lng, p.lat])
            .setPopup(new maplibregl.Popup({ offset: 26 }).setHTML('<div class="fb-pop"><b>' + esc(p.title) + '</b><div class="muted">' + esc(r.recipe.label) + ' · ' + FB.fmtDist(p.km) + '</div>' +
              (p.why.length ? '<div class="muted">' + esc(p.why.join(', ')) + '</div>' : '') +
              '<div class="ui-row"><button class="ui-btn sm primary" data-save-place=\'' + esc(JSON.stringify({ title: p.title, lat: p.lat, lng: p.lng, address: p.address, osm: p.osm })) + '\'>' + UI.icon('heart') + 'Save</button>' +
              (p.website ? '<a class="ui-btn sm" target="_blank" rel="noopener" href="' + esc(p.website) + '">Website</a>' : '') + '</div></div>')).addTo(m));
        });
        UI.toast(r.list.length ? r.list.length + ' ' + r.recipe.label.toLowerCase() + ' nearby you haven\'t saved (dashed pins)' : 'No new ' + r.recipe.label.toLowerCase() + ' around here', r.list.length ? 'ok' : null);
      }, function () { UI.toast('Suggestions are unavailable right now. Try again in a minute.', 'error'); });
    }
    function save() { UI.store.set('map.state', st); }
    function loadList() {
      if (!listFilter) { listIds = null; return Promise.resolve(); }
      return UI.apiQuiet('get_list', listFilter).then(function (r) { listIds = r.list.items.map(function (i) { return i.id; }); }, function () { listIds = null; listFilter = null; });
    }
    function loadAll() {
      var out = [];
      function page(off) {
        return UI.apiQuiet('list_faves', { status: 'all' }, off).then(function (r) { out = out.concat(r.faves); return r.more && off < 1200 ? page(off + 60) : out; });
      }
      return page(0);
    }
    var ready = Promise.all([FB.boot(), loadAll(), FB.geo(false), UI.apiQuiet('my_lists'), loadList()]).then(function (r) {
      all = r[1]; here = r[2]; lists = r[3].mine.concat(r[3].shared);
      drawFilters(); drawList();
      var start = here || (all.filter(function (f) { return f.lat != null; })[0]) || { lat: 45.5165, lng: -73.5795 };
      return FB.map.make(mapEl, { center: start, zoom: 12 }).then(function (map) {
        if (!alive) { if (map) map.remove(); return; }
        m = map; drawPins(visible()); showMe(); fitAll();
        if (ctx.args[0] === 'find' && ctx.args[1]) { view.querySelector('[data-search] input').value = ctx.args[1]; find(ctx.args[1]); }
      });
    });
    return { ready: ready, destroy: function () { alive = false; document.removeEventListener('click', onDocClick); if (m) try { m.remove(); } catch (e) {} } };
  });
})();

/* ===== profile.html ===== */
(function () {
  var esc = UI.esc;
  UI.page('profile', { title: 'Your profile', auth: 'user' }, function (view, ctx) {
    var me = ctx.me;
    view.innerHTML = '<div class="ui-wrap ui-narrow"><div class="pf-head"><span class="ui-avatar">' + esc(UI.initials(me.name)) + '</span>' +
      '<div><h1>' + esc(me.name) + '</h1><div class="muted">' + esc(me.email) + (me.joined ? ' · member since ' + esc(UI.fmtDate(me.joined, { month: 'long', year: 'numeric' })) : '') + '</div></div></div>' +
      '<div class="pf-grid"><form class="ui-card ui-stack" data-name><h3>Your name</h3><label class="ui-field"><span>Shown to other people</span>' +
      '<input type="text" name="name" value="' + esc(me.name) + '" maxlength="60" required></label><button class="ui-btn primary" type="submit">Save</button></form>' +
      '<div class="ui-card ui-stack"><h3>Appearance</h3><p class="muted small">Follow your device, or pick one.</p><div data-theme-box></div>' +
      '<h3 style="margin-top:22px">Password</h3><p class="muted small">We\'ll email you a link to choose a new one.</p>' +
      '<button class="ui-btn" data-reset>' + UI.icon('mail') + 'Email me a reset link</button></div></div>' +
      '<div class="ui-card" style="margin-top:16px"><div class="pf-links">' +
      (me.is_admin ? '<a href="#admin" data-go="admin">' + UI.icon('shield') + 'Admin</a>' : '') +
      '<button data-feedback>' + UI.icon('chat') + 'Submit feedback</button>' +
      '<button data-lk-open="overview">' + UI.icon('lock') + 'Privacy &amp; Terms, and your data</button>' +
      '<button data-signout-here>' + UI.icon('logout') + 'Sign out</button></div></div></div>';
    function themeBox() {
      var t = UI.theme();
      view.querySelector('[data-theme-box]').innerHTML = '<div class="ui-seg">' + [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']].map(function (o) {
        return '<button type="button" data-theme-pick="' + o[0] + '" class="' + (t === o[0] ? 'on' : '') + '">' + o[1] + '</button>';
      }).join('') + '</div>';
    }
    themeBox();
    view.addEventListener('click', function (e) {
      var t = e.target.closest('[data-theme-pick]');
      if (t) { UI.setTheme(t.getAttribute('data-theme-pick')); themeBox(); UI.renderChrome(); return; }
      if (e.target.closest('[data-reset]')) {
        UI.busy(e.target.closest('[data-reset]'), UI.auth('reset', { email: me.email })).then(function (r) { UI.toast(r.message, 'ok'); });
      }
      if (e.target.closest('[data-signout-here]')) UI.auth('logout');
    });
    view.querySelector('[data-name]').addEventListener('submit', function (e) {
      e.preventDefault();
      var v = UI.formData(e.target);
      UI.busy(e.target.querySelector('[type=submit]'), UI.api('update_profile', v.name)).then(function (r) {
        UI.setMe(r.me); ctx.me = r.me; UI.toast('Saved', 'ok');
        view.querySelector('.pf-head h1').textContent = r.me.name;
      });
    });
  });
})();

/* ===== shared.html ===== */
(function () {
  var esc = UI.esc;
  UI.page('s', { title: 'Shared list' }, function (view, ctx) {
    var token = ctx.args[0], L = null, m = null, alive = true;
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:120px"></div><div class="ui-skel" style="height:300px;margin-top:16px"></div></div>';
    function draw() {
      var places = L.items.filter(function (f) { return f.lat != null; });
      document.title = L.name + ' · ' + UI.config.name;
      view.innerHTML = '<div class="ui-wrap"><div class="sh-hero"><span class="em" style="background:color-mix(in srgb,' + esc(L.color) + ' 20%,var(--c-bg))">' + esc(L.emoji) + '</span>' +
        '<div><span class="eyebrow">A list shared by ' + esc(L.owner) + '</span><h1>' + esc(L.name) + '</h1>' + (L.description ? '<p class="muted" style="margin:6px 0 0">' + esc(L.description) + '</p>' : '') +
        '<p class="small muted" style="margin:6px 0 0">' + UI.plural(L.count, 'fave') + (places.length ? ' · ' + UI.plural(places.length, 'place') + ' on the map' : '') + '</p></div></div>' +
        (places.length ? '<div class="sh-map" data-map></div>' : '') +
        FB.grid(L.items, { noStage: true, href: '#s/' + token, actions: function (f) {
          return (L.signed_in ? '<button class="ui-btn sm primary" data-copy="' + esc(f.id) + '">' + UI.icon('heart') + 'Save to mine</button>' : '') +
            (f.url ? '<a class="ui-btn sm" href="' + esc(f.url) + '" target="_blank" rel="noopener">' + UI.icon('external') + 'Open</a>' : '') +
            (f.lat != null ? '<a class="ui-btn sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + f.lat + ',' + f.lng + '">' + UI.icon('compass') + 'Go</a>' : '');
        } }) +
        (L.signed_in ? '' : '<div class="sh-cta"><div><h3 style="margin:0">Keep your own favourites like this</h3><p class="muted" style="margin:4px 0 0">Save tabs, map pins and screenshots; they\'re sorted for you. Free.</p></div>' +
          '<a class="ui-btn primary" href="#auth/signup" data-go="auth/signup">Make your own, free</a></div>') + '</div>';
      // cards link to the list itself for visitors (they can't open other people's faves)
      view.querySelectorAll('.fb-card a[href="#s/' + token + '"]').forEach(function (a) { a.removeAttribute('href'); });
      if (places.length) {
        FB.map.make(view.querySelector('[data-map]'), { center: places[0], zoom: 13, cooperative: true }).then(function (map) {
          if (!map || !alive) return;
          m = map;
          places.forEach(function (f) {
            new maplibregl.Marker({ element: FB.map.pinEl(f), anchor: 'bottom' }).setLngLat([f.lng, f.lat])
              .setPopup(new maplibregl.Popup({ offset: 26 }).setHTML(FB.map.popup(f, '<a class="ui-btn sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + f.lat + ',' + f.lng + '">Directions</a>'))).addTo(m);
          });
          FB.map.fit(m, places, 40);
        });
      }
    }
    view.addEventListener('click', function (e) {
      var b = e.target.closest('[data-copy]'); if (!b) return;
      UI.busy(b, UI.api('copy_shared', token, b.getAttribute('data-copy'))).then(function (r) {
        b.disabled = true; b.innerHTML = UI.icon('check') + 'Saved';
        UI.toast(r.created ? 'Saved to your inbox' : 'Already in your faves', 'ok');
      });
    });
    var ready = UI.api('shared_list', token).then(function (r) { FB.setCats(r.cats); L = r.list; draw(); },
      function (err) {
        view.innerHTML = '<div class="ui-wrap"><div class="ui-empty">' + UI.icon('lock') + '<h3>This list isn\'t available</h3><p>' + esc(err.message) + '</p><a class="ui-btn primary" href="#landing" data-go="landing">About Faves Buddy</a></div></div>';
      });
    return { ready: ready, destroy: function () { alive = false; if (m) try { m.remove(); } catch (e) {} } };
  });
})();

/* ===== tabs.html ===== */
(function () {
  var esc = UI.esc;
  UI.page('tabs', { title: 'Tab sets', auth: 'user' }, function (view) {
    var sets = [];
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:220px"></div></div>';
    function draw() {
      view.innerHTML = '<div class="ui-wrap ui-narrow" style="max-width:900px"><div class="ui-page-head"><div><h1>Tab sets</h1>' +
        '<p class="muted">Whole windows of tabs you saved at once. Close the tabs with a clear mind: they\'re all here, sorted.</p></div></div>' +
        (sets.length ? sets.map(function (s) {
          return '<div class="fb-panel tb-set" data-set="' + esc(s.id) + '"><div class="tb-head"><div><h3 contenteditable="true" spellcheck="false" data-name>' + esc(s.name) + '</h3>' +
            '<span class="muted small">' + UI.plural(s.count, 'tab') + ' · saved ' + esc(UI.ago(s.created)) + (s.inbox ? ' · ' + s.inbox + ' still in your inbox' : ' · all sorted ✓') + '</span></div>' +
            '<div class="ui-row"><button class="ui-btn sm primary" data-openall>' + UI.icon('external') + 'Open all</button><button class="ui-btn sm" data-copyall>' + UI.icon('copy') + 'Copy links</button>' +
            (s.inbox ? '<button class="ui-btn sm" data-keepall>' + UI.icon('check') + 'Keep all</button>' : '') +
            '<button class="ui-btn sm icon danger" data-del title="Delete set" aria-label="Delete set">' + UI.icon('trash') + '</button></div></div>' +
            '<div class="tb-cats">' + s.cats.map(function (c) { var k = FB.cat(c[0]); return '<span class="fb-chip sm flat">' + k.emoji + ' ' + esc(k.name) + ' <span class="n">' + c[1] + '</span></span>'; }).join('') + '</div>' +
            '<details><summary class="small muted" style="cursor:pointer">Show the tabs</summary><div class="tb-links">' + s.faves.map(function (f) {
              return '<a class="tb-link" href="#fave/' + esc(f.id) + '"><span>' + esc(FB.cat(f.cat).emoji) + '</span>' +
                '<span class="t">' + esc(f.title) + '</span><span class="d">' + esc(f.domain || '') + '</span></a>';
            }).join('') + '</div></details></div>';
        }).join('') : '<div class="ui-empty">' + UI.icon('tabs') + '<h3>No tab sets yet</h3><p>With the Chrome extension, “Save all tabs in this window” puts a whole window here in one click.</p>' +
          '<a class="ui-btn primary" href="#tools" data-go="tools">' + UI.icon('puzzle') + 'Get the extension</a></div>') + '</div>';
    }
    function setOf(el) { var id = el.closest('[data-set]').getAttribute('data-set'); return sets.filter(function (s) { return s.id === id; })[0]; }
    view.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      var s = b.closest('[data-set]') ? setOf(b) : null; if (!s) return;
      var urls = s.faves.map(function (f) { return f.url; }).filter(Boolean);
      if (b.matches('[data-openall]')) {
        var opened = 0;
        urls.forEach(function (u) { if (window.open(u, '_blank', 'noopener')) opened++; });
        if (opened < urls.length) UI.toast('Your browser blocked some tabs. Allow pop-ups for this site, or use the extension\'s “Reopen a tab set”.', 'error');
      }
      if (b.matches('[data-copyall]')) FB.copy(urls.join('\n'), UI.plural(urls.length, 'link') + ' copied');
      if (b.matches('[data-keepall]')) UI.busy(b, UI.api('keep_tabset', s.id)).then(function (r) { UI.toast(UI.plural(r.kept, 'tab') + ' kept', 'ok'); load(); });
      if (b.matches('[data-del]')) {
        var m = UI.modal('<h2>Delete “' + esc(s.name) + '”?</h2><p class="muted">Keep the tabs as faves and only remove the group, or delete the tabs too.</p>' +
          '<div class="ui-row end" style="margin-top:18px"><button class="ui-btn ghost" data-close>Cancel</button><button class="ui-btn" data-only>Remove the group</button><button class="ui-btn danger solid" data-all>Delete the tabs too</button></div>');
        m.el.addEventListener('click', function (ev) {
          var only = ev.target.closest('[data-only]'), all = ev.target.closest('[data-all]');
          if (only || all) UI.busy(only || all, UI.api('delete_tabset', s.id, !!all)).then(function () { m.close(); UI.toast('Done', 'ok'); load(); });
        });
      }
    });
    view.addEventListener('focusout', function (e) {
      if (!e.target.matches('[data-name]')) return;
      var s = setOf(e.target), name = e.target.textContent.trim();
      if (name && name !== s.name) UI.api('rename_tabset', s.id, name).then(function () { s.name = name; UI.toast('Renamed', 'ok'); });
    });
    view.addEventListener('keydown', function (e) { if (e.target.matches('[data-name]') && e.key === 'Enter') { e.preventDefault(); e.target.blur(); } });
    function load() { return Promise.all([FB.boot(), UI.api('tabsets')]).then(function (r) { sets = r[1].tabsets; draw(); }); }
    return load();
  });
})();

/* ===== tidy.html ===== */
(function () {
  'use strict';
  var esc = UI.esc;
  var incoming = null;   // what #share/<code> handed over: {code, links, photos, note, name}

  function isPhone() { return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent); }
  function platform() { var u = navigator.userAgent; return /iPhone|iPad|iPod/i.test(u) ? 'ios' : /Android/i.test(u) ? 'android' : 'desktop'; }
  function installed() { return window.matchMedia && window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true; }
  function pct(x) { return Math.round((x || 0) * 100) + '%'; }

  /* ------------------------------------------------------------------ how to get things in (hub + tabs input) */
  function howTabs() {
    return {
      android: '<ol><li>Install Faves Buddy once (button above, or Chrome menu <b>⋮ → Add to Home screen</b>).</li>' +
        '<li>In Chrome, open the tab switcher, touch and hold any tab (or tap <b>⋮</b>) and choose <b>Select tabs</b>.</li>' +
        '<li>Tick the tabs (or all of them), tap <b>⋮ → Share tabs</b> and pick <b>Faves Buddy</b>.</li>' +
        '<li>They open here, already sorted. Swipe through them. Close the tabs in Chrome afterwards.</li></ol>',
      ios: '<ol><li>In Safari, open the tab overview, then touch and hold the tab group\'s name (or tap <b>⋯</b>) and choose <b>Copy N Links</b>.</li>' +
        '<li>Come back here, open <b>Sort my open tabs</b> and tap <b>Paste</b>. The titles come along.</li>' +
        '<li>Chrome on iPhone: in the tab grid tap <b>Edit → Select tabs</b>, pick them, then <b>Share → Copy</b>, and paste here.</li></ol>',
      desktop: '<ol><li>Install the <a href="#tools" data-go="tools">Chrome extension</a> and connect it.</li>' +
        '<li>Open it and look under <b>Tabs on your other devices</b>: with Chrome sync on, your phone\'s open Chrome tabs are listed there.</li>' +
        '<li>Tap <b>Sort these</b> and they open here as a pile to swipe through. (Or save this computer\'s window in one click.)</li></ol>'
    };
  }
  function helpPanel() {
    var p = platform(), h = howTabs();
    var inst = installed() ? '<p class="ok small">' + UI.icon('check') + ' Faves Buddy is installed on this device.</p>'
      : (window.fbInstallPrompt ? '<button class="ui-btn primary" data-install>' + UI.icon('download') + 'Install Faves Buddy on this device</button>' : '');
    var sec = function (id, icon, title, body) { return '<details' + (p === id ? ' open' : '') + '><summary>' + UI.icon(icon) + title + '</summary>' + body + '</details>'; };
    return '<div class="fb-panel td-help"><h2 style="margin-top:0">Getting your tabs and screenshots in</h2>' + inst +
      sec('android', 'phone', 'Android phone (Chrome)', h.android +
        '<p class="small muted" style="margin:10px 0 0">Screenshots: in Photos or Gallery, select several, tap <b>Share</b> and pick <b>Faves Buddy</b>. Or use <b>Sweep my screenshots</b> above.</p>') +
      sec('ios', 'phone', 'iPhone or iPad', h.ios +
        '<p class="small muted" style="margin:10px 0 0">Screenshots: <b>Sweep my screenshots</b> lets you pick a batch from the Screenshots album. To keep Faves Buddy on your Home Screen: Safari <b>Share → Add to Home Screen</b>.</p>') +
      sec('desktop', 'puzzle', 'A computer (Chrome extension)', h.desktop) + '</div>';
  }
  window.addEventListener('beforeinstallprompt', function (e) { e.preventDefault(); window.fbInstallPrompt = e; });

  /* ------------------------------------------------------------------ hub */
  function hub(view) {
    var saved = UI.store.get('tidy.tabs', null), left = saved && saved.items ? saved.items.length - saved.idx : 0;
    var job = function (to, icon, title, text, cls) {
      return '<a class="td-job ' + (cls || '') + '" href="#tidy/' + to + '" data-go="tidy/' + to + '"><span class="ic">' + UI.icon(icon) + '</span><span><h2>' + title + '</h2><p>' + text + '</p></span></a>';
    };
    view.innerHTML = '<div class="ui-wrap td-wrap"><div class="ui-page-head"><div><h1>Tidy up</h1><p class="muted">Clear a pile in a few minutes. Everything is already sorted for you: say yes, move it, or skip it.</p></div></div>' +
      '<div class="td-big">' + job('tabs', 'tabs', 'Sort my open tabs', left > 0 ? 'You have ' + UI.plural(left, 'tab') + ' left from last time. Pick up where you left off.' : 'Share or paste a pile of tabs, then swipe: keep, move or skip.') +
      job('shots', 'image', 'Sweep my screenshots', 'Pick your screenshots. Their text is read on this device and each one is sorted for you.', 'coral') + '</div>' +
      '<div data-waiting></div>' + helpPanel() + '</div>';
    return UI.apiQuiet('drops_waiting').then(function (r) {
      if (!r.drops.length) return;
      view.querySelector('[data-waiting]').innerHTML = '<h2>Shared with Faves Buddy, still to tidy</h2><div class="td-wait">' + r.drops.map(function (d) {
        var what = [d.links ? UI.plural(d.links, 'link') : '', d.photos ? UI.plural(d.photos, 'picture') : ''].filter(Boolean).join(' and ');
        return '<div class="td-wait-row">' + UI.icon('share') + '<div class="grow"><b>' + esc(d.name || what) + '</b><div class="muted small">' + esc(what) + ' · ' + esc(UI.ago(d.created)) + '</div></div>' +
          '<a class="ui-btn sm primary" href="#share/' + esc(d.code) + '">Tidy</a><button class="ui-btn sm ghost" data-discard="' + esc(d.code) + '" aria-label="Throw away">' + UI.icon('trash') + '</button></div>';
      }).join('') + '</div>';
    }).catch(function () {});
  }

  /* ------------------------------------------------------------------ tabs */
  function linksFromHtml(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html'), out = [];
    doc.querySelectorAll('a[href]').forEach(function (a) {
      var u = a.getAttribute('href');
      if (/^https?:/i.test(u)) out.push(u + ' | ' + (a.textContent || '').replace(/\s+/g, ' ').trim());
    });
    return out;
  }

  function tabsMode(view) {
    var st = null;   // {items, idx, dec: {url: {act, cat}}, drop, name, history: [url]}
    var mode = UI.store.get('tidy.view', 'deck');
    var fetching = {};
    function save() { if (st) UI.store.set('tidy.tabs', st); }
    function clear() { st = null; UI.store.set('tidy.tabs', null); }
    function frame(inner) {
      view.innerHTML = '<div class="ui-wrap td-wrap"><div class="ui-page-head"><div><a class="ui-btn ghost sm" href="#tidy" data-go="tidy">' + UI.icon('back') + 'Tidy up</a><h1>Sort my open tabs</h1></div></div><div data-body>' + inner + '</div></div>';
    }
    function inputScreen() {
      var p = platform();
      frame('<div class="fb-panel td-input ui-stack"><div><h2 style="margin:0 0 4px">Your tabs</h2><p class="muted small" style="margin:0">One link per line. Pasting Safari\'s or Chrome\'s copied links keeps their titles. Nothing is opened yet; they\'re sorted from the link and title.</p></div>' +
        '<textarea data-paste placeholder="https://…&#10;https://…" spellcheck="false"></textarea>' +
        '<div class="ui-row"><button class="ui-btn" data-clip>' + UI.icon('copy') + 'Paste</button><span class="grow"></span><button class="ui-btn primary lg" data-sort>' + UI.icon('sort') + 'Sort them</button></div></div>' +
        '<div class="fb-panel td-help" style="margin-top:18px"><details open><summary>' + UI.icon('info') + 'How to get my tabs here</summary>' + howTabs()[p] +
        (p !== 'desktop' ? '' : '<p class="small muted">On a phone? Open Faves Buddy there: Android shares tabs straight in, iPhone copies them in one go.</p>') + '</details></div>');
    }
    function start(links, drop, name) {
      st = { items: links.map(function (l) { return Object.assign({}, l); }), idx: 0, dec: {}, drop: drop || null, name: name || '', history: [] };
      save(); render();
    }
    function decided(a) { return st.items.filter(function (it) { return st.dec[it.url] && st.dec[it.url].act === a; }).length; }
    function catOf(it) { return (st.dec[it.url] && st.dec[it.url].cat) || it.pick || it.cat; }
    function render() {
      if (!st) return inputScreen();
      if (st.idx >= st.items.length) return finish();
      return mode === 'list' ? listView() : deckView();
    }
    function topBar() {
      var n = st.items.length;
      return '<div class="td-top"><div><b>' + (mode === 'deck' ? 'Tab ' + Math.min(st.idx + 1, n) + ' of ' + n : n + ' tabs') + '</b> <span class="muted small">· ' +
        decided('keep') + ' kept · ' + decided('later') + ' later · ' + decided('skip') + ' skipped</span></div>' +
        '<div class="ui-seg" role="group" aria-label="View"><button type="button" data-view="deck" class="' + (mode === 'deck' ? 'on' : '') + '">Cards</button><button type="button" data-view="list" class="' + (mode === 'list' ? 'on' : '') + '">List</button></div></div>' +
        '<div class="td-bar"><i style="width:' + (st.idx / n * 100) + '%"></i></div>';
    }
    function sureLeft() { return st.items.slice(st.idx).filter(function (it) { return !st.dec[it.url] && it.conf >= 0.6 && it.cat !== 'other' && !it.already; }); }
    function deckView() {
      var it = st.items[st.idx], cat = catOf(it), c = FB.cat(cat), sure = sureLeft();
      var f = { id: it.url, title: it.title, cat: cat, kind: it.kind === 'place' ? 'place' : 'link', image: it.image };
      frame(topBar() + (sure.length > 2 ? '<div class="td-sure">' + UI.icon('sparkle') + '<span><b>' + sure.length + '</b> of these tabs are sorted with confidence.</span><button class="ui-btn sm" data-sure>Keep them as sorted</button></div>' : '') +
        '<div class="td-stage"><div class="td-card" data-card><span class="td-stamp keep">KEEP</span><span class="td-stamp skip">SKIP</span>' + FB.cover(f) +
        '<h2>' + esc(it.title || it.domain) + '</h2><div class="fb-sub">' + UI.icon('globe') + '<span>' + esc(it.site || it.domain) + '</span></div>' +
        (it.desc ? '<p class="td-desc">' + esc(it.desc) + '</p>' : '') +
        (it.already ? '<div class="td-already">' + UI.icon('check') + 'Already saved, in ' + esc(FB.cat(it.already_cat).emoji + ' ' + FB.cat(it.already_cat).name) + '</div>' : '') +
        '<div class="td-sorted"><div class="fb-why">' + (it.cat !== 'other' ? FB.catChip(it.cat) + ' ' + pct(it.conf) + ' sure: ' + (it.reasons || []).map(function (x) { return '<span class="fb-tag">' + esc(x) + '</span>'; }).join('') : 'Not sure where this goes: pick one.') + '</div>' +
        '<div class="td-cats" data-cats>' + FB.CATS.map(function (k) { return '<button type="button" class="fb-chip sm' + (k.id === cat ? ' on' : '') + '" data-cat="' + k.id + '">' + k.emoji + ' ' + esc(k.name) + '</button>'; }).join('') + '</div></div></div>' +
        '<div class="td-acts"><button class="ui-btn" data-act="skip" title="Skip (←)">' + UI.icon('x') + '<span>Skip</span></button>' +
        '<button class="ui-btn" data-act="later" title="Later: to the inbox (↓)">' + UI.icon('inbox') + 'Later</button>' +
        '<button class="ui-btn primary" data-act="keep" title="Keep (→)">' + UI.icon('heart') + '<span>' + (cat === 'other' ? 'Keep' : '<span class="kin">Keep in </span>' + esc(c.emoji + ' ' + c.name)) + '</span></button></div>' +
        '<div class="td-under"><button class="ui-btn ghost sm" data-undo' + (st.history.length ? '' : ' disabled') + '>' + UI.icon('back') + 'Undo</button>' +
        '<a class="ui-btn ghost sm" href="' + esc(it.url) + '" target="_blank" rel="noopener">' + UI.icon('external') + 'Open the page</a>' +
        '<button class="ui-btn ghost sm" data-finish>Finish now</button></div></div>');
      wireSwipe(view.querySelector('[data-card]'));
      prefetch();
    }
    function listView() {
      var rest = st.items.slice(st.idx);
      frame(topBar() + '<p class="muted small">Untick what you don\'t want. Change a category with the menu. Then save them all.</p><div class="td-list">' + rest.map(function (it, i) {
        var d = st.dec[it.url], on = d ? d.act !== 'skip' : (it.conf >= 0.5 && !it.already);
        return '<label class="td-row"><input type="checkbox" data-row="' + i + '"' + (on ? ' checked' : '') + '><span style="min-width:0"><b>' + esc(it.title || it.domain) + '</b><span class="muted small">' + esc(it.domain) +
          (it.already ? ' · already saved' : '') + '</span></span><select data-rowcat="' + i + '" aria-label="Category">' + FB.CATS.map(function (k) {
            return '<option value="' + k.id + '"' + (k.id === catOf(it) ? ' selected' : '') + '>' + k.emoji + ' ' + esc(k.name) + '</option>'; }).join('') + '</select></label>';
      }).join('') + '</div><div class="td-sticky"><button class="ui-btn primary lg" data-listdone>' + UI.icon('check') + 'Done: save the ticked ones</button></div>');
    }
    function decide(act, cat) {
      var it = st.items[st.idx];
      st.dec[it.url] = { act: act, cat: cat || catOf(it) };
      st.history.push(it.url); st.idx++; save();
      var card = view.querySelector('[data-card]');
      if (card) {
        card.style.transform = act === 'skip' ? 'translateX(-120%) rotate(-12deg)' : act === 'keep' ? 'translateX(120%) rotate(12deg)' : 'translateY(60px)';
        card.style.opacity = '0';
        setTimeout(render, 180);
      } else render();
    }
    function undo() {
      if (!st.history.length) return;
      var url = st.history.pop(); delete st.dec[url];
      st.idx = Math.max(0, st.items.findIndex(function (it) { return it.url === url; }));
      save(); render();
    }
    function wireSwipe(card) {
      if (!card) return;
      var x0 = null, y0 = 0, dx = 0, stamps = card.querySelectorAll('.td-stamp');
      card.addEventListener('pointerdown', function (e) {
        if (e.target.closest('button, a, .td-cats')) return;
        x0 = e.clientX; y0 = e.clientY; dx = 0; card.classList.add('drag');
      });
      card.addEventListener('pointermove', function (e) {
        if (x0 == null) return;
        dx = e.clientX - x0;
        if (Math.abs(dx) < 8 || Math.abs(e.clientY - y0) > Math.abs(dx) * 1.2) return;
        card.style.transform = 'translateX(' + dx + 'px) rotate(' + dx / 22 + 'deg)';
        stamps[0].style.opacity = Math.max(0, Math.min(1, dx / 90)); stamps[1].style.opacity = Math.max(0, Math.min(1, -dx / 90));
      });
      var end = function () {
        if (x0 == null) return;
        x0 = null; card.classList.remove('drag');
        if (dx > 90) decide('keep'); else if (dx < -90) decide('skip');
        else { card.style.transform = ''; stamps[0].style.opacity = stamps[1].style.opacity = 0; }
      };
      card.addEventListener('pointerup', end); card.addEventListener('pointercancel', end); card.addEventListener('pointerleave', end);
    }
    function prefetch() {
      var want = st.items.slice(st.idx, st.idx + 4).filter(function (it) { return !it.detail && !fetching[it.url]; });
      if (!want.length) return;
      want.forEach(function (it) { fetching[it.url] = true; });
      UI.apiQuiet('triage_detail', want.map(function (it) { return it.url; })).then(function (r) {
        var cur = st && st.items[st.idx], redraw = false;
        (r.pages || []).forEach(function (p) {
          var it = st && st.items.find(function (x) { return x.url === p.url; });
          if (!it) return;
          it.detail = true;
          if (p.failed) return;
          if (p.title && (!it.title || it.title === it.domain)) it.title = p.title;
          it.image = p.image || it.image; it.desc = p.desc || it.desc; it.site = p.site || it.site; it.meta = p.meta;
          if (p.kind === 'place') { it.kind = 'place'; it.lat = p.lat; it.lng = p.lng; it.address = p.address; }
          if (!it.pick && !(st.dec[it.url]) && p.conf >= it.conf) { it.cat = p.cat; it.conf = p.conf; it.reasons = p.reasons; }
          if (it === cur) redraw = true;
        });
        save();
        if (redraw && mode === 'deck' && !view.querySelector('.td-card.drag')) deckView();
      }).catch(function () { want.forEach(function (it) { it.detail = true; }); });
    }
    function finish() {
      var keep = st.items.filter(function (it) { return st.dec[it.url] && st.dec[it.url].act === 'keep'; });
      var later = st.items.filter(function (it) { return st.dec[it.url] && st.dec[it.url].act === 'later'; });
      var skip = st.items.length - keep.length - later.length, tally = {};
      keep.forEach(function (it) { var c = st.dec[it.url].cat; tally[c] = (tally[c] || 0) + 1; });
      var name = st.name || 'Tidied tabs, ' + new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      frame('<div class="fb-panel td-done"><div class="big">🧹</div><h2>' + (keep.length + later.length ? 'Ready to save' : 'All skipped') + '</h2>' +
        '<p class="muted">' + UI.plural(keep.length, 'tab') + ' to keep, ' + later.length + ' for later (inbox), ' + skip + ' skipped.</p>' +
        '<div class="td-tally">' + Object.keys(tally).map(function (k) { return '<span class="fb-chip sm on">' + FB.cat(k).emoji + ' ' + esc(FB.cat(k).name) + ' · ' + tally[k] + '</span>'; }).join('') + '</div>' +
        (keep.length + later.length > 1 ? '<div class="td-group"><label class="ui-check"><input type="checkbox" data-group' + (keep.length + later.length >= 5 ? ' checked' : '') + '> Also keep them together as a tab set, to reopen them all at once</label>' +
          '<input type="text" data-groupname maxlength="80" value="' + esc(name) + '" aria-label="Tab set name"></div>' : '') +
        '<div class="ui-row" style="justify-content:center;margin-top:20px"><button class="ui-btn ghost" data-back>' + UI.icon('back') + 'Back to the cards</button>' +
        '<button class="ui-btn primary lg" data-save>' + UI.icon('heart') + (keep.length + later.length ? 'Save ' + (keep.length + later.length) : 'Done') + '</button></div></div>');
    }
    function doSave(btn) {
      var items = st.items.filter(function (it) { return st.dec[it.url] && st.dec[it.url].act !== 'skip'; }).map(function (it) {
        var d = st.dec[it.url];
        return { url: it.url, title: it.title, category: d.act === 'keep' && d.cat !== 'other' ? d.cat : null, meta: it.meta || {}, kind: it.kind, lat: it.lat, lng: it.lng, address: it.address };
      });
      var g = view.querySelector('[data-group]'), group = g && g.checked ? (view.querySelector('[data-groupname]').value || '').trim() : null, drop = st.drop;
      var other = incoming && incoming.code === drop && incoming.photos && incoming.photos.length ? incoming.photos.length : 0;
      return UI.busy(btn, UI.api('triage_save', items, group, drop)).then(function (r) {
        clear();
        frame('<div class="fb-panel td-done"><div class="big">✨</div><h2>Tidy!</h2><p class="muted">' + (r.saved ? UI.plural(r.saved, 'new fave') + ' saved' : 'Nothing new saved') + (r.again ? ', ' + r.again + ' were already there' : '') + '.</p>' +
          '<div class="td-tally">' + Object.keys(r.by_cat).map(function (k) { return '<a class="fb-chip sm" href="#home/cat/' + k + '">' + FB.cat(k).emoji + ' ' + esc(FB.cat(k).name) + ' · ' + r.by_cat[k] + '</a>'; }).join('') + '</div>' +
          '<div class="ui-row" style="justify-content:center">' + (other ? '<a class="ui-btn primary" href="#tidy/shots" data-go="tidy/shots">' + UI.icon('image') + 'Now sweep the ' + UI.plural(other, 'picture') + ' you shared</a>' : '') +
          (r.tabset ? '<a class="ui-btn" href="#tabs" data-go="tabs">' + UI.icon('tabs') + 'See the tab set</a>' : '') +
          '<a class="ui-btn" href="#inbox" data-go="inbox">' + UI.icon('inbox') + 'Inbox</a><a class="ui-btn ghost" href="#tidy" data-go="tidy">Tidy more</a></div></div>');
      });
    }
    function sortText(text, btn) {
      return UI.busy(btn, UI.api('triage_links', null, text)).then(function (r) {
        if (!r.links.length) { UI.toast('No links found there.', 'error'); return; }
        start(r.links, null, '');
      });
    }

    view.addEventListener('click', function (e) {
      var b = e.target.closest('button, a'); if (!b || !view.contains(b)) return;
      if (b.hasAttribute('data-clip')) {
        var box = view.querySelector('[data-paste]');
        var put = function (t) { box.value = (box.value ? box.value.replace(/\s*$/, '\n') : '') + t; };
        var p = navigator.clipboard && navigator.clipboard.read ? navigator.clipboard.read().then(function (items) {
          var it = items.find(function (x) { return x.types.indexOf('text/html') >= 0; });
          if (it) return it.getType('text/html').then(function (bl) { return bl.text(); }).then(function (h) { var l = linksFromHtml(h); if (l.length) return put(l.join('\n')); return navigator.clipboard.readText().then(put); });
          return navigator.clipboard.readText().then(put);
        }) : navigator.clipboard ? navigator.clipboard.readText().then(put) : Promise.reject();
        p.catch(function () { box.focus(); UI.toast('Long-press the box and choose Paste.'); });
        return;
      }
      if (b.hasAttribute('data-sort')) { var t = view.querySelector('[data-paste]').value; if (!t.trim()) { UI.toast('Paste some links first.', 'error'); return; } sortText(t, b); return; }
      if (b.hasAttribute('data-view')) { mode = b.getAttribute('data-view'); UI.store.set('tidy.view', mode); render(); return; }
      if (b.hasAttribute('data-cat') && view.querySelector('[data-card]')) {
        var it = st.items[st.idx]; it.pick = b.getAttribute('data-cat'); save(); deckView(); return;
      }
      if (b.hasAttribute('data-act')) { decide(b.getAttribute('data-act')); return; }
      if (b.hasAttribute('data-undo')) { undo(); return; }
      if (b.hasAttribute('data-sure')) {
        sureLeft().forEach(function (x) { st.dec[x.url] = { act: 'keep', cat: x.cat }; });
        var rest = st.items.slice(st.idx), done = rest.filter(function (x) { return st.dec[x.url]; }), open = rest.filter(function (x) { return !st.dec[x.url]; });
        st.items = st.items.slice(0, st.idx).concat(done, open); st.idx += done.length; save();
        UI.toast(UI.plural(done.length, 'tab') + ' kept as sorted.', 'ok'); render(); return;
      }
      if (b.hasAttribute('data-finish')) { st.idx = st.items.length; save(); finish(); return; }
      if (b.hasAttribute('data-listdone')) {
        st.items.slice(st.idx).forEach(function (it, i) {
          var on = view.querySelector('[data-row="' + i + '"]').checked, cat = view.querySelector('[data-rowcat="' + i + '"]').value;
          st.dec[it.url] = { act: on ? 'keep' : 'skip', cat: cat };
        });
        st.idx = st.items.length; save(); finish(); return;
      }
      if (b.hasAttribute('data-back')) { st.idx = Math.max(0, st.items.findIndex(function (x) { return !st.dec[x.url]; })); if (st.idx < 0 || st.idx >= st.items.length) st.idx = Math.max(0, st.items.length - 1); save(); render(); return; }
      if (b.hasAttribute('data-save')) { doSave(b); return; }
      if (b.hasAttribute('data-restart')) { clear(); inputScreen(); }
    });
    view.addEventListener('paste', function (e) {
      if (!e.target.matches('[data-paste]') || !e.clipboardData) return;
      var h = e.clipboardData.getData('text/html');
      var l = h ? linksFromHtml(h) : [];
      if (l.length) { e.preventDefault(); var box = e.target; box.value = (box.value ? box.value.replace(/\s*$/, '\n') : '') + l.join('\n'); }
    });
    function onKey(e) {
      if (!st || mode !== 'deck' || !view.querySelector('[data-card]') || /INPUT|TEXTAREA|SELECT/.test((e.target.tagName || ''))) return;
      if (e.key === 'ArrowRight') decide('keep'); else if (e.key === 'ArrowLeft') decide('skip'); else if (e.key === 'ArrowDown') decide('later');
      else if ((e.key === 'z' && (e.ctrlKey || e.metaKey)) || e.key === 'Backspace') undo();
    }
    document.addEventListener('keydown', onKey);

    var ready = FB.boot().then(function () {
      if (incoming && incoming.links && incoming.links.length && !incoming.linksTaken) {
        incoming.linksTaken = true;
        return UI.api('triage_links', incoming.links).then(function (r) { start(r.links, incoming.code, incoming.name); });
      }
      st = UI.store.get('tidy.tabs', null);
      if (st && (!st.items || !st.items.length)) st = null;
      if (st) { st.history = st.history || []; render(); if (st.idx < st.items.length) UI.toast('Picking up where you left off. ' + UI.plural(st.items.length - st.idx, 'tab') + ' to go.'); }
      else inputScreen();
    });
    return { ready: ready, destroy: function () { document.removeEventListener('keydown', onKey); } };
  }

  /* ------------------------------------------------------------------ screenshots */
  function fpOf(file) {
    var s = (file.name || '') + '|' + (file.size || 0) + '|' + (file.lastModified || 0), h1 = 0x811c9dc5, h2 = 0;
    for (var i = 0; i < s.length; i++) { h1 = Math.imul(h1 ^ s.charCodeAt(i), 16777619) >>> 0; h2 = (h2 * 31 + s.charCodeAt(i)) >>> 0; }
    return 's' + h1.toString(36) + h2.toString(36);
  }
  var idb = {
    open: function () { return new Promise(function (res, rej) { var r = indexedDB.open('favesbuddy', 1); r.onupgradeneeded = function () { r.result.createObjectStore('kv'); }; r.onsuccess = function () { res(r.result); }; r.onerror = rej; }); },
    get: function (k) { return idb.open().then(function (db) { return new Promise(function (res) { var q = db.transaction('kv').objectStore('kv').get(k); q.onsuccess = function () { res(q.result); }; q.onerror = function () { res(null); }; }); }).catch(function () { return null; }); },
    set: function (k, v) { return idb.open().then(function (db) { return new Promise(function (res) { var t = db.transaction('kv', 'readwrite'); t.objectStore('kv').put(v, k); t.oncomplete = res; t.onerror = res; }); }).catch(function () {}); }
  };
  var IMG = /\.(png|jpe?g|webp|heic|gif)$/i;

  function shotsMode(view) {
    var list = [], hidden = [], queue = Promise.resolve(), folder = null;
    var canFolder = !!window.showDirectoryPicker && !isPhone();
    function frame() {
      view.innerHTML = '<div class="ui-wrap td-wrap"><div class="ui-page-head"><div><a class="ui-btn ghost sm" href="#tidy" data-go="tidy">' + UI.icon('back') + 'Tidy up</a><h1>Sweep my screenshots</h1>' +
        '<p class="muted">Each one is read on this device (free, private: the picture doesn\'t leave your phone for this), then sorted. Keep the useful ones, skip the rest. Skipped ones won\'t show up again.</p></div></div>' +
        '<div class="fb-panel ui-stack"><div class="td-src"><label class="ui-btn primary lg">' + UI.icon('image') + 'Choose screenshots<input type="file" accept="image/*" multiple hidden data-files></label>' +
        (canFolder ? '<button class="ui-btn" data-folder>' + UI.icon('layers') + 'Choose a folder</button><span data-folderbox></span>' : '') + '</div>' +
        '<label class="ui-check small"><input type="checkbox" data-ocr ' + (UI.store.get('tidy.ocr', true) ? 'checked' : '') + '> Read the text in them (the first time downloads the reader, about 10 MB)</label>' +
        '<p class="muted small" data-seenline style="margin:0"></p>' +
        (isPhone() ? '<p class="muted small" style="margin:0">' + (platform() === 'ios' ? 'Tip: in the picker, open <b>Albums → Screenshots</b> and select a batch.' : 'Tip: in the picker, open the <b>Screenshots</b> album and select a batch, or share them from Photos to Faves Buddy.') + '</p>' : '') +
        '</div><div data-summary></div><div class="td-shots" data-shots></div></div>';
      if (canFolder) idb.get('shots.folder').then(function (h) { folder = h || null; folderBox(); });
      UI.apiQuiet('shots_seen', []).then(function (r) { seenLine(r.total_seen); });
    }
    function seenLine(n) {
      var el = view.querySelector('[data-seenline]');
      if (el) el.innerHTML = n ? UI.plural(n, 'screenshot') + ' looked at before will be skipped. <button class="ui-btn ghost sm" data-forget>Show them again next time</button>' : '';
    }
    function folderBox() {
      var b = view.querySelector('[data-folderbox]');
      if (b) b.innerHTML = folder ? '<button class="ui-btn" data-recheck>' + UI.icon('refresh') + 'Check “' + esc(folder.name) + '” for new ones</button>' : '';
    }
    function summary() {
      var n = function (s) { return list.filter(function (x) { return x.status === s; }).length; };
      var ready = n('ready'), busy = n('queued') + n('reading'), kept = n('kept') + n('later'), skipped = n('skipped');
      var el = view.querySelector('[data-summary]'); if (!el) return;
      el.innerHTML = list.length || hidden.length ? '<div class="td-summary"><span class="grow">' + [ready ? '<b>' + ready + ' ready</b>' : '', busy ? busy + ' reading' : '', kept ? kept + ' kept' : '', skipped ? skipped + ' skipped' : ''].filter(Boolean).join(' · ') +
        (hidden.length ? ' · ' + hidden.length + ' seen before, hidden <button class="ui-btn ghost sm" data-showhidden>Show</button>' : '') + '</span>' +
        (ready > 1 ? '<button class="ui-btn sm primary" data-keepall>' + UI.icon('check') + 'Keep all ' + ready + ' as sorted</button>' : '') + '</div>' : '';
    }
    function add(entries) {
      if (!entries.length) return;
      var fps = entries.map(function (e) { return e.fp; }).filter(Boolean);
      (fps.length ? UI.apiQuiet('shots_seen', fps) : Promise.resolve({ seen: [] })).then(function (r) {
        var seen = r.seen || [];
        entries.forEach(function (e) {
          if (e.fp && seen.indexOf(e.fp) >= 0) { hidden.push(e); return; }
          if (list.some(function (x) { return x.fp && x.fp === e.fp; })) return;
          enqueue(e);
        });
        if (!list.length && hidden.length) UI.toast('You looked at all of these before. Tap Show to see them again.');
        if (!list.length && !hidden.length) UI.toast('No pictures in that choice.');
        summary();
      });
    }
    function enqueue(e) {
      e.key = 'k' + Math.random().toString(36).slice(2); e.status = 'queued'; list.push(e);
      view.querySelector('[data-shots]').insertAdjacentHTML('beforeend', '<div class="td-shot" data-k="' + e.key + '"></div>');
      draw(e);
      queue = queue.then(function () { return read(e); }).catch(function (err) { e.status = 'error'; e.err = err && err.message || 'That one didn\'t work.'; draw(e); summary(); });
    }
    function read(e) {
      e.status = 'reading'; e.step = 'Getting it ready…'; draw(e);
      return Promise.all([FB.media.shrink(e.file, 1600), FB.media.exif(e.file)]).then(function (r) {
        e.shot = r[0].dataUrl; e.exif = r[1]; draw(e);
        if (!view.querySelector('[data-ocr]') || !view.querySelector('[data-ocr]').checked) return '';
        return FB.media.ocr(e.shot, function (s, p) {
          var bar = view.querySelector('[data-k="' + e.key + '"] .fv-progress i'); if (bar) bar.style.width = Math.round(p * 100) + '%';
          var st = view.querySelector('[data-k="' + e.key + '"] .st'); if (st) st.textContent = s === 'recognizing text' ? 'Reading the text…' : 'Getting the reader ready (first time only)…';
        });
      }).then(function (text) {
        e.text = text || ''; e.found = FB.media.extract(e.text);
        return UI.apiQuiet('shot_sort', e.text, e.name, e.found);
      }).then(function (s) {
        e.sort = s; e.title = s.title; e.pick = null; e.useUrl = !!s.url; e.status = 'ready'; e.file = null;
        draw(e); summary();
      });
    }
    function draw(e) {
      var el = view.querySelector('[data-k="' + e.key + '"]'); if (!el) return;
      var img = e.shot ? '<img src="' + e.shot + '" alt="">' : '<div class="ph"></div>';
      el.className = 'td-shot' + (e.status === 'kept' || e.status === 'later' ? ' done' : e.status === 'skipped' ? ' done skipped' : '');
      if (e.status === 'queued' || e.status === 'reading') { el.innerHTML = img + '<div class="body"><b>' + esc(e.name) + '</b><div class="st">' + (e.status === 'queued' ? 'Waiting its turn…' : esc(e.step)) + '</div><div class="fv-progress"><i></i></div></div>'; return; }
      if (e.status === 'error') { el.innerHTML = img + '<div class="body"><b>' + esc(e.name) + '</b><div class="st">' + esc(e.err) + '</div></div>'; return; }
      if (e.status === 'kept' || e.status === 'later') { el.innerHTML = img + '<div class="body"><span>' + UI.icon('check') + ' <a href="#fave/' + esc(e.fave.id) + '">' + esc(e.fave.title) + '</a> <span class="muted small">' + (e.status === 'kept' ? 'kept in ' + esc(FB.cat(e.fave.cat).emoji + ' ' + FB.cat(e.fave.cat).name) : 'in your inbox') + (e.fave.saved_before ? ' (already saved: added the screenshot)' : '') + '</span></span></div>'; return; }
      if (e.status === 'skipped') { el.innerHTML = img + '<div class="body"><span class="muted small">Skipped ' + esc(e.title || e.name) + '</span></div>'; return; }
      var s = e.sort, cat = e.pick || s.cat, found = FB.media.foundCount(e.found);
      el.innerHTML = img + '<div class="body"><input class="title" type="text" value="' + esc(e.title) + '" data-title aria-label="Title" maxlength="200">' +
        '<div class="fb-why">' + (s.cat !== 'other' ? FB.catChip(s.cat) + ' ' + pct(s.conf) + ' sure: ' : '') + (s.reasons || []).map(function (x) { return '<span class="fb-tag">' + esc(x) + '</span>'; }).join('') + '</div>' +
        '<div class="td-cats">' + FB.CATS.map(function (k) { return '<button type="button" class="fb-chip sm' + (k.id === cat ? ' on' : '') + '" data-scat="' + k.id + '">' + k.emoji + ' ' + esc(k.name) + '</button>'; }).join('') + '</div>' +
        (s.url ? '<label class="ui-check small"><input type="checkbox" data-useurl' + (e.useUrl ? ' checked' : '') + '> Link it to <b>' + esc(s.url.replace(/^https?:\/\//, '').slice(0, 60)) + '</b> (found in it)</label>' : '') +
        (found ? '<details><summary class="small muted">Found ' + UI.plural(found, 'useful bit') + '</summary>' + FB.media.foundHtml(e.found) + '</details>' : '') +
        (e.text ? '<div class="td-ocr">' + esc(e.text.slice(0, 400)) + '</div>' : '') +
        '<div class="acts"><button class="ui-btn primary" data-keep>' + UI.icon('heart') + (cat === 'other' ? 'Keep' : 'Keep in ' + esc(FB.cat(cat).emoji + ' ' + FB.cat(cat).name)) + '</button>' +
        '<button class="ui-btn" data-later>' + UI.icon('inbox') + 'Later</button><button class="ui-btn ghost" data-skip>' + UI.icon('x') + 'Skip</button></div></div>';
    }
    function entryOf(el) { var k = el.closest('[data-k]'); return k && list.find(function (x) { return x.key === k.getAttribute('data-k'); }); }
    function keep(e, later, btn) {
      var t = view.querySelector('[data-k="' + e.key + '"] [data-title]');
      if (t) e.title = t.value.trim() || e.title;
      var cat = e.pick || e.sort.cat;
      var f = { photo: e.drop_id ? null : e.shot, drop_id: e.drop_id || null, title: e.title, category: later || cat === 'other' ? null : cat, ocr: e.text, found: e.found,
        exif: e.exif || {}, url: e.useUrl ? e.sort.url : null, fp: e.fp || null, source: e.drop_id ? 'share' : 'screenshot' };
      return UI.busy(btn, UI.apiQuiet('shot_save', f)).then(function (r) {
        e.fave = Object.assign(r.fave, { saved_before: !r.created }); e.status = later || cat === 'other' ? 'later' : 'kept'; draw(e); summary();
      }, function (err) { UI.toast(err.message || 'Couldn\'t save that one.', 'error'); });
    }
    function skip(e) {
      e.status = 'skipped'; draw(e); summary();
      UI.apiQuiet('shots_skip', e.fp ? [e.fp] : [], e.drop_id ? [e.drop_id] : []).catch(function () {});
    }
    function fromFolder(handle, ask) {
      var perm = handle.queryPermission ? handle.queryPermission({ mode: 'read' }) : Promise.resolve('granted');
      return perm.then(function (p) { return p === 'granted' || !ask ? p : handle.requestPermission({ mode: 'read' }); }).then(function (p) {
        if (p !== 'granted') throw Object.assign(new Error('Faves Buddy needs permission to look in that folder.'), { uiApi: true });
        var files = [], it = handle.values(), step = function () {
          return it.next().then(function (n) {
            if (n.done) return files;
            if (n.value.kind === 'file' && IMG.test(n.value.name)) return n.value.getFile().then(function (f) { files.push(f); return step(); });
            return step();
          });
        };
        return step();
      }).then(function (files) {
        files.sort(function (a, b) { return b.lastModified - a.lastModified; });
        UI.toast(UI.plural(files.length, 'picture') + ' in “' + handle.name + '”. Showing the newest ones you haven\'t looked at.');
        add(files.slice(0, 120).map(function (f) { return { file: f, name: f.name, fp: fpOf(f) }; }));
      });
    }

    view.addEventListener('change', function (ev) {
      if (ev.target.matches('[data-files]')) {
        var files = Array.prototype.slice.call(ev.target.files || []).filter(function (f) { return /^image\//.test(f.type) || IMG.test(f.name); });
        add(files.map(function (f) { return { file: f, name: f.name, fp: fpOf(f) }; }));
        ev.target.value = '';
      }
      if (ev.target.matches('[data-ocr]')) UI.store.set('tidy.ocr', ev.target.checked);
      if (ev.target.matches('[data-useurl]')) { var e = entryOf(ev.target); if (e) e.useUrl = ev.target.checked; }
    });
    view.addEventListener('input', function (ev) { if (ev.target.matches('[data-title]')) { var e = entryOf(ev.target); if (e) e.title = ev.target.value; } });
    view.addEventListener('click', function (ev) {
      var b = ev.target.closest('button'); if (!b || !view.contains(b)) return;
      var e = entryOf(b);
      if (b.hasAttribute('data-scat') && e) { e.pick = b.getAttribute('data-scat'); var t = view.querySelector('[data-k="' + e.key + '"] [data-title]'); if (t) e.title = t.value; draw(e); return; }
      if (b.hasAttribute('data-keep') && e) { keep(e, false, b); return; }
      if (b.hasAttribute('data-later') && e) { keep(e, true, b); return; }
      if (b.hasAttribute('data-skip') && e) { skip(e); return; }
      if (b.hasAttribute('data-keepall')) {
        var ready = list.filter(function (x) { return x.status === 'ready'; });
        UI.busy(b, ready.reduce(function (p, x) { return p.then(function () { return keep(x, false); }); }, Promise.resolve())).then(function () { UI.toast(UI.plural(ready.length, 'screenshot') + ' kept.', 'ok'); });
        return;
      }
      if (b.hasAttribute('data-showhidden')) { var h = hidden; hidden = []; h.forEach(enqueue); summary(); return; }
      if (b.hasAttribute('data-forget')) { UI.api('shots_forget').then(function () { seenLine(0); UI.toast('Next time, every screenshot shows again.', 'ok'); }); return; }
      if (b.hasAttribute('data-folder')) {
        window.showDirectoryPicker({ id: 'fb-shots', mode: 'read', startIn: 'pictures' }).then(function (hd) {
          folder = hd; idb.set('shots.folder', hd); folderBox(); return fromFolder(hd, false);
        }).catch(function (err) { if (err && err.name !== 'AbortError') UI.toast(err.message || 'Couldn\'t open that folder.', 'error'); });
        return;
      }
      if (b.hasAttribute('data-recheck') && folder) { fromFolder(folder, true).catch(function (err) { UI.toast(err.message || 'Couldn\'t open that folder.', 'error'); }); }
    });

    frame();
    return FB.boot().then(function () {
      if (incoming && incoming.photos && incoming.photos.length && !incoming.photosTaken) {
        incoming.photosTaken = true;
        incoming.photos.forEach(function (p) {
          var e = { name: p.name || 'Shared picture', drop_id: p.id, fp: null };
          e.file = null;
          e.load = fetch(p.image).then(function (r) { return r.blob(); });
          e.key = null;
          enqueueDrop(e);
        });
      }
    });
    function enqueueDrop(e) {
      e.key = 'k' + Math.random().toString(36).slice(2); e.status = 'queued'; list.push(e);
      view.querySelector('[data-shots]').insertAdjacentHTML('beforeend', '<div class="td-shot" data-k="' + e.key + '"></div>');
      draw(e); summary();
      queue = queue.then(function () { return e.load.then(function (blob) { e.file = blob; return read(e); }); })
        .catch(function (err) { e.status = 'error'; e.err = err && err.message || 'That shared picture couldn\'t be opened.'; draw(e); summary(); });
    }
  }

  /* ------------------------------------------------------------------ pages */
  UI.page('tidy', { title: 'Tidy up', auth: 'user' }, function (view, ctx) {
    var mode = ctx.args[0];
    if (mode === 'tabs') return tabsMode(view);
    if (mode === 'shots') return shotsMode(view);
    return hub(view);
  });

  UI.page('share', { title: 'Shared with Faves Buddy', auth: 'user' }, function (view, ctx) {
    var code = ctx.args[0] || '';
    view.innerHTML = '<div class="ui-wrap td-wrap"><div class="ui-skel" style="height:220px;margin-top:30px"></div></div>';
    return UI.apiQuiet('drop_open', code).then(function (r) {
      incoming = r;
      if (r.links.length) { UI.store.set('tidy.tabs', null); setTimeout(function () { UI.go('tidy', 'tabs'); }); return; }
      if (r.photos.length) { setTimeout(function () { UI.go('tidy', 'shots'); }); return; }
      var lines = (r.note || '').split('\n'), title = lines[0].slice(0, 200), rest = lines.slice(1).join('\n').trim();
      view.innerHTML = '<div class="ui-wrap td-wrap" style="max-width:640px"><div class="ui-page-head"><div><h1>Save this?</h1><p class="muted">You shared some text with Faves Buddy.</p></div></div>' +
        '<form class="fb-panel ui-stack" data-noteform><label class="ui-field"><span>Title</span><input name="title" maxlength="200" required value="' + esc(title) + '"></label>' +
        '<label class="ui-field"><span>Details</span><textarea name="note" rows="5" maxlength="4000">' + esc(rest) + '</textarea></label>' +
        '<div class="ui-row end"><button type="button" class="ui-btn ghost" data-drop-no>Don\'t save</button><button class="ui-btn primary" type="submit">' + UI.icon('heart') + 'Save as a note</button></div></form></div>';
      view.querySelector('[data-noteform]').addEventListener('submit', function (e) {
        e.preventDefault();
        var v = UI.formData(e.target);
        UI.busy(e.target.querySelector('[type=submit]'), UI.api('save_fave', { title: v.title, note: v.note, kind: 'note', source: 'share' })).then(function (s) {
          UI.apiQuiet('drop_discard', code); var c = FB.cat(s.fave.cat); UI.toast('Saved as ' + c.emoji + ' ' + c.name, 'ok'); UI.go('fave', s.fave.id);
        });
      });
      view.querySelector('[data-drop-no]').addEventListener('click', function () { UI.apiQuiet('drop_discard', code).then(function () { UI.go('tidy'); }); });
    }, function (err) {
      view.innerHTML = '<div class="ui-wrap td-wrap"><div class="fb-panel td-done"><div class="big">🤷</div><h2>Nothing to tidy here</h2><p class="muted">' + esc(err.message || 'That share has already been tidied, or it expired.') + '</p>' +
        '<a class="ui-btn primary" href="#tidy" data-go="tidy">Tidy up</a></div></div>';
    });
  });

  /* The hub's buttons that live outside a mode (install, discard). */
  document.addEventListener('click', function (e) {
    var ins = e.target.closest('[data-install]');
    if (ins && window.fbInstallPrompt) {
      window.fbInstallPrompt.prompt();
      window.fbInstallPrompt.userChoice.then(function (c) { if (c.outcome === 'accepted') { UI.toast('Installed. Faves Buddy is now in your share menu.', 'ok'); ins.remove(); } });
      window.fbInstallPrompt = null;
    }
    var d = e.target.closest('[data-discard]');
    if (d) UI.confirm({ title: 'Throw this shared pile away?', ok: 'Throw away', danger: true }).then(function (yes) {
      if (yes) UI.api('drop_discard', d.getAttribute('data-discard')).then(function () { d.closest('.td-wait-row').remove(); });
    });
  });
})();

/* ===== tools.html ===== */
(function () {
  var esc = UI.esc, TM_KEY = 'favesbuddy.tm';
  var SECS = [['extension', 'Browser extension', 'puzzle'], ['phone', 'On your phone', 'phone'], ['import', 'Import', 'upload'], ['export', 'Export', 'download'], ['ai', 'AI (your key)', 'wand'],
              ['events', 'Events key', 'ticket'], ['home', 'Home spot', 'pin'], ['learned', 'What it learned', 'sparkle'], ['samples', 'Sample faves', 'grid']];

  /* ---------------------------------------------------------------- import parsers (all in the browser) */
  var P = {};
  P.bookmarks = function (html) {
    var doc = new DOMParser().parseFromString(html, 'text/html'), out = [];
    doc.querySelectorAll('a[href]').forEach(function (a) {
      var href = a.getAttribute('href'); if (!/^https?:/i.test(href)) return;
      var folders = [], el = a.parentElement;
      while (el) { if (el.tagName === 'DL') { var h = el.previousElementSibling; if (h && h.tagName === 'H3') folders.unshift(h.textContent.trim()); } el = el.parentElement; }
      folders = folders.filter(function (f) { return !/^(bookmarks( bar| menu| toolbar)?|other bookmarks|barre de favoris|favoris|autres favoris|mobile bookmarks)$/i.test(f); });
      out.push({ url: href, title: a.textContent.trim(), tags: folders.slice(-2).map(function (f) { return f.toLowerCase().slice(0, 30); }) });
    });
    return out;
  };
  P.onetab = function (text) {
    return text.split(/\r?\n/).map(function (l) { var m = l.match(/^(https?:\/\/\S+)\s*\|\s*(.*)$/); return m ? { url: m[1], title: m[2].trim() } : null; }).filter(Boolean);
  };
  P.csvRows = function (text) {
    var rows = [], row = [], cell = '', q = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (q) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch; }
      else if (ch === '"') q = true; else if (ch === ',') { row.push(cell); cell = ''; }
      else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
      else cell += ch;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows.filter(function (r) { return r.some(function (c) { return c.trim(); }); });
  };
  P.csv = function (text) {
    var rows = P.csvRows(text); if (rows.length < 2) return [];
    var h = rows[0].map(function (x) { return x.trim().toLowerCase(); }), col = function (n) { return h.indexOf(n); };
    var iu = col('url'), it = col('title'), itags = col('tags'), inote = col('note'), icom = col('comment'), ilat = col('lat'), ilng = col('lng');
    if (iu < 0 && it < 0) return [];
    return rows.slice(1).map(function (r) {
      var o = { url: iu >= 0 ? (r[iu] || '').trim() : '', title: it >= 0 ? (r[it] || '').trim() : '' };
      if (itags >= 0 && r[itags]) o.tags = r[itags].split(/[|,]/).map(function (t) { return t.trim().toLowerCase(); }).filter(Boolean).slice(0, 5);
      var note = [inote >= 0 ? r[inote] : '', icom >= 0 ? r[icom] : ''].filter(Boolean).join('\n').trim(); if (note) o.note = note;
      if (ilat >= 0 && ilng >= 0 && r[ilat]) { o.lat = +r[ilat]; o.lng = +r[ilng]; }
      return o;
    }).filter(function (o) { return o.url || o.title; });
  };
  P.geojson = function (j) {
    return (j.features || []).map(function (f) {
      var p = f.properties || {}, g = (f.geometry || {}).coordinates || [], loc = p.location || p.Location || {};
      var o = { title: p.Title || p.title || loc.name || loc['Business Name'] || p.name || '', url: p.google_maps_url || p['Google Maps URL'] || '',
                address: loc.address || loc.Address || '', note: p.Comment || p.comment || '' };
      if (g.length >= 2 && (g[0] || g[1])) { o.lng = g[0]; o.lat = g[1]; }
      var gc = loc['Geo Coordinates']; if (gc && gc.Latitude) { o.lat = +gc.Latitude; o.lng = +gc.Longitude; }
      if (!o.url && o.lat == null) return null;
      return o;
    }).filter(Boolean);
  };
  P.links = function (text) {
    var seen = {}, out = [];
    (text.match(/https?:\/\/[^\s<>"')]+/g) || []).forEach(function (u) { u = u.replace(/[.,;)]+$/, ''); if (!seen[u]) { seen[u] = 1; out.push({ url: u }); } });
    return out;
  };
  P.detect = function (name, text) {
    var low = name.toLowerCase();
    if (/<!doctype netscape-bookmark|<dl>/i.test(text.slice(0, 3000))) return ['Bookmarks file (Chrome, Firefox, Safari, Edge)', P.bookmarks(text)];
    if (/\.(geo)?json$/.test(low) || /^\s*[{[]/.test(text)) {
      try {
        var j = JSON.parse(text);
        if (j.type === 'FeatureCollection') return ['Google Takeout saved places', P.geojson(j)];
        if (j.faves) return ['Faves Buddy export', j.faves.map(function (f) { return { url: f.url, title: f.title, note: f.note, tags: f.tags, lat: f.lat, lng: f.lng, address: f.address, kind: f.kind, category: f.cat !== 'other' ? f.cat : null }; })];
      } catch (e) {}
    }
    if (/\.csv$/.test(low) || /^[^\n]*\b(url|title)\b[^\n]*,/i.test(text.slice(0, 300))) {
      var rows = P.csv(text);
      if (rows.length) return [/time_added/.test(text.slice(0, 200)) ? 'Pocket export' : /comment/i.test(text.slice(0, 120)) ? 'Google Maps saved list' : 'Spreadsheet (CSV)', rows];
    }
    var ot = P.onetab(text);
    if (ot.length) return ['OneTab export', ot];
    return ['Links', P.links(text)];
  };

  UI.page('tools', { title: 'Tools', auth: 'user' }, function (view, ctx) {
    var sec = SECS.some(function (s) { return s[0] === ctx.args[0]; }) ? ctx.args[0] : 'extension';
    var pendingImport = null;
    view.innerHTML = '<div class="ui-wrap"><div class="ui-page-head"><div><h1>Tools</h1><p class="muted">Bring your stuff in, take it out, and plug in the extras.</p></div></div>' +
      '<div class="tl-layout"><nav class="tl-nav">' + SECS.map(function (s) { return '<a href="#tools/' + s[0] + '" class="' + (s[0] === sec ? 'on' : '') + '">' + UI.icon(s[2]) + s[1] + '</a>'; }).join('') +
      '</nav><div class="tl-sec" data-sec><div class="ui-skel"></div></div></div></div>';
    var box = view.querySelector('[data-sec]');

    var DRAW = {
      extension: function () {
        return UI.api('clip_info').then(function (d) {
          box.innerHTML = '<div class="fb-panel"><h2>Faves Buddy for Chrome</h2><p class="muted">Save the tab you\'re on, a whole window of tabs (and close them), a link, a picture or selected text, from the toolbar or the right-click menu. Works in Chrome, Edge, Brave and Arc.</p>' +
            '<ol class="tl-steps" style="margin-top:16px"><li><a class="ui-btn primary sm" href="_/theme/faves-buddy-extension.zip" download>' + UI.icon('download') + 'Download the extension (.zip)</a> and unzip it.</li>' +
            '<li>Open <b>chrome://extensions</b>, switch on <b>Developer mode</b> (top right), click <b>Load unpacked</b> and pick the unzipped folder.</li>' +
            '<li>Pin it (the puzzle icon → pin), click it, and paste your connection code below.</li></ol>' +
            '<p class="muted small" style="margin-top:14px">Shortcuts once installed: <b>Alt+Shift+S</b> saves this tab, <b>Alt+Shift+W</b> saves the whole window.</p></div>' +
            '<div class="fb-panel"><h3>Your connection code</h3><p class="muted small">It lets the extension save into your account. Treat it like a password; anyone with it can add faves (but can\'t read them).</p>' +
            '<div class="tl-code" data-code>' + esc(d.code) + '</div><div class="ui-row" style="margin-top:12px"><button class="ui-btn primary" data-copy-code>' + UI.icon('copy') + 'Copy code</button>' +
            '<button class="ui-btn" data-rotate>' + UI.icon('refresh') + 'Make a new code</button><span class="muted small">' + UI.plural(d.saved, 'fave') + ' saved from the extension so far</span></div>' +
            '<p class="muted small" style="margin-top:10px">Making a new code disconnects every browser that used the old one.</p></div>';
        });
      },
      import: function () {
        box.innerHTML = '<div class="fb-panel"><h2>Import</h2><p class="muted">Drop a file. Everything lands in your inbox, sorted; links are read in the background so a big import is quick. Duplicates are merged.</p>' +
          '<label class="ad-drop" data-drop style="margin-top:14px">' + UI.icon('upload') + '<b>Drop a file here, or tap to choose</b><span class="muted small">.html bookmarks, OneTab .txt, Pocket .csv, Google Takeout .json / .csv, or any text with links</span><input type="file" hidden data-file accept=".html,.htm,.txt,.csv,.json,.geojson"></label>' +
          '<details style="margin-top:14px"><summary class="muted small" style="cursor:pointer">Or paste links / OneTab text</summary><textarea data-paste rows="5" style="margin-top:10px" placeholder="https://… one per line, or OneTab\'s “url | title” lines"></textarea><button class="ui-btn sm" data-parse-paste style="margin-top:8px">Read the text</button></details>' +
          '<div data-import-preview style="margin-top:16px"></div></div>' +
          '<div class="fb-panel"><h3>Where to find your exports</h3><div class="tl-formats">' +
          '<div><b>Chrome bookmarks</b>Bookmarks manager (Ctrl+Shift+O) → ⋮ → Export bookmarks. Folders become tags.</div>' +
          '<div><b>OneTab</b>OneTab → Export / Import URLs → copy the text.</div>' +
          '<div><b>Pocket</b>Your Pocket export CSV (title, url, tags).</div>' +
          '<div><b>Google Maps</b>takeout.google.com → “Maps (your places)” or “Saved” → Saved Places.json or a list\'s .csv.</div>' +
          '<div><b>Safari / Firefox</b>File → Export bookmarks (HTML).</div><div><b>Anything else</b>A text or CSV file with links in it.</div></div></div>';
        var drop = box.querySelector('[data-drop]');
        drop.addEventListener('dragover', function (e) { e.preventDefault(); drop.classList.add('over'); });
        drop.addEventListener('dragleave', function () { drop.classList.remove('over'); });
        drop.addEventListener('drop', function (e) { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]); });
        return Promise.resolve();
      },
      export: function () {
        box.innerHTML = '<div class="fb-panel"><h2>Export</h2><p class="muted">Your faves are yours. Take them anywhere, anytime.</p><div class="ui-row" style="margin-top:12px">' +
          '<button class="ui-btn" data-exp="json">' + UI.icon('download') + 'Everything (JSON)</button><button class="ui-btn" data-exp="csv">' + UI.icon('download') + 'Spreadsheet (CSV)</button>' +
          '<button class="ui-btn" data-exp="geojson">' + UI.icon('download') + 'Places (GeoJSON)</button><button class="ui-btn" data-exp="html">' + UI.icon('download') + 'Bookmarks (HTML)</button></div>' +
          '<p class="muted small" style="margin-top:12px">GeoJSON opens in Google My Maps, QGIS or uMap. The bookmarks file imports into any browser, with a folder per category.</p></div>';
        return Promise.resolve();
      },
      phone: function () {
        box.innerHTML = '<div class="fb-panel"><h2>Faves Buddy on your phone</h2><p class="muted">Open Faves Buddy in your phone’s browser and sign in. Then:</p>' +
          '<ul class="ui-stack" style="padding-left:20px"><li><b>Android:</b> install it (Chrome menu ⋮ → <b>Add to Home screen</b>). It then appears in the share sheet: share a pile of Chrome tabs (tab switcher → <b>Select tabs</b> → ⋮ → <b>Share tabs</b>) or a batch of screenshots from Photos, and swipe through them here.</li>' +
          '<li><b>iPhone:</b> Safari <b>Share → Add to Home Screen</b>. For tabs, use Safari’s <b>Copy N Links</b> and paste them in <b>Tidy my open tabs</b>; for screenshots, pick a batch in <b>Sweep my screenshots</b>.</li>' +
          '<li><b>From a computer:</b> the Chrome extension lists the tabs open on your phone’s Chrome (with Chrome sync on) under <b>Tabs on your other devices</b>, ready to sort here.</li></ul>' +
          '<div class="ui-row" style="margin-top:14px"><a class="ui-btn primary" href="#tidy" data-go="tidy">' + UI.icon('wand') + 'Open Tidy up</a>' +
          '<button class="ui-btn" data-copy-link>' + UI.icon('copy') + 'Copy the app’s address</button></div></div>';
        return Promise.resolve();
      },
      ai: function () {
        var a = FB.ai.get(), s = FB.aiSort || {};
        var sortBlock = '<div class="fb-panel" style="margin-bottom:18px"><div class="ui-row" style="justify-content:space-between"><h2 style="margin:0">AI second opinion for sorting</h2><span class="ui-badge brand">In progress</span></div>' +
          '<p class="muted">The sorter works without AI. When this is on, the items it isn’t sure about get a second opinion from Claude in your inbox, with a one-line reason. It only suggests; you still choose. ' +
          'Only the title, the website, the link’s path and a short bit of text go to Anthropic (no pictures). This uses the app’s own key, not yours.</p>' +
          (s.available ? '<label class="ui-check"><input type="checkbox" data-aisort' + (s.on ? ' checked' : '') + '> Ask the AI about items the sorter isn’t sure of</label>'
            : '<p class="ui-note">' + UI.icon('clock') + ' Coming soon: this is built and being switched on. Nothing is sent to any AI until it is, and you’ll opt in here.</p>') + '</div>';
        box.innerHTML = sortBlock + '<div class="fb-panel"><h2>AI with your own key</h2><p class="muted">Faves Buddy sorts everything without AI. With your own Anthropic API key, it can also describe pictures and screenshots: what they show, the places and dates in them, a better title. ' +
          'The key is stored only in this browser and sent only to Anthropic; our server never sees it or your pictures\' AI requests. You pay Anthropic directly (usually a fraction of a cent per picture).</p>' +
          '<form class="ui-stack" data-aiform style="margin-top:12px"><label class="ui-field"><span>Anthropic API key</span><input type="password" name="key" autocomplete="off" placeholder="sk-ant-…" value="' + esc(a.key || '') + '"></label>' +
          '<label class="ui-field"><span>Model</span><select name="model">' + FB.ai.MODELS.map(function (mm) { return '<option value="' + mm[0] + '"' + (FB.ai.model() === mm[0] ? ' selected' : '') + '>' + mm[1] + ': ' + esc(mm[2]) + '</option>'; }).join('') + '</select></label>' +
          '<div class="ui-row"><button class="ui-btn primary" type="submit">Save</button><button class="ui-btn" type="button" data-ai-test>Test it</button>' + (a.key ? '<button class="ui-btn danger" type="button" data-ai-clear>Remove key</button>' : '') + '</div></form>' +
          '<p class="muted small" style="margin-top:12px">Get a key at console.anthropic.com → API keys. Set a monthly spend limit there for peace of mind.</p></div>';
        return Promise.resolve();
      },
      events: function () {
        var k = ''; try { k = localStorage.getItem(TM_KEY) || ''; } catch (e) {}
        box.innerHTML = '<div class="fb-panel"><h2>Dated events (Ticketmaster)</h2><p class="muted">Discover finds festivals near you from Wikidata with no setup. For concerts, shows and games with dates, add a free Ticketmaster Discovery API key (5,000 searches a day). It stays in this browser and goes only to Ticketmaster.</p>' +
          '<ol class="tl-steps" style="margin:14px 0"><li>Sign up at developer.ticketmaster.com (free).</li><li>Open “My Apps”: copy the <b>Consumer Key</b>.</li><li>Paste it here.</li></ol>' +
          '<form class="ui-row" data-tmform><input type="password" name="key" autocomplete="off" placeholder="Consumer key" value="' + esc(k) + '" style="flex:1;min-width:200px"><button class="ui-btn primary" type="submit">Save</button>' +
          (k ? '<button class="ui-btn danger" type="button" data-tm-clear>Remove</button>' : '') + '</form></div>';
        return Promise.resolve();
      },
      home: function () {
        var h = FB.prefs && FB.prefs.home;
        box.innerHTML = '<div class="fb-panel"><h2>Home spot</h2><p class="muted">Used for distances and Discover when your location isn\'t shared. Only the spot you choose is stored, never your live location.</p>' +
          (h ? '<p><b>' + esc(h.label) + '</b> <span class="muted small">(' + h.lat.toFixed(4) + ', ' + h.lng.toFixed(4) + ')</span></p>' : '<p class="muted">Not set.</p>') +
          '<div class="ui-row"><button class="ui-btn" data-home-here>' + UI.icon('locate') + 'Use where I am now</button>' + (h ? '<button class="ui-btn danger" data-home-clear>Clear</button>' : '') + '</div>' +
          '<form class="ui-row" data-home-search style="margin-top:14px"><input type="search" name="q" placeholder="Or search: a neighbourhood, a street…" style="flex:1;min-width:200px"><button class="ui-btn" type="submit">' + UI.icon('search') + 'Search</button></form>' +
          '<div data-home-results style="margin-top:10px"></div></div>';
        return Promise.resolve();
      },
      learned: function () {
        return UI.api('learned').then(function (d) {
          var row = function (kind) { return function (x) { var c = FB.cat(x.cat); return '<tr><td>' + esc(x.key) + '</td><td>' + c.emoji + ' ' + esc(c.name) + ' <span class="muted small">× ' + x.n + '</span></td><td><button class="ui-btn sm ghost" data-forget="' + kind + '|' + esc(x.key) + '">Forget</button></td></tr>'; }; };
          box.innerHTML = '<div class="fb-panel"><h2>What Faves Buddy learned from you</h2><p class="muted">Each time you keep a fave in a category (or move it), the sorter remembers the website and the words in its title. No AI, no data leaves your account.</p>' +
            '<div class="ui-row" style="gap:28px;margin:14px 0"><div><div class="tl-big">' + d.lessons + '</div><span class="muted small">lessons</span></div>' +
            (d.judged ? '<div><div class="tl-big">' + Math.round(d.right / d.judged * 100) + '%</div><span class="muted small">of first guesses you kept as they were (' + d.right + ' of ' + d.judged + ')</span></div>' : '') + '</div>' +
            (d.domains.length ? '<h3>Websites</h3><table class="tl-table">' + d.domains.map(row('domain')).join('') + '</table>' : '<p class="muted">Nothing yet. Keep a few faves from your inbox and it starts learning.</p>') +
            (d.words.length ? '<h3 style="margin-top:20px">Words</h3><table class="tl-table">' + d.words.slice(0, 25).map(row('word')).join('') + '</table>' : '') +
            (d.lessons ? '<button class="ui-btn danger" data-forget-all style="margin-top:16px">' + UI.icon('trash') + 'Forget everything it learned</button>' : '') + '</div>';
        });
      },
      samples: function () {
        box.innerHTML = '<div class="fb-panel"><h2>Sample faves</h2><p class="muted">About thirty example faves (made-up places around Montréal, recipes, reads, a poster screenshot, a few tabs waiting in the inbox) and three lists. A good way to try everything. Samples never teach the sorter.</p>' +
          '<div class="ui-row" style="margin-top:12px"><button class="ui-btn primary" data-samples-load>' + UI.icon('sparkle') + 'Add sample faves</button><button class="ui-btn danger" data-samples-remove>' + UI.icon('trash') + 'Remove sample faves</button></div></div>';
        return Promise.resolve();
      }
    };

    function readFile(file) {
      if (file.size > 25e6) { UI.toast('That file is over 25 MB. Split it first.', 'error'); return; }
      file.text().then(function (text) { showImport(P.detect(file.name, text), file.name); });
    }
    function showImport(det, name) {
      var kind = det[0], items = det[1].filter(function (i) { return i.url || i.lat != null || i.title; });
      pendingImport = items;
      var out = box.querySelector('[data-import-preview]');
      out.innerHTML = items.length ? '<div class="ui-note"><b>' + esc(kind) + ':</b> ' + UI.plural(items.length, 'item') + ' found' + (items.filter(function (i) { return i.lat != null; }).length ? ' (' + items.filter(function (i) { return i.lat != null; }).length + ' with a map location)' : '') + '.</div>' +
        '<ul class="small muted" style="margin:10px 0">' + items.slice(0, 5).map(function (i) { return '<li>' + esc(i.title || i.url) + '</li>'; }).join('') + (items.length > 5 ? '<li>…</li>' : '') + '</ul>' +
        '<form class="ui-row" data-do-import><input type="text" name="group" value="' + esc((name || kind).replace(/\.[a-z]+$/i, '')) + '" placeholder="Group name (optional)" style="flex:1;min-width:200px">' +
        '<button class="ui-btn primary" type="submit">' + UI.icon('upload') + 'Import ' + items.length + '</button></form><p class="muted small">The group shows under Tab sets, so you can open, keep or remove the whole import at once.</p>'
        : '<div class="ui-error">No links or places found in that file.</div>';
    }
    function doImport(group, btn) {
      var items = pendingImport.slice(), added = 0, again = 0, total = items.length, CH = 300, first = true;
      function next() {
        if (!items.length) return Promise.resolve();
        var chunk = items.splice(0, CH);
        btn.textContent = 'Importing… ' + Math.round((total - items.length) / total * 100) + '%';
        return UI.apiQuiet('import_items', chunk, 'import', first ? group : (group ? group + ' (cont.)' : null)).then(function (r) { first = false; added += r.added; again += r.again; return next(); });
      }
      btn.disabled = true;
      return next().then(function () {
        UI.toast(UI.plural(added, 'new fave') + ' imported' + (again ? ', ' + again + ' already saved' : '') + '. They\'re in your inbox.', 'ok');
        pendingImport = null; UI.go('inbox');
      }, function (e) { btn.disabled = false; btn.textContent = 'Try again'; UI.toast(e.message, 'error'); });
    }
    function exportAs(kind, btn) {
      return UI.busy(btn, UI.api('export_all')).then(function (d) {
        var day = new Date().toISOString().slice(0, 10), fv = d.faves;
        if (kind === 'json') FB.download('faves-buddy-' + day + '.json', JSON.stringify(d, null, 1), 'application/json');
        if (kind === 'csv') {
          var cols = ['title', 'url', 'category_name', 'kind', 'status', 'stage', 'rating', 'tags', 'note', 'address', 'lat', 'lng', 'event_at', 'created'];
          var q = function (v) { v = Array.isArray(v) ? v.join('|') : v == null ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
          FB.download('faves-buddy-' + day + '.csv', cols.join(',') + '\n' + fv.map(function (f) { return cols.map(function (c) { return q(f[c]); }).join(','); }).join('\n'), 'text/csv');
        }
        if (kind === 'geojson') {
          FB.download('faves-buddy-places-' + day + '.geojson', JSON.stringify({ type: 'FeatureCollection', features: fv.filter(function (f) { return f.lat != null; }).map(function (f) {
            return { type: 'Feature', geometry: { type: 'Point', coordinates: [f.lng, f.lat] }, properties: { name: f.title, category: f.category_name, address: f.address, url: f.url, note: f.note, stage: f.stage, tags: f.tags } };
          }) }), 'application/geo+json');
        }
        if (kind === 'html') {
          var by = {}; fv.filter(function (f) { return f.url; }).forEach(function (f) { (by[f.category_name] = by[f.category_name] || []).push(f); });
          var h = '<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n<TITLE>Bookmarks</TITLE>\n<H1>Faves Buddy</H1>\n<DL><p>\n' +
            Object.keys(by).sort().map(function (k) { return '<DT><H3>' + esc(k) + '</H3>\n<DL><p>\n' + by[k].map(function (f) { return '<DT><A HREF="' + esc(f.url) + '" ADD_DATE="' + Math.round(new Date(f.created).getTime() / 1000) + '">' + esc(f.title) + '</A>\n'; }).join('') + '</DL><p>\n'; }).join('') + '</DL><p>\n';
          FB.download('faves-buddy-bookmarks-' + day + '.html', h, 'text/html');
        }
        UI.toast('Downloaded', 'ok');
      });
    }
    view.addEventListener('click', function (e) {
      var t = e.target;
      if (t.closest('[data-copy-link]')) FB.copy(location.origin + '/', 'Address copied. Open it on your phone.');
      if (t.closest('[data-copy-code]')) FB.copy(box.querySelector('[data-code]').textContent, 'Code copied. Paste it in the extension.');
      if (t.closest('[data-rotate]')) UI.confirm({ title: 'Make a new code?', text: 'Browsers using the old code will be disconnected until you paste the new one.', ok: 'New code' })
        .then(function (y) { if (y) UI.api('rotate_clip_token').then(function (r) { box.querySelector('[data-code]').textContent = r.code; UI.toast('New code made', 'ok'); }); });
      if (t.closest('[data-parse-paste]')) { var v = box.querySelector('[data-paste]').value; showImport(P.detect('pasted.txt', v), 'Pasted links'); }
      var ex = t.closest('[data-exp]'); if (ex) exportAs(ex.getAttribute('data-exp'), ex);
      if (t.closest('[data-ai-test]')) {
        var f = box.querySelector('[data-aiform]'); FB.ai.set({ key: f.key.value.trim(), model: f.model.value });
        UI.busy(t.closest('button'), FB.ai.test()).then(function (r) { UI.toast('It works: “' + r.trim() + '”', 'ok'); });
      }
      if (t.closest('[data-ai-clear]')) { FB.ai.clear(); DRAW.ai(); UI.toast('Key removed from this browser', 'ok'); }
      if (t.closest('[data-tm-clear]')) { try { localStorage.removeItem(TM_KEY); } catch (er) {} DRAW.events(); UI.toast('Key removed', 'ok'); }
      if (t.closest('[data-home-here]')) {
        UI.busy(t.closest('button'), FB.geo(true)).then(function (g) {
          if (!g || g.home) { UI.toast('Location isn\'t available. Search instead.', 'error'); return; }
          return UI.api('set_prefs', { lat: g.lat, lng: g.lng, label: 'Home base' }).then(function (r) { FB.prefs.home = r.home; DRAW.home(); UI.toast('Home spot saved', 'ok'); });
        });
      }
      if (t.closest('[data-home-clear]')) UI.api('set_prefs', {}).then(function () { FB.prefs.home = null; DRAW.home(); });
      var hp = t.closest('[data-home-pick]');
      if (hp) { var p = JSON.parse(hp.getAttribute('data-home-pick')); UI.api('set_prefs', { lat: p.lat, lng: p.lng, label: p.title }).then(function (r) { FB.prefs.home = r.home; DRAW.home(); UI.toast('Home spot saved', 'ok'); }); }
      var fg = t.closest('[data-forget]');
      if (fg) { var parts = fg.getAttribute('data-forget').split('|'); UI.api('forget_learned', parts[0], parts.slice(1).join('|')).then(function () { DRAW.learned(); }); }
      if (t.closest('[data-forget-all]')) UI.confirm({ title: 'Forget everything?', text: 'Sorting goes back to the built-in rules. Your faves and their categories stay as they are.', ok: 'Forget', danger: true })
        .then(function (y) { if (y) UI.api('forget_learned').then(function () { DRAW.learned(); UI.toast('Forgotten', 'ok'); }); });
      if (t.closest('[data-samples-load]')) UI.busy(t.closest('button'), UI.api('load_samples')).then(function (r) { UI.toast(r.added ? r.added + ' sample faves added' : 'Samples are already there', 'ok'); });
      if (t.closest('[data-samples-remove]')) UI.busy(t.closest('button'), UI.api('remove_samples')).then(function (r) { UI.toast(UI.plural(r.removed, 'sample') + ' removed', 'ok'); });
    });
    view.addEventListener('change', function (e) {
      if (e.target.matches('[data-file]') && e.target.files[0]) readFile(e.target.files[0]);
      if (e.target.matches('[data-aisort]')) {
        var on = e.target.checked;
        UI.api('set_prefs', null, { ai_sort: on }).then(function () { FB.aiSort.on = on; UI.toast(on ? 'AI second opinion on. Your inbox will show its suggestions.' : 'AI second opinion off.', 'ok'); });
      }
    });
    view.addEventListener('submit', function (e) {
      e.preventDefault();
      var f = e.target;
      if (f.matches('[data-do-import]')) doImport(f.group.value.trim(), f.querySelector('button'));
      if (f.matches('[data-aiform]')) { FB.ai.set({ key: f.key.value.trim(), model: f.model.value }); UI.toast(f.key.value.trim() ? 'Saved in this browser' : 'Key removed', 'ok'); DRAW.ai(); }
      if (f.matches('[data-tmform]')) { try { localStorage.setItem(TM_KEY, f.key.value.trim()); } catch (er) {} UI.toast('Saved in this browser', 'ok'); DRAW.events(); }
      if (f.matches('[data-home-search]')) {
        UI.busy(f.querySelector('button'), FB.data.photon(f.q.value, null, 6)).then(function (res) {
          box.querySelector('[data-home-results]').innerHTML = res.map(function (p) { return '<button class="fb-chip" style="margin:0 6px 6px 0" data-home-pick=\'' + esc(JSON.stringify(p)) + '\'>' + UI.icon('pin') + esc(p.title) + ' <span class="n">' + esc(p.address) + '</span></button>'; }).join('') || '<p class="muted">Nothing found.</p>';
        });
      }
    });
    return FB.boot().then(function () { return DRAW[sec](); });
  });
  window.FB = window.FB || {};
  FB.importParsers = P;  // for tests
})();
