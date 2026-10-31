"""Discover: suggestions built from what you already love. No AI: a "taste profile" turns your kept faves into
well-formed searches, and the browser runs them against open data:

  places   OpenStreetMap via Overpass (tag filters like amenity=cafe + cuisine=vietnamese + outdoor_seating=yes,
           around your usual spots), with the map's own vector tiles as a fallback when Overpass is busy
  ideas    Wikipedia "more like this" on the titles of your favourite reads, videos and courses,
           and Wikipedia articles near you for culture lovers
  events   Wikidata festivals and recurring events near you (no key), and Ticketmaster's Discovery API when
           you add your own free key (kept in your browser), filtered by the kinds of things you save

This module only builds the profile (taste); saving a suggestion is Faves.save_fave with source "suggested".
"""
import anvil.server
from anvil.tables import app_tables

from . import common as C
from . import Store
from . import Taxonomy as T

# The main OSM tag to search for each place category when your faves don't tell us more.
CAT_QUERY = {
    "coffee": ("amenity", "cafe"), "eat": ("amenity", "restaurant"), "nightlife": ("amenity", "bar"),
    "outdoors": ("leisure", "park"), "culture": ("tourism", "museum"), "shop": ("shop", "*"), "stay": ("tourism", "hotel"),
    "health": ("leisure", "fitness_centre"), "home": ("shop", "furniture"),
}
MAIN_KEYS = ("amenity", "shop", "tourism", "leisure", "historic", "craft", "natural")
# Tags you keep using -> OSM filters that find more of the same.
TAG_FILTERS = {
    "vegan": ["diet:vegan", "yes|only"], "vegetarian": ["diet:vegetarian", "yes|only"], "terrace": ["outdoor_seating", "yes"],
    "wifi": ["internet_access", "wlan|yes"], "accessible": ["wheelchair", "yes"], "dog-friendly": ["dog", "yes"],
    "gluten-free": ["diet:gluten_free", "yes|only"],
}
LABELS = {
    "amenity=cafe": ("Cafés", "☕"), "amenity=restaurant": ("Restaurants", "🍜"), "amenity=bar": ("Bars", "🍸"), "amenity=pub": ("Pubs", "🍺"),
    "amenity=fast_food": ("Quick bites", "🌯"), "amenity=ice_cream": ("Ice cream", "🍦"), "leisure=park": ("Parks", "🌳"),
    "tourism=museum": ("Museums", "🏛️"), "tourism=gallery": ("Galleries", "🖼️"), "shop=bakery": ("Bakeries", "🥐"), "shop=books": ("Bookshops", "📚"),
    "tourism=viewpoint": ("Viewpoints", "🌄"), "leisure=garden": ("Gardens", "🌷"), "amenity=theatre": ("Theatres", "🎭"),
    "amenity=cinema": ("Cinemas", "🎬"), "tourism=hotel": ("Hotels", "🏨"), "leisure=fitness_centre": ("Gyms", "💪"),
    "shop=clothes": ("Clothes shops", "👗"), "shop=second_hand": ("Thrift shops", "🧥"), "craft=brewery": ("Breweries", "🍺"),
    "amenity=marketplace": ("Markets", "🧺"), "leisure=sports_centre": ("Sports centres", "🏸"), "shop=coffee": ("Coffee shops", "☕"),
}
EVENT_CLASSES = {"listen": "Music", "culture": "Arts & Theatre", "health": "Sports", "learn": "Miscellaneous", "watch": "Film",
                 "nightlife": "Music", "events": None}


def _label(k, v, cuisine=None):
    base, emoji = LABELS.get("%s=%s" % (k, v), (v.replace("_", " ").capitalize() + ("s" if not v.endswith("s") else ""), "📍"))
    if cuisine:
        return "%s %s" % (cuisine.replace("_", " ").capitalize(), base.lower()), emoji
    return base, emoji


def _centers(rows, home):
    out = []
    if home:
        out.append({"lat": home["lat"], "lng": home["lng"], "label": home.get("label") or "Home base", "n": 0, "home": True})
    buckets = {}
    for r in rows:
        if r["lat"] is None:
            continue
        key = (round(r["lat"] / 0.02), round(r["lng"] / 0.03))
        b = buckets.setdefault(key, {"lat": 0.0, "lng": 0.0, "n": 0, "rows": []})
        b["lat"] += r["lat"]
        b["lng"] += r["lng"]
        b["n"] += 1
        b["rows"].append(r)
    for key, b in sorted(buckets.items(), key=lambda kv: -kv[1]["n"])[:3]:
        lat, lng = b["lat"] / b["n"], b["lng"] / b["n"]
        if any(abs(c["lat"] - lat) < 0.01 and abs(c["lng"] - lng) < 0.015 for c in out):
            continue
        # name the area after the fave nearest its centre ("near Café Lumière")
        mid = min(b["rows"], key=lambda r: (r["lat"] - lat) ** 2 + (r["lng"] - lng) ** 2)
        out.append({"lat": round(lat, 5), "lng": round(lng, 5), "label": "near " + (mid["title"] or "your faves")[:40], "n": b["n"]})
    return out


