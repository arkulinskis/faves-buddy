from anvil import *

from ._anvil_designer import FactTemplate
from ... import state


class Fact(FactTemplate):
    """One line of facts about a place or a page: item = {icon, text, href, external, open ("open"/"closed"/"")}."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i = self.item
        self.icon.classes.add("ic-" + i["icon"])
        self.open.visible, self.closed.visible = i.get("open") == "open", i.get("open") == "closed"
        has = bool(i.get("href"))
        self.link.visible, self.plain.visible = has, not has
        self.dom_nodes["a"].textContent = i["text"]
        self.dom_nodes["t"].textContent = i["text"]
        if has:
            state.set_attr(self.link, "href", i["href"])
            if i.get("external"):
                state.set_attr(self.link, "target", "_blank")
                state.set_attr(self.link, "rel", "noopener")
