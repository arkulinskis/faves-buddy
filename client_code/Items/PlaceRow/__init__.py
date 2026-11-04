from anvil import *

from ._anvil_designer import PlaceRowTemplate
from ... import fb, state


class PlaceRow(PlaceRowTemplate):
    """A place found by name on the Save page: Save puts it in the inbox (sorted from its OpenStreetMap type)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        p = self.item
        self.dom_nodes["title"].textContent = p.get("title") or ""
        bits = [x for x in (p.get("kind"), p.get("address")) if x]
        if p.get("km") is not None:
            bits.append(fb.fmt_dist(p["km"]))
        self.dom_nodes["info"].textContent = " · ".join(bits)

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        p = self.item
        self.save_button.enabled = False
        r = state.call("save_fave", {"title": p["title"], "lat": p["lat"], "lng": p["lng"], "address": p.get("address") or "",
                                     "osm": p.get("osm") or {}, "kind": "place"})
        if not r:
            self.save_button.enabled = True
            return
        self.save_button.text = "Saved"
        state.toast(("Saved to your inbox as " if r.get("created") else "Already saved as ") + fb.cat_label(r["fave"]["cat"]), "ok")