@anvil.server.callable(require_user=True)
def taste():
    me = C.require_user()
    p = Store.prefs_for(me)
    rows = [r for r in app_tables.faves.search(owner=me) if r["status"] != "archived"]
    kept = [r for r in rows if r["status"] == "kept" or r["confirmed"]]
    places = [r for r in kept if r["lat"] is not None]

    groups = {}
    for r in places:
        osm = r["osm"] or {}
        main = next(((k, osm[k]) for k in MAIN_KEYS if osm.get(k)), None)
        if main is None:
            q = CAT_QUERY.get(r["category"])
            if not q:
                continue
            main = q
        cuisine = (osm.get("cuisine") or "").split(";")[0].strip() or None
        weight = 1 + (1 if r["stage"] == "loved" else 0) + max(0, (r["rating"] or 0) - 3) * 0.5
        for key in ((main[0], main[1], cuisine), (main[0], main[1], None)) if cuisine else ((main[0], main[1], None),):
            g = groups.setdefault(key, {"n": 0, "w": 0.0, "seeds": [], "tags": {}, "cat": r["category"]})
            g["n"] += 1
            g["w"] += weight
            if len(g["seeds"]) < 4:
                g["seeds"].append(r["title"])
            for t in r["tags"] or []:
                g["tags"][t] = g["tags"].get(t, 0) + 1
    recipes = []
    for (k, v, cuisine), g in sorted(groups.items(), key=lambda kv: (-kv[1]["w"], kv[0][2] is None)):
        if cuisine is None and any(c and kk == k and vv == v and gg["n"] == g["n"] for (kk, vv, c), gg in groups.items()):
            continue  # "Bakeries" adds nothing when every one is a bagel bakery
        label, emoji = _label(k, v, cuisine)
        filters = [[k, v]]
        if cuisine:
            filters.append(["cuisine", cuisine])
        extra = [TAG_FILTERS[t] for t, n in sorted(g["tags"].items(), key=lambda kv: -kv[1]) if t in TAG_FILTERS and n >= max(2, g["n"] // 2)][:1]
        because = "You saved %d %s like %s" % (g["n"], "place" if g["n"] == 1 else "places", " and ".join(g["seeds"][:2]))
        recipes.append({"id": "%s-%s-%s" % (k, v, cuisine or "any"), "label": label, "emoji": emoji, "cat": g["cat"],
                        "filters": filters, "prefer": extra, "because": because, "seeds": g["seeds"], "n": g["n"]})
        if len(recipes) >= 8:
            break
    if not recipes:
        for cid in ("coffee", "eat", "outdoors", "culture"):
            k, v = CAT_QUERY[cid]
            label, emoji = _label(k, v)
            recipes.append({"id": "%s-%s-any" % (k, v), "label": label, "emoji": emoji, "cat": cid, "filters": [[k, v]], "prefer": [],
                            "because": "A good start while we learn what you like", "seeds": [], "n": 0})

    counts = {}
    for r in kept:
        counts[r["category"] or "other"] = counts.get(r["category"] or "other", 0) + 1
    reads = sorted([r for r in kept if r["category"] in ("read", "learn", "watch", "listen", "ideas", "tools") and r["kind"] != "place"],
                   key=lambda r: (-(r["rating"] or 0), r["created"]), reverse=False)
    seeds = []
    for r in reads[:12]:
        t = (r["meta"] or {}).get("entity") or r["title"] or ""
        t = t.split(" | ")[0].split(" - ")[0].split(" – ")[0].strip()
        if 3 <= len(t) <= 90 and t not in seeds:
            seeds.append(t)
    classes = []
    for cid, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        c = EVENT_CLASSES.get(cid, "x")
        if c != "x" and c and c not in classes:
            classes.append(c)
    tags = {}
    for r in kept:
        for t in r["tags"] or []:
            tags[t] = tags.get(t, 0) + 1
    saved = [[(r["title"] or "").lower(), r["lat"], r["lng"]] for r in rows if r["lat"] is not None][:600]
    return {"centers": _centers(places, p["home"]), "recipes": recipes, "seeds": seeds[:6], "event_classes": classes[:3],
            "counts": counts, "tags": sorted(tags.items(), key=lambda kv: -kv[1])[:10], "saved": saved,
            "saved_urls": [r["url_norm"] for r in rows if r["url_norm"]][:2000], "places": len(places), "kept": len(kept),
            "cats": T.public()}
