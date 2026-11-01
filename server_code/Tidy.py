"""Tidy up, made for phones: sort a pile of open tabs, sweep screenshots, and take in things shared to the app.

Tabs   A list of links (pasted after Chrome's or Safari's "Copy links", shared from Chrome's tab switcher, or sent by
       the extension's "Tabs on your other devices") is sorted at once from the link and title alone (fast, no AI,
       nothing fetched): triage_links. The page then shows one card at a time; triage_detail reads a few pages ahead
       for better titles and pictures. triage_save keeps the chosen ones in their categories (which teaches the sorter).
Shots  Screenshots are read on the device (Tesseract.js). shot_sort sorts that text and guesses a title; shot_save
       keeps one (photo, text, found bits). The files already looked at are remembered as fingerprints
       (prefs.settings.shots_seen), so the next sweep only shows new screenshots.
Share  The installed app's web manifest (/_/api/manifest.json, swapped in by head.html) has a share_target that
       POSTs to /_/api/share. That request doesn't say who is sharing, so what came in is parked as "drop" rows
       (faves with owner None, status "drop", url_norm "drop:<code>") and the browser is sent to #share/<code>, where
       the signed-in app claims them (meta.claimed_by). Drop rows never show anywhere else: every list of faves is
       searched by owner. Unclaimed drops go after 3 days, claimed ones after 30.
"""
import datetime as dt
import json
import re
from email import policy
from email.parser import BytesParser

import anvil
import anvil.server
from anvil.tables import app_tables

from . import common as C
from . import Classify
from . import Fetch
from . import Store
from . import Taxonomy as T

MAX_LINKS = 200
MAX_FILES = 30
MAX_FILE = 15 * 1024 * 1024
SEEN_KEEP = 4000
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'|]+[^\s<>\"'|.,;:!?)\]]", re.I)


# ------------------------------------------------------------------------------------------- helpers
def parse_links(text, title=None):
    """Links from shared or pasted text: one per line ("Copy links"), OneTab's "url | title", or a title line
    followed by its link (Chrome's share of several tabs). Duplicates removed, order kept."""
    out, seen, last = [], set(), ""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        urls = URL_RE.findall(line)
        if not urls:
            last = line[:200]
            continue
        rest = URL_RE.sub("", line).strip(" |-–—:·\t")
        for u in urls:
            if not u.lower().startswith("http"):
                u = "https://" + u
            norm = Fetch.normalize_url(u)
            if norm in seen:
                continue
            seen.add(norm)
            out.append({"url": u[:1000], "title": (rest or last or "")[:200]})
        last = ""
    if len(out) == 1 and title and not out[0]["title"]:
        out[0]["title"] = C.text(title, 200)
    return out[:MAX_LINKS]


STATUS_BAR = re.compile(r"^(\d{1,2}[:.]\d{2}( ?[ap]m)?|\d{1,3} ?%|lte|[345]g\+?|wi-?fi|q|search|done|cancel|back|edit|share|x|<|>|…)$", re.I)


def guess_title(text, name=""):
    """A readable title from a screenshot's text: the first line that looks like words (not the status bar,
    a link, a time or a button label)."""
    for line in (text or "").splitlines()[:30]:
        s = re.sub(r"\s+", " ", line).strip(" |•·-–—_>:<«»\"'")
        if len(s) < 6 or len(s) > 90 or STATUS_BAR.match(s):
            continue
        compact = s.replace(" ", "")
        if sum(ch.isalpha() for ch in compact) < 0.65 * len(compact) or len(s.split()) < 2:
            continue
        if re.search(r"https?://|www\.|\.(com|ca|org|net|io)\b", s, re.I):
            continue
        return s[:80]
    base = re.sub(r"\.[a-z0-9]{2,4}$", "", name or "", flags=re.I)
    base = re.sub(r"[_-]+", " ", base).strip()
    return base[:80] or "Screenshot"


