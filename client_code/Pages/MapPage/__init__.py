import anvil.js
from anvil import *
from anvil.js import window

from ._anvil_designer import MapPageTemplate
from ... import fb, router, state

RADII = [(1, "1 km"), (3, "3 km"), (10, "10 km"), (0, "Anywhere")]


class MapPage(MapPageTemplate):
    """#map, #map/find/<text>, #map/list/<id>: every fave with a location on one map, nearest first in the side list.
    Near me (asks for location once), radius, category and list filters, "open now", a place search (Photon) whose
    results can be saved, "Suggest nearby" (your top Discover search around the map's centre: dashed pins) and
    "Top faves" (places people save most around here). Server: list_faves pages, my_lists, get_list, taste, save_fave,
    top_faves."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.args = list(args)
        self.st: dict = state.store_get("map.state", None) or {"radius": 0, "cat": "", "open": False}
        self.list_filter = args[1] if len(args) > 1 and args[0] == "list" else None
        self.list_ids = None
        self.all = []
        self.here = None
        self.found = []
        self.on_id = None
        self.results.visible = False
        state.set_control_attr(self.search_box, "aria-label", "Find a place")
        self.radius_chips.add_event_handler("x-chip", self._radius)
        self.cat_chips.add_event_handler("x-chip", self._cat)
        self.results_panel.add_event_handler("x-pick", self._pick)
        fb.boot()
        self.all = self._load_all()
        self.here = fb.geo(False)
        ml = state.call_quiet("my_lists") or {"mine": [], "shared": []}
        lists = ml["mine"] + ml["shared"]
        self.list_box.items = [("All lists", "")] + [("%s %s" % (l.get("emoji") or "", l["name"]), l["id"]) for l in lists]
        self.list_box.visible = bool(lists)
        state.set_control_attr(self.list_box, "aria-label", "List")
        self._load_list()
        self.list_box.selected_value = self.list_filter or ""
        self.open_box.checked = bool(self.st.get("open"))
        self._draw_filters()
        self._draw_list()

    def _load_all(self):
        out, off = [], 0
        while True:
            r = state.call_quiet("list_faves", {"status": "all"}, off) or {}
            out += r.get("faves") or []
            if not r.get("more") or off >= 1200:
                return out
            off += 60

    def _load_list(self):
        if not self.list_filter:
            self.list_ids = None
            return
        r = state.call_quiet("get_list", self.list_filter)
        if r and r.get("ok"):
            self.list_ids = [i["id"] for i in r["list"]["items"]]
        else:
            self.list_ids, self.list_filter = None, None

    @handle("", "show")
    def form_show(self, **event_args):
        if self.map.ready:
            return
        start = self.here or next((f for f in self.all if f.get("lat") is not None), None) or fb.DEFAULT_CENTER
        self.map.open(center=start, zoom=12, on_pin=self._pin, on_save=self._save_place)
        self._draw_pins()
        self.map.me(self.here)
        self._fit()
        if len(self.args) > 1 and self.args[0] == "find":
            self.search_box.text = self.args[1]
            self.search_button_click()

    def leave(self):
        self.map.destroy()

    def _save_st(self):
        state.store_set("map.state", self.st)

    # ---- what's shown
    def _visible(self):
        st, out = self.st, []
        for f in self.all:
            if f.get("lat") is None:
                continue
            if st.get("cat") and f.get("cat") != st["cat"]:
                continue
            if self.list_ids is not None and f["id"] not in self.list_ids:
                continue
            if st.get("open") and fb.open_state(f) != "open":
                continue
            if st.get("radius") and self.here and (fb.dist(self.here, f) or 0) > st["radius"]:
                continue
            out.append(f)
        if self.here:
            out.sort(key=lambda f: fb.dist(self.here, f) or 0)
        else:
            out.sort(key=lambda f: (f.get("title") or "").lower())
        return out

    def _draw_filters(self):
        h = self.here
        self.where_label.text = (h.get("label") or "Home base") if h and h.get("home") else ("Near you" if h else "Your places")
        self.radius_chips.items = [{"key": r, "label": label, "on": self.st.get("radius", 0) == r, "sm": True,
                                    "disabled": not h and bool(r), "title": "Use Near me first" if not h and r else ""} for r, label in RADII]
        counts = {}
        for f in self.all:
            if f.get("lat") is not None:
                counts[f["cat"]] = counts.get(f["cat"], 0) + 1
        self.cat_chips.items = fb.chip_items(fb.cats(), self.st.get("cat") or None, counts, all_label="All", sm=True)

    def _draw_list(self):
        v = self._visible()
        self.rows.items = [dict(f, _from=self.here, _on=f["id"] == self.on_id) for f in v]
        self.empty.visible = not v
        any_place = any(f.get("lat") is not None for f in self.all)
        self.empty_text.text = ("Try a bigger radius or another category." if any_place else
                                "Paste a Google Maps link or search for a place to pin your first one.")
        self._draw_pins(v)

    def _draw_pins(self, v=None):
        if self.map.ready:
            self.map.pins(v if v is not None else self._visible(), "fave")

    def _fit(self):
        v = self._visible()
        if self.here and self.st.get("radius"):
            self.map.fit(v + [self.here])
        else:
            self.map.fit(v if v else ([self.here] if self.here else []))

    def _pin(self, fid):
        self.on_id = fid
        self.rows.items = [dict(f, _on=f["id"] == fid) for f in self.rows.items]
        node = anvil.js.get_dom_node(self.rows).querySelector('[data-row="%s"]' % window.CSS.escape(fid))
        if node:
            node.scrollIntoView({"block": "nearest"})

    # ---- filters
    def _radius(self, key, **event_args):
        self.st["radius"] = key
        self._save_st()
        self._draw_filters()
        self._draw_list()
        self._fit()

    def _cat(self, key, **event_args):
        k = state.focus_key()
        self.st["cat"] = key or ""
        self._save_st()
        self._draw_filters()
        state.refocus(self.cat_chips, k)
        self._draw_list()
        self._fit()

    @handle("open_box", "change")
    def open_box_change(self, **event_args):
        self.st["open"] = bool(self.open_box.checked)
        self._save_st()
        self._draw_list()

    @handle("list_box", "change")
    def list_box_change(self, **event_args):
        self.list_filter = self.list_box.selected_value or None
        self._load_list()
        self._draw_list()
        self._fit()

    @handle("near_button", "click")
    def near_button_click(self, **event_args):
        self.near_button.enabled = False
        try:
            g = fb.geo(True)
        finally:
            self.near_button.enabled = True
        if not g:
            state.toast("Location is off. Set a home spot in Tools instead.", "error")
            return
        self.here = g
        if not self.st.get("radius"):
            self.st["radius"] = 3
        self._save_st()
        self.map.me(g)
        self._draw_filters()
        self._draw_list()
        self._fit()
        if g.get("home"):
            state.toast("Using your home spot (location wasn't shared).")

    # ---- search + suggestions
    @handle("search_box", "pressed_enter")
    def search_box_pressed_enter(self, **event_args):
        self.search_button_click()

    @handle("search_button", "click")
    def search_button_click(self, **event_args):
        q = (self.search_box.text or "").strip()
        if not q:
            return
        c = self.map.center() or self.here or fb.DEFAULT_CENTER
        self.search_button.enabled = False
        try:
            res = fb.from_js(window.FB.data.photon(q, fb.to_js({"lat": c["lat"], "lng": c["lng"]}), 8))
        except Exception:
            state.toast("Place search is unavailable right now.", "error")
            return
        finally:
            self.search_button.enabled = True
        self.found = res
        self.results_panel.items = [dict(p, _i=i) for i, p in enumerate(res)]
        self.results.visible = bool(res)
        if not res:
            state.toast('No place found for "%s"' % q, "error")

    @handle("close_results", "click")
    def close_results_click(self, **event_args):
        self.results.visible = False

    def _pick(self, place, **event_args):
        self.results.visible = False
        if self.map.ready:
            self.map.jump(place["lat"], place["lng"], 16)
            self.map.sugs([place], emoji="📍", cat="other", label=place.get("kind") or "", open=True)
        else:
            self._save_place(place)

    def _save_place(self, p):
        r = state.call("save_fave", {"title": p["title"], "lat": p["lat"], "lng": p["lng"], "address": p.get("address") or "",
                                     "osm": p.get("osm") or {}, "kind": "place", "source": "map"})
        if r:
            state.toast(("Saved to your inbox: " if r.get("created") else "Already saved: ") + fb.cat_label(r["fave"]["cat"]), "ok")
            if r.get("created"):
                self.all.append(r["fave"])
                self._draw_filters()
                self._draw_list()
        return bool(r)

    @handle("suggest_button", "click")
    def suggest_button_click(self, **event_args):
        if not self.map.ready:
            state.toast("The map needs to be showing for suggestions.", "error")
            return
        c = self.map.center()
        self.suggest_button.enabled = False
        try:
            t = state.call_quiet("taste") or {}
            recipe = (t.get("recipes") or [None])[0]
            if not recipe:
                return
            found = fb.from_js(window.FB.data.findPlaces(fb.to_js(recipe), fb.to_js(c), 1.5, fb.to_js(t.get("saved") or [])))
        except Exception:
            state.toast("Suggestions are unavailable right now. Try again in a minute.", "error")
            return
        finally:
            self.suggest_button.enabled = True
        places = (found.get("places") or [])[:12]
        self.map.clear_sugs()
        self.map.sugs(places, emoji=recipe["emoji"], cat=recipe["cat"], label=recipe["label"])
        label = recipe["label"].lower()
        if places:
            state.toast("%d %s nearby you haven't saved (dashed pins)" % (len(places), label), "ok")
        else:
            state.toast("No new %s around here" % label)

    @handle("top_button", "click")
    def top_button_click(self, **event_args):
        if not self.map.ready:
            return
        c = self.map.center()
        r = state.call_quiet("top_faves", c["lat"], c["lng"], 5) or {}
        places = r.get("places") or []
        self.map.clear_sugs()
        self.map.sugs([dict(p, why=["saved by %d people" % p["people"]]) for p in places], emoji="⭐", label="Top fave")
        if places:
            state.toast("%s around here (starred pins)" % state.plural(len(places), "top fave"), "ok")
            self.map.fit(places + [c])
        else:
            state.toast("No top faves around here yet. They show once a few people save the same place.")
