from anvil import *

from ._anvil_designer import ListsPickerTemplate
from ... import state


class ListsPicker(ListsPickerTemplate):
    """Tick the lists a fave is in (your own lists and ones you can add to), or make a new one.
    Closes with the updated fave, or None."""

    def __init__(self, fave, lists, current, **properties):
        super().__init__(**properties)
        self.fave = fave
        state.set_control_attr(self.new_box, "aria-label", "New list name")
        state.set_control_attr(self.new_box, "maxlength", "60")
        self.rows = [{"id": l["id"], "emoji": l.get("emoji") or "⭐", "name": l["name"],
                      "owner": l.get("owner") if l.get("role") == "editor" else "", "_on": l["id"] in (current or [])}
                     for l in (lists or []) if l.get("role") in ("owner", "editor")]
        self._draw()

    def _draw(self):
        self.lists_panel.items = self.rows
        self.none.visible = not self.rows

    @handle("new_box", "pressed_enter")
    def new_box_pressed_enter(self, **event_args):
        self.create_button_click()

    @handle("create_button", "click")
    def create_button_click(self, **event_args):
        name = (self.new_box.text or "").strip()
        if not name:
            return
        r = state.call("save_list", None, {"name": name})
        if r:
            l = r["list"]
            self.rows.insert(0, {"id": l["id"], "emoji": l.get("emoji") or "⭐", "name": l["name"], "owner": "", "_on": True})
            self.new_box.text = ""
            self._draw()

    @handle("cancel_button", "click")
    def cancel_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=None)

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        ids = [r["id"] for r in self.rows if r.get("_on")]
        self.save_button.enabled = False
        try:
            r = state.call("update_fave", self.fave["id"], {"lists": ids})
        finally:
            self.save_button.enabled = True
        if r:
            state.toast("Lists updated", "ok")
            self.raise_event("x-close-alert", value=r["fave"])
