"""Sharing one fave by link, and Top faves: what people save most around a spot.

  share_fave(id, on)       the owner turns a public link to one fave on (a random token) or off
  shared_fave(token)       anyone with the link: the fave without its note, tags or the owner's email
  copy_shared_fave(token)  a signed-in visitor saves it into their own collection (visitors sign up first)
  top_faves(lat, lng, km)  places saved by at least MIN_PEOPLE different people near a spot, most saved first.
                           Counted anonymously: never who saved them, never notes or pictures. Samples don't count
                           (everyone's copies would add up), and people who turned it off in Tools don't count.
"""
import math
import re

import anvil.server
import anvil.tables.query as q
from anvil.tables import app_tables

from . import common as C
from . import Store
from . import Taxonomy as T

MIN_PEOPLE = 2
OSM_KEYS = ("amenity", "shop", "tourism", "leisure", "craft", "historic")


# ------------------------------------------------------------------------------------------- one fave by link
@anvil.server.callable(require_user=True)
def share_fave(fave_id, on=True):
    me = C.require_user()
    row = C.row_by_id(app_tables.faves, fave_id)
    if row is None or row["owner"] != me:
        return C.fail("You can only share your own faves.")
    if on:
        if not row["share_token"]:
            row["share_token"] = Store.token(22)
    else:
        row["share_token"] = None
    return C.ok(token=row["share_token"])


def _shared_row(token):
    token = C.text(token, 40)
    if not token or not re.match(r"^[A-Za-z0-9_-]+$", token):
        return None
    row = app_tables.faves.get(share_token=token)
    if row is None or row["owner"] is None or row["status"] == "drop":
        return None
    return row


def _yours(me, row):
    """The person's own copy of a shared fave, if they already have it (same link, or same name at the same spot)."""
    if me is None:
        return None
    if row["owner"] == me:
        return row
    if row["url_norm"]:
        mine = app_tables.faves.get(owner=me, url_norm=row["url_norm"])
        if mine is not None:
            return mine
    if row["lat"] is not None:
        t = (row["title"] or "").strip().lower()
        for r in app_tables.faves.search(owner=me, lat=q.between(row["lat"] - 0.0005, row["lat"] + 0.0005)):
            if r["lng"] is not None and abs(r["lng"] - row["lng"]) < 0.0007 and (r["title"] or "").strip().lower() == t:
                return r
    return None


@anvil.server.callable
def shared_fave(token):
    """A fave someone shared by link. Anyone with the link; no note, no tags, no emails."""
    row = _shared_row(token)
    if row is None:
        return C.fail("This link doesn't work any more. Ask whoever shared it for a new one.")
    me = C.me()
    d = Store.fave(row, None, slim=True)
    for k in ("mine", "sample", "demo", "conf", "enriched", "saves", "tags", "status", "stage", "rating"):
        d.pop(k, None)
    d["owner"] = C.name_of(row["owner"])
    yours = _yours(me, row)
    return C.ok(fave=d, signed_in=me is not None, own=me is not None and row["owner"] == me,
                yours=yours.get_id() if yours is not None else None, cats=T.public())


@anvil.server.callable(require_user=True)
def copy_shared_fave(token):
    """Save a fave from a shared link into your own collection (it lands in the inbox, sorted)."""
    me = C.require_user()
    fv = _shared_row(token)
    if fv is None:
        return C.fail("This link doesn't work any more. Ask whoever shared it for a new one.")
    mine = _yours(me, fv)
    if mine is not None:
        return C.ok(fave=Store.fave(mine, me, slim=True), created=False)
    f = {"url": fv["url"], "title": fv["title"], "lat": fv["lat"], "lng": fv["lng"], "address": fv["address"], "osm": fv["osm"],
         "kind": fv["kind"], "event_at": C.iso(fv["event_at"]), "enriched": True,
         "meta": {k: v for k, v in (fv["meta"] or {}).items() if k in ("description", "image", "site_name", "og_type", "schema", "read_min")},
         "note": "Shared with you by %s" % C.name_of(fv["owner"])}
    row, created = Store.create(me, f, source="fave-link")
    if created and fv["photo"] is not None:
        row.update(photo=fv["photo"], photo_key=Store.token(28))
    return C.ok(fave=Store.fave(row, me, slim=True), created=created)


