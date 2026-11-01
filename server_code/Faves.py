"""Your faves: the library, the inbox (triage), one fave's page, photos, search, import/export, tab sets, prefs.
Everything here is about the signed-in person's own faves; shared lists are in Lists.py."""
import datetime as dt
import random

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import AISort
from . import Classify
from . import DemoData
from . import Fetch
from . import Store
from . import Taxonomy as T

PAGE = 60


def _mine(fave_id):
    me = C.require_user()
    r = C.row_by_id(app_tables.faves, fave_id)
    if r is None or r["owner"] != me:
        return me, None
    return me, r


def _my_rows(me):
    return app_tables.faves.search(tables.order_by("created", ascending=False), owner=me)


def _snoozed(r, now):
    return r["remind_at"] is not None and r["remind_at"] > now


@anvil.server.callable(require_user=True)
def fb_boot():
    """What every page needs once: categories, and this person's prefs."""
    me = C.require_user()
    Store.claim_invites(me)
    p = Store.prefs_for(me)
    return {"cats": T.public(), "home": p["home"], "settings": public_settings(p), "api": Store.api_origin(),
            "ai": AISort.state_for(me)}


PRIVATE_SETTINGS = ("shots_seen", "drops", "ai_day", "ai_n")


def public_settings(p):
    """The person's settings without the bookkeeping (screenshot fingerprints, open shares, AI usage)."""
    return {k: v for k, v in (p["settings"] or {}).items() if k not in PRIVATE_SETTINGS}


# ------------------------------------------------------------------------------------------- library
def _filter(rows, f, me):
    f = f or {}
    cat, kind, status, q = f.get("cat"), f.get("kind"), f.get("status") or "kept", C.text(f.get("q"), 80).lower()
    tag, list_id, stage = f.get("tag"), f.get("list"), f.get("stage")
    in_list = None
    if list_id:
        lst = C.row_by_id(app_tables.lists, list_id)
        if lst is not None and Store.role(me, lst):
            in_list = set(li["fave"].get_id() for li in app_tables.list_items.search(list=lst) if li["fave"] is not None)
        else:
            in_list = set()
    now = C.now()
    out = []
    for r in rows:
        if status == "all":
            if r["status"] == "archived":
                continue
        elif status == "inbox":
            if r["status"] != "inbox" or _snoozed(r, now):
                continue
        elif r["status"] != status:
            continue
        if cat and (r["category"] or "other") != cat:
            continue
        if kind and r["kind"] != kind:
            continue
        if stage and (r["stage"] or "") != stage:
            continue
        if tag and tag not in (r["tags"] or []):
            continue
        if in_list is not None and r.get_id() not in in_list:
            continue
        if q:
            m = r["meta"] or {}
            hay = " ".join([r["title"] or "", r["note"] or "", r["domain"] or "", r["address"] or "", " ".join(r["tags"] or []),
                            m.get("description") or "", m.get("ocr") or "", m.get("site_name") or ""]).lower()
            if not all(w in hay for w in q.split()):
                continue
        out.append(r)
    sort = f.get("sort") or "new"
    if sort == "old":
        out.reverse()
    elif sort == "az":
        out.sort(key=lambda r: (r["title"] or "").lower())
    elif sort == "loved":
        out.sort(key=lambda r: (-(r["rating"] or 0), {"loved": 0, "been": 1, "want": 2}.get(r["stage"] or "", 3)))
    elif sort == "soon":
        far = dt.datetime(9999, 1, 1, tzinfo=dt.timezone.utc)
        out.sort(key=lambda r: r["event_at"] or far)
    return out


@anvil.server.callable(require_user=True)
def list_faves(filters=None, offset=0):
    me = C.require_user()
    rows = _filter(_my_rows(me), filters, me)
    offset = max(0, int(offset or 0))
    page = rows[offset:offset + PAGE]
    return {"faves": [Store.fave(r, me, lists=[], slim=True) for r in page], "total": len(rows), "more": offset + PAGE < len(rows)}


