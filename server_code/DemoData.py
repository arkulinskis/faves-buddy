"""Demo content, so the app never looks empty.

Two kinds:
  - The demo (is_demo=True): three fictional people (Maya, Theo, Ines) with faves and two PUBLIC lists the
    landing page links to ("peek at a shared list"). Loaded on the first visit, removable in Admin -> Demo data.
    Removing it is remembered: it doesn't come back by itself.
  - Sample packs (is_sample=True): a new member can load the same example faves into their own account from
    the empty library, and remove them in one click from Tools.

Every place is fictional (made-up names on plausible Montréal streets); links point at .example sites,
except a few real, stable pages (Paul Graham's essay, a Wikipedia article, a GitHub topic).
"""
import datetime as dt

from anvil.tables import app_tables

from . import common as C
from . import Store

DEMO_USERS = [
    ("Maya Chen", "maya.demo@example.com"),
    ("Theo Martin", "theo.demo@example.com"),
    ("Ines Ozola", "ines.demo@example.com"),
]
# Tables that hold demo rows (each has an is_demo column). Children before parents.
DEMO_TABLES = ["list_items", "members", "lists", "faves", "tabsets"]


def _sat_evening():
    now = C.now()
    days = (5 - now.weekday()) % 7 or 7
    d = (now + dt.timedelta(days=days)).replace(hour=23, minute=0, second=0, microsecond=0)  # 19:00 in Montréal
    return d.isoformat()


