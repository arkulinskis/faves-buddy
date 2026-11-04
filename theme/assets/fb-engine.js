/* fb-engine.js: the browser-side engines the Python Forms call through window.FB (client_code/fb.py wraps them).
   Nothing here builds a page or a list: it draws pictures (a fave's cover), does maths (distances, opening hours),
   talks to browser APIs (location, clipboard, files, folders, installing) and parses/creates files.
     FB.setCats / FB.cat              the 20 categories (fb_boot gives them; Python passes them in)
     FB.drawCover(el, fave, o)         a fave's picture, or a soft gradient tile in its category colour; o.pills adds the
                                       category / date / read-time pills on top
     FB.when / FB.dist / FB.fmtDist / FB.openNow / FB.geo / FB.snoozeChoices
     FB.copy / FB.download / FB.appUrl / FB.share
     FB.importParsers (P.detect)       bookmarks HTML, OneTab, Pocket/Google CSV, Takeout GeoJSON, an export, any links
     FB.exportAs(kind, data)           JSON / CSV / GeoJSON / bookmarks HTML download
     FB.tidy                           swipe cards, clipboard links, screenshot fingerprints, a remembered folder,
                                       platform + install prompt
     FB.confetti, FB.dropZone, FB.onKeys
   The map + open data are in fb-map.js; pictures, OCR and AI in fb-media.js. */
