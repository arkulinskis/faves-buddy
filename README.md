# Faves Buddy

A personal collection for everything you mean to come back to: open browser tabs (one or a whole window), Google Maps
pins, screenshots and photos, notes and ideas. Each thing is sorted into a category **without AI** (rules + a small
learner that picks up how you file things), places go on a map with "open now", Discover finds more of what you love in
open data, and lists can be shared with a link or with people. A Chrome extension saves straight into it. Built on
[Anvil](https://anvil.works).

- **App repo:** github.com/arkulinskis/faves-buddy (branch `master`). Anvil pulls `master`.
- **Live:** not published yet (planned `favesbuddy.anvil.app` until a domain is chosen).

## What it does

**For visitors:** a landing page (promise, how it works, features, FAQ) that links to two public demo lists
("Peek at a shared list"); any shared list opens without an account (`#s/<token>`); sign-up with email and password;
feedback form; Privacy & Terms.

**For members:**
- **Faves (library, `#home`):** quick add (paste a link or Maps pin, or jot an idea: plain text = note, "idea:" = idea),
  inbox nudge, *Coming up* (faves with an event date), *Rediscover* (an old fave, one per day), your lists, then every
  kept fave as cards with filters: search (titles, notes, text read from pictures), kind, status (kept / + inbox /
  archived), sort (newest, oldest, A–Z, most loved, coming up), category chips with counts, tag cloud. Heart on each
  card = "Loved". New members get a welcome panel with "Load sample faves".
- **Inbox (`#inbox`):** every new fave, already sorted: suggested category, confidence bar, the reasons ("schema.org:
  Recipe", "site: youtube.com", "OpenStreetMap: amenity=cafe", "you filed X under Y before"), tags. Keep (one tap),
  Change (pick a category: teaches the sorter), lists, snooze (tonight / weekend / next week / month), archive, delete.
  "Keep the N sure ones" in bulk. Keyboard: J/K, Enter, A, S, Delete. Tabs saved in bulk are read a few at a time in
  the background (progress bar). Inbox zero = confetti.
- **Map (`#map`, `#map/find/<text>`, `#map/list/<id>`):** MapLibre + OpenFreeMap (light/dark follow the theme). Every
  fave with a location, nearest first, with distance and open/closed (from OSM opening_hours). Near me, radius chips,
  category and list filters, Open now. Search a place by name (Photon) and save it from its popup. "Suggest nearby"
  runs your top Discover search around the map centre (dashed pins, save in one tap).
- **Discover (`#discover/places|events|ideas`):** on-demand searches built from your taste (server `taste()`), around
  one of your areas ("near Café Lumière"), your home spot or you, within 1–15 km. Each card shows its exact filter:
  - *Places like yours:* OpenStreetMap via Overpass (`amenity=cafe + cuisine=… + outdoor_seating=yes`); when Overpass
    is busy, the map tiles' own points of interest. Already-saved places are hidden; results rank by your preferred
    tags, completeness (hours, website, Wikipedia) and distance.
  - *Events:* Wikidata festivals near you (no key); Ticketmaster Discovery events with your own free key.
  - *Ideas & reads:* Wikipedia "more like this" for your favourite reads/videos; Wikipedia articles around a spot.
- **A fave (`#fave/<id>`):** picture, inline-editable title, open link / directions / OpenStreetMap, place facts (hours,
  open now, website, phone, cuisine, accessibility), event date, recipe time, reading time; status (worded per kind:
  Want to go / Been there, or To read / Done…) + 1–5 stars; category picker with reasons ("Let Faves Buddy sort it
  again"); tags; lists; note (saves on blur); mini map (click to move the pin) + "More like this nearby"; "Where is it?"
  search for place-like faves without a pin; for pictures: *read the text* (on-device OCR), what was found in it
  (links, dates, times, phones, addresses → map search, handles, prices), *Describe with AI* (own key); archive,
  remind me later, delete. Members of a shared list can open its faves and "Save to my faves".
- **Save something (`#add/link|place|photo|note`, `#add/link/<url>`):** link preview (server reads the page: title,
  picture, schema.org, Maps link → place + OSM match) with the suggested category + reasons, lists, note → Save (kept)
  or "Save to inbox for later"; place search near you or "Pin where I am"; pictures: many at once, shrunk on the device,
  EXIF GPS → place, OCR (toggle) and AI (toggle, own key), each lands sorted in the inbox; note or idea. A bookmarklet
  for non-Chrome browsers.
- **Lists (`#lists`, `#list/<id>`):** tiles with picture mosaics; create/edit (name, emoji, colour, description); add
  faves; remove; mini map of the list's places; Share: public link on/off (copy), invite by email as *can view* or
  *can add*, change roles, remove; invites to emails without an account wait for that sign-up; members can leave.
- **Tab sets (`#tabs`):** windows of tabs saved together (and imports): rename, open all, copy links, keep all, delete
  the set (keep or delete its faves).
- **Tools (`#tools/…`):** *Browser extension* (download zip, install steps, connection code, new code); *Import*
  (drop a file: Chrome/Firefox/Safari bookmarks HTML with folders → tags, OneTab text, Pocket CSV, Google Takeout
  Saved Places GeoJSON and saved-list CSV, a Faves Buddy JSON export, any text with links; chunks of 300; becomes a tab
  set); *Export* (JSON, CSV, GeoJSON, bookmarks HTML by category); *AI (your key)* (Anthropic key + model, test);
  *Events key* (Ticketmaster); *Home spot* (here, or search); *What it learned* (websites and words → category,
  accuracy "first guesses you kept", forget one / all); *Sample faves* (add / remove).

**Chrome extension (`extension/`, MV3, v1.0.0):** popup: save this tab (note, list, optional category), save & close,
save the whole window as a tab set (optionally closing it, pinned tabs stay), re-file what was just saved, reopen a tab
set in a new window. Right-click: save page / link / picture / selected text as a note. Shortcuts Alt+Shift+S (tab),
Alt+Shift+W (window). Reads the page it saves (title, description, picture, schema.org, place, event date) so the
server doesn't fetch it again. Connects with a code from Tools (`FAVES1.<base64 {api origin, token}>`).

**For admins** (`#admin`; arkulinskis@gmail.com becomes an admin on first sign-in):
- **Overview:** people, faves (this week), saved from the extension, people using the extension, lists (public).
- **Feedback inbox:** New / Read / Done, private notes.
- **Users:** search, make admin, disable an account.
- **Sorting:** how often first guesses were kept, per category, the most common corrections, and a sorter tester
  (paste a link, optionally read live, or any text; see every score and reason).
- **Demo data:** Maya, Theo and Ines (fictional) with faves and two public lists; remove or reload.

## How sorting works (no AI)

`server_code/Taxonomy.py` has 20 categories, each with signals; `Classify.py` scores them. Strongest first:
OpenStreetMap tags of a place (6), specific schema.org types in the page's JSON-LD (6; generic Article/BlogPosting 3),
known websites (5, ~350 domains), an event date (3.5), og:type (3; "article" 1.5), URL paths (2), keywords in English
and French (title 1.4, text 0.6, "strong" words ×2.2, capped at 6), and a date + time in the text, like a poster
(2.5). The per-person learner (in `prefs.model`) adds up to 7 for a website the person filed before and up to 6 for
title words. Confidence = top / (top + second + 2). Research on 2026-10-31: 35/35 real pages read live, 34/35 from URL
+ title alone, 28/28 held-out notes, screenshot text and places (`tools/research/`).

## Setting it up in Anvil (once)

1. In the Anvil editor: **Create app → Clone from GitHub**, and paste `https://github.com/arkulinskis/faves-buddy`.
2. **Users** service: email + password, sign-up allowed (already set in `anvil.yaml`; check it).
3. Open the app in the editor. If it shows a **Schema Mismatch** alert, choose **"The schema of the source code is correct"** so Anvil creates the tables.
4. **Run** it and sign up with **arkulinskis@gmail.com** straight away (that account becomes the admin).
5. **Publish** (Publish → public URL, or your own domain).

<!-- libraries:start -->
## Libraries and outside services

What this project uses besides its own code. Generated by `APP_MAKER/tools/libraries.py`; to change it, edit `APP_MAKER/libraries/catalog.py` and re-run the script.

| Name | How it gets in | Used here for |
|---|---|---|
| [MapLibre GL JS](https://maplibre.org) 4.7.1 | Loaded from a CDN | the map of your saved places, lists and suggestions (light and dark styles) |
| [OpenFreeMap](https://openfreemap.org) | Outside web service | Free vector map tiles: the shapes of streets, buildings, parks and water. |
| [Photon](https://photon.komoot.io) | Outside web service | A fast address search built on OpenStreetMap, good for "search as you type". |
| [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) | Outside web service | Asks OpenStreetMap questions like "every café within 500 m of here". |
| [Tesseract.js](https://tesseract.projectnaptha.com) 5.1.1 | Loaded from a CDN | reads posters, menus and screenshots so they can be sorted and searched |
| [Claude API](https://docs.anthropic.com) | Outside web service | Anthropic's API for Claude models. |
| [Google Fonts](https://fonts.google.com) | Loaded from a CDN | Inter, Nunito |

**Built into the browser:** Canvas 2D, WebGL, Geolocation, localStorage, Clipboard, File downloads (Blob), Chrome extension APIs (Manifest V3).

**Anvil platform:** Anvil, Anvil Data Tables, Anvil JS bridge (anvil.js), Anvil Users.

**Build and test tools (not shipped):** Node.js, PyYAML, Headless Chrome (DevTools Protocol).

<!-- libraries:end -->

## Working on it

See `.claude/skills/favesbuddy/SKILL.md`. In short:

```
python -I tools/check.py --ui                    # syntax, server tests, headless UI tests → ALL CHECKS PASSED
python -I tools/preview/devserver.py 8765        # the app on in-memory data: http://localhost:8765/  (?as=ana#home, ?as=admin#admin)
python -I tools/build_extension.py               # after changing extension/: icons + assets/faves-buddy-extension.zip
python -I tools/research/heldout.py              # sorter check (offline); classify_research.py reads live pages
python tools/deploy.py                           # dry run (needs PyYAML, so no -I)
python tools/deploy.py --push "Message"          # deploy: commit + push to GitHub, Anvil pulls it
```

## Project layout

```
web/            the interface: core.js/core.css (engine + neumorphic design tokens), app.js (header, footer, tab bar), pages/*.html
                (_fb = shared cards/helpers, _fbmap = map + open-data searches, _fbmedia = pictures, OCR, AI)
client_code/    Main.py (the only Anvil form: bridge to the server, sign-in), legal.py
server_code/    Taxonomy.py + Classify.py (sorting), Fetch.py (reading links, Maps URLs, OSM matching), Store.py (shared fave logic),
                Faves.py, Lists.py, Clip.py (extension endpoint), Discover.py, DemoData.py, Admin.py, Accounts.py, Feedback.py, common.py
extension/      the Chrome extension (manifest, background.js, popup); zipped into assets/ by tools/build_extension.py
assets/         icon.svg + PNG icons, demo-poster.jpg, faves-buddy-extension.zip (served at _/theme/<name>)
tools/          sync_to_anvil.py (settings + table schema), deploy.py, check.py, build_extension.py, research/, preview/, testing/
```