def _seen(p):
    return list((p["settings"] or {}).get("shots_seen") or [])


def _mark_seen(me, fps):
    fps = [C.text(f, 40) for f in (fps or []) if isinstance(f, str) and C.text(f, 40)]
    if not fps:
        return
    p = Store.prefs_for(me)
    s = dict(p["settings"] or {})
    seen = [x for x in (s.get("shots_seen") or []) if x not in fps] + fps
    s["shots_seen"] = seen[-SEEN_KEEP:]
    p["settings"] = s


def _app_origin():
    return re.sub(r"/_/api/?$", "", Store.api_origin() or "")


def _sort_info(me, info):
    r = Classify.classify(info, Store.model_of(me))
    return {"cat": r["category"], "conf": round(r["confidence"], 2), "reasons": r["reasons"][:3], "tags": r["tags"][:5]}


# ------------------------------------------------------------------------------------------- tabs
@anvil.server.callable(require_user=True)
def triage_links(items=None, text=None):
    """Sort a pile of links without opening them: category, how sure, why, and whether it's already saved."""
    me = C.require_user()
    if text:
        items = parse_links(C.text(text, 100000, multiline=True))
    items = [i for i in (items or []) if isinstance(i, dict) and i.get("url")][:MAX_LINKS]
    if not items:
        return C.fail("No links found. Paste one link per line.")
    mine = {r["url_norm"]: r for r in app_tables.faves.search(owner=me) if r["url_norm"]}
    model = Store.model_of(me)
    out, seen = [], set()
    for it in items:
        url = C.text(it.get("url"), 1000)
        if not re.match(r"^https?://", url, re.I):
            continue
        norm = Fetch.normalize_url(url)
        if norm in seen:
            continue
        seen.add(norm)
        title = C.text(it.get("title"), 200)
        r = Classify.classify({"kind": "link", "title": title, "url": url}, model)
        same = mine.get(norm)
        out.append({"url": url, "title": title or Classify.domain_of(url), "domain": Classify.domain_of(url),
                    "cat": r["category"], "conf": round(r["confidence"], 2), "reasons": r["reasons"][:3],
                    "already": same.get_id() if same is not None else None,
                    "already_cat": same["category"] if same is not None else None})
    return C.ok(links=out)


@anvil.server.callable(require_user=True)
def triage_detail(urls):
    """Read up to 4 pages (the next cards) for a better title, picture and category."""
    me = C.require_user()
    urls = [C.text(u, 1000) for u in (urls or []) if isinstance(u, str)][:4]
    if C.rate_limited("triage_detail", 400, 3600):
        return C.ok(pages=[])
    model = Store.model_of(me)
    out = []
    for url in urls:
        if not re.match(r"^https?://", url, re.I):
            continue
        try:
            p = Fetch.read_page(url)
        except Exception:
            out.append({"url": url, "failed": True})
            continue
        r = Classify.classify({"kind": p.get("kind") or "link", "title": p.get("title"), "url": url, "text": p.get("description"),
                               "schema": p.get("schema"), "og_type": p.get("og_type"), "site_name": p.get("site_name"),
                               "when": bool(p.get("startDate"))}, model)
        out.append({"url": url, "title": p.get("title"), "image": p.get("image"), "desc": (p.get("description") or "")[:240],
                    "site": p.get("site_name"), "cat": r["category"], "conf": round(r["confidence"], 2), "reasons": r["reasons"][:3],
                    "meta": {k: p.get(k) for k in ("description", "image", "site_name", "og_type", "schema", "lang", "read_min",
                                                     "startDate", "servesCuisine", "totalTime") if p.get(k)},
                    "lat": p.get("lat"), "lng": p.get("lng"), "address": p.get("address"), "kind": p.get("kind")})
    return C.ok(pages=out)


