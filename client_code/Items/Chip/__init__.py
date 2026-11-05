from anvil import *

from ._anvil_designer import ChipTemplate
from ... import state


class Chip(ChipTemplate):
    """One chip: a category, a filter, a radius, a place result... item = {key, label, n, on, sm, flat, icon, disabled,
    title}. Clicking raises x-chip(key, item) on the RepeatingPanel; the page decides what it means."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i = self.item
        self.dom_nodes["label"].textContent = i.get("label") or ""
        n = i.get("n")
        self.dom_nodes["n"].textContent = "" if n in (None, "") else str(n)
        self.btn.classes["on"] = bool(i.get("on"))
        self.btn.classes["sm"] = bool(i.get("sm"))
        self.btn.classes["flat"] = bool(i.get("flat")) and not i.get("on")
        self.icon.visible = bool(i.get("icon"))
        if i.get("icon"):
            self.icon.classes.add("ic-" + i["icon"])
        state.set_attr(self.btn, "data-key", i.get("key"))
        state.set_attr(self.btn, "aria-pressed", "true" if i.get("on") else "false")
        if i.get("title"):
            state.set_attr(self.btn, "title", i["title"])
        if i.get("disabled"):
            state.set_attr(self.btn, "disabled", "")

    def btn_click(self, event):
        if self.item.get("disabled"):
            return
        self.parent.raise_event("x-chip", key=self.item.get("key"), item=self.item)
