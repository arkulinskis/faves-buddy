"""Shared logic for faves, used by every feature module (Faves, Lists, Clip, Discover, DemoData).

- create(owner, fields, source): save something, or bump the copy that's already saved (same link, same place)
- sort_row(row): first-pass category + tags (Classify), unless the person already chose
- confirm(row, category): the person chose: store it and teach their learner
- enrich(row): read the link (Fetch) and fill in title, picture, place, schema, then sort again
- fave(row, me): the plain dict the browser gets
- roles on shared lists, prefs (extension token, learner, home spot), photo storage + URLs
"""
import base64
import datetime as dt
import random
import re
import string

import anvil
import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import Classify
from . import Fetch
from . import Taxonomy as T

KINDS = ("link", "place", "photo", "note", "idea", "event")
STATUSES = ("inbox", "kept", "archived")
STAGES = ("", "want", "been", "loved")
MAX_PHOTO = 3 * 1024 * 1024
META_KEYS = ("description", "image", "site_name", "og_type", "schema", "lang", "read_min", "address", "startDate", "endDate",
             "priceRange", "servesCuisine", "recipeYield", "totalTime", "entity", "ocr", "ai", "found", "exif", "final_url",
             "fetch_error", "selection", "favicon", "tags_edited", "fetched", "osm_ref", "suggested_by", "country", "wiki", "ai_sort")


def token(n=24):
    rnd = random.SystemRandom()
    return "".join(rnd.choice(string.ascii_letters + string.digits) for _ in range(n))


# ------------------------------------------------------------------------------------------- prefs
def prefs_for(user, create=True):
    row = app_tables.prefs.get(owner=user)
    if row is None and create:
        row = app_tables.prefs.add_row(owner=user, clip_token=token(32), model={}, home=None, settings={}, created=C.now())
    return row


def model_of(user):
    p = prefs_for(user, create=False)
    return (p["model"] if p is not None else None) or {}


def api_origin():
    try:
        return anvil.server.get_api_origin()
    except Exception:
        return ""


def photo_url(row):
    if not row["photo_key"]:
        return None
    return "%s/photo?k=%s" % (api_origin(), row["photo_key"])


# ------------------------------------------------------------------------------------------- sorting
def info_of(row):
    m = row["meta"] or {}
    return {"kind": row["kind"], "title": row["title"] or "", "url": row["url"] or "", "text": m.get("description") or "",
            "note": row["note"] or "", "ocr": m.get("ocr") or "", "schema": m.get("schema") or [], "og_type": m.get("og_type") or "",
            "osm": row["osm"] or {}, "site_name": m.get("site_name") or "", "when": row["event_at"] is not None}


def sort_row(row, model=None):
    """Category + tags from the rules and this person's learner. Leaves a confirmed category alone."""
    if model is None:
        model = model_of(row["owner"])
    r = Classify.classify(info_of(row), model)
    upd = {}
    if not row["confirmed"]:
        upd.update(category=r["category"], confidence=r["confidence"], reasons=r["reasons"])
        if not row["suggested"]:
            upd["suggested"] = r["category"]
    m = row["meta"] or {}
    if not m.get("tags_edited"):
        upd["tags"] = _merge_tags(row["tags"] or [], r["tags"])
    if upd:
        row.update(**upd)
    return r


def _merge_tags(a, b):
    out = []
    for t in list(a) + list(b):
        t = C.text(t, 30).lower()
        if t and t not in out:
            out.append(t)
    return out[:12]


def confirm(row, category, teach=True):
    """The person says this belongs in `category`: keep it, and learn from it (domain + title words).
    Sample and demo faves don't teach (removing them shouldn't leave lessons behind)."""
    if category not in T.BY_ID:
        return False
    before = row["category"]
    if teach and not row["is_sample"] and not row["is_demo"]:
        prefs = prefs_for(row["owner"])
        forget = before if (before and before != category and not row["confirmed"]) else None
        prefs["model"] = Classify.learn(prefs["model"] or {}, info_of(row), category, forget=forget)
    reasons = row["reasons"] or []
    if before != category:
        reasons = ["you chose it"]
    row.update(category=category, confirmed=True, confidence=1.0, reasons=reasons, updated=C.now())
    return True


