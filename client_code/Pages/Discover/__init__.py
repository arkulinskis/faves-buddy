import anvil.js
from anvil import *
from anvil.js import window

from ._anvil_designer import DiscoverTemplate
from ... import fb, state

TABS = ["places", "top", "events", "ideas"]
KMS = [1, 2, 5, 15]
TM_KEY = "favesbuddy.tm"


def _tm_key():
    try:
        return window.localStorage.getItem(TM_KEY) or ""
    except Exception:
        return ""


class Discover(DiscoverTemplate):
    """#discover/places|top|events|ideas: suggestions from what you already love, on demand. No AI: Discover.taste()
    turns your kept faves into searches and this page runs them against open data, showing exactly what was searched:
        Places like yours  OpenStreetMap with your tags (both Overpass servers at once) and the map's own points of
                           interest in parallel: the first answer shows, a better one replaces it (FB.data.findPlaces)
        Top faves          places Faves Buddy people save most around the spot (top_faves, counted anonymously)
        Events             Wikidata festivals near you; Ticketmaster with your own free key (Tools -> Events)
        Ideas              Wikipedia "more like this" for your favourite reads/videos; Wikipedia near you
    Saving a suggestion = save_fave(source "suggested"): it lands in the inbox, sorted."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.tab = args[0] if args and args[0] in TABS else "places"
        self.km = state.store_get("dc.km", 2)
        self.current = []
        self.saved_urls = set()
        self.run_key = None
        self.alive = True
        state.heading(self.title, 1)
        state.live(self.loading_text)
        for name, el in (("places", self.tab_places), ("top", self.tab_top), ("events", self.tab_events), ("ideas", self.tab_ideas)):
            el.classes["on"] = name == self.tab
            if name == self.tab:
                state.set_attr(el, "aria-current", "page")
        self.centre_chips.add_event_handler("x-chip", self._centre)
        self.km_chips.add_event_handler("x-chip", self._km)
        self.recipes.add_event_handler("x-run", self._run)
        self.seed_chips.add_event_handler("x-chip", self._seed)
        self.results.add_event_handler("x-save", self._save)
        fb.boot()
        self.taste = state.call("taste") or {}
        if not self.taste.get("centers"):
            self.taste["centers"] = [{"lat": 45.5165, "lng": -73.5795, "label": "in Montréal", "n": 0}]
        self.center = self.taste["centers"][0]
        g = fb.geo(False)
        if g and not g.get("home"):
            self.center = {"lat": g["lat"], "lng": g["lng"], "label": "near you", "me": True}
        n = self.taste.get("kept") or 0
        self.intro.text = "More of what you love, found in open data on demand. " + (
            "Based on your %s." % state.plural(n, "kept fave") if n else "Save a few faves and this gets personal.")
        self._draw()

    def leave(self):
        self.alive = False

    def _where(self):
        c: dict = self.center or {}
        if c.get("me"):
            return "near you"
        label = str(c.get("label") or "")
        return ("around " + label) if c.get("home") else label or "near you"

    # ---- drawing
    def _draw(self):
        cs = self.taste["centers"]
        c = self.center
        chips = [{"key": i, "label": ("🏠 " if x.get("home") else "📍 ") + x["label"], "sm": True,
                  "on": not c.get("me") and x["lat"] == c["lat"] and x["lng"] == c["lng"]} for i, x in enumerate(cs)]
        chips.append({"key": "me", "label": "Near me", "icon": "locate", "sm": True, "on": bool(c.get("me"))})
        self.centre_chips.items = chips
        self.km_chips.items = [{"key": k, "label": "%d km" % k, "sm": True, "on": self.km == k} for k in KMS]
        self.seeds_part.visible = self.tab == "ideas"
        self.tm_nudge.visible = self.tab == "events" and not _tm_key()
        self._clear()
        if self.tab == "places":
            self.recipes.items = [{"key": i, "emoji": r["emoji"], "label": r["label"], "because": r["because"],
                                   "q": " + ".join("%s=%s" % (a, b) for a, b in r["filters"] + r["prefer"])}
                                  for i, r in enumerate(self.taste["recipes"])]
            self.hint.text = "Tap a search to look %s." % self._where()
        elif self.tab == "events":
            items = [{"key": "wikidata", "emoji": "🎪", "label": "Festivals around here",
                      "because": "Recurring festivals and events listed on Wikidata within %d km." % max(self.km, 15),
                      "q": "wikidata: instance of festival, near"}]
            if _tm_key():
                for cls in (self.taste.get("event_classes") or []) + [""]:
                    items.append({"key": "tm:" + cls, "emoji": "🎟️", "label": (cls + " events") if cls else "Everything coming up",
                                  "because": "Dated events from Ticketmaster, soonest first.",
                                  "q": "ticketmaster: %sradius=%dkm" % (("classificationName=%s + " % cls) if cls else "", max(self.km, 10))})
            self.recipes.items = items[:5]
            self.hint.text = ""
        elif self.tab == "ideas":
            seeds = self.taste.get("seeds") or []
            self.seeds_intro.text = ("More like your favourite reads and videos (Wikipedia “more like this”):" if seeds else
                                     "Keep a few articles, videos or courses and you'll get “more like this” ideas here.")
            self.seed_chips.items = [{"key": i, "label": (s[:40] + "…") if len(s) > 40 else s, "icon": "book"} for i, s in enumerate(seeds)]
            self.recipes.items = [{"key": "wiki", "emoji": "🏛️", "label": "Stories " + self._where(),
                                   "because": "Wikipedia articles about places within %d km: history, architecture, oddities." % self.km,
                                   "q": "wikipedia: geosearch radius=%dkm" % min(10, self.km)}]
            self.hint.text = ""
        else:
            self.recipes.items = []
            self.hint.text = ""
            self._top()

    def _clear(self):
        self.loading.visible = False
        self.error.visible = False
        self.results_part.visible = False

    def _loading(self, text):
        self.error.visible = False
        self.results_part.visible = False
        self.loading.visible = True
        self.loading_text.text = text

    def _fail(self, text):
        self.loading.visible = False
        self.error.text = text
        self.error.visible = True

    def _show(self, items, head):
        self.loading.visible = False
        self.error.visible = False
        self.hint.text = ""
        self.current = items
        self.results_part.visible = True
        self.res_head.text = head
        self.res_count.text = state.plural(len(items), "result")
        self.top_results.visible = False
        self.results.visible = bool(items)
        self.results.items = [dict(s, _i=i, _saved=bool(s.get("url")) and s["url"] in self.saved_urls) for i, s in enumerate(items)]
        self.no_results.visible = not items
        self.dom_nodes["none_title"].textContent = "Nothing new found"
        self.none_text.text = "Try a bigger distance or another spot."

    def _mark(self, key):
        self.run_key = key
        self.recipes.items = [dict(r, on=r["key"] == key) for r in self.recipes.items]

    # ---- top faves (Prepsto idea: "a section of top faves where you see what has been saved around you the most")
    def _top(self):
        c = self.center
        self._loading("Counting what people save %s…" % self._where())
        r = state.call_quiet("top_faves", c["lat"], c["lng"], max(self.km, 2)) or {}
        places = r.get("places") or []
        self.loading.visible = False
        self.results_part.visible = True
        self.res_head.text = "⭐ Top faves " + self._where()
        self.res_count.text = "Saved by at least %d people · counted anonymously" % (r.get("min_people") or 2)
        self.results.visible = False
        self.top_results.visible = bool(places)
        here = c if c.get("me") else None
        self.top_results.items = [dict(p, _from=here) for p in places]
        self.no_results.visible = not places
        self.dom_nodes["none_title"].textContent = "No top faves here yet"
        self.none_text.text = ("They appear once at least %d people save the same place. Try a bigger distance, "
                               "another spot, or share a list to get friends saving." % (r.get("min_people") or 2))

    # ---- choosing where
    def _centre(self, key, **event_args):
        if key == "me":
            g = fb.geo(True)
            if not g or g.get("home"):
                state.toast("Location isn't available. Pick one of your spots instead.", "error")
                return
            self.center = {"lat": g["lat"], "lng": g["lng"], "label": "near you", "me": True}
        else:
            self.center = self.taste["centers"][key]
        self._draw()

    def _km(self, key, **event_args):
        self.km = key
        state.store_set("dc.km", key)
        self._draw()

    # ---- running searches
    def _run(self, key, item, **event_args):
        self._mark(key)
        if self.tab == "places":
            self._places(self.taste["recipes"][key])
        elif key == "wikidata":
            self._festivals()
        elif isinstance(key, str) and key.startswith("tm:"):
            self._ticketmaster(key[3:])
        elif key == "wiki":
            self._wiki_near()

    def _places(self, r):
        where, km = self._where(), self.km
        self._loading("Searching OpenStreetMap and the map for %s within %d km, %s…" % (r["label"].lower(), km, where))
        head = "%s %s %s" % (r["emoji"], r["label"], where)
        key = self.run_key
        better = anvil.js.report_exceptions(lambda j: self._better(key, r, head, j))
        try:
            res = fb.from_js(window.FB.data.findPlaces(fb.to_js(r), fb.to_js({"lat": self.center["lat"], "lng": self.center["lng"]}),
                                                        km, fb.to_js(self.taste.get("saved") or []), better))
        except Exception:
            self._fail("OpenStreetMap and the map tiles didn't answer. Try again in a minute.")
            return
        self._show_places(r, head, res)

    def _show_places(self, r, head, res):
        items = [dict(p, cat=r["cat"]) for p in (res.get("places") or [])[:24]]
        self._show(items, head + (" (from the map; fewer details)" if res.get("source") == "tiles" else ""))

    def _better(self, key, r, head, j):
        """OpenStreetMap answered after the map tiles: show its richer list, unless the person moved on."""
        if self.alive and self.run_key == key and self.tab == "places":
            self._show_places(r, head, fb.from_js(j))

    def _festivals(self):
        c, km = self.center, max(self.km, 15)
        self._loading("Looking up festivals %s on Wikidata…" % self._where())
        try:
            res = fb.from_js(window.FB.data.wikidataEvents(fb.to_js(c), km))
        except Exception:
            self._fail("Wikidata didn't answer. Try again in a minute.")
            return
        items = [dict(x, cat="events", kind="event", km=fb.dist(c, x)) for x in res]
        self._show(items, "🎪 Festivals " + self._where())

    def _ticketmaster(self, cls):
        c = self.center
        self._loading("Asking Ticketmaster for events %s…" % self._where())
        try:
            res = fb.from_js(window.FB.data.ticketmaster(_tm_key(), fb.to_js(c), max(self.km, 10), cls))
        except Exception as e:
            self._fail(str(getattr(e, "message", None) or "Ticketmaster didn't answer. Try again in a minute."))
            return
        items = [dict(x, cat="events", kind="event", km=fb.dist(c, x)) for x in res]
        self._show(items, "🎟️ %s %s" % ((cls + " events") if cls else "Coming up", self._where()))

    def _seed(self, key, **event_args):
        seed = self.taste["seeds"][key]
        self.seed_chips.items = [dict(c, on=c["key"] == key) for c in self.seed_chips.items]
        self._loading("Finding Wikipedia articles like “%s”…" % seed)
        try:
            res = fb.from_js(window.FB.data.wikiLike(seed))
        except Exception:
            self._fail("Wikipedia didn't answer. Try again.")
            return
        items = [dict(x, cat="read", kind="link", why=["like " + x["from"]] if x.get("from") else []) for x in res]
        self._show(items, "📖 More like “%s”" % seed)

    def _wiki_near(self):
        c = self.center
        self._loading("Reading Wikipedia %s…" % self._where())
        try:
            res = fb.from_js(window.FB.data.wikiNearby(fb.to_js(c), min(10000, self.km * 1000)))
        except Exception:
            self._fail("Wikipedia didn't answer. Try again.")
            return
        items = [dict(x, cat="culture", kind="link", km=fb.dist(c, x)) for x in res]
        self._show(items, "🏛️ Stories " + self._where())

    # ---- saving a suggestion
    def _save(self, i, button, **event_args):
        s = self.current[i]
        if s.get("kind") == "event":
            kind = "event" if s.get("start") else "link"
        else:
            kind = "link" if s.get("url") else "place"
        f = {"title": s["title"], "source": "suggested", "url": s.get("url"), "lat": s.get("lat"), "lng": s.get("lng"),
             "address": s.get("address") or "", "osm": s.get("osm") or {}, "kind": kind, "event_at": s.get("start"),
             "meta": {"description": s.get("desc") or "", "image": s.get("image") or "", "suggested_by": self.tab},
             "enriched": bool(s.get("url"))}
        if not f["url"] and f["lat"] is None:
            f["kind"] = "note"
        button.enabled = False
        r = state.call("save_fave", f)
        if not r:
            button.enabled = True
            return
        if s.get("url"):
            self.saved_urls.add(s["url"])
        self.taste.setdefault("saved", []).append([s["title"].lower(), s.get("lat"), s.get("lng")])
        button.text = "Saved"
        state.toast("In your inbox as " + fb.cat_label(r["fave"]["cat"]), "ok")