@anvil.server.callable(require_user=True)
def triage_save(items, group=None, drop_code=None):
    """Keep the chosen links. A category (picked or accepted) files it and teaches the sorter; none = inbox.
    group names a tab set holding them all. drop_code finishes a shared-in pile."""
    me = C.require_user()
    items = [i for i in (items or []) if isinstance(i, dict) and i.get("url")]
    if len(items) > MAX_LINKS:
        return C.fail("Send at most %d at a time." % MAX_LINKS)
    if C.rate_limited("triage_save", 60, 3600):
        return C.fail("That's a lot of tidying for one hour. Try again later.")
    ts = None
    if items and group:
        ts = app_tables.tabsets.add_row(owner=me, name=C.text(group, 80) or "Tidied tabs", count=0, created=C.now(), is_demo=False)
    model = Store.model_of(me)
    saved = again = 0
    by_cat = {}
    for it in items:
        cat = it.get("category") if it.get("category") in T.BY_ID else None
        meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        f = {"url": it.get("url"), "title": it.get("title"), "note": it.get("note"), "meta": meta, "category": cat,
             "status": "kept" if cat else "inbox", "enriched": bool(meta.get("description") or meta.get("schema")),
             "lat": it.get("lat"), "lng": it.get("lng"), "address": it.get("address"),
             "kind": "place" if it.get("kind") == "place" else None, "event_at": meta.get("startDate")}
        row, created = Store.create(me, f, source="tidy", tabset=ts, model=model)
        if not created and cat and row["category"] != cat:
            Store.confirm(row, cat)
            row.update(status="kept", updated=C.now())
        saved += created
        again += not created
        c = row["category"] or "other"
        by_cat[c] = by_cat.get(c, 0) + 1
    if ts is not None:
        ts["count"] = len(app_tables.faves.search(tabset=ts))
        if not ts["count"]:
            ts.delete()
            ts = None
    if drop_code:
        for r in _drop_rows(me, drop_code):
            if r["kind"] != "photo":
                r.delete()
    return C.ok(saved=saved, again=again, by_cat=by_cat, tabset=ts.get_id() if ts is not None else None)


# ------------------------------------------------------------------------------------------- screenshots
@anvil.server.callable(require_user=True)
def shots_seen(fps):
    """Which of these screenshot fingerprints were looked at in an earlier sweep."""
    me = C.require_user()
    p = Store.prefs_for(me)
    seen = set(_seen(p))
    return {"seen": [f for f in (fps or []) if isinstance(f, str) and f in seen], "total_seen": len(seen)}


@anvil.server.callable(require_user=True)
def shot_sort(text, name=None, found=None):
    """Title, category and reasons for a screenshot, from the text read on the device. No AI."""
    me = C.require_user()
    text = C.text(text, 6000, multiline=True)
    found = found if isinstance(found, dict) else {}
    urls = [u for u in (found.get("urls") or []) if isinstance(u, str)]
    url = urls[0] if urls else ""
    if url and not url.lower().startswith("http"):
        url = "https://" + url
    title = guess_title(text, C.text(name, 120))
    info = {"kind": "photo", "title": title, "ocr": text, "url": url,
            "when": bool(found.get("dates")) and bool(found.get("times"))}
    res = _sort_info(me, info)
    if not text.strip():
        res["reasons"] = ["no text found in it"] + res["reasons"][:1]
    res.update(title=title, url=url or None, words=len(text.split()))
    return C.ok(**res)


