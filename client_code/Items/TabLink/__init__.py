from anvil import *

from ._anvil_designer import TabLinkTemplate
from ... import fb, router, state


class TabLink(TabLinkTemplate):
    """A tab inside a tab set: emoji of its category, title, website."""

    def __init__(self, **properties):
        super().__init__(**properties)
        f = self.item
        state.set_attr(self.a, "href", router.href("fave", f["id"]))
        self.dom_nodes["em"].textContent = fb.cat(f.get("cat"))["emoji"]
        self.dom_nodes["t"].textContent = f.get("title") or ""
        self.dom_nodes["d"].textContent = f.get("domain") or ""
