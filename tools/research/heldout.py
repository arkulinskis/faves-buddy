"""Offline check of the sorter on notes, screenshot text, tab titles and OSM places it was not tuned on, plus the learner.
    python -I tools/research/heldout.py   (2026-10-31: 28/28)
"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "server_code"))
import Classify as C

CASES = [
    ({"kind": "note", "title": "Try the miso caramel brownies from Sunday", "text": "bake 25 min at 350, 1 cup sugar"}, "recipes"),
    ({"kind": "note", "title": "App idea: shared grocery list that learns what we buy"}, "ideas"),
    ({"kind": "photo", "title": "Screenshot", "ocr": "JAZZ AU PARC Samedi 14 nov 19h Parc Laurier Entree libre"}, "events"),
    ({"kind": "photo", "title": "Screenshot", "ocr": "Add to cart $89.99 Free shipping on orders over $50 Merino wool sweater"}, "shop"),
    ({"kind": "photo", "title": "IMG_2041", "ocr": "Ingredients 2 tbsp olive oil 1 onion Preheat oven to 400F"}, "recipes"),
    ({"kind": "note", "title": "Gift for Mom's birthday: that ceramic teapot"}, "gifts"),
    ({"kind": "note", "title": "Book: The Overstory by Richard Powers, novel everyone recommends"}, "read"),
    ({"kind": "note", "title": "Climbing gym near Jean-Talon for bouldering on Tuesdays"}, "health"),
    ({"kind": "note", "title": "Repaint the balcony railing before winter, need primer"}, "home"),
    ({"kind": "note", "title": "Podcast episode about sleep science"}, "listen"),
    ({"url": "https://www.lapresse.ca/actualites/2026-10-30/une-histoire.php", "title": "Une histoire de quartier | La Presse"}, "read"),
    ({"url": "https://www.timeout.com/montreal/things-to-do/best-things-to-do-in-montreal", "title": "Best things to do in Montreal"}, "culture"),
    ({"url": "https://www.reddit.com/r/montreal/comments/abc/best_bagels/", "title": "Best bagels in Mile End? : r/montreal"}, "eat"),
    ({"url": "https://www.amazon.ca/dp/B0C123", "title": "Sony WH-1000XM5 Wireless Headphones"}, "shop"),
    ({"url": "https://news.ycombinator.com/item?id=1", "title": "Show HN: A tiny Rust database"}, "tools"),
    ({"url": "https://www.udemy.com/course/python-bootcamp/", "title": "Complete Python Bootcamp"}, "learn"),
    ({"url": "https://www.meetup.com/montreal-js/events/123/", "title": "MontrealJS meetup October"}, "events"),
    ({"url": "https://www.hostelworld.com/hostels/quebec-city", "title": "Hostels in Quebec City"}, "stay"),
    ({"url": "https://letterboxd.com/film/past-lives/", "title": "Past Lives (2023)"}, "watch"),
    ({"url": "https://www.indeed.ca/viewjob?jk=1", "title": "Product Designer - Montreal"}, "work"),
    ({"url": "https://some-roaster.example/beans", "title": "Single origin Ethiopia beans | Small batch coffee roastery"}, "coffee"),
    ({"url": "https://blog.example/cocktails", "title": "10 speakeasy cocktail bars worth the hunt"}, "nightlife"),
    ({"kind": "place", "title": "Somewhere", "osm": {"leisure": "park"}}, "outdoors"),
    ({"kind": "place", "title": "Le Petit Ramen", "osm": {"amenity": "restaurant", "cuisine": "ramen"}}, "eat"),
    ({"kind": "place", "title": "Bar Furco", "osm": {"amenity": "bar"}}, "nightlife"),
    ({"kind": "place", "title": "Musée", "osm": {"tourism": "museum"}}, "culture"),
    ({"kind": "place", "title": "Shop", "osm": {"shop": "clothes"}}, "shop"),
    ({"kind": "place", "title": "Shop", "osm": {"shop": "bakery"}}, "eat"),
]
good = 0
for info, want in CASES:
    r = C.classify(info)
    ok = r["category"] == want
    good += ok
    print("OK  " if ok else "MISS", want.ljust(9), r["category"].ljust(9), r["confidence"], (info.get("title") or "")[:50], r["reasons"][:2], r["tags"])
print("%d/%d" % (good, len(CASES)))
# learning: two corrections teach a new domain
m = {}
info = {"url": "https://www.cozyhomeblog.example/post/1", "title": "Our reading nook"}
print("before:", C.classify(info, m)["category"])
m = C.learn(m, info, "home")
m = C.learn(m, {"url": "https://www.cozyhomeblog.example/post/2", "title": "Window seat build"}, "home")
print("after 2 corrections:", C.classify({"url": "https://www.cozyhomeblog.example/post/9", "title": "Something new"}, m))
