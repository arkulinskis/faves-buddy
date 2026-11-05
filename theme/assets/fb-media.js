/* fb-media.js: pictures (FB.media: shrink, EXIF, on-device OCR, extract) and bring-your-own-key AI (FB.ai).
   Moved unchanged from the JavaScript version's web/pages/_fbmedia.html. */
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
})();