@anvil.server.callable(require_user=True)
def faves_home(filters=None):
    """The library page in one call: counts, inbox size, lists, what's coming up, one to rediscover, the first page."""
    me = C.require_user()
    Store.claim_invites(me)
    rows = list(_my_rows(me))
    now = C.now()
    kept = [r for r in rows if r["status"] == "kept"]
    counts = {}
    for r in kept:
        counts[r["category"] or "other"] = counts.get(r["category"] or "other", 0) + 1
    tags = {}
    for r in kept:
        for t in r["tags"] or []:
            tags[t] = tags.get(t, 0) + 1
    inbox = [r for r in rows if r["status"] == "inbox" and not _snoozed(r, now)]
    soon = sorted([r for r in rows if r["event_at"] is not None and r["event_at"] > now - dt.timedelta(hours=6) and r["status"] != "archived"],
                  key=lambda r: r["event_at"])[:4]
    old = [r for r in kept if (r["opened_at"] or r["created"]) < now - dt.timedelta(days=21)]
    rnd = random.Random(now.strftime("%Y-%m-%d") + me.get_id())
    rediscover = rnd.choice(old) if old else None
    listed = _filter(rows, filters, me)
    return {"counts": counts, "total_kept": len(kept), "inbox": len(inbox), "archived": len([r for r in rows if r["status"] == "archived"]),
            "places": len([r for r in kept if r["lat"] is not None]),
            "tags": sorted(tags.items(), key=lambda kv: -kv[1])[:14],
            "week": len([r for r in rows if r["created"] > now - dt.timedelta(days=7)]),
            "soon": [Store.fave(r, me, lists=[], slim=True) for r in soon],
            "rediscover": Store.fave(rediscover, me, lists=[], slim=True) if rediscover else None,
            "lists": _brief_lists(me), "has_samples": any(r["is_sample"] for r in rows), "count_all": len(rows),
            "faves": [Store.fave(r, me, lists=[], slim=True) for r in listed[:PAGE]], "total": len(listed), "more": len(listed) > PAGE,
            "tabsets": len(app_tables.tabsets.search(owner=me))}


def _brief_lists(me):
    out = []
    for lst in app_tables.lists.search(tables.order_by("updated", ascending=False), owner=me):
        out.append({"id": lst.get_id(), "name": lst["name"], "emoji": lst["emoji"] or "", "color": lst["color"] or "",
                    "count": len(app_tables.list_items.search(list=lst)), "public": bool(lst["is_public"]), "role": "owner"})
    for m in app_tables.members.search(user=me):
        lst = m["list"]
        if lst is not None:
            out.append({"id": lst.get_id(), "name": lst["name"], "emoji": lst["emoji"] or "", "color": lst["color"] or "",
                        "count": len(app_tables.list_items.search(list=lst)), "public": bool(lst["is_public"]), "role": m["role"],
                        "owner": C.name_of(lst["owner"])})
    return out


# ------------------------------------------------------------------------------------------- inbox
@anvil.server.callable(require_user=True)
def inbox():
    me = C.require_user()
    now = C.now()
    rows = [r for r in _my_rows(me) if r["status"] == "inbox"]
    due = [r for r in rows if not _snoozed(r, now)]
    return {"faves": [Store.fave(r, me, lists=[]) for r in due[:150]], "total": len(due),
            "snoozed": len(rows) - len(due), "pending": len([r for r in rows if not r["enriched"]]),
            "lists": _brief_lists(me)}


