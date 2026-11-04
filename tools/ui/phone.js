/* Phone-width check (run at 390 px wide by tools/ui_test.py): every page loads without errors and without sideways
   scrolling, signed out and signed in. Resolves to {ok, log}. */
(async function () {
  const log = [], bad = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function until(fn, what, ms) {
    const end = Date.now() + (ms || 20000);
    while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (e) {} await sleep(150); }
    throw new Error('timed out waiting for: ' + what);
  }
  const $ = (s) => document.querySelector(s), $$ = (s) => Array.from(document.querySelectorAll(s));
  function type(input, value) {
    input.focus(); input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  async function check(hash, ready) {
    if (location.hash !== hash) window.UI_READY = false;  // the old page stays until the router runs
    location.hash = hash;
    await until(() => window.UI_READY && location.hash === hash && (!ready || ready()), hash, 30000);
    await sleep(500);
    const w = document.documentElement.scrollWidth, vw = window.innerWidth;
    const wide = $$('body *').filter((e) => { const r = e.getBoundingClientRect(); return r.width && r.right > vw + 1; })
      .slice(0, 3).map((e) => e.tagName.toLowerCase() + '.' + String(e.className).split(' ').slice(0, 2).join('.'));
    if (w > vw + 1) bad.push(hash + ' scrolls sideways (' + w + ' > ' + vw + ') ' + wide.join(' '));
    log.push((w > vw + 1 ? 'WIDE ' : 'ok   ') + hash + ' (' + w + ')');
  }
  try {
    for (const h of ['#landing', '#auth', '#auth/signup', '#app']) await check(h);
    // sign up so the member pages can be checked too
    location.hash = '#auth/signup';
    await until(() => window.UI_READY && $$('.au-card input').length >= 3, 'sign-up form');
    const inputs = $$('.au-card input[type=text], .au-card input[type=email], .au-card input[type=password]');
    type(inputs[0], 'Phone Tester'); type(inputs[1], 'phone' + Date.now() + '@example.com'); type(inputs[2], 'Hb-' + Math.random().toString(36).slice(2) + '-Kq7');
    const tick = $('.au-card input[type=checkbox]'); if (tick && !tick.checked) tick.click();
    $$('.anvil-role-btn-block button').find((b) => /Create account/.test(b.textContent)).click();
    await until(() => location.hash === '#home' && window.UI_READY, 'signed in', 30000);
    // the sample faves, so every page has something on it
    const sb = await until(() => $$('.anvil-role-ic-sparkle button').find((b) => /sample/i.test(b.textContent)), 'Load sample faves button', 30000);
    sb.click();
    await until(() => window.UI_READY && $$('.fb-card').length > 3, 'samples loaded', 60000);
    for (const h of ['#home', '#inbox', '#map', '#discover', '#discover/top', '#discover/events', '#discover/ideas', '#lists', '#add', '#add/place', '#add/photo',
                     '#add/note', '#tabs', '#tidy', '#tidy/tabs', '#tidy/shots', '#tools', '#tools/phone', '#tools/import', '#tools/export', '#tools/ai', '#tools/events',
                     '#tools/home', '#tools/learned', '#tools/samples', '#app', '#profile']) await check(h);
    const fave = $$('.fb-card a.fb-card-link').map((a) => a.getAttribute('href')).find((h) => /^#fave\//.test(h || ''));
    if (fave) await check(fave);
    const lst = await (async () => { await check('#lists'); return $$('a.ls-tile').map((a) => a.getAttribute('href')).find((h) => /^#list\//.test(h || '')); })();
    if (lst) await check(lst);
    log.push(bad.length ? 'PROBLEMS: ' + bad.join(' | ') : 'PASSED');
    return { ok: !bad.length, log: log };
  } catch (e) {
    log.push(String(e && e.message || e));
    return { ok: false, log: log };
  }
})();