@anvil.server.callable(require_user=True)
def shot_save(fields):
    """Keep one screenshot: the picture (a data URL, or a shared-in drop), its text and found bits, a title,
    and a category (none = inbox). Remembers its fingerprint so the next sweep skips it."""
    me = C.require_user()
    f = dict(fields or {})
    if C.rate_limited("save", 400, 3600):
        return C.fail("That's a lot of saving for one hour. Take a breather and try again soon.")
    drop = None
    if f.get("drop_id"):
        drop = C.row_by_id(app_tables.faves, f["drop_id"])
        if drop is None or drop["status"] != "drop" or (drop["meta"] or {}).get("claimed_by") != me.get_id():
            return C.fail("That shared picture isn't here any more.")
    elif not f.get("photo"):
        return C.fail("No picture to save.")
    cat = f.get("category") if f.get("category") in T.BY_ID else None
    found = f.get("found") if isinstance(f.get("found"), dict) else {}
    found = {k: [C.text(x, 200) for x in (v or [])[:8] if isinstance(x, str)] for k, v in found.items()
             if k in ("urls", "emails", "phones", "dates", "times", "addresses", "handles", "prices")}
    exif = f.get("exif") if isinstance(f.get("exif"), dict) else {}
    meta = {"ocr": C.text(f.get("ocr"), 6000, multiline=True), "found": found,
            "exif": {k: exif[k] for k in ("taken", "camera") if exif.get(k)}}
    url = C.text(f.get("url"), 1000) or None
    row, created = Store.create(me, {"title": C.text(f.get("title"), 200) or "Screenshot", "kind": "photo", "url": url,
                                     "note": f.get("note"), "meta": meta, "category": cat, "status": "kept" if cat else "inbox",
                                     "lat": exif.get("lat"), "lng": exif.get("lng")}, source=C.text(f.get("source"), 20) or "screenshot")
    if created or not row["photo_key"]:
        if drop is not None:
            row.update(photo=drop["photo"], photo_key=row["photo_key"] or Store.token(28))
        else:
            err = Store.store_photo(row, f["photo"])
            if err:
                if created:
                    row.delete()
                return err
    if not created:
        m = dict(row["meta"] or {})
        if meta["ocr"] and not m.get("ocr"):
            m.update(Store.clean_meta(meta))
            row["meta"] = Store.clean_meta(m)
        if cat and row["category"] != cat:
            Store.confirm(row, cat)
            row.update(status="kept", updated=C.now())
    elif not cat:
        Store.sort_row(row)
    if drop is not None:
        drop.delete()
    _mark_seen(me, [f.get("fp")])
    return C.ok(fave=Store.fave(row, me, lists=[], slim=True), created=created)


@anvil.server.callable(require_user=True)
def shots_skip(fps=None, drop_ids=None):
    """Not worth keeping: remember these so the next sweep doesn't show them; delete shared-in copies."""
    me = C.require_user()
    _mark_seen(me, fps)
    n = 0
    for i in (drop_ids or [])[:MAX_FILES * 3]:
        r = C.row_by_id(app_tables.faves, i)
        if r is not None and r["status"] == "drop" and (r["meta"] or {}).get("claimed_by") == me.get_id():
            r.delete()
            n += 1
    return C.ok(skipped=len(fps or []), deleted=n)


@anvil.server.callable(require_user=True)
def shots_forget():
    """Start over: the next sweep shows every screenshot again (already-saved ones are still spotted as saved)."""
    me = C.require_user()
    p = Store.prefs_for(me)
    s = dict(p["settings"] or {})
    s.pop("shots_seen", None)
    p["settings"] = s
    return C.ok()


# ------------------------------------------------------------------------------------------- shared in (drops)
def _clean_drops():
    now = C.now()
    for r in app_tables.faves.search(status="drop"):
        age = now - (r["created"] or now)
        claimed = bool((r["meta"] or {}).get("claimed_by"))
        if age > dt.timedelta(days=30 if claimed else 3):
            r.delete()


def _drop_rows(me, code):
    code = C.text(code, 40)
    if len(code) < 20:
        return []
    rows = list(app_tables.faves.search(url_norm="drop:" + code, status="drop"))
    return [r for r in rows if (r["meta"] or {}).get("claimed_by") in (None, me.get_id())]