@anvil.server.callable(require_user=True)
def triage(fave_id, action, category=None, until=None):
    """keep (optionally with a category: that teaches the sorter) | archive | delete | snooze (until an ISO time) | inbox."""
    me, r = _mine(fave_id)
    if r is None:
        return C.fail("That fave isn't yours or no longer exists.")
    if action == "keep":
        if category and category not in T.BY_ID:
            return C.fail("Unknown category.")
        Store.confirm(r, category or r["category"] or "other")
        r.update(status="kept", remind_at=None, updated=C.now())
    elif action == "archive":
        r.update(status="archived", remind_at=None, updated=C.now())
    elif action == "inbox":
        r.update(status="inbox", remind_at=None, updated=C.now())
    elif action == "snooze":
        when = Store.parse_when(until)
        if when is None or when < C.now():
            return C.fail("Pick a time in the future.")
        r.update(status="inbox", remind_at=when, updated=C.now())
    elif action == "delete":
        _delete(r)
        return C.ok(deleted=True)
    else:
        return C.fail("Unknown action.")
    return C.ok(fave=Store.fave(r, me, lists=[], slim=True))


@anvil.server.callable(require_user=True)
def accept_confident(threshold=0.6):
    """Keep every inbox fave whose suggested category is confident enough (and teach the sorter with them)."""
    me = C.require_user()
    try:
        threshold = min(0.95, max(0.3, float(threshold)))
    except (TypeError, ValueError):
        threshold = 0.6
    now, n = C.now(), 0
    for r in list(_my_rows(me)):
        if r["status"] == "inbox" and not _snoozed(r, now) and r["enriched"] and (r["confidence"] or 0) >= threshold and r["category"] != "other":
            Store.confirm(r, r["category"])
            r.update(status="kept", updated=now)
            n += 1
    return C.ok(kept=n)


@anvil.server.callable(require_user=True)
def enrich_pending(limit=4):
    """Read a few links saved in bulk (tabs, imports) that haven't been looked at yet. The inbox calls this
    again while some are left, so a big save fills in gradually without one long wait."""
    me = C.require_user()
    model = Store.model_of(me)
    pending = [r for r in _my_rows(me) if not r["enriched"]]
    done = []
    for r in pending[:max(1, min(8, int(limit or 4)))]:
        Store.enrich(r, model=model)
        done.append(Store.fave(r, me, lists=[]))
    return {"done": done, "left": max(0, len(pending) - len(done))}


# ------------------------------------------------------------------------------------------- one fave
@anvil.server.callable(require_user=True)
def get_fave(fave_id):
    me = C.require_user()
    r = C.row_by_id(app_tables.faves, fave_id)
    if r is None or not Store.can_view(me, r):
        return C.fail("That fave isn't there any more, or it isn't shared with you.")
    d = Store.fave(r, me)
    mine = r["owner"] == me
    return C.ok(fave=d, mine=mine, lists=_brief_lists(me) if mine else [],
                tabset_count=len(app_tables.faves.search(tabset=r["tabset"])) if r["tabset"] is not None else 0)