def _pack():
    """key -> fields. Places carry OpenStreetMap-style tags (what a real match gives), so sorting and Discover work."""
    return [
        ("lumiere", {"title": "Café Lumière", "kind": "place", "lat": 45.52352, "lng": -73.58681, "address": "212 Rue Saint-Viateur O, Montréal",
                     "osm": {"amenity": "cafe", "internet_access": "wlan", "outdoor_seating": "yes", "opening_hours": "Mo-Fr 07:00-18:00; Sa,Su 08:00-17:00"},
                     "stage": "loved", "rating": 5, "note": "Best flat white in the neighbourhood. Window seats are perfect for writing mornings."}),
        ("nord", {"title": "Torréfacteur Nord", "kind": "place", "lat": 45.52618, "lng": -73.59902, "address": "45 Rue Bernard O, Montréal",
                  "osm": {"shop": "coffee", "opening_hours": "Tu-Su 09:00-17:00"}, "stage": "want",
                  "note": "Roastery with Saturday cuppings. Bring a bag for beans."}),
        ("pho", {"title": "Phở Saigon Rouge", "kind": "place", "lat": 45.52991, "lng": -73.61502, "address": "980 Rue Jean-Talon O, Montréal",
                 "osm": {"amenity": "restaurant", "cuisine": "vietnamese", "opening_hours": "Mo-Su 11:00-21:30"}, "stage": "been", "rating": 4,
                 "note": "Get the special with extra herbs. Cash only!"}),
        ("bagel", {"title": "Bagel Atelier", "kind": "place", "lat": 45.52291, "lng": -73.60052, "address": "88 Rue Fairmount O, Montréal",
                   "osm": {"shop": "bakery", "cuisine": "bagel", "opening_hours": "24/7"}, "stage": "loved", "rating": 5,
                   "note": "Sesame, still warm. Open all night."}),
        ("nonna", {"title": "Trattoria Nonna Lu", "kind": "place", "lat": 45.53452, "lng": -73.61401, "address": "6800 Boul. Saint-Laurent, Montréal",
                   "osm": {"amenity": "restaurant", "cuisine": "italian", "outdoor_seating": "yes", "opening_hours": "Tu-Su 17:00-22:30"},
                   "stage": "want", "tags": ["date night", "terrace", "italian"], "note": "Book a terrace table for a summer Friday."}),
        ("vert", {"title": "Le Comptoir Vert", "kind": "place", "lat": 45.51802, "lng": -73.58501, "address": "4100 Rue Saint-Denis, Montréal",
                  "osm": {"amenity": "restaurant", "cuisine": "vegan", "diet:vegan": "only", "opening_hours": "We-Su 11:30-21:00"}, "stage": "want"}),
        ("hibou", {"title": "Bar Hibou", "kind": "place", "lat": 45.52082, "lng": -73.58252, "address": "3990 Rue Saint-Laurent, Montréal",
                   "osm": {"amenity": "bar", "opening_hours": "Mo-Su 17:00-03:00"}, "stage": "been", "rating": 4,
                   "tags": ["cocktails", "late night"], "note": "Ask for the off-menu maple old fashioned."}),
        ("canal", {"title": "Microbrasserie du Canal", "kind": "place", "lat": 45.47972, "lng": -73.57861, "address": "1200 Rue Notre-Dame O, Montréal",
                   "osm": {"craft": "brewery", "amenity": "pub", "outdoor_seating": "yes"}, "stage": "want"}),
        ("erables", {"title": "Parc des Érables", "kind": "place", "lat": 45.52802, "lng": -73.57003, "address": "Avenue des Érables, Montréal",
                     "osm": {"leisure": "park"}, "stage": "loved", "tags": ["picnic", "summer"],
                     "note": "Big shady trees by the pond. Bring the blanket."}),
        ("belvedere", {"title": "Belvédère du Mont", "kind": "place", "lat": 45.50402, "lng": -73.58752, "address": "Chemin du Mont, Montréal",
                       "osm": {"tourism": "viewpoint"}, "stage": "want", "tags": ["sunset"], "note": "Go 30 minutes before sunset."}),
        ("machines", {"title": "Musée des Petites Machines", "kind": "place", "lat": 45.50102, "lng": -73.55602, "address": "350 Rue de la Commune O, Montréal",
                      "osm": {"tourism": "museum", "opening_hours": "Tu-Su 10:00-17:00", "wheelchair": "yes"}, "stage": "want",
                      "tags": ["rainy day", "kid-friendly"]}),
        ("ruelle", {"title": "Galerie Ruelle", "kind": "place", "lat": 45.52552, "lng": -73.59521, "address": "5300 Avenue du Parc, Montréal",
                    "osm": {"tourism": "gallery"}, "stage": "been", "rating": 4}),
        ("friperie", {"title": "Friperie Bon Matin", "kind": "place", "lat": 45.52232, "lng": -73.58332, "address": "4300 Rue Saint-Laurent, Montréal",
                      "osm": {"shop": "second_hand"}, "stage": "want", "tags": ["vintage"]}),
        ("librairie", {"title": "Librairie Page Blanche", "kind": "place", "lat": 45.52452, "lng": -73.59302, "address": "5100 Rue Saint-Urbain, Montréal",
                       "osm": {"shop": "books"}, "stage": "loved", "rating": 5, "note": "The staff picks shelf never misses."}),
        ("bloc", {"title": "Bloc Escalade Nord", "kind": "place", "lat": 45.53902, "lng": -73.61352, "address": "7200 Rue Saint-Hubert, Montréal",
                  "osm": {"leisure": "sports_centre", "sport": "climbing"}, "stage": "want", "note": "Tuesday beginner night."}),
        ("marche", {"title": "Marché des Saisons", "kind": "place", "lat": 45.53632, "lng": -73.61452, "address": "7070 Avenue Henri-Julien, Montréal",
                    "osm": {"amenity": "marketplace", "opening_hours": "Mo-Su 08:00-18:00"}, "stage": "loved", "tags": ["weekend"]}),
        # links
        ("salmon", {"title": "Maple miso salmon (one sheet pan, 25 minutes)", "url": "https://recipes.example/maple-miso-salmon",
                    "meta": {"description": "Weeknight dinner: maple, white miso and ginger glaze, roasted with broccoli on one pan.",
                             "schema": ["Recipe"], "site_name": "Recipes Example", "totalTime": "PT25M"}, "enriched": True, "tags": ["quick"]}),
        ("greatwork", {"title": "How to Do Great Work", "url": "https://paulgraham.com/greatwork.html",
                       "meta": {"description": "Paul Graham's long essay on choosing what to work on and doing it well.", "read_min": 45},
                       "enriched": True, "rating": 5}),
        ("bagelwiki", {"title": "Montreal-style bagel", "url": "https://en.wikipedia.org/wiki/Montreal-style_bagel",
                       "meta": {"description": "Hand-rolled, boiled in honey water and baked in a wood-fired oven.", "schema": ["Article"],
                                "site_name": "Wikipedia", "read_min": 6}, "enriched": True}),
        ("topo", {"title": "Learn to read a topographic map in 20 minutes", "url": "https://learn.example/topo-maps",
                  "meta": {"description": "A beginner tutorial: contour lines, scale and finding your way on a hiking map.", "schema": ["Course"]},
                  "enriched": True}),
        ("lofi", {"title": "Rainy café: a lo-fi playlist for deep focus", "url": "https://music.example/playlist/rainy-cafe",
                  "meta": {"description": "Two hours of lo-fi beats.", "og_type": "music.playlist"}, "enriched": True}),
        ("stars", {"title": "Dark Skies: a stargazing documentary", "url": "https://video.example/watch/dark-skies",
                   "meta": {"description": "Feature documentary about the last dark-sky reserves.", "og_type": "video.movie", "schema": ["Movie"]},
                   "enriched": True, "tags": ["rainy day"]}),
        ("bookmarks", {"title": "Self-hosted bookmark managers (GitHub topic)", "url": "https://github.com/topics/bookmark-manager",
                       "meta": {"description": "Open source tools for saving and organising links."}, "enriched": True}),
        ("teapot", {"title": "Speckled ceramic teapot", "url": "https://shop.example/products/speckled-teapot",
                    "meta": {"description": "Hand-thrown stoneware, 900 ml. Add to cart.", "schema": ["Product"], "priceRange": "$64"},
                    "enriched": True, "tags": ["gift"], "note": "Mom's birthday (March).", "category": "gifts"}),
        # a screenshot of a poster, read on the device
        ("jazz", {"title": "Jazz au Parc poster", "kind": "photo", "address": "Parc Laurier, Montréal", "lat": 45.53182, "lng": -73.58672,
                  "meta": {"image": "_/theme/demo-poster.jpg",
                           "ocr": "JAZZ AU PARC\nSamedi soir 19h\nParc Laurier\nEntrée libre / Free\nTrio Bleu Nuit + invités",
                           "found": {"times": ["19h"], "addresses": ["Parc Laurier"]}},
                  "enriched": True, "event_at": _sat_evening(), "tags": ["free", "live music"]}),
        # notes and ideas
        ("picnic", {"title": "Idea: a summer picnic map", "kind": "idea",
                    "note": "Every park with shade + a bakery within 5 minutes. Rate them by how good the bread is."}),
        ("herbs", {"title": "Balcony herb garden", "kind": "note",
                   "note": "Basil, thyme and mint in one long planter. Mint in its own pot or it takes over. Repaint the railing first."}),
        # still in the inbox: saved from the extension, waiting to be sorted
        ("ramen", {"title": "Where to find the best ramen in the city? : r/montreal", "url": "https://forum.example/r/montreal/best-ramen",
                   "meta": {"description": "Thread with 300 comments about ramen spots."}, "enriched": True, "status": "inbox", "source": "extension"}),
        ("quebec", {"title": "48 hours in Québec City: an easy weekend itinerary", "url": "https://travel.example/quebec-city-weekend",
                    "meta": {"description": "Where to stay, eat and walk on a two-day trip.", "schema": ["Article"]}, "enriched": True,
                    "status": "inbox", "source": "extension"}),
        ("shoes", {"title": "Trail running shoes, 30% off this week", "url": "https://shop.example/products/trail-shoes",
                   "meta": {"description": "Add to cart. Free shipping over $50.", "schema": ["Product"]}, "enriched": True,
                   "status": "inbox", "source": "extension"}),
        ("pottery", {"title": "Beginner wheel-throwing workshop, Sundays", "url": "https://studio.example/workshops/wheel",
                     "meta": {"description": "Six-week pottery course for beginners. Book your spot."}, "enriched": True,
                     "status": "inbox", "source": "extension"}),
        ("untitled", {"title": "docs.example: Q3 planning notes", "url": "https://docs.example/d/q3-plan", "enriched": True,
                      "status": "inbox", "source": "extension"}),
    ]


