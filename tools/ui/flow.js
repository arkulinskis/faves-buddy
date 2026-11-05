/* The main user journeys, run inside the real app (Anvil App Server) by tools/ui_test.py through tools/live/drive.mjs.
   Resolves to {ok, log}. Keep log lines ASCII (the Windows console).
   Visitor: landing, Get the app. Member: sign up (sent back to the page they wanted), sample faves, quick add, inbox
   (keys + keep), a fave (status, tag, share link), a shared fave link, lists (new list), the map, Discover (top faves,
   a places search), Tidy (paste tabs, swipe, save), Tools (import pasted links), sign out. Then a visitor opens the
   shared fave, creates an account from it and the fave is saved into the new account. */
(async function () {
  const log = [], t0 = Date.now();
  const say = (m) => log.push(((Date.now() - t0) / 1000).toFixed(1) + 's ' + m);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function until(fn, what, ms) {
    const end = Date.now() + (ms || 20000);
    while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (e) {} await sleep(150); }
    throw new Error('timed out waiting for: ' + what);
  }
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const vis = (e) => e && e.getClientRects().length > 0;
  const norm = (s) => (s || '').trim().replace(/\s+/g, ' ');
  const btn = (text, scope) => $$('button', scope).filter(vis).find((b) => norm(b.textContent) === text);
  const btnLike = (re, scope) => $$('button', scope).filter(vis).find((b) => re.test(norm(b.textContent)));
  async function click(text, scope) {
    const b = await until(() => (typeof text === 'string' ? btn(text, scope) : btnLike(text, scope)), 'button ' + text);
    b.scrollIntoView({ block: 'center' });
    b.click();
    return b;
  }
  function type(input, value) {
    input.focus();
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function enter(input) { input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, which: 13, bubbles: true })); }
  async function page(hash, ready, what) {
    if (location.hash !== hash) window.UI_READY = false;
    location.hash = hash;
    await until(() => window.UI_READY && location.hash === hash && ready(), what || hash, 40000);
    await sleep(300);
  }
  const dialog = () => $$('.anvil-modal-content').filter(vis).pop();
  const ok = (cond, msg) => { if (!cond) throw new Error('FAILED: ' + msg); say('ok   ' + msg); };
  async function signUp(name, landing) {
    await until(() => window.UI_READY && $$('.au-card input').filter(vis).length >= 2, 'sign-in form');
    if ($$('.au-card input').filter(vis).length < 3) await click('Create account', $('.au-card .ui-seg'));
    await until(() => $$('.au-card input').filter(vis).length >= 3, 'sign-up form');
    const inputs = $$('.au-card input[type=text], .au-card input[type=email], .au-card input[type=password]').filter(vis);
    type(inputs[0], name); type(inputs[1], name.toLowerCase().replace(/\W+/g, '') + Date.now() + '@example.com'); type(inputs[2], 'Hb-' + Math.random().toString(36).slice(2) + '-Kq7');
    const tick = $('.au-card input[type=checkbox]');
    if (tick && !tick.checked) tick.click();
    await click('Create account', $('.au-card .anvil-role-btn-block'));
    await until(() => location.hash === landing && window.UI_READY, 'signed up and sent to ' + landing, 60000);
  }

  try {
    // ---- visitors
    await page('#landing', () => $('.lp-hero'), 'landing');
    ok($('.lp-hero a[href="#auth/signup"]') && $('.lp-proof a[href="#app"]'), 'landing: sign-up and Get the app links');
    await page('#app', () => $$('.ga-card').length === 3, 'get the app');
    ok(/Add to Home Screen/.test($('.ga-wrap').textContent) && /Android/.test($('.ga-wrap').textContent), 'get the app: Android, iPhone and computer steps');

    // ---- a members-only page sends visitors to sign in, then back
    await page('#inbox', () => true);
    await signUp('Flow Tester', '#inbox');
    await until(() => /Inbox zero/.test(document.body.textContent), 'empty inbox');
    ok(true, 'sign-up: back on the inbox they asked for (empty)');

    // ---- home: samples, quick add
    await page('#home', () => btnLike(/Load sample faves/), 'home welcome');
    await click(/Load sample faves/);
    await until(() => window.UI_READY && $$('.fb-card').length > 10, 'samples', 60000);
    ok(!/·\s*·/.test($$('.fb-meta').map((m) => m.textContent).join('|')), 'home: cards with samples, clean meta lines');
    type($('input.anvil-role-hm-quick-box'), 'idea: a picnic in the rain');
    await click('Save', $('.hm-quick'));
    await until(() => /in your inbox as/i.test(document.body.textContent), 'quick add toast');
    ok(true, 'home: quick add files an idea in the inbox');

    // ---- inbox: keys, keep
    await page('#inbox', () => $$('.ib-item').length > 0, 'inbox');
    const n0 = $$('.ib-item').length;
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }));
    await sleep(400);
    ok($$('.ib-item.focus').length === 1, 'inbox: J moves the focus');
    $$('.ib-item')[0].querySelector('.anvil-role-ic-check button').click();
    await until(() => $$('.ib-item').length === n0 - 1, 'kept one', 20000);
    ok(true, 'inbox: Keep removes the item');

    // ---- a fave: status, tag, share
    await page('#home', () => $$('.fb-card').length > 3, 'home again');
    say('info home: top faves row ' + ($$('.top-card').length ? 'shows ' + $$('.top-card').length + ' places' : 'empty (no place saved by 2+ people nearby yet)'));
    const grid = $$('.anvil-role-fb-grid .fb-card');
    const card = grid.find((c) => /Caf. Lumi.re/.test(c.textContent)) || grid[0];
    const href = $('.fb-card-link', card).getAttribute('href');
    await page(href, () => $('input.anvil-role-fv-title-box'), 'fave page');
    await click('Loved it');
    await until(() => btn('Loved it') && btn('Loved it').classList.contains('on'), 'loved');
    ok(true, 'fave: status Loved it');
    const tagBox = $('input.anvil-role-fv-tag-box');
    type(tagBox, 'flowtag'); enter(tagBox);
    await until(() => /#flowtag/.test($('.fv-tags').textContent), 'tag added');
    ok(true, 'fave: a tag is added with Enter');
    await click('Share');
    const link = await until(() => dialog() && $$('input', dialog()).map((i) => i.value).find((v) => /#f\//.test(v)), 'share link');
    const token = link.split('#f/')[1];
    ok(token && token.length >= 20, 'fave: Share makes a link (#f/...)');
    await click('Done', dialog());
    await page('#f/' + token, () => $('.sf-save'), 'own shared fave');
    ok(vis($('.sf-save a.ui-btn')), 'shared fave: the owner sees "in your faves"');

    // ---- lists
    await page('#lists', () => btn('New list'), 'lists');
    await click('New list');
    const nameBox = await until(() => dialog() && $('input', dialog()), 'new list dialog');
    type(nameBox, 'Flow list');
    await click('Create list', dialog());
    await until(() => /^#list\//.test(location.hash) && window.UI_READY && /Flow list/.test(document.body.textContent), 'list page', 30000);
    ok(true, 'lists: a new list opens its page');

    // ---- map
    await page('#map', () => $$('.mp-row').length > 3, 'map');
    await until(() => $('.mp-map canvas.maplibregl-canvas') || $('.fb-map-off'), 'map drawn', 30000);
    ok(true, 'map: places listed and the map drawn');

    // ---- discover
    await page('#discover/top', () => /Top faves/.test(document.body.textContent) && !vis($('.dc-loading')), 'top faves');
    ok(vis($('.top-card')) || /No top faves here yet/.test(document.body.textContent), 'discover: top faves tab answers');
    await page('#discover/places', () => $$('.dc-recipe').length > 0, 'discover places');
    $$('.dc-recipe')[0].click();
    await until(() => vis($('.dc-res-head')) || vis($('.anvil-role-msg-error')), 'places search answers', 60000);
    say('info discover: ' + String(vis($('.dc-res-head')) ? norm($('.dc-res-head').textContent) : 'search unavailable: ' + norm($('.anvil-role-msg-error').textContent)).replace(/[^ -~]/g, ''));
    ok(true, 'discover: a places search finishes (results or a clear message)');

    // ---- tidy: paste tabs, swipe, save
    localStorage.removeItem('favesbuddy.tidy.tabs');
    await page('#tidy/tabs', () => $('textarea.anvil-role-td-paste'), 'tidy tabs');
    type($('textarea.anvil-role-td-paste'), 'https://en.wikipedia.org/wiki/Montreal | Montreal\nhttps://www.allrecipes.com/recipe/1/x | Pancakes\nhttps://github.com/anvil-works | Anvil on GitHub');
    await click(/Sort them/);
    await until(() => vis($('.td-card')), 'card', 40000);
    ok(/Tab 1 of 3/.test(document.body.textContent), 'tidy: three tabs sorted, one card at a time');
    await click(/^Keep( in .*)?$/); await sleep(600);
    await click('Skip'); await sleep(600);
    await click('Later');
    await until(() => btnLike(/^Save \d/), 'finish screen', 20000);
    await click(/^Save \d/);
    await until(() => /Tidy!/.test(document.body.textContent), 'saved', 40000);
    ok(true, 'tidy: keep, skip, later, then save');

    // ---- tools: import pasted links
    await page('#tools/import', () => $('.tl-paste'), 'import');
    $('.tl-paste summary').click();
    type($('.tl-paste textarea'), 'https://example.org/a\nhttps://example.org/b');
    await click('Read the text');
    await until(() => btnLike(/^Import 2/), 'import preview');
    await click(/^Import 2/);
    await until(() => location.hash === '#inbox' && window.UI_READY, 'imported', 40000);
    ok(true, 'tools: pasted links import into the inbox');

    // ---- sign out
    await click(/^FT$/);
    await click('Sign out', $('.ui-menu'));
    await until(() => location.hash === '#landing' && window.UI_READY, 'signed out');
    ok(true, 'sign out: back to the landing page');

    // ---- a visitor opens the shared fave, makes an account from it, and it is saved for them
    await page('#f/' + token, () => $('.sf-save'), 'shared fave as a visitor');
    ok(/Shared by Flow Tester/.test(document.body.textContent), 'shared fave: shows who shared it, no account needed');
    await click('Create a free account to save it');
    await signUp('Second Person', '#f/' + token);
    await until(() => /Saved to your inbox/.test(document.body.textContent) && vis($('.sf-save a.ui-btn')), 'saved after sign-up', 40000);
    ok(true, 'shared fave: after sign-up it is saved into the new account');

    say('PASSED');
    return { ok: true, log: log };
  } catch (e) {
    say(String(e && e.message || e));
    return { ok: false, log: log };
  }
})();
