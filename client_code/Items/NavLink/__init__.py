from anvil import *

from ._anvil_designer import NavLinkTemplate
from ... import router, state


class NavLink(NavLinkTemplate):
    """A header menu link. item = {page, label, icon, on, count} (count: the inbox's waiting things)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        state.set_attr(self, "href", router.href(self.item["page"]))
        self.icon.classes.add("ic-" + self.item["icon"])
        self.dom_nodes["label"].textContent = self.item["label"]
        n = self.item.get("count") or 0
        self.count.visible = bool(n)
        self.dom_nodes["count"].textContent = str(n)
        self.classes["on"] = bool(self.item.get("on"))
        if self.item.get("on"):
            state.set_attr(self, "aria-current", "page")
