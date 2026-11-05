from anvil import *

from ._anvil_designer import PeekListTemplate
from ... import router, state


class PeekList(PeekListTemplate):
    """A public demo list on the landing page (links to its shared page #s/<token>)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        l = self.item
        state.set_attr(self.tile, "href", router.href("s", l["token"]))
        self.dom_nodes["em"].textContent = l.get("emoji") or "⭐"
        self.em.style["background"] = "color-mix(in srgb,%s 20%%,var(--c-bg))" % (l.get("color") or "#5b5bf0")
        self.dom_nodes["name"].textContent = l["name"]
        self.dom_nodes["info"].textContent = "%s · by %s" % (state.plural(l.get("count") or 0, "fave"), l.get("owner") or "")
