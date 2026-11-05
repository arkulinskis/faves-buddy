"""Real-page check of the sorter: reads ~35 live pages (needs the network) and compares each category with the
expected one.   python -I tools/research/classify_research.py   (2026-10-31: 35/35; from URL + title only: 34/35)
"""
import sys, json, time
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "server_code"))
import Fetch, Classify

CASES = [
    ("https://www.seriouseats.com/the-food-lab-best-chocolate-chip-cookie-recipe", "recipes"),
    ("https://www.allrecipes.com/recipe/24074/alysias-basic-meat-lasagna/", "recipes"),
    ("https://www.ricardocuisine.com/recettes/5541-pate-chinois", "recipes"),
    ("https://www.bbcgoodfood.com/recipes/easy-pancakes", "recipes"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "watch"),
    ("https://vimeo.com/76979871", "watch"),
    ("https://www.imdb.com/title/tt0111161/", "watch"),
    ("https://en.wikipedia.org/wiki/Montreal-style_bagel", "read"),
    ("https://www.theguardian.com/science/2024/jan/01/example", "read"),
    ("https://paulgraham.com/greatwork.html", "read"),
    ("https://aeon.co/essays/the-joys-of-boredom", "read"),
    ("https://github.com/anvil-works/anvil-runtime", "tools"),
    ("https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API", "tools"),
    ("https://www.etsy.com/ca/c/jewelry", "shop"),
    ("https://www.ikea.com/ca/en/p/billy-bookcase-white-00263850/", "shop"),
    ("https://www.mec.ca/en/products/clothing", "shop"),
    ("https://www.eventbrite.ca/d/canada--montreal/events/", "events"),
    ("https://www.montrealjazzfest.com/en-CA", "events"),
    ("https://www.coursera.org/learn/machine-learning", "learn"),
    ("https://www.khanacademy.org/math/algebra", "learn"),
    ("https://www.alltrails.com/canada/quebec", "outdoors"),
    ("https://www.sepaq.com/pq/mot/", "outdoors"),
    ("https://www.mbam.qc.ca/en/", "culture"),
    ("https://www.booking.com/city/ca/montreal.html", "stay"),
    ("https://www.airbnb.ca/montreal-canada/stays", "stay"),
    ("https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv", "listen"),
    ("https://bandcamp.com/", "listen"),
    ("https://www.apartmenttherapy.com/small-space-living", "home"),
    ("https://www.instructables.com/Workshop/", "home"),
    ("https://www.healthline.com/nutrition/how-much-protein-per-day", "health"),
    ("https://www.yogajournal.com/poses/", "health"),
    ("https://www.linkedin.com/jobs/", "work"),
    ("https://www.pinterest.ca/ideas/", "ideas"),
    ("https://www.google.com/maps/place/Schwartz's/@45.5162,-73.5776,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d45.5162229!4d-73.5776108", "eat"),
    ("https://www.google.com/maps/place/Parc+La+Fontaine/@45.5276,-73.5695,15z", "outdoors"),
]

def run():
    good = fetched = 0
    rows = []
    for url, want in CASES:
        info = {"url": url}
        err = ""
        try:
            page = Fetch.read_page(url)
            fetched += 1
            info.update({"title": page.get("title"), "text": page.get("description"), "schema": page.get("schema"),
                         "og_type": page.get("og_type"), "site_name": page.get("site_name"), "kind": page.get("kind") or "link"})
            if page.get("lat") is not None and page.get("kind") == "place":
                m = Fetch.osm_match(page["lat"], page["lng"], page.get("name")) or {}; tags, ref = m.get("osm"), m.get("ref")
                info["osm"] = tags or {}
                info["_osm"] = ref
        except Exception as e:
            err = str(e)
        r = Classify.classify(info)
        ok = r["category"] == want
        good += ok
        rows.append((ok, want, r["category"], r["confidence"], url[:70], (info.get("title") or "")[:50], r["reasons"][:2], err, info.get("schema"), info.get("_osm")))
        print(("OK  " if ok else "MISS"), want.ljust(9), r["category"].ljust(9), r["confidence"], url[:70], "|", (info.get("title") or "")[:45], "|", r["reasons"][:2], err, info.get("_osm") or "", flush=True)
    print("\n%d/%d correct, %d pages fetched" % (good, len(CASES), fetched))
    # title-only (what a bulk tab save gets before enrichment)
    g2 = 0
    for ok, want, got, conf, url, title, *_ in rows:
        r = Classify.classify({"url": url, "title": title})
        g2 += r["category"] == want
    print("URL + title only: %d/%d" % (g2, len(CASES)))

run()