def new_drop(links=None, files=None, note=None, title=None, claimed_by=None, name=None):
    """Park shared things under a fresh code. Returns the code."""
    code = Store.token(28)
    base = {"owner": None, "status": "drop", "url_norm": "drop:" + code, "created": C.now(), "updated": C.now(),
            "is_demo": False, "is_sample": False, "confirmed": False, "category": "other", "source": "share"}
    claim = {"claimed_by": claimed_by} if claimed_by else {}
    if links or note:
        app_tables.faves.add_row(kind="note", title=C.text(name or title, 200) or "Shared links",
                                 meta=dict(claim, links=links or [], note=C.text(note, 4000, multiline=True), name=C.text(name, 80)), **base)
    for m in (files or [])[:MAX_FILES]:
        app_tables.faves.add_row(kind="photo", title=C.text(getattr(m, "name", "") or "Shared picture", 200), photo=m,
                                 photo_key=Store.token(28), meta=dict(claim), **base)
    if claimed_by:
        _remember_drop(claimed_by, code)
    return code


def _remember_drop(user_or_id, code):
    u = user_or_id if not isinstance(user_or_id, str) else C.row_by_id(app_tables.users, user_or_id)
    if u is None:
        return
    p = Store.prefs_for(u)
    s = dict(p["settings"] or {})
    s["drops"] = ([c for c in (s.get("drops") or []) if c != code] + [code])[-20:]
    p["settings"] = s


@anvil.server.callable(require_user=True)
def drop_open(code):
    """Claim what was shared in under this code and return it: links to sort, a note, pictures to sweep."""
    me = C.require_user()
    rows = _drop_rows(me, code)
    if not rows:
        return C.fail("That share has already been tidied, or it expired. Share it again.")
    links, photos, note, name = [], [], "", ""
    for r in rows:
        m = dict(r["meta"] or {})
        if not m.get("claimed_by"):
            m["claimed_by"] = me.get_id()
            r["meta"] = m
        if r["kind"] == "photo":
            photos.append({"id": r.get_id(), "name": r["title"], "image": Store.photo_url(r)})
        else:
            links += m.get("links") or []
            note = note or m.get("note") or ""
            name = name or m.get("name") or ""
    _remember_drop(me, C.text(code, 40))
    return C.ok(code=code, links=links, photos=photos, note=note, name=name)


@anvil.server.callable(require_user=True)
def drops_waiting():
    """Shared-in piles this person opened but hasn't finished."""
    me = C.require_user()
    p = Store.prefs_for(me)
    s = dict(p["settings"] or {})
    out, keep = [], []
    for code in s.get("drops") or []:
        rows = _drop_rows(me, code)
        if not rows:
            continue
        keep.append(code)
        out.append({"code": code, "photos": len([r for r in rows if r["kind"] == "photo"]),
                    "links": sum(len((r["meta"] or {}).get("links") or []) for r in rows if r["kind"] != "photo"),
                    "name": next(((r["meta"] or {}).get("name") for r in rows if (r["meta"] or {}).get("name")), ""),
                    "created": C.iso(min(r["created"] for r in rows))})
    if keep != (s.get("drops") or []):
        s["drops"] = keep
        p["settings"] = s
    return {"drops": out}


@anvil.server.callable(require_user=True)
def drop_discard(code):
    me = C.require_user()
    n = 0
    for r in _drop_rows(me, code):
        r.delete()
        n += 1
    return C.ok(deleted=n)