# ------------------------------------------------------------------------------------------- saving
def _num(v, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 6) if lo <= f <= hi else None


def parse_when(v):
    """ISO date or datetime (from schema.org startDate, the browser...) -> aware datetime, or None."""
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    s = str(v).strip().replace("Z", "+00:00")
    try:
        if len(s) == 10:
            d = dt.date.fromisoformat(s)
            return dt.datetime(d.year, d.month, d.day, 12, tzinfo=dt.timezone.utc)
        d = dt.datetime.fromisoformat(s[:32])
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def clean_meta(meta):
    out = {}
    for k, v in (meta or {}).items():
        if k not in META_KEYS or v in (None, "", []):
            continue
        if isinstance(v, str):
            v = C.text(v, 6000 if k in ("ocr", "ai") else 600, multiline=k in ("ocr", "ai"))
        elif isinstance(v, list):
            v = [C.text(x, 120) if isinstance(x, str) else x for x in v[:20]]
        elif isinstance(v, dict):
            v = {C.text(a, 40): (C.text(b, 400) if isinstance(b, str) else b) for a, b in list(v.items())[:30]}
        out[k] = v
    return out


def find_same(owner, url_norm=None, title=None, lat=None, lng=None):
    if url_norm:
        return app_tables.faves.get(owner=owner, url_norm=url_norm)
    if title and lat is not None:
        for r in app_tables.faves.search(owner=owner, title=title):
            if r["lat"] is not None and abs(r["lat"] - lat) < 0.0005 and abs(r["lng"] - lng) < 0.0007:
                return r
    return None


def create(owner, f, source="app", tabset=None, model=None, enrich_now=False):
    """Save one thing. Returns (row, created). The same link or place saved again bumps the existing one."""
    f = f or {}
    url = C.text(f.get("url"), 1000)
    if url and not re.match(r"^https?://", url, re.I):
        url = "https://" + url if "." in url and " " not in url else ""
    norm = Fetch.normalize_url(url) if url else ""
    lat, lng = _num(f.get("lat"), -90, 90), _num(f.get("lng"), -180, 180)
    if lat is None or lng is None:
        lat = lng = None
    title = C.text(f.get("title"), 200)
    note = C.text(f.get("note"), 4000, multiline=True)
    meta = clean_meta(f.get("meta"))
    osm = Fetch.slim_tags(f.get("osm")) if isinstance(f.get("osm"), dict) else {}
    kind = f.get("kind") if f.get("kind") in KINDS else None
    if url and Fetch.is_maps_url(url):
        place = Fetch.parse_maps_url(url)
        if lat is None and place.get("lat") is not None:
            lat, lng = place["lat"], place["lng"]
        title = title if title and not title.lower().startswith(("google maps", "http")) else (place.get("name") or title)
        kind = kind or "place"
    if not kind:
        kind = "link" if url else ("place" if lat is not None else "note")

    same = find_same(owner, norm or None, title if kind == "place" else None, lat, lng)
    if same is not None:
        upd = {"saves": (same["saves"] or 1) + 1, "updated": C.now()}
        if note and note not in (same["note"] or ""):
            upd["note"] = ((same["note"] or "") + "\n\n" + note).strip()[:4000]
        if same["status"] == "archived":
            upd["status"] = "inbox"
        same.update(**upd)
        _add_to_list(owner, same, f.get("list_id"))
        return same, False

    status = f.get("status") if f.get("status") in STATUSES else "inbox"
    if f.get("enriched"):
        meta["fetched"] = True  # the browser or the extension already read the page
    needs = bool(url and not meta.get("fetched")) or (kind == "place" and lat is not None and not osm)
    row = app_tables.faves.add_row(
        owner=owner, kind=kind, title=title or (Classify.domain_of(url) if url else "Untitled"), url=url or None, url_norm=norm or None,
        domain=Classify.domain_of(url) if url else None, note=note or None, category="other", confidence=0, suggested=None, confirmed=False,
        reasons=[], tags=[C.text(t, 30).lower() for t in (f.get("tags") or [])[:12] if C.text(t, 30)], status=status,
        stage=f.get("stage") if f.get("stage") in STAGES else "", rating=None, lat=lat, lng=lng, address=C.text(f.get("address"), 200) or None,
        osm=osm, meta=meta, photo=None, photo_key=None, tabset=tabset, source=C.text(source, 20), saves=1,
        enriched=not needs, remind_at=None, event_at=parse_when(f.get("event_at") or meta.get("startDate")),
        opened_at=None, created=C.now(), updated=C.now(), is_demo=bool(f.get("is_demo")), is_sample=bool(f.get("is_sample")))
    if f.get("tags"):
        row["meta"] = dict(row["meta"] or {}, tags_edited=True)
    if enrich_now and needs:
        enrich(row, model=model)
    else:
        sort_row(row, model)
    cat = f.get("category")
    if cat in T.BY_ID and cat != "other":
        confirm(row, cat)
        if status == "inbox" and f.get("status") is None:
            row["status"] = "kept"
    _add_to_list(owner, row, f.get("list_id"))
    return row, True


