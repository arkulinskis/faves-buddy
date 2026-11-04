import json

from anvil import *
from anvil.js import window

from ._anvil_designer import ListTileTemplate
from ... import router, state


class ListTile(ListTileTemplate):
    """A list on the Lists page: a mosaic of its pictures, emoji, name, count and who it's shared with. item {_new: True}
    is the dashed "New list" tile (raises x-new)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        l = self.item
        new = bool(l.get("_new"))
        self.tile.visible, self.new_tile.visible = not new, new
        if new:
            return
        state.set_attr(self.tile, "href", router.href("list", l["id"]))
        window.FB.drawMosaic(self.dom_nodes["mosaic"], json.dumps(l))
        self.dom_nodes["em"].textContent = l.get("emoji") or "⭐"
        self.em.style["background"] = "color-mix(in srgb,%s 18%%,transparent)" % (l.get("color") or "#5b5bf0")
        self.dom_nodes["name"].textContent = l["name"]
        info = state.plural(l.get("count") or 0, "fave")
        if l.get("role") != "owner":
            info += " · by %s · %s" % (l.get("owner") or "", "you can add" if l.get("role") == "editor" else "view only")
        else:
            if l.get("public"):
                info += " · 🔗 public"
            if l.get("members_n"):
                info += " · shared with %d" % l["members_n"]
        self.dom_nodes["info"].textContent = info

    def new_click(self, event):
        self.parent.raise_event("x-new")