# ------------------------------------------------------------------------------------------- top faves
def _opted_out():
    return set(p["owner"].get_id() for p in app_tables.prefs.search()
               if p["owner"] is not None and (p["settings"] or {}).get("top_faves") is False)


def _spot_for(me):
    """Where "around you" is when the browser didn't share a location: the home spot, else the middle of your places."""
    p = Store.prefs_for(me)
    if p["home"]:
        return p["home"]["lat"], p["home"]["lng"], "around " + (p["home"].get("label") or "your home spot")
    pts = [(r["lat"], r["lng"]) for r in app_tables.faves.search(owner=me) if r["lat"] is not None and r["status"] != "archived"]
    if not pts:
        return None
    return sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts), "around your places"


def _key(row):
    ref = (row["meta"] or {}).get("osm_ref")
    if ref:
        return "osm:" + str(ref)
    name = re.sub(r"[^a-z0-9]+", "", (row["title"] or "").lower())[:40]
    return "n:%s@%.3f,%.3f" % (name, row["lat"], row["lng"])


@anvil.server.callable(require_user=True)
def top_faves(lat=None, lng=None, km=5):
    me = C.require_user()
    near = "near you"
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)) or abs(lat) > 90 or abs(lng) > 180:
        spot = _spot_for(me)
        if spot is None:
            return C.ok(places=[], near="", min_people=MIN_PEOPLE)
        lat, lng, near = spot
    km = min(25.0, max(0.5, float(km or 5) if isinstance(km, (int, float)) else 5.0))
    dlat = km / 111.0
    dlng = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    out_ids = _opted_out()
    groups: dict = {}
    for r in app_tables.faves.search(lat=q.between(lat - dlat, lat + dlat), lng=q.between(lng - dlng, lng + dlng)):
        if r["owner"] is None or r["is_sample"] or r["status"] in ("drop", "archived") or r["lat"] is None:
            continue
        oid = r["owner"].get_id()
        if oid in out_ids and r["owner"] != me:
            continue
        g = groups.setdefault(_key(r), {"rows": [], "people": set()})
        g["rows"].append(r)
        g["people"].add(oid)
    out = []
    for key, g in groups.items():
        others = g["people"] - ({me.get_id()} if me is not None else set())
        if len(g["people"]) < MIN_PEOPLE or not others:
            continue
        rows = g["rows"]
        titles, cats = {}, {}
        for r in rows:
            titles[r["title"] or ""] = titles.get(r["title"] or "", 0) + 1
            cats[r["category"] or "other"] = cats.get(r["category"] or "other", 0) + 1
        first = rows[0]
        plat = sum(r["lat"] for r in rows) / len(rows)
        plng = sum(r["lng"] for r in rows) / len(rows)
        image = next(((r["meta"] or {}).get("image") for r in rows if (r["meta"] or {}).get("image")), None)
        osm = {k: v for k, v in (first["osm"] or {}).items() if k in Store.OSM_SHOW}
        place: dict = {"id": "top:" + key, "key": key, "title": max(titles, key=lambda t: titles[t]) or "A place",
                        "cat": max(cats, key=lambda c: cats[c]), "kind": "place", "lat": round(plat, 6), "lng": round(plng, 6),
                        "address": next((r["address"] for r in rows if r["address"]), ""), "image": image, "osm": osm,
                        "people": len(g["people"]), "mine": any(r["owner"] == me for r in rows),
                        "km": round(math.hypot((plat - lat) * 111.0, (plng - lng) * 111.0 * math.cos(math.radians(lat))), 2)}
        out.append(place)
    out.sort(key=lambda p: (-p["people"], p["km"]))
    return C.ok(places=out[:30], near=near, min_people=MIN_PEOPLE, center={"lat": lat, "lng": lng})


@anvil.server.callable(require_user=True)
def save_top_fave(place):
    """Save a top fave into your own collection (only what's public about it: name, spot, OpenStreetMap tags)."""
    me = C.require_user()
    if not isinstance(place, dict):
        return C.fail("That place didn't come through.")
    f = {"title": C.text(place.get("title"), 200), "lat": place.get("lat"), "lng": place.get("lng"),
         "address": C.text(place.get("address"), 300), "osm": place.get("osm") if isinstance(place.get("osm"), dict) else {},
         "kind": "place"}
    if f["lat"] is None or not f["title"]:
        return C.fail("That place didn't come through.")
    row, created = Store.create(me, f, source="suggested")
    return C.ok(fave=Store.fave(row, me, slim=True), created=created)