LISTS = [
    ("Plateau coffee crawl", "☕", "#5b5bf0", "Sample list: my favourite cafés and the bakery to finish at.",
     ["lumiere", "nord", "bagel", "librairie", "friperie"], True),
    ("Rainy day ideas", "🌧️", "#42a5f5", "Sample list: things to do when it pours.", ["machines", "ruelle", "stars", "librairie", "lofi"], False),
    ("Date nights", "❤️", "#ec407a", "Sample list: for special evenings.", ["nonna", "hibou", "belvedere", "jazz"], False),
]
TABSET = ("Saturday morning tabs", ["ramen", "quebec", "shoes", "pottery"])


def load_samples(user, demo=False):
    """Add the example pack to one person's account. Returns how many faves were added (0 if already there)."""
    if not demo and len(app_tables.faves.search(owner=user, is_sample=True)):
        return 0
    flag = {"is_demo": True} if demo else {"is_sample": True}
    ts = app_tables.tabsets.add_row(owner=user, name=TABSET[0], count=len(TABSET[1]), created=C.now() - dt.timedelta(days=1), is_demo=demo)
    rows, n = {}, 0
    pack = _pack()
    for i, (key, f) in enumerate(pack):
        f = dict(f, **flag)
        status, cat, stage, rating = f.pop("status", "kept"), f.pop("category", None), f.pop("stage", ""), f.pop("rating", None)
        source = f.pop("source", "sample")
        row, created = Store.create(user, dict(f, status=status), source="demo" if demo else source,
                                    tabset=ts if key in TABSET[1] else None)
        age = dt.timedelta(days=len(pack) + 5 - i, hours=i) if status == "kept" else dt.timedelta(hours=20 - i)
        row.update(stage=stage, rating=rating, created=C.now() - age, updated=C.now() - age)
        if status == "kept":
            Store.confirm(row, cat or row["category"])
        rows[key] = row
        n += created
    for name, emoji, color, desc, items, public in LISTS:
        lst = app_tables.lists.add_row(owner=user, name=name, emoji=emoji, color=color, description=desc,
                                       share_token=Store.token(22) if public else None, is_public=public,
                                       created=C.now() - dt.timedelta(days=20), updated=C.now() - dt.timedelta(days=2), is_demo=demo)
        for k in items:
            if k in rows:
                app_tables.list_items.add_row(list=lst, fave=rows[k], added_by=user, added=C.now() - dt.timedelta(days=3), is_demo=demo)
    return n