(function () {
  'use strict';
  var FB = window.FB = window.FB || {}, esc = UI.esc;
  FB.CATS = []; FB.CAT = {};
  FB.setCats = function (cats) {
    if (typeof cats === 'string') cats = JSON.parse(cats);
    if (!cats || !cats.length) return;
    FB.CATS = cats; FB.CAT = {}; cats.forEach(function (c) { FB.CAT[c.id] = c; });
  };
  FB.cat = function (id) { return FB.CAT[id] || FB.CAT.other || { id: 'other', name: 'Unsorted', emoji: '📌', color: '#90a4ae' }; };
  /* The category as a small coloured dot + name (map popups). */
  FB.catChip = function (id, cls) {
    var c = FB.cat(id);
    return '<span class="fb-cat ' + (cls || '') + '"><span class="dot" style="background:' + esc(c.color) + '"></span>' + esc(c.emoji) + ' ' + esc(c.name) + '</span>';
  };
  FB.KIND_ICON = { link: 'link', place: 'pin', photo: 'image', note: 'note', idea: 'bulb', event: 'calendar' };

  /* ---------------------------------------------------------------- covers */
  function hash(s) { var h = 0; s = String(s || ''); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); }
  FB.tileHtml = function (f) {
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
  FB.drawCover = function (el, f, o) {
    if (!el) return;
    if (typeof f === 'string') f = JSON.parse(f);
    if (typeof o === 'string') o = JSON.parse(o);
    f = f || {}; o = o || {};
    var c = FB.cat(f.cat), pills = '';
    if (o.pills) {
      pills = '<span class="fb-pill">' + esc(c.emoji) + ' ' + esc(c.name) + '</span>';
      if (f.event_at) pills += '<span class="fb-pill accent">' + UI.icon('calendar') + esc(FB.when(f.event_at, true)) + '</span>';
      else if (f.read_min) pills += '<span class="fb-pill dark">' + f.read_min + ' min</span>';
      pills = '<div class="fb-on-img">' + pills + '</div>';
    }
    el.innerHTML = FB.tileHtml(f) + (f.image ? '<img src="' + esc(f.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : '') + pills;
  };
  /* A list's mosaic: up to three pictures, else tinted squares with its emoji. */
  FB.drawMosaic = function (el, l) {
    if (typeof l === 'string') l = JSON.parse(l);
    var p = (l.preview || []).slice(0, 3), tint = 'color-mix(in srgb,' + esc(l.color || '#5b5bf0') + ' 22%,var(--c-surface-2))';
    el.innerHTML = [0, 1, 2].map(function (i) {
      return p[i] ? '<div style="background-image:url(\'' + esc(p[i]) + '\')"></div>' : '<div class="ph" style="background:' + tint + '">' + (i === 0 ? esc(l.emoji) : '') + '</div>';
    }).join('');
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
  FB.fmtDate = function (iso) { return iso ? new Date(iso.length <= 10 ? iso + 'T12:00:00' : iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : ''; };
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
  /* 'open' | 'closed' | '' (unknown) for Python, which can't tell JS null from false easily. */
  FB.openState = function (spec) { var v = FB.openNow(spec); return v === true ? 'open' : v === false ? 'closed' : ''; };
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

  /* ---------------------------------------------------------------- location
     FB.geo(ask, home): ask=false -> the location shared in the last 10 minutes, else the home spot (or null).
     ask=true asks the browser once. Resolves with a JSON string ("null" when there's nothing) for Python. */
  var geoP = null;
  FB.geo = function (ask, homeJson) {
    var home = homeJson ? JSON.parse(homeJson) : null;
    var fallback = home ? JSON.stringify(Object.assign({ home: true }, home)) : 'null';
    var cached = null;
    try { cached = JSON.parse(sessionStorage.getItem('fb.geo') || 'null'); } catch (e) {}
    if (cached && Date.now() - cached.t < 10 * 60e3) return Promise.resolve(JSON.stringify(cached));
    if (!ask) return Promise.resolve(fallback);
    if (!geoP) {
      geoP = new Promise(function (resolve) {
        if (!navigator.geolocation) return resolve(null);
        navigator.geolocation.getCurrentPosition(function (p) {
          var g = { lat: p.coords.latitude, lng: p.coords.longitude, t: Date.now(), label: 'You are here' };
          try { sessionStorage.setItem('fb.geo', JSON.stringify(g)); } catch (e) {}
          resolve(g);
        }, function () { resolve(null); }, { enableHighAccuracy: false, timeout: 9000, maximumAge: 300000 });
      }).then(function (g) { geoP = null; return g ? JSON.stringify(g) : fallback; });
    }
    return geoP;
  };

  FB.snoozeChoices = function () {
    var now = new Date(), out = [];
    var tonight = new Date(now); tonight.setHours(19, 0, 0, 0); if (tonight <= now) tonight.setDate(tonight.getDate() + 1);
    var sat = new Date(now); sat.setDate(now.getDate() + ((6 - now.getDay() + 7) % 7 || 7)); sat.setHours(9, 0, 0, 0);
    var week = new Date(now); week.setDate(now.getDate() + ((8 - now.getDay()) % 7 || 7)); week.setHours(9, 0, 0, 0);
    var month = new Date(now); month.setMonth(now.getMonth() + 1); month.setHours(9, 0, 0, 0);
    out.push(['Tonight', tonight], ['This weekend', sat], ['Next week', week], ['In a month', month]);
    return JSON.stringify(out.map(function (x) { return [x[0], x[1].toISOString(), x[1].toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })]; }));
  };

  /* ---------------------------------------------------------------- copy, download, share */
  FB.copy = function (text) {
    function fallback() { var t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); var ok = false; try { ok = document.execCommand('copy'); } catch (e) {} t.remove(); return ok; }
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallback(); });
    return Promise.resolve(fallback());
  };
  FB.appUrl = function (hash) { return location.origin + location.pathname + hash; };
  FB.download = function (name, text, type) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: type || 'text/plain' }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  };
  /* The phone's own share sheet when there is one. Resolves 'shared', 'cancelled' or 'unsupported'. */
  FB.canShare = function () { return !!navigator.share; };
  FB.share = function (title, text, url) {
    if (!navigator.share) return Promise.resolve('unsupported');
    return navigator.share({ title: title, text: text, url: url }).then(function () { return 'shared'; }, function () { return 'cancelled'; });
  };

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
  FB.importParsers = P;
  /* For Python: JSON {kind, items} (items keep only what has a url, a place or a title). */
  FB.detectImport = function (name, text) {
    var d = P.detect(name, text);
    return JSON.stringify({ kind: d[0], items: d[1].filter(function (i) { return i.url || i.lat != null || i.title; }) });
  };
  FB.readText = function (file) {
    if (file.size > 25e6) return Promise.reject(new Error('That file is over 25 MB. Split it first.'));
    return file.text();
  };

  /* ---------------------------------------------------------------- export */
  FB.exportAs = function (kind, dataJson) {
    var d = typeof dataJson === 'string' ? JSON.parse(dataJson) : dataJson;
    var day = new Date().toISOString().slice(0, 10), fv = d.faves || [];
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
  };

  /* ---------------------------------------------------------------- small shared effects */
  FB.confetti = function () {
    if (UI.reducedMotion && UI.reducedMotion()) return;
    var box = document.createElement('div'); box.className = 'ib-confetti';
    var colors = ['#5b5bf0', '#ff6f61', '#ffb300', '#26a69a', '#ec407a', '#42a5f5'];
    for (var i = 0; i < 70; i++) {
      var p = document.createElement('i');
      p.style.left = Math.random() * 100 + 'vw'; p.style.background = colors[i % colors.length];
      p.style.animationDelay = Math.random() * .6 + 's'; p.style.animationDuration = 1.8 + Math.random() * 1.4 + 's';
      box.appendChild(p);
    }
    document.body.appendChild(box); setTimeout(function () { box.remove(); }, 3600);
  };
  /* Files dropped on (or picked through) el: onFiles(FileList). Returns nothing; the listeners live as long as el. */
  FB.dropZone = function (el, onFiles) {
    el.addEventListener('dragover', function (e) { e.preventDefault(); el.classList.add('over'); });
    el.addEventListener('dragleave', function () { el.classList.remove('over'); });
    el.addEventListener('drop', function (e) { e.preventDefault(); el.classList.remove('over'); if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files); });
  };
  FB.imagesOf = function (files) { return Array.prototype.slice.call(files || []).filter(function (f) { return /^image\//.test(f.type) || /\.(png|jpe?g|webp|heic|gif)$/i.test(f.name); }); };
  /* Keyboard shortcuts for a page: handler(key, event) gets the lower-cased key when focus isn't in a field or a dialog.
     Returns the function that removes the listener (a page's leave()). */
  FB.onKeys = function (handler) {
    function k(e) {
      if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName || '') || e.target.isContentEditable) return;
      if (document.querySelector('.anvil-modal.in, .modal.in, .anvil-modal[style*="display: block"]')) return;
      if (handler(e.key.toLowerCase(), e.ctrlKey || e.metaKey) === true) e.preventDefault();
    }
    document.addEventListener('keydown', k);
    return function () { document.removeEventListener('keydown', k); };
  };
  FB.scrollIntoView = function (el) { if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); };

  /* ---------------------------------------------------------------- tidy up (phone piles) */
  var T = FB.tidy = {};
  T.platform = function () { var u = navigator.userAgent; return /iPhone|iPad|iPod/i.test(u) ? 'ios' : /Android/i.test(u) ? 'android' : 'desktop'; };
  T.isPhone = function () { return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent); };
  T.installed = function () { return !!(window.matchMedia && window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true); };
  T.canInstall = function () { return !!window.fbInstallPrompt; };
  T.install = function () {
    var p = window.fbInstallPrompt;
    if (!p) return Promise.resolve('unavailable');
    window.fbInstallPrompt = null;
    p.prompt();
    return p.userChoice.then(function (c) { return c.outcome; }, function () { return 'dismissed'; });
  };
  window.addEventListener('beforeinstallprompt', function (e) { e.preventDefault(); window.fbInstallPrompt = e; });
  T.linksFromHtml = function (html) {
    var doc = new DOMParser().parseFromString(html, 'text/html'), out = [];
    doc.querySelectorAll('a[href]').forEach(function (a) {
      var u = a.getAttribute('href');
      if (/^https?:/i.test(u)) out.push(u + ' | ' + (a.textContent || '').replace(/\s+/g, ' ').trim());
    });
    return out;
  };
  /* Read the clipboard: rich "Copy links" HTML keeps titles. Resolves with text lines, or rejects when not allowed. */
  T.readClipboard = function () {
    if (navigator.clipboard && navigator.clipboard.read) {
      return navigator.clipboard.read().then(function (items) {
        var it = items.find(function (x) { return x.types.indexOf('text/html') >= 0; });
        if (it) return it.getType('text/html').then(function (bl) { return bl.text(); }).then(function (h) { var l = T.linksFromHtml(h); return l.length ? l.join('\n') : navigator.clipboard.readText(); });
        return navigator.clipboard.readText();
      });
    }
    if (navigator.clipboard) return navigator.clipboard.readText();
    return Promise.reject(new Error('no clipboard'));
  };
  /* Pasting rich links into a textarea keeps their titles ("url | title" lines). */
  T.richPaste = function (textarea) {
    textarea.addEventListener('paste', function (e) {
      if (!e.clipboardData) return;
      var h = e.clipboardData.getData('text/html'), l = h ? T.linksFromHtml(h) : [];
      if (l.length) { e.preventDefault(); textarea.value = (textarea.value ? textarea.value.replace(/\s*$/, '\n') : '') + l.join('\n'); textarea.dispatchEvent(new Event('change', { bubbles: true })); }
    });
  };
  /* Swipe a card: right = keep, left = skip. cb('keep' | 'skip'). Buttons, links and the category strip don't drag. */
  T.swipe = function (card, cb) {
    if (!card || card._swipe) return;
    card._swipe = true;
    var x0 = null, y0 = 0, dx = 0;
    var stamps = function () { return card.querySelectorAll('.td-stamp'); };
    card.addEventListener('pointerdown', function (e) {
      if (e.target.closest('button, a, .td-cats, input')) return;
      x0 = e.clientX; y0 = e.clientY; dx = 0; card.classList.add('drag');
    });
    card.addEventListener('pointermove', function (e) {
      if (x0 == null) return;
      dx = e.clientX - x0;
      if (Math.abs(dx) < 8 || Math.abs(e.clientY - y0) > Math.abs(dx) * 1.2) return;
      card.style.transform = 'translateX(' + dx + 'px) rotate(' + dx / 22 + 'deg)';
      var s = stamps(); if (s.length > 1) { s[0].style.opacity = Math.max(0, Math.min(1, dx / 90)); s[1].style.opacity = Math.max(0, Math.min(1, -dx / 90)); }
    });
    var end = function () {
      if (x0 == null) return;
      x0 = null; card.classList.remove('drag');
      var s = stamps();
      if (dx > 90) cb('keep'); else if (dx < -90) cb('skip');
      else { card.style.transform = ''; if (s.length > 1) s[0].style.opacity = s[1].style.opacity = 0; }
    };
    card.addEventListener('pointerup', end); card.addEventListener('pointercancel', end); card.addEventListener('pointerleave', end);
  };
  /* The card flies off before the next one is drawn. */
  T.fling = function (card, act) {
    if (!card) return Promise.resolve();
    card.style.transform = act === 'skip' ? 'translateX(-120%) rotate(-12deg)' : act === 'keep' ? 'translateX(120%) rotate(12deg)' : 'translateY(60px)';
    card.style.opacity = '0';
    return new Promise(function (r) { setTimeout(function () { card.style.transform = ''; card.style.opacity = ''; var s = card.querySelectorAll('.td-stamp'); s.forEach(function (x) { x.style.opacity = 0; }); r(); }, 180); });
  };
  /* Screenshot fingerprints: name|size|lastModified hashed here (not the content), so a renamed file counts as new. */
  T.fpOf = function (file) {
    var s = (file.name || '') + '|' + (file.size || 0) + '|' + (file.lastModified || 0), h1 = 0x811c9dc5, h2 = 0;
    for (var i = 0; i < s.length; i++) { h1 = Math.imul(h1 ^ s.charCodeAt(i), 16777619) >>> 0; h2 = (h2 * 31 + s.charCodeAt(i)) >>> 0; }
    return 's' + h1.toString(36) + h2.toString(36);
  };
  var idb = T.idb = {
    open: function () { return new Promise(function (res, rej) { var r = indexedDB.open('favesbuddy', 1); r.onupgradeneeded = function () { r.result.createObjectStore('kv'); }; r.onsuccess = function () { res(r.result); }; r.onerror = rej; }); },
    get: function (k) { return idb.open().then(function (db) { return new Promise(function (res) { var q = db.transaction('kv').objectStore('kv').get(k); q.onsuccess = function () { res(q.result); }; q.onerror = function () { res(null); }; }); }).catch(function () { return null; }); },
    set: function (k, v) { return idb.open().then(function (db) { return new Promise(function (res) { var t = db.transaction('kv', 'readwrite'); t.objectStore('kv').put(v, k); t.oncomplete = res; t.onerror = res; }); }).catch(function () {}); }
  };
  var IMG = /\.(png|jpe?g|webp|heic|gif)$/i;
  T.canFolder = function () { return !!window.showDirectoryPicker && !T.isPhone(); };
  T.folderName = function () { return idb.get('shots.folder').then(function (h) { T._folder = h || null; return h ? h.name : ''; }); };
  /* Newest pictures in the remembered (or a newly picked) folder, at most 120. Resolves with [] when cancelled. */
  T.folderFiles = function (pick) {
    var getHandle = pick ? window.showDirectoryPicker({ id: 'fb-shots', mode: 'read', startIn: 'pictures' }).then(function (h) { T._folder = h; idb.set('shots.folder', h); return h; })
      : Promise.resolve(T._folder);
    return getHandle.then(function (handle) {
      if (!handle) return [];
      var perm = handle.queryPermission ? handle.queryPermission({ mode: 'read' }) : Promise.resolve('granted');
      return perm.then(function (p) { return p === 'granted' ? p : handle.requestPermission({ mode: 'read' }); }).then(function (p) {
        if (p !== 'granted') throw new Error('Faves Buddy needs permission to look in that folder.');
        var files = [], it = handle.values(), step = function () {
          return it.next().then(function (n) {
            if (n.done) return files;
            if (n.value.kind === 'file' && IMG.test(n.value.name)) return n.value.getFile().then(function (f) { files.push(f); return step(); });
            return step();
          });
        };
        return step();
      }).then(function (files) { files.sort(function (a, b) { return b.lastModified - a.lastModified; }); return files.slice(0, 120); });
    }, function (err) { if (err && err.name === 'AbortError') return []; throw err; });
  };
  T.blobOf = function (url) { return fetch(url).then(function (r) { return r.blob(); }); };
})();