def _add_to_list(user, fave, list_id):
    if not list_id:
        return
    lst = C.row_by_id(app_tables.lists, list_id)
    if lst is None or role(user, lst) not in ("owner", "editor"):
        return
    if app_tables.list_items.get(list=lst, fave=fave) is None:
        app_tables.list_items.add_row(list=lst, fave=fave, added_by=user, added=C.now(), is_demo=bool(fave["is_demo"]))
        lst["updated"] = C.now()


def _match_place(row):
    m = Fetch.osm_match(row["lat"], row["lng"], row["title"] if row["title"] and row["title"] != "Untitled" else None)
    if not m:
        return False
    upd = {"osm": dict(m.get("osm") or {}), "meta": dict(row["meta"] or {}, osm_ref=m.get("ref"), country=m.get("country"))}
    if not row["address"] and m.get("address"):
        upd["address"] = m["address"][:200]
    if (not row["title"] or row["title"] == "Untitled") and m.get("name"):
        upd["title"] = m["name"][:200]
    row.update(**upd)
    return True


def enrich(row, model=None):
    """Read the saved link (what the page says about itself) and match places to OpenStreetMap.
    Safe to call twice: a link is read once, a place matched once."""
    if row["enriched"]:
        return row
    meta = dict(row["meta"] or {})
    if row["url"] and not meta.get("fetched"):
        try:
            page = Fetch.read_page(row["url"])
        except Exception as e:
            page = {}
            meta["fetch_error"] = str(e)[:200]
        meta["fetched"] = True
    else:
        page = {}
    upd = {}
    for k in ("description", "image", "site_name", "og_type", "schema", "lang", "read_min", "startDate", "endDate", "priceRange",
              "servesCuisine", "recipeYield", "totalTime", "entity", "final_url"):
        if page.get(k) not in (None, "", []) and not meta.get(k):
            meta[k] = page[k]
    t = row["title"] or ""
    if page.get("title") and (not t or t == row["domain"] or t.startswith("http") or t == "Untitled"):
        upd["title"] = page["title"][:200]
    if page.get("kind") == "place" and row["kind"] == "link":
        upd["kind"] = "place"
    if row["lat"] is None and page.get("lat") is not None:
        upd["lat"], upd["lng"] = page["lat"], page["lng"]
    if not row["address"] and page.get("address"):
        upd["address"] = page["address"][:200]
    if not row["event_at"] and page.get("startDate"):
        upd["event_at"] = parse_when(page["startDate"])
    upd["meta"] = clean_meta(meta)
    upd["enriched"] = True
    row.update(**upd)
    if row["kind"] == "place" and row["lat"] is not None and not row["osm"]:
        _match_place(row)
    sort_row(row, model)
    return row


