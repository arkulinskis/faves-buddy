import json

import anvil.js
from anvil import *
from anvil.js import window

from ._anvil_designer import MapViewTemplate
from ... import fb


class MapView(MapViewTemplate):
    """The map. open() draws it (False when the browser can't: the message is shown in its place); after that:
        pins(faves, mode)    your faves; mode "fave" (popup: Open + Directions), "go" (Directions), "none"
        sugs(places, ...)    dashed suggestion pins whose popup has Save (on_save gets the place as a dict)
        clear_sugs(), me(spot), fit(points, pad), center(), jump(lat, lng, zoom), tile_pois(...), destroy()
    Handlers: on_pin(fave_id), on_save(place) -> anything, on_click(lat, lng)."""

    def __init__(self, **properties):
        self._ctl = None
        self._handlers: dict = {}
        super().__init__(**properties)

    @property
    def ready(self):
        return self._ctl is not None

    def open(self, center=None, zoom=12, cooperative=False, on_pin=None, on_save=None, on_click=None):
        c = center or fb.DEFAULT_CENTER
        handlers = {}
        if on_pin is not None:
            handlers["onPin"] = anvil.js.report_exceptions(on_pin)
        if on_save is not None:
            handlers["onSave"] = anvil.js.report_exceptions(lambda p: on_save(json.loads(p)))
        if on_click is not None:
            handlers["onClick"] = anvil.js.report_exceptions(on_click)
        opts = {"center": {"lat": c["lat"], "lng": c["lng"]}, "zoom": zoom, "cooperative": bool(cooperative)}
        self._ctl = window.FB.mapView(self.dom_nodes["el"], fb.to_js(opts), handlers)
        return self._ctl is not None

    def pins(self, faves, mode="fave"):
        if self._ctl is not None:
            self._ctl.pins(fb.to_js([f for f in faves if f.get("lat") is not None]), mode)

    def sugs(self, places, emoji=None, cat=None, label=None, open=False):
        if self._ctl is not None:
            self._ctl.sugs(fb.to_js(places), fb.to_js({"emoji": emoji, "cat": cat, "label": label, "open": bool(open)}))

    def clear_sugs(self):
        if self._ctl is not None:
            self._ctl.clearSugs()

    def me(self, spot):
        if self._ctl is not None:
            self._ctl.me(fb.to_js(spot) if spot else None)

    def fit(self, points, pad=60):
        if self._ctl is not None:
            self._ctl.fit(fb.to_js([{"lat": p["lat"], "lng": p["lng"]} for p in points if p and p.get("lat") is not None]), pad)

    def center(self):
        if self._ctl is None:
            return None
        return fb.from_js(self._ctl.center())

    def jump(self, lat, lng, zoom=15):
        if self._ctl is not None:
            self._ctl.jump(lat, lng, zoom)

    def tile_pois(self, recipe, center, km, saved):
        if self._ctl is None:
            return []
        return fb.from_js(self._ctl.tilePois(fb.to_js(recipe), fb.to_js(center), km, fb.to_js(saved)))

    def destroy(self):
        if self._ctl is not None:
            self._ctl.destroy()
            self._ctl = None

    @handle("", "hide")
    def form_hide(self, **event_args):
        self.destroy()