@anvil.server.callable(require_user=True)
def update_fave(fave_id, fields):
    me, r = _mine(fave_id)
    if r is None:
        return C.fail("You can only change your own faves.")
    f = fields or {}
    upd = {"updated": C.now()}
    if "title" in f:
        t = C.text(f["title"], 200)
        if not t:
            return C.fail("Give it a name.")
        upd["title"] = t
    if "note" in f:
        upd["note"] = C.text(f["note"], 4000, multiline=True) or None
    if "url" in f:
        url = C.text(f["url"], 1000)
        upd.update(url=url or None, url_norm=Fetch.normalize_url(url) if url else None, domain=Classify.domain_of(url) if url else None)
    if "tags" in f:
        upd["tags"] = Store._merge_tags([t for t in (f["tags"] or []) if isinstance(t, str)], [])
        upd["meta"] = dict(r["meta"] or {}, tags_edited=True)
    if "stage" in f:
        if f["stage"] not in Store.STAGES:
            return C.fail("Unknown stage.")
        upd["stage"] = f["stage"]
    if "rating" in f:
        try:
            v = int(f["rating"] or 0)
        except (TypeError, ValueError):
            return C.fail("Rating is 1 to 5 stars.")
        upd["rating"] = max(0, min(5, v)) or None
    if "lat" in f or "lng" in f:
        lat, lng = Store._num(f.get("lat"), -90, 90), Store._num(f.get("lng"), -180, 180)
        if (f.get("lat") is not None and lat is None) or (f.get("lng") is not None and lng is None):
            return C.fail("That location doesn't look right.")
        upd["lat"], upd["lng"] = (lat, lng) if lat is not None and lng is not None else (None, None)
        if lat is not None and r["kind"] in ("link", "note", "idea"):
            upd["kind"] = r["kind"] if r["url"] else "place"
    if "address" in f:
        upd["address"] = C.text(f["address"], 200) or None
    if "osm" in f and isinstance(f["osm"], dict):
        upd["osm"] = Fetch.slim_tags(f["osm"])
    if "event_at" in f:
        upd["event_at"] = Store.parse_when(f["event_at"])
    if "kind" in f and f["kind"] in Store.KINDS:
        upd["kind"] = f["kind"]
    r.update(**upd)
    if "category" in f and f["category"]:
        if f["category"] not in T.BY_ID:
            return C.fail("Unknown category.")
        Store.confirm(r, f["category"])
        if r["status"] == "inbox":
            r["status"] = "kept"
    elif any(k in f for k in ("title", "note", "url", "osm")):
        Store.sort_row(r)
    if "lists" in f and isinstance(f["lists"], list):
        _set_lists(me, r, f["lists"])
    return C.ok(fave=Store.fave(r, me))


def _set_lists(me, r, want_ids):
    want = set(i for i in want_ids if isinstance(i, str))
    for li in list(app_tables.list_items.search(fave=r)):
        lst = li["list"]
        if lst is not None and Store.role(me, lst) in ("owner", "editor") and lst.get_id() not in want:
            li.delete()
    for lid in want:
        Store._add_to_list(me, r, lid)


@anvil.server.callable(require_user=True)
def opened(fave_id):
    me, r = _mine(fave_id)
    if r is not None:
        r["opened_at"] = C.now()
    return C.ok()


def _delete(r):
    for li in app_tables.list_items.search(fave=r):
        li.delete()
    ts = r["tabset"]
    r.delete()
    if ts is not None:
        n = len(app_tables.faves.search(tabset=ts))
        if n == 0:
            ts.delete()
        else:
            ts["count"] = n


@anvil.server.callable(require_user=True)
def delete_fave(fave_id):
    me, r = _mine(fave_id)
    if r is None:
        return C.ok()
    _delete(r)
    return C.ok()


@anvil.server.callable(require_user=True)
def resort_fave(fave_id):
    """Forget the chosen category and let the sorter look again (shows its reasons)."""
    me, r = _mine(fave_id)
    if r is None:
        return C.fail("That fave isn't yours.")
    r.update(confirmed=False)
    if not r["enriched"]:
        Store.enrich(r)
    res = Store.sort_row(r)
    return C.ok(fave=Store.fave(r, me), scores=res["scores"])


# ------------------------------------------------------------------------------------------- adding
@anvil.server.callable(require_user=True)
def preview_link(url):
    """Read a link before saving it: title, picture, place, and the suggested category with reasons."""
    me = C.require_user()
    url = C.text(url, 1000)
    if not url:
        return C.fail("Paste a link first.")
    if C.rate_limited("preview", 120, 3600):
        return C.fail("That's a lot of previews this hour. Try again in a little while.")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    info = {"url": url, "title": "", "kind": "link"}
    err = None
    try:
        page = Fetch.read_page(url)
    except Exception as e:
        page, err = {}, str(e)
    info.update({k: v for k, v in page.items() if v not in (None, "", [])})
    if info.get("kind") == "place" and info.get("lat") is not None:
        m = Fetch.osm_match(info["lat"], info["lng"], info.get("name") or info.get("title"))
        if m:
            info["osm"], info["osm_ref"] = m.get("osm") or {}, m.get("ref")
            info.setdefault("address", m.get("address"))
            if not info.get("title"):
                info["title"] = m.get("name")
    res = Classify.classify({"kind": info.get("kind"), "title": info.get("title"), "url": url, "text": info.get("description"),
                             "schema": info.get("schema"), "og_type": info.get("og_type"), "osm": info.get("osm"),
                             "site_name": info.get("site_name")}, Store.model_of(me))
    same = app_tables.faves.get(owner=me, url_norm=Fetch.normalize_url(url))
    return C.ok(page=info, sort=res, error=err, already=same.get_id() if same is not None else None)


