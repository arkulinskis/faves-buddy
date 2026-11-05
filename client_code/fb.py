"""Faves Buddy's shared client pieces: the categories (fb_boot, loaded once), stages, the inbox count in the header,
location, and thin wrappers around the JavaScript engines in theme/assets:

    fb-engine.js   FB.drawCover, openNow/dist/when, geo, copy/download/share, import parsers, export, FB.tidy
    fb-map.js      FB.map / FB.mapView (Components/MapView) and FB.data (OpenStreetMap, Photon, Wikipedia, Wikidata,
                   Ticketmaster)
    fb-media.js    FB.media (shrink, EXIF, on-device OCR, extract) and FB.ai (bring-your-own-key Claude)

Data crosses to JavaScript as JSON (to_js / from_js), so nested dicts and lists arrive as plain objects both ways.
"""
import json

import anvil.server
from anvil.js import window

from . import router, state

KIND_ICON = {"link": "link", "place": "pin", "photo": "image", "note": "note", "idea": "bulb", "event": "calendar"}
STAGES = [("", "No status"), ("want", "Want to go"), ("been", "Been there"), ("loved", "Loved it")]
LATER = {"read": "To read", "watch": "To watch", "listen": "To listen", "recipes": "To cook", "learn": "To learn",
         "shop": "Want it", "gifts": "To give"}
SOURCES = {"extension": "the browser extension", "app": "the app", "import": "an import", "onetab": "OneTab",
           "suggested": "Discover", "shared": "a shared list", "sample": "the samples", "map": "the map",
           "share": "your phone's share menu", "screenshot": "a screenshot sweep", "fave-link": "a shared link"}
DEFAULT_CENTER = {"lat": 45.5165, "lng": -73.5795}  # Montréal, until the person has places or a home spot
_cache: dict = {"boot": None, "inbox": 0, "cats": [], "cat": {}}


def to_js(value):
    """A Python dict/list as a plain JavaScript object (through JSON)."""
    return window.JSON.parse(json.dumps(value))


def from_js(value):
    """A JavaScript object/array (or a JSON string) as Python dicts and lists."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return json.loads(window.JSON.stringify(value))


# ---------------------------------------------------------------- categories + prefs
def set_cats(cats):
    if not cats:
        return
    _cache["cats"] = cats
    _cache["cat"] = {c["id"]: c for c in cats}
    window.FB.setCats(json.dumps(cats))


def boot(force=False):
    """fb_boot once per visit: categories, home spot, settings, the AI-sorting switch."""
    if _cache["boot"] is None or force:
        b = anvil.server.call_s("fb_boot")
        set_cats(b.get("cats"))
        _cache["boot"] = b
    return _cache["boot"]


def cats():
    return _cache["cats"]


def cat(cid):
    c = _cache["cat"].get(cid) or _cache["cat"].get("other")
    return c or {"id": "other", "name": "Unsorted", "emoji": "📌", "color": "#90a4ae"}


def cat_label(cid):
    c = cat(cid)
    return "%s %s" % (c["emoji"], c["name"])


def home():
    b = _cache["boot"] or {}
    return b.get("home")


def set_home(h):
    if _cache["boot"] is not None:
        _cache["boot"]["home"] = h


def ai_sort():
    b = _cache["boot"] or {}
    return b.get("ai") or {"available": False, "on": False}


def stages(f):
    """The three statuses, worded for what the fave is (places: Want to go; reads: To read...)."""
    if f.get("kind") in ("place", "event") or f.get("lat") is not None:
        return STAGES[1:]
    return [("want", LATER.get(f.get("cat"), "Later")), ("been", "Done"), ("loved", "Loved it")]


def stage_label(f):
    s = f.get("stage") or ""
    for key, label in stages(f):
        if key == s:
            return "Loved" if s == "loved" else label
    return ""


# ---------------------------------------------------------------- inbox count (header + tab bar)
def set_inbox(n):
    n = n or 0
    if _cache["inbox"] == n:
        return
    _cache["inbox"] = n
    sh = router.shell()
    if sh is not None and hasattr(sh, "show_inbox"):
        sh.show_inbox(n)


def inbox_count():
    return _cache["inbox"]


# ---------------------------------------------------------------- time, distance, hours
def when(iso, short=False):
    return window.FB.when(iso, short) if iso else ""


def fmt_date(iso):
    return window.FB.fmtDate(iso) if iso else ""


def dist(a, b):
    """km between two {lat, lng} (None when either has no spot)."""
    if not a or not b or a.get("lat") is None or b.get("lat") is None:
        return None
    return window.FB.dist(to_js({"lat": a["lat"], "lng": a["lng"]}), to_js({"lat": b["lat"], "lng": b["lng"]}))


def fmt_dist(km):
    return window.FB.fmtDist(km) if km is not None else ""


def open_state(f):
    """'open', 'closed' or '' (no hours, or hours we can't read) from OpenStreetMap opening_hours."""
    spec = (f.get("osm") or {}).get("opening_hours")
    return window.FB.openState(spec) if spec else ""


def geo(ask=False):
    """Where the person is: their shared location (asks the browser when ask=True), else their home spot, else None.
    The dict has home=True when it is the home spot."""
    h = home()
    return from_js(window.FB.geo(bool(ask), json.dumps(h) if h else ""))


def snooze_choices():
    return from_js(window.FB.snoozeChoices())


def app_url(hash_part):
    return window.FB.appUrl(hash_part)


def copy(text, message="Copied"):
    if window.FB.copy(text):
        state.toast(message, "ok")
    else:
        state.toast("Couldn't copy. Select the text and copy it yourself.", "error")


def directions_url(f):
    return "https://www.google.com/maps/dir/?api=1&destination=%s,%s" % (f["lat"], f["lng"])


def osm_url(f):
    return "https://www.openstreetmap.org/?mlat=%s&mlon=%s#map=18/%s/%s" % (f["lat"], f["lng"], f["lat"], f["lng"])


def short_url(u):
    u = (u or "").split("://", 1)[-1]
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def chip_items(cats_list, selected=None, counts=None, all_label=None, total=None, sm=False):
    """Items for a row of category chips (Items/Chip): optional "All" first, then each category with its count."""
    out = []
    if all_label is not None:
        out.append({"key": "", "label": all_label, "n": total, "on": not selected, "sm": sm})
    for c in cats_list:
        n = counts.get(c["id"]) if counts is not None else None
        if counts is not None and not n:
            continue
        out.append({"key": c["id"], "label": "%s %s" % (c["emoji"], c["name"]), "n": n, "on": c["id"] == selected, "sm": sm})
    return out
