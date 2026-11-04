from anvil import *

from ._anvil_designer import HomeListTemplate
from ... import router, state


class HomeList(HomeListTemplate):
    """A list in the home page's "Your lists" row, or the dashed "New list" tile (item {_new: True})."""

    def __init__(self, **properties):
        super().__init__(**properties)
        l = self.item
        new = bool(l.get("_new"))
        self.tile.visible, self.new_tile.visible = not new, new
        if new:
            return
        state.set_attr(self.tile, "href", router.href("list", l["id"]))
        self.dom_nodes["em"].textContent = l.get("emoji") or "⭐"
        self.em.style["background"] = "color-mix(in srgb,%s 18%%,transparent)" % (l.get("color") or "#5b5bf0")
        self.dom_nodes["name"].textContent = l["name"]
        info = state.plural(l.get("count") or 0, "fave")
        if l.get("role") != "owner":
            info += " · shared by " + (l.get("owner") or "")
        elif l.get("public"):
            info += " · public link"
        self.dom_nodes["info"].textContent = info
