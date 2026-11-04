from anvil import *

from ._anvil_designer import DropRowTemplate
from ... import router, state


class DropRow(DropRowTemplate):
    """A pile shared in from a phone or another device that isn't tidied yet. Raises x-discarded after throwing it away."""

    def __init__(self, **properties):
        super().__init__(**properties)
        d = self.item
        what = " and ".join(x for x in (state.plural(d["links"], "link") if d.get("links") else "",
                                        state.plural(d["photos"], "picture") if d.get("photos") else "") if x)
        self.dom_nodes["name"].textContent = d.get("name") or what
        self.dom_nodes["info"].textContent = "%s · %s" % (what, state.ago(d.get("created")))
        state.set_attr(self.open_link, "href", router.href("share", d["code"]))

    @handle("discard_button", "click")
    def discard_button_click(self, **event_args):
        if confirm("Throw this shared pile away?", buttons=[("Cancel", False), ("Throw away", True)], role="app-dialog"):
            if state.call("drop_discard", self.item["code"]) is not None:
                self.parent.raise_event("x-discarded")