@anvil.server.callable(require_user=True)
def save_fave(fields):
    """Save from the app (quick add, preview, a suggestion, a place search result)."""
    me = C.require_user()
    f = dict(fields or {})
    if not (C.text(f.get("title"), 200) or C.text(f.get("url"), 1000) or C.text(f.get("note"), 4000)) and f.get("lat") is None:
        return C.fail("Add a link, a place, a note or a picture.")
    if C.rate_limited("save", 400, 3600):
        return C.fail("That's a lot of saving for one hour. Take a breather and try again soon.")
    if f.get("kind") == "event" and not f.get("event_at"):
        f["kind"] = "note"
    row, created = Store.create(me, f, source=C.text(f.get("source") or "app", 20), enrich_now=True)
    if f.get("photo"):
        err = Store.store_photo(row, f["photo"])
        if err:
            if created:
                _delete(row)
            return err
    return C.ok(fave=Store.fave(row, me), created=created)


@anvil.server.callable(require_user=True)
def save_photo_ocr(fave_id, ocr_text=None, found=None, ai=None, exif=None):
    """After saving a picture: the text read from it (on-device OCR), bits found in that text (links, dates,
    phone numbers, addresses), the AI's notes when the person used their own key, and the photo's EXIF.
    Re-sorts unless the person already chose a category."""
    me, r = _mine(fave_id)
    if r is None:
        return C.fail("That fave isn't yours.")
    meta = dict(r["meta"] or {})
    if ocr_text is not None:
        meta["ocr"] = C.text(ocr_text, 6000, multiline=True)
    if isinstance(found, dict):
        meta["found"] = {k: [C.text(x, 200) for x in (v or [])[:8] if isinstance(x, str)] for k, v in found.items()
                         if k in ("urls", "emails", "phones", "dates", "times", "addresses", "handles", "prices")}
    upd = {"meta": Store.clean_meta(meta), "updated": C.now()}
    if isinstance(ai, dict):
        meta["ai"] = C.text(ai.get("summary"), 2000, multiline=True)
        upd["meta"] = Store.clean_meta(meta)
        if ai.get("title") and (r["title"] or "").lower().startswith(("screenshot", "img_", "photo", "image", "pxl_")):
            upd["title"] = C.text(ai["title"], 200)
        if ai.get("tags"):
            upd["tags"] = Store._merge_tags(r["tags"] or [], [t for t in ai["tags"] if isinstance(t, str)][:6])
    if isinstance(exif, dict):
        meta["exif"] = {k: exif[k] for k in ("taken", "camera") if exif.get(k)}
        upd["meta"] = Store.clean_meta(meta)
        lat, lng = Store._num(exif.get("lat"), -90, 90), Store._num(exif.get("lng"), -180, 180)
        if lat is not None and lng is not None and r["lat"] is None:
            upd["lat"], upd["lng"] = lat, lng
    r.update(**upd)
    if isinstance(ai, dict) and ai.get("category") in T.BY_ID and not r["confirmed"]:
        res = Store.sort_row(r)
        if (r["confidence"] or 0) < 0.5 and ai["category"] != "other":
            r.update(category=ai["category"], confidence=0.75, reasons=["your AI read the picture"] + (res["reasons"][:1] or []))
    else:
        Store.sort_row(r)
    return C.ok(fave=Store.fave(r, me))


