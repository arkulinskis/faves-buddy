from anvil import *

from ._anvil_designer import AddFavesTemplate
from ... import fb, state


class AddFaves(AddFavesTemplate):
    """Tick faves to add to a list (with a filter). Closes with how many were added, or None."""

    def __init__(self, lst, addable, **properties):
        super().__init__(**properties)
        self.lst = lst
        self.heading.text = "Add faves to “%s”" % lst["name"]
        state.set_control_attr(self.filter_box, "aria-label", "Filter your faves")
        self.all = [{"id": f["id"], "emoji": fb.cat(f.get("cat"))["emoji"], "name": f.get("title") or "", "owner": "", "_on": False}
                    for f in addable or []]
        self.none.visible = not self.all
        self.rows.items = self.all

    @handle("filter_box", "change")
    def filter_box_change(self, **event_args):
        q = (self.filter_box.text or "").lower()
        self.rows.items = [r for r in self.all if not q or q in str(r["name"]).lower()]

    @handle("cancel_button", "click")
    def cancel_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=None)

    @handle("add_button", "click")
    def add_button_click(self, **event_args):
        ids = [r["id"] for r in self.all if r.get("_on")]
        if not ids:
            self.raise_event("x-close-alert", value=None)
            return
        self.add_button.enabled = False
        try:
            r = state.call("list_add", self.lst["id"], ids)
        finally:
            self.add_button.enabled = True
        if r:
            self.raise_event("x-close-alert", value=r.get("added") or len(ids))
