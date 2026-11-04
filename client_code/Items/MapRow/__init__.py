from anvil import *

from ._anvil_designer import MapRowTemplate
from ... import fb, router, state


class MapRow(MapRowTemplate):
    """A place in the map's side list: picture, name, category, open now, distance. item = fave + _from + _on."""

    def __init__(self, **properties):
        super().__init__(**properties)
        f = self.item
        self.cover.fave = f
        state.set_attr(self.row, "href", router.href("fave", f["id"]))
        state.set_attr(self.row, "data-row", f["id"])
        self.row.classes["on"] = bool(f.get("_on"))
        self.dom_nodes["title"].textContent = f.get("title") or ""
        self.dom_nodes["cat"].textContent = fb.cat_label(f.get("cat"))
        o = fb.open_state(f)
        self.open.visible, self.closed.visible = o == "open", o == "closed"
        self.dom_nodes["dist"].textContent = fb.fmt_dist(fb.dist(f.get("_from"), f)) if f.get("_from") else ""
