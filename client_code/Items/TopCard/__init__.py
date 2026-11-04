from anvil import *

from ._anvil_designer import TopCardTemplate
from ... import fb, router, state


class TopCard(TopCardTemplate):
    """A top fave: a place people save most around here. item = {title, cat, lat, lng, address, image, osm, people,
    mine, km, _from}. Save puts it in your inbox (save_top_fave); the card opens the map there."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self._draw()

    def _draw(self):
        p = self.item
        self.cover.fave = dict(p, kind="place")
        self.dom_nodes["title"].textContent = p.get("title") or ""
        self.dom_nodes["people"].textContent = "Saved by %d people" % p.get("people", 0)
        d = fb.dist(p.get("_from"), p) if p.get("_from") else p.get("km")
        where = [x for x in (fb.fmt_dist(d) if d is not None else "", p.get("address") or "") if x]
        self.dom_nodes["where"].textContent = " · ".join(where) or fb.cat_label(p.get("cat"))
        self.open.visible = fb.open_state(p) == "open"
        state.set_attr(self.link, "href", router.href("map", "find", p.get("title") or ""))
        mine = bool(p.get("mine"))
        self.save_button.visible, self.yours.visible = not mine, mine
        state.set_attr(self.go_link, "href", fb.directions_url(p))

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        p = self.item
        self.save_button.enabled = False
        r = state.call("save_top_fave", {k: p.get(k) for k in ("title", "lat", "lng", "address", "osm")})
        self.save_button.enabled = True
        if r:
            state.toast(("In your inbox as " if r.get("created") else "Already saved as ") + fb.cat_label(r["fave"]["cat"]), "ok")
            p["mine"] = True
            self._draw()
