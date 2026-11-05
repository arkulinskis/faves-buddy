/* fb-map.js: the map (FB.map, MapLibre 4.7.1 + OpenFreeMap) and the open-data searches (FB.data). Moved unchanged
   from the JavaScript version's web/pages/_fbmap.html; FB.mapView (the controller Components/MapView uses) is at the end. */
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
  /* Both public Overpass servers at once; the first good answer wins and the other request is cancelled.
     (Until Nov 2026 they were tried one after the other with 22 s each: a busy server meant 44 s of waiting.) */
  data.overpass = function (q, ms) {
    return new Promise(function (resolve, reject) {
      var left = OVERPASS.length, ctrls = [], done = false;
      OVERPASS.forEach(function (url) {
        var ac = window.AbortController ? new AbortController() : null;
        ctrls.push(ac);
        timeout(fetch(url, { method: 'POST', body: 'data=' + encodeURIComponent(q), headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, signal: ac ? ac.signal : undefined }), ms || 12000)
          .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
          .then(function (j) {
            if (done) return;
            done = true;
            ctrls.forEach(function (c) { if (c && c !== ac) try { c.abort(); } catch (e) {} });
            resolve(j.elements || []);
          }, function () { if (--left === 0 && !done) reject(new Error('OpenStreetMap search is busy right now.')); });
      });
    });
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

/* FB.mapView(el, opts, handlers): the map controller Components/MapView wraps. Python hands it plain data and gets
   callbacks; it never builds HTML itself.
     opts      {center: {lat, lng}, zoom, cooperative}
     handlers  {onPin(id), onSave(placeJson), onClick(lat, lng)}  (any may be missing)
   Resolves with ctl (or null when the browser can't draw maps):
     ctl.pins(faves, mode)       your faves as pins; mode 'fave' (Open + Directions), 'go' (Directions only), 'none'
     ctl.sugs(places, o)         dashed suggestion pins with a Save button; o {emoji, cat, label, open (popup the first)}
     ctl.clearSugs(), ctl.me(pt), ctl.fit(points, pad), ctl.center(), ctl.jump(lat, lng, zoom)
     ctl.tilePois(recipe, center, km, saved)   places from the map's own tiles (Discover's fallback)
     ctl.destroy() */
(function () {
  'use strict';
  var FB = window.FB, esc = UI.esc;
  function dirUrl(p) { return 'https://www.google.com/maps/dir/?api=1&destination=' + p.lat + ',' + p.lng; }
  FB.mapView = function (el, o, h) {
    o = o || {}; h = h || {};
    return FB.map.make(el, o).then(function (m) {
      if (!m) return null;
      var pins = [], sugs = [], meMk = null, saveData = [];
      if (h.onClick) m.on('click', function (e) { if (!e.originalEvent || !e.originalEvent.target.closest('.fb-pin, .maplibregl-popup')) h.onClick(+e.lngLat.lat.toFixed(6), +e.lngLat.lng.toFixed(6)); });
      el.addEventListener('click', function (e) {
        var b = e.target.closest('[data-fb-save]');
        if (b && h.onSave) { e.preventDefault(); var p = saveData[+b.getAttribute('data-fb-save')]; b.disabled = true; b.textContent = 'Saving…'; Promise.resolve(h.onSave(JSON.stringify(p))).then(function () { b.textContent = 'Saved'; }, function () { b.disabled = false; b.textContent = 'Save'; }); }
      });
      var ctl = {
        map: m,
        pins: function (list, mode) {
          pins.forEach(function (mk) { mk.remove(); }); pins = [];
          (list || []).forEach(function (f) {
            if (f.lat == null) return;
            var pe = FB.map.pinEl(f), mk = new maplibregl.Marker({ element: pe, anchor: 'bottom' }).setLngLat([f.lng, f.lat]);
            if (mode !== 'none') {
              var acts = mode === 'go' ? '<a class="ui-btn sm" target="_blank" rel="noopener" href="' + dirUrl(f) + '">Directions</a>'
                : '<a class="ui-btn sm primary" href="#fave/' + encodeURIComponent(f.id) + '">Open</a><a class="ui-btn sm" target="_blank" rel="noopener" href="' + dirUrl(f) + '">Directions</a>';
              mk.setPopup(new maplibregl.Popup({ offset: 26, closeButton: true }).setHTML(FB.map.popup(f, acts)));
            }
            if (h.onPin) pe.addEventListener('click', function () { h.onPin(f.id); });
            mk.addTo(m); pins.push(mk);
          });
        },
        sugs: function (list, so) {
          so = so || {};
          (list || []).forEach(function (p) {
            if (p.lat == null) return;
            var i = saveData.push({ title: p.title, lat: p.lat, lng: p.lng, address: p.address || '', osm: p.osm || {} }) - 1;
            var pe = FB.map.pinEl({ cat: so.cat || p.cat || 'other', title: p.title }, { suggestion: true, emoji: so.emoji || p.emoji });
            var info = [so.label || p.kind || '', p.km != null ? FB.fmtDist(p.km) : '', p.address || ''].filter(Boolean).join(' · ');
            var html = '<div class="fb-pop"><b>' + esc(p.title) + '</b><div class="muted">' + esc(info) + '</div>' +
              (p.why && p.why.length ? '<div class="muted">' + esc(p.why.join(', ')) + '</div>' : '') +
              '<div class="ui-row"><button type="button" class="ui-btn sm primary" data-fb-save="' + i + '">Save</button>' +
              (p.website ? '<a class="ui-btn sm" target="_blank" rel="noopener" href="' + esc(p.website) + '">Website</a>' : '') + '</div></div>';
            var mk = new maplibregl.Marker({ element: pe, anchor: 'bottom' }).setLngLat([p.lng, p.lat]).setPopup(new maplibregl.Popup({ offset: 26 }).setHTML(html)).addTo(m);
            sugs.push(mk);
          });
          if (so.open && sugs.length) sugs[sugs.length - 1].togglePopup();
        },
        clearSugs: function () { sugs.forEach(function (mk) { mk.remove(); }); sugs = []; },
        me: function (pt) {
          if (meMk) meMk.remove(); meMk = null;
          if (pt && pt.lat != null) meMk = new maplibregl.Marker({ element: FB.map.meEl() }).setLngLat([pt.lng, pt.lat]).addTo(m);
        },
        fit: function (pts, pad) { FB.map.fit(m, pts || [], pad); },
        center: function () { var c = m.getCenter(); return { lat: c.lat, lng: c.lng }; },
        jump: function (lat, lng, zoom) { m.jumpTo({ center: [lng, lat], zoom: zoom || 15 }); },
        tilePois: function (recipe, center, km, saved) { return FB.data.tilePois(m, recipe, center, km, saved); },
        destroy: function () { try { m.remove(); } catch (e) {} }
      };
      return ctl;
    });
  };
})();

/* FB.data.findPlaces(recipe, center, km, saved, onBetter): what Discover, the map's "Suggest nearby" and a fave's
   "More like this nearby" use. Fast first, then better:
     - a result for the same search in the last 15 minutes comes straight from this browser's cache;
     - OpenStreetMap (both Overpass servers at once) and the map tiles' own points of interest (a hidden map that is
       kept for the whole visit) start together; whichever answers first is shown;
     - when the tiles won and OpenStreetMap answers later, onBetter(json) gets the richer list (opening hours,
       websites, cuisines).
   Resolves with {places, source: 'osm' | 'tiles' | 'cache'} (a JSON string for Python). */
(function () {
  'use strict';
  var FB = window.FB, data = FB.data;
  data.photonJson = function (q, near, limit) { return data.photon(q, near, limit); };
  var hidden = null, hiddenP = null;
  function tileMap(center) {
    if (hidden) { hidden.jumpTo({ center: [center.lng, center.lat], zoom: 15 }); return Promise.resolve(hidden); }
    if (!hiddenP) {
      var el = document.createElement('div');
      el.setAttribute('aria-hidden', 'true');
      el.style.cssText = 'position:fixed;left:-9999px;top:0;width:640px;height:640px;pointer-events:none';
      document.body.appendChild(el);
      hiddenP = FB.map.make(el, { center: center, zoom: 15 }).then(function (m) { hidden = m; return m; }, function () { hiddenP = null; return null; });
    }
    return hiddenP.then(function (m) { if (m) m.jumpTo({ center: [center.lng, center.lat], zoom: 15 }); return m; });
  }
  function settle(m) {
    return new Promise(function (res) {
      if (!m) return res();
      var t = setTimeout(res, 2500);
      m.once('idle', function () { clearTimeout(t); res(); });
    });
  }
  data.tilesNear = function (recipe, center, km, saved) {
    return tileMap(center).then(function (m) {
      return settle(m).then(function () { return m ? data.tilePois(m, recipe, center, km, saved).map(function (p) { p.why = ['from the map']; return p; }) : []; });
    });
  };
  var KEY = 'fb.places.';
  function cacheKey(recipe, c, km) { return KEY + JSON.stringify([recipe.filters, recipe.prefer || [], +(+c.lat).toFixed(3), +(+c.lng).toFixed(3), km]); }
  function cached(k) { try { var v = JSON.parse(sessionStorage.getItem(k) || 'null'); return v && Date.now() - v.t < 15 * 60e3 ? v.places : null; } catch (e) { return null; } }
  function store(k, places) { try { sessionStorage.setItem(k, JSON.stringify({ t: Date.now(), places: places })); } catch (e) {} }
  function unsaved(list, saved) {
    return list.filter(function (p) {
      var key = (p.title || '').toLowerCase();
      return !(saved || []).some(function (s) { return s[0] === key || (Math.abs(s[1] - p.lat) < 0.0004 && Math.abs(s[2] - p.lng) < 0.0006 && s[0].slice(0, 4) === key.slice(0, 4)); });
    });
  }
  data.findPlaces = function (recipe, center, km, saved, onBetter) {
    var k = cacheKey(recipe, center, km), hit = cached(k);
    if (hit) return Promise.resolve(JSON.stringify({ places: unsaved(hit, saved), source: 'cache' }));
    return new Promise(function (resolve, reject) {
      var answered = false, osmFailed = false, tilesFailed = false, tilesList = null;
      data.placesLike(recipe, center, km, saved).then(function (list) {
        store(k, list);
        if (!answered) { answered = true; resolve(JSON.stringify({ places: list, source: 'osm' })); }
        else if (onBetter && list.length) onBetter(JSON.stringify({ places: list, source: 'osm' }));
      }, function () {
        osmFailed = true;
        if (!answered && tilesFailed) reject(new Error('Place search is unavailable right now.'));
        if (!answered && tilesList) { answered = true; resolve(JSON.stringify({ places: tilesList, source: 'tiles' })); }
      });
      data.tilesNear(recipe, center, km, saved).then(function (list) {
        tilesList = list;
        // Tiles only win when they found something, or when OpenStreetMap has already failed.
        if (!answered && (list.length || osmFailed)) { answered = true; resolve(JSON.stringify({ places: list, source: 'tiles' })); }
      }, function () {
        tilesFailed = true;
        if (!answered && osmFailed) reject(new Error('Place search is unavailable right now.'));
      });
    });
  };
})();
