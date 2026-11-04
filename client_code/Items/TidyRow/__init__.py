from anvil import *

from ._anvil_designer import TidyRowTemplate
from ... import fb, state


class TidyRow(TidyRowTemplate):
    """A tab in Tidy's list view: tick to keep, change its category. item = tab + _on, _cat (both written back)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        it = self.item
        self.dom_nodes["title"].textContent = it.get("title") or it.get("domain") or ""
        self.dom_nodes["info"].textContent = (it.get("domain") or "") + (" · already saved" if it.get("already") else "")
        self.cat_box.items = [("%s %s" % (c["emoji"], c["name"]), c["id"]) for c in fb.cats()]
        self.cat_box.selected_value = it.get("_cat") or "other"
        state.set_control_attr(self.cat_box, "aria-label", "Category for " + (it.get("title") or "this tab"))
        state.set_control_attr(self.on_box, "aria-label", "Keep " + (it.get("title") or "this tab"))

    @handle("cat_box", "change")
    def cat_box_change(self, **event_args):
        self.item["_cat"] = self.cat_box.selected_value