# ------------------------------------------------------------------------------------------- photos
def store_photo(row, data_url):
    """data:image/jpeg;base64,... (shrunk in the browser) -> media on the row + an unguessable key for its URL."""
    m = re.match(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", data_url or "", re.S)
    if not m:
        return C.fail("That picture couldn't be read. Try a JPEG or PNG.")
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except Exception:
        return C.fail("That picture couldn't be read.")
    if len(raw) > MAX_PHOTO:
        return C.fail("That picture is too big (over 3 MB even after shrinking).")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[m.group(1)]
    row.update(photo=anvil.BlobMedia(m.group(1), raw, name="fave.%s" % ext), photo_key=row["photo_key"] or token(28))
    return None


# ------------------------------------------------------------------------------------------- lists + roles
def claim_invites(user):
    """Invites sent to this person's email before they had an account (or before they signed in) become theirs."""
    email = (user["email"] or "").lower()
    if not email:
        return
    for m in app_tables.members.search(email=email, user=None):
        m["user"] = user


def role(user, lst):
    if lst is None:
        return None
    if user is not None and lst["owner"] == user:
        return "owner"
    if user is not None:
        m = app_tables.members.get(list=lst, user=user)
        if m is not None:
            return m["role"] if m["role"] in ("viewer", "editor") else "viewer"
    return None


def lists_of_fave(fave, user):
    """Ids of the lists this fave is in that `user` can see."""
    out = []
    for li in app_tables.list_items.search(fave=fave):
        if role(user, li["list"]):
            out.append(li["list"].get_id())
    return out


def can_view(user, fave):
    if fave is None:
        return False
    if user is not None and fave["owner"] == user:
        return True
    for li in app_tables.list_items.search(fave=fave):
        if role(user, li["list"]):
            return True
    return False


# ------------------------------------------------------------------------------------------- what the browser gets
OSM_SHOW = ("opening_hours", "website", "contact:website", "phone", "contact:phone", "cuisine", "amenity", "shop", "tourism", "leisure",
            "wheelchair", "outdoor_seating", "diet:vegan", "diet:vegetarian", "wikipedia", "wikidata")


def fave(row, me=None, lists=None, slim=False):
    m = row["meta"] or {}
    mine = me is not None and row["owner"] == me
    d = {"id": row.get_id(), "kind": row["kind"], "title": row["title"] or "", "url": row["url"], "domain": row["domain"],
         "cat": row["category"] or "other", "conf": row["confidence"] or 0, "confirmed": bool(row["confirmed"]),
         "tags": row["tags"] or [], "status": row["status"], "stage": row["stage"] or "", "rating": row["rating"],
         "lat": row["lat"], "lng": row["lng"], "address": row["address"], "image": photo_url(row) or m.get("image"),
         "photo": bool(row["photo_key"]), "event_at": C.iso(row["event_at"]), "created": C.iso(row["created"]),
         "saves": row["saves"] or 1, "mine": mine, "sample": bool(row["is_sample"]), "demo": bool(row["is_demo"]),
         "desc": (m.get("description") or "")[:240], "read_min": m.get("read_min") or 0, "enriched": bool(row["enriched"]),
         "osm": {k: v for k, v in (row["osm"] or {}).items() if k in OSM_SHOW}}
    if not mine:
        d["owner"] = C.name_of(row["owner"])
    if slim:
        return d
    d.update({"note": row["note"] or "", "reasons": row["reasons"] or [], "suggested": row["suggested"], "source": row["source"],
              "remind_at": C.iso(row["remind_at"]),
              "opened_at": C.iso(row["opened_at"]), "updated": C.iso(row["updated"]),
              "tabset": row["tabset"].get_id() if row["tabset"] is not None else None,
              "tabset_name": row["tabset"]["name"] if row["tabset"] is not None else None,
              "meta": {k: m.get(k) for k in ("site_name", "og_type", "schema", "lang", "startDate", "endDate", "priceRange",
                                              "servesCuisine", "recipeYield", "totalTime", "entity", "ocr", "ai", "found", "exif",
                                              "fetch_error", "selection", "ai_sort") if m.get(k)}})
    if lists is not None:
        d["lists"] = lists
    elif me is not None:
        d["lists"] = lists_of_fave(row, me)
    return d