@anvil.server.callable(require_user=True)
def set_photo(fave_id, data_url):
    me, r = _mine(fave_id)
    if r is None:
        return C.fail("That fave isn't yours.")
    err = Store.store_photo(r, data_url)
    return err or C.ok(fave=Store.fave(r, me))


@anvil.server.http_endpoint("/photo")
def photo(k=None, **kw):
    r = app_tables.faves.get(photo_key=k) if k and len(k) >= 20 else None
    if r is None or r["photo"] is None:
        return anvil.server.HttpResponse(404, "Not found")
    return anvil.server.HttpResponse(200, r["photo"], headers={"Cache-Control": "public, max-age=31536000, immutable",
                                                               "Content-Type": r["photo"].content_type})


# ------------------------------------------------------------------------------------------- tab sets
@anvil.server.callable(require_user=True)
def tabsets():
    me = C.require_user()
    out = []
    for ts in app_tables.tabsets.search(tables.order_by("created", ascending=False), owner=me):
        rows = list(app_tables.faves.search(tabset=ts))
        cats = {}
        for r in rows:
            cats[r["category"] or "other"] = cats.get(r["category"] or "other", 0) + 1
        out.append({"id": ts.get_id(), "name": ts["name"], "created": C.iso(ts["created"]), "count": len(rows),
                    "cats": sorted(cats.items(), key=lambda kv: -kv[1])[:5],
                    "inbox": len([r for r in rows if r["status"] == "inbox"]),
                    "faves": [Store.fave(r, me, lists=[], slim=True) for r in rows[:200]]})
    return {"tabsets": out}


@anvil.server.callable(require_user=True)
def rename_tabset(tabset_id, name):
    me = C.require_user()
    ts = C.row_by_id(app_tables.tabsets, tabset_id)
    if ts is None or ts["owner"] != me:
        return C.fail("That tab set isn't yours.")
    name = C.text(name, 80)
    if not name:
        return C.fail("Give it a name.")
    ts["name"] = name
    return C.ok()


@anvil.server.callable(require_user=True)
def delete_tabset(tabset_id, with_faves=False):
    me = C.require_user()
    ts = C.row_by_id(app_tables.tabsets, tabset_id)
    if ts is None or ts["owner"] != me:
        return C.ok()
    for r in list(app_tables.faves.search(tabset=ts)):
        if with_faves:
            _delete(r)
        else:
            r["tabset"] = None
    if C.row_by_id(app_tables.tabsets, tabset_id) is not None:
        ts.delete()
    return C.ok()


@anvil.server.callable(require_user=True)
def keep_tabset(tabset_id):
    """Keep every tab of a set still in the inbox, with its suggested category."""
    me = C.require_user()
    ts = C.row_by_id(app_tables.tabsets, tabset_id)
    if ts is None or ts["owner"] != me:
        return C.fail("That tab set isn't yours.")
    n = 0
    for r in app_tables.faves.search(tabset=ts, status="inbox"):
        Store.confirm(r, r["category"] or "other")
        r.update(status="kept", updated=C.now())
        n += 1
    return C.ok(kept=n)


# ------------------------------------------------------------------------------------------- import / export
IMPORT_MAX = 400


@anvil.server.callable(require_user=True)
def import_items(items, source="import", group_name=None):
    """Bookmarks, OneTab, Pocket, Google Takeout, plain links: parsed in the browser, saved here. Links are read
    later (the inbox's enrich pass), so a big import is quick. Up to 400 per call; the page sends chunks."""
    me = C.require_user()
    if not isinstance(items, list) or not items:
        return C.fail("Nothing to import.")
    if len(items) > IMPORT_MAX:
        return C.fail("Send at most %d at a time." % IMPORT_MAX)
    if C.rate_limited("import", 40, 3600):
        return C.fail("That's a lot of importing for one hour. Try again later.")
    ts = None
    if group_name:
        ts = app_tables.tabsets.add_row(owner=me, name=C.text(group_name, 80) or "Imported", count=0, created=C.now(), is_demo=False)
    model = Store.model_of(me)
    added = again = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        f = {k: it.get(k) for k in ("url", "title", "note", "lat", "lng", "address", "tags", "category", "kind", "event_at")}
        if not (f.get("url") or f.get("lat") is not None or f.get("title")):
            continue
        f["status"] = "kept" if it.get("category") else "inbox"
        if it.get("added"):
            pass
        row, created = Store.create(me, f, source=C.text(source, 20) or "import", tabset=ts, model=model)
        added += created
        again += not created
    if ts is not None:
        ts["count"] = len(app_tables.faves.search(tabset=ts))
        if not ts["count"]:
            ts.delete()
    return C.ok(added=added, again=again)


