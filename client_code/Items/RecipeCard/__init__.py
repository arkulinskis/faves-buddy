from anvil import *

from ._anvil_designer import RecipeCardTemplate
from ... import state


class RecipeCard(RecipeCardTemplate):
    """One Discover search: emoji, name, why it's suggested, and the exact query it sends. item = {key, emoji, label,
    because, q, on}. Raises x-run(key, item, button)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i = self.item
        self.dom_nodes["em"].textContent = i.get("emoji") or ""
        self.dom_nodes["label"].textContent = i.get("label") or ""
        self.dom_nodes["because"].textContent = i.get("because") or ""
        self.dom_nodes["q"].textContent = i.get("q") or ""
        self.q.visible = bool(i.get("q"))
        self.btn.classes["on"] = bool(i.get("on"))
        state.set_attr(self.btn, "aria-pressed", "true" if i.get("on") else "false")
        state.set_attr(self.btn, "data-key", i.get("key"))

    def btn_click(self, event):
        self.parent.raise_event("x-run", key=self.item["key"], item=self.item)
