---
name: favesbuddy
description: Context, workflow and recipes for Faves Buddy (folder faves-buddy-forms), the user's Anvil app built as native Anvil Forms: a personal collection of saved tabs, map pins, screenshots, notes and ideas, sorted without AI, mapped, shared as lists or single links, with Top faves, a Chrome extension and phone tidy-up. Load this before any feature request, bug fix, restyle, content change or deploy for this app.
---

# Faves Buddy: working on the app

**What it is:** a place to tame "for later" chaos. People save open tabs (one or a whole window, via the Chrome
extension), Google Maps links, screenshots/photos, notes and ideas; each is sorted into one of 20 categories by rules +
a per-person learner (no AI), lands in an **inbox** to confirm, then lives in the **library**, on the **map** (near me,
open now), in **lists** (shared by link or with people), can be **shared on its own** by link (#f/<token>), feeds
**Discover** (on-demand open-data searches) and counts, anonymously, toward **Top faves** (places 2+ people saved near a
spot). Optional bring-your-own-key AI describes pictures; text in pictures is read on the device (Tesseract.js).
**Get the app** (#app) explains installing it from the browser on Android / iPhone / computer (there is no store app).

**Where it lives:**
- Folder `C:\Users\arkvi\Documents\CLAUDE\faves-buddy-forms\` = the git clone of **github.com/arkulinskis/faves-buddy**.
  "git" layout: the folder *is* the Anvil app; Anvil pulls master, pushing is the deploy. Live: https://faves-buddy.anvil.app.
  Rebuilt as native Forms on Nov 4 2026 and merged on Nov 5; the old JavaScript folder `faves-buddy` is retired
  (RETIRED.md; its deploy.py refuses to run).
- Made the template-forms way (`APP_MAKER\template-forms`); Anvil's agent skills: `APP_MAKER\vendor\anvil-agent-references`.
- **README.md** lists every feature. Keep it up to date.

**What the user wants:** "neumorphic buttons with white flat design with rounded corners for texts and images".
Palette: page `#f3f5fa`, surface white, ink `#1d2433`, brand indigo `#4f4fe0` (was #5b5bf0; darkened for WCAG AA),
accent coral `#ff6f61` (white text sits on `#c4392b`), dark page `#1b1f28`. Fonts Nunito (headings) + Inter. Cards flat
white, radius 20, pictures 16; buttons, chips, inputs, segmented controls and tabs are neumorphic (`--neu-out`/`--neu-in`).
First-pass sorting and suggestions stay **LLM-free** but pluggable (anything returning Classify.classify's dict).
Claude assumes details and builds; Claude deploys. Mobile-first (390 px), light + dark, WCAG 2.2 AA.
Feedback: Prepsto only ("Submit feedback", link code vef7qyr). Prepsto tickets for this app: link 1140815-10048422745
(Claude reads them with `python ~/.prepsto/prepsto.py tickets --link 1140815-10048422745`).

## Workflow for any change

1. `git pull --ff-only` (Anvil commits "Edited ..." when the user changes something in the IDE; read those commits).
2. Edit a page's template and Python side by side (`client_code/Pages/X/form_template.html` + `__init__.py`).
3. `python tools/check.py` (no -I) -> **ALL CHECKS PASSED**: `anvil validate` (type-checks every template and Python
   file, server code too), JS syntax, asset hashes, server tests (tools/testing/test_server.py, 80+ functions).
4. `python -I tools/ui_test.py` (Docker Desktop running) -> **ALL UI TESTS PASSED**: flow.js (every journey incl. share
   link -> visitor signs up -> saved), phone.js (32 pages at 390 px), admin.js, a11y.js (axe, light + dark). Server
   edits need `--restart`; `--only flow.js`; `--shots DIR [--shots-only=light|dark]` and Read the PNGs. Set
   `PYTHONIOENCODING=utf-8` (emoji in logs). drive.mjs runs Chrome with SwiftShader so maps draw.
5. Commit only your files as arkulinskis with the Co-Authored-By line; `git push origin master` (or the branch).
   New tables/columns: tell the user to accept **Schema Mismatch** ("The schema of the source code is correct").

## Architecture

```
anvil.yaml                startup module `startup`; db_schema; head_html: SEO block, legal-kit.js, manifest swap (our
                          _/api/manifest.json with the Android share target), Prepsto widget, icons.css, app.css,
                          app-kit.js, fb-engine.js, fb-map.js, fb-media.js (hashes by tools/assets.py)
client_code/
  router.py               PAGES (same #addresses as the JS version), NAV (5 header links), _form, go/href/link;
                          calls the open page's leave() before the next (maps, key listeners); keeps in-app link clicks
  fb.py                   boot() (fb_boot once: cats, home, settings, AI switch), cat/cat_label, stages, set_inbox
                          (header count), when/dist/fmt_dist/open_state, geo(ask), copy, to_js/from_js
  state.py auth.py legal.py startup.py   template pieces (LEGAL_THEME accent #4f4fe0)
  Layouts/Shell           header (nav + Save + account menu), footer (Get the app, extension, Submit feedback), tab bar
                          (Faves, Inbox + dot, big +, Map, Discover); refresh(page), show_inbox(n)
  Pages/                  Landing, Auth, Home, Inbox, MapPage, Discover, Lists, ListView, Fave, Add, Tabs, Tidy (hub,
                          tabs deck/list/finish, shots), ShareIn (#share/<code>), Tools, SharedList (#s), SharedFave (#f),
                          GetApp (#app), Profile, Admin (overview, feedback, users, sorting, AI sorting, demo)
  Items/                  FaveCard (_from, _href, _nostage, _actions), InboxItem (draw, set_focus, gone), Chip (every chip:
                          key/label/n/on/sm/flat/icon -> x-chip), TopCard, SugCard, RecipeCard, MapRow, PlaceResult,
                          ListTile, HomeList, PeekList, MemberRow, ListCheck, TabSet, TabLink, PlaceRow, PhotoRow, ShotRow,
                          TidyRow, DropRow, Fact, Tag, EditTag, Reason, FoundGroup/FoundLink, LearnedRow, SortRow, ...
  Dialogs/                ListsPicker, Snooze, EditList, AddFaves, ShareList, ShareFave
  Components/             Cover (FB.drawCover), MapView (FB.mapView: open, pins, sugs, me, fit, center, jump, destroy),
                          CatPicker ("pick" event), Found, AiNudge
theme/assets/
  fb-engine.js            FB.setCats/cat/catChip, drawCover/drawMosaic, when/dist/openNow/openState, geo, snoozeChoices,
                          copy/share/download, importParsers + detectImport, exportAs, confetti, dropZone, onKeys,
                          FB.tidy (platform, installed, install prompt, swipe/fling, clipboard links, fingerprints, folder)
  fb-map.js               FB.map + FB.data (Overpass: both servers at once; placesLike, tilePois, photon, wiki*, wikidata,
                          ticketmaster) + FB.mapView + FB.data.findPlaces (cache -> race OSM vs hidden-map tiles -> onBetter)
  fb-media.js             FB.media (shrink, exif, ocr Tesseract 5.1.1, extract), FB.ai (Anthropic BYOK)
  app.css                 Faves tokens + template base/role layer + the Faves look + every page + the Forms layer (end)
server_code/              Taxonomy, Classify, Fetch, Store, Faves, Lists, Social (share_fave, shared_fave [public],
                          copy_shared_fave, top_faves, save_top_fave), Clip (extension), Tidy (drops, share target,
                          manifest), Discover (taste), AISort (in progress), DemoData, Admin, Accounts, Feedback, common
```

**Tables** (all `client: none`): users, app_settings, feedback, faves (… + `share_token` since Nov 4 2026), tabsets,
lists, list_items, members, prefs (settings: drops, shots_seen, ai_sort, `top_faves` = False means don't count me).

## How things are done here

- Template-forms rules apply (one Form per page with the Shell layout; RepeatingPanel + Items; Dialogs + alert();
  Labels for changing text; Buttons with roles `btn btn-primary ic-x`; JS only for engines).
- Item templates set their text once with `anvil:dom-node` spans (lighter than Labels in big grids). Items whose content
  changes in place (InboxItem, PhotoRow, ShotRow) have `draw()`; PhotoRow/ShotRow put themselves in `item["_form"]`.
- Every template's root is a plain wrapper (`*-host`, `display: contents` in app.css): `anvil validate` can't see an
  `anvil:name` on the root element.
- JS engines get JSON or plain dicts (fb.to_js) and give back JSON strings or objects (fb.from_js); a JS Promise returned
  to Python is already awaited; JS errors arrive as exceptions (`getattr(e, "message", None)`).
- Pages with maps or keyboard shortcuts define `leave()`; the router calls it before opening the next page.

## Recipes

- **New page:** Pages/X + router PAGES/_form, phone.js list, a11y.js list, a journey in flow.js.
- **Improve sorting:** Taxonomy.py / Classify.py; `python -I tools/research/heldout.py`; server tests. Admin → Sorting
  lists the corrections people make.
- **AI sorting (in progress):** App Secret `anthropic_api_key`, Admin → AI sorting → on; people opt in at Tools → AI.
- **Extension change:** edit extension/, bump the manifest version, `python -I tools/build_extension.py`, tools/assets.py.
- **New Discover source:** an `FB.data.x` in fb-map.js returning `[{title, url, image, lat, lng, desc, start}]`, a recipe
  in Pages/Discover, the provider in the legal kit (`fb_*` in kit.json).
- **Restyle:** app.css (tokens at the top, "Faves Buddy look", pages, then the Forms layer at the end), `tools/assets.py`.

## Gotchas

- Grids that hold a scrolling chip row need `grid-template-columns: minmax(0, 1fr)` or the page scrolls sideways on
  phones (Home filters, map filters, tidy cards).
- The App Server 1.18 wraps named elements in `<anvil-dropzone>` (display: contents): `> * + *` separators and child
  selectors see the wrappers. Build separator text in Python instead (FaveCard meta line).
- `toLocaleDateString(null, …)` throws "Cannot convert undefined or null to object": pass `[]` as the locales.
- Overpass is often busy: findPlaces shows the map tiles' POIs first; nothing waits on Overpass alone.
- Top faves exclude samples (everyone's copies would add up) and opted-out people; MIN_PEOPLE = 2. Test accounts in the
  local Docker database make Top faves appear there (Café Lumière): pick cards from `.anvil-role-fb-grid` in tests.
- Shared fave links: visitors who sign up from #f/<token> get it saved automatically (the token waits in localStorage
  `favesbuddy.pending.fave` while they sign up).
- Email confirmation is off: whoever first signs up with arkulinskis@gmail.com becomes admin.
- Pictures are served at `/_/api/photo?k=<key>`: anyone with the key can view (documented in Privacy).

## Privacy & Terms (legal kit)

From `APP_MAKER/legal-kit`: change `apps/favesbuddy.json`, then there `python -I build.py favesbuddy` and `python -I install.py favesbuddy`, then `python tools/assets.py`. The facts version is 2026-11-04 (single-fave share links + Top faves):
people review the updated policy on their next visit. Sign-up keeps the tick box (`legal.consent_field()` in Pages/Auth).
