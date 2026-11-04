from anvil import *

from ._anvil_designer import FoundLinkTemplate
from ... import state


class FoundLink(FoundLinkTemplate):
    """One found bit: a link (web, map, phone, email) or plain text (a date, a price)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i = self.item
        has = bool(i.get("href"))
        self.link.visible, self.plain.visible = has, not has
        self.dom_nodes["a"].textContent = i["text"]
        self.dom_nodes["span"].textContent = i["text"]
        if has:
            state.set_attr(self.link, "href", i["href"])
            if i.get("external"):
                state.set_attr(self.link, "target", "_blank")
                state.set_attr(self.link, "rel", "noopener")