def state():
    return C.get_setting("demo", "never")  # "never" | "loaded" | "removed"


def ensure_loaded():
    """Called from the public callables (landing page, shared links): loads the demo once, unless an admin removed it."""
    if state() == "never":
        load()


def load():
    remove(remember=False)
    users = []
    for name, email in DEMO_USERS:
        u = app_tables.users.get(email=email) or app_tables.users.add_row(email=email, enabled=False)
        u.update(display_name=name, is_demo=True, signed_up=C.now() - dt.timedelta(days=60))
        users.append(u)
    maya, theo, ines = users
    load_samples(maya, demo=True)
    # Maya's coffee crawl and rainy-day list are public: the landing page links to them.
    for lst in app_tables.lists.search(owner=maya):
        if lst["name"] == "Plateau coffee crawl":
            lst.update(name="Maya's Mile End coffee crawl", description="Five stops for a slow Saturday morning, ending with warm bagels.")
        elif lst["name"] == "Rainy day ideas":
            lst.update(name="Maya's rainy-day Montréal", is_public=True, share_token=Store.token(22),
                       description="Museums, a gallery, a bookshop and a film for grey days.")
    dates = app_tables.lists.get(owner=maya, name="Date nights")
    for u in (theo, ines):
        app_tables.members.add_row(list=dates, user=u, email=u["email"], role="editor" if u == theo else "viewer",
                                   invited_by=maya, created=C.now(), is_demo=True)
    C.set_setting("demo", "loaded")
    return counts()


def share_demo_with(user, role="editor"):
    """Dev/demo helper: Maya shares her Date nights list with this person."""
    maya = app_tables.users.get(email=DEMO_USERS[0][1])
    lst = app_tables.lists.get(owner=maya, name="Date nights") if maya is not None else None
    if lst is not None and app_tables.members.get(list=lst, user=user) is None:
        app_tables.members.add_row(list=lst, user=user, email=user["email"], role=role, invited_by=maya, created=C.now(), is_demo=True)


def remove(remember=True):
    for name in DEMO_TABLES:
        for r in getattr(app_tables, name).search(is_demo=True):
            r.delete()
    for u in app_tables.users.search(is_demo=True):
        for p in app_tables.prefs.search(owner=u):
            p.delete()
        u.delete()
    if remember:
        C.set_setting("demo", "removed")
    return counts()


def counts():
    out = {"users": len(app_tables.users.search(is_demo=True))}
    for name in DEMO_TABLES:
        out[name] = len(getattr(app_tables, name).search(is_demo=True))
    return out