@anvil.server.callable(require_user=True)
def export_all():
    me = C.require_user()
    out = []
    for r in _my_rows(me):
        d = Store.fave(r, me)
        d["category_name"] = T.BY_ID.get(d["cat"], {}).get("name", "")
        out.append(d)
    return {"faves": out, "lists": _brief_lists(me), "exported": C.iso(C.now())}


# ------------------------------------------------------------------------------------------- prefs + learning
@anvil.server.callable(require_user=True)
def set_prefs(home=None, settings=None):
    me = C.require_user()
    p = Store.prefs_for(me)
    if home is not None:
        if home == {}:
            p["home"] = None
        else:
            lat, lng = Store._num(home.get("lat"), -90, 90), Store._num(home.get("lng"), -180, 180)
            if lat is None or lng is None:
                return C.fail("That location doesn't look right.")
            p["home"] = {"lat": lat, "lng": lng, "label": C.text(home.get("label"), 80) or "Home base"}
    if isinstance(settings, dict):
        s = dict(p["settings"] or {})
        for k in ("radius_km", "units", "auto_keep", "events_classes", "ai_sort"):
            if k in settings:
                s[k] = settings[k] if not isinstance(settings[k], str) else C.text(settings[k], 60)
        p["settings"] = s
    return C.ok(home=p["home"], settings=public_settings(p))


@anvil.server.callable(require_user=True)
def learned():
    """What the sorter learned from this person: sites and words, with the category each points to."""
    me = C.require_user()
    m = Store.model_of(me)
    def top(table, n):
        out = []
        for k, cats in (table or {}).items():
            total = sum(cats.values())
            best = max(cats.items(), key=lambda kv: kv[1])
            out.append({"key": k, "cat": best[0], "n": best[1], "total": total})
        out.sort(key=lambda x: -x["total"])
        return out[:n]
    rows = list(_my_rows(me))
    judged = [r for r in rows if r["confirmed"] and r["suggested"]]
    right = len([r for r in judged if r["suggested"] == r["category"]])
    return {"domains": top(m.get("d"), 40), "words": top(m.get("w"), 40), "lessons": m.get("n") or 0,
            "judged": len(judged), "right": right}


@anvil.server.callable(require_user=True)
def forget_learned(kind=None, key=None):
    me = C.require_user()
    p = Store.prefs_for(me)
    m = dict(p["model"] or {})
    if kind is None:
        p["model"] = {}
        return C.ok()
    table = dict(m.get("d" if kind == "domain" else "w") or {})
    table.pop(key, None)
    m["d" if kind == "domain" else "w"] = table
    p["model"] = m
    return C.ok()


@anvil.server.callable(require_user=True)
def load_samples():
    me = C.require_user()
    n = DemoData.load_samples(me)
    return C.ok(added=n)


@anvil.server.callable(require_user=True)
def remove_samples():
    me = C.require_user()
    n = 0
    for r in list(app_tables.faves.search(owner=me, is_sample=True)):
        _delete(r)
        n += 1
    for lst in list(app_tables.lists.search(owner=me)):
        if (lst["description"] or "").startswith("Sample list") and not len(app_tables.list_items.search(list=lst)):
            lst.delete()
    return C.ok(removed=n)
