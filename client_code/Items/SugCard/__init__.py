from anvil import *

from ._anvil_designer import SugCardTemplate
from ... import fb, state


class SugCard(SugCardTemplate):
    """A Discover suggestion (a place from OpenStreetMap, a festival, an event, a Wikipedia article). item = {title,
    cat, kind, image, lat, lng, address/venue, desc, start, km, genre, why, url/website, _i, _saved}. Raises
    x-save(i, button)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        s = self.item
        self.cover.fave = {"id": "sug%s" % s.get("_i"), "title": s.get("title"), "cat": s.get("cat") or "other", "kind": s.get("kind") or "place",
                           "image": s.get("image"), "event_at": s.get("start"), "desc": s.get("desc")}
        self.dom_nodes["title"].textContent = s.get("title") or ""
        sub = s.get("desc") or s.get("venue") or s.get("address") or ""
        self.sub_row.visible = bool(sub)
        self.dom_nodes["sub"].textContent = sub
        meta = []
        if s.get("km") is not None:
            meta.append(fb.fmt_dist(s["km"]) + " away")
        if s.get("genre"):
            meta.append(s["genre"])
        self.dom_nodes["meta"].textContent = " · ".join(meta)
        self.why.visible = bool(s.get("why"))
        self.dom_nodes["why_t"].textContent = "✓ " + " · ".join(s.get("why") or [])
        saved = bool(s.get("_saved"))
        self.save_button.text = "Saved" if saved else "Save"
        self.save_button.enabled = not saved
        link = s.get("url") or s.get("website")
        self.look_link.visible = bool(link)
        if link:
            state.set_attr(self.look_link, "href", link)
        self.map_link.visible = s.get("lat") is not None and not s.get("url")
        if self.map_link.visible:
            state.set_attr(self.map_link, "href", fb.osm_url(s))

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        self.parent.raise_event("x-save", i=self.item["_i"], button=self.save_button)
