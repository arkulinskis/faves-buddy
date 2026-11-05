from anvil import *

from ._anvil_designer import EmojiPickTemplate
from ... import state


class EmojiPick(EmojiPickTemplate):
    """An emoji to choose for a list: item {v, on}. Raises x-pick(v)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.dom_nodes["b"].textContent = self.item["v"]
        self.btn.classes["on"] = bool(self.item.get("on"))
        state.set_attr(self.btn, "aria-pressed", "true" if self.item.get("on") else "false")
        state.set_attr(self.btn, "data-key", self.item["v"])

    def btn_click(self, event):
        self.parent.raise_event("x-pick", v=self.item["v"])
