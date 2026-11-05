from anvil import *

from ._anvil_designer import LearnedRowTemplate
from ... import fb, state


class LearnedRow(LearnedRowTemplate):
    """Something the sorter learned (a website or a word -> a category). Raises x-forget(kind, key)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        x = self.item
        self.dom_nodes["key"].textContent = x["key"]
        self.dom_nodes["cat"].textContent = "%s × %d" % (fb.cat_label(x["cat"]), x["n"])
        state.set_control_attr(self.forget_button, "aria-label", "Forget " + x["key"])

    @handle("forget_button", "click")
    def forget_button_click(self, **event_args):
        self.parent.raise_event("x-forget", kind=self.item["_kind"], key=self.item["key"])