def _read_share(kw):
    """Fields and files from a share-target request: Anvil's parsed form fields when it gives them,
    else the raw multipart body."""
    req = anvil.server.request
    fields, files = {}, []
    src = dict(kw or {})
    src.update(getattr(req, "form_params", None) or {})

    def take(k, v):
        if hasattr(v, "get_bytes"):
            files.append(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                take(k, x)
        elif isinstance(v, str):
            fields[k] = v

    for k, v in src.items():
        take(k, v)
    ctype = (req.headers or {}).get("content-type") or ""
    if not files and "multipart/form-data" in ctype.lower() and req.body is not None:
        raw = req.body.get_bytes() if hasattr(req.body, "get_bytes") else req.body
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="surrogateescape")
        try:
            msg = BytesParser(policy=policy.HTTP).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + raw)
            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition") or ""
                data = part.get_payload(decode=True) or b""
                if part.get_filename() is not None:
                    if data:
                        files.append(anvil.BlobMedia(part.get_content_type() or "application/octet-stream", data, name=part.get_filename()))
                else:
                    fields[name] = data.decode("utf-8", errors="replace")
        except Exception as e:
            print("share: couldn't read the form: %r" % e)
    files = [m for m in files if (getattr(m, "content_type", "") or "").startswith("image/") and len(m.get_bytes()) <= MAX_FILE]
    return fields, files


@anvil.server.http_endpoint("/share", methods=["GET", "POST"])
def share(**kw):
    """The share sheet's door (Android, installed app). Parks what came in and sends the browser to #share/<code>."""
    try:
        _clean_drops()
    except Exception as e:
        print("share: cleanup failed: %r" % e)
    fields, files = _read_share(kw)
    title, text, url = (C.text(fields.get(k), 100000, multiline=True) for k in ("title", "text", "url"))
    links = parse_links("\n".join(x for x in (url, text) if x), title)
    note = ""
    if not links and not files and (text or title):
        note = "\n".join(x for x in (title, text) if x)
    base = _app_origin() if _app_origin().startswith("https://") else ""
    got = "links=%d; files=%d; note=%d" % (len(links), len(files), 1 if note else 0)
    if not (links or files or note):
        return anvil.server.HttpResponse(303, "", headers={"Location": base + "/#tidy", "X-Faves-Received": got})
    code = new_drop(links=links, files=files, note=note, title=title, name=title if len(links) > 1 else None)
    return anvil.server.HttpResponse(303, "", headers={"Location": base + "/#share/" + code, "Cache-Control": "no-store",
                                                       "X-Faves-Received": got})


@anvil.server.http_endpoint("/manifest.json")
def manifest(**kw):
    """The installable app's manifest: Anvil's own one plus a share target (links and pictures) and shortcuts."""
    o = _app_origin()
    icon = lambda p, s, purpose="any": {"src": o + "/_/theme/" + p, "sizes": s, "type": "image/png", "purpose": purpose}
    m = {"id": "/", "name": "Faves Buddy", "short_name": "Faves Buddy",
         "description": "Tabs, pins, screenshots and ideas: sorted, mapped and shared.",
         "start_url": "/", "scope": "/", "display": "standalone", "orientation": "any",
         "background_color": "#f4f6fb", "theme_color": "#f4f6fb",
         "icons": [icon("icon-180.png", "180x180"), icon("icon-512.png", "512x512"), icon("icon-512.png", "512x512", "maskable")],
         "share_target": {"action": "/_/api/share", "method": "POST", "enctype": "multipart/form-data",
                          "params": {"title": "title", "text": "text", "url": "url",
                                     "files": [{"name": "files", "accept": ["image/*", ".png", ".jpg", ".jpeg", ".webp", ".heic"]}]}},
         "shortcuts": [{"name": "Save something", "url": "/#add", "icons": [icon("icon-180.png", "180x180")]},
                       {"name": "Tidy my tabs", "url": "/#tidy/tabs", "icons": [icon("icon-180.png", "180x180")]},
                       {"name": "Sweep screenshots", "url": "/#tidy/shots", "icons": [icon("icon-180.png", "180x180")]},
                       {"name": "Inbox", "url": "/#inbox", "icons": [icon("icon-180.png", "180x180")]}]}
    return anvil.server.HttpResponse(200, json.dumps(m), headers={"Content-Type": "application/manifest+json",
                                                                  "Cache-Control": "public, max-age=3600"})
