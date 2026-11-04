from anvil import *

from ._anvil_designer import ColorPickTemplate
from ... import state

NAMES = {"#5b5bf0": "Indigo", "#ff6f61": "Coral", "#ffb300": "Amber", "#26a69a": "Teal", "#ec407a": "Pink", "#42a5f5": "Blue",
         "#66bb6a": "Green", "#8d6e63": "Brown", "#ab47bc": "Purple", "#78909c": "Grey"}


class ColorPick(ColorPickTemplate):
    """A colour to choose for a list: item {v, on}. Raises x-pick(v)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        v = self.item["v"]
        self.btn.style["background"] = v
        self.btn.classes["on"] = bool(self.item.get("on"))
        state.set_attr(self.btn, "aria-label", NAMES.get(v.lower(), v))
        state.set_attr(self.btn, "aria-pressed", "true" if self.item.get("on") else "false")
        state.set_attr(self.btn, "data-key", v)

    def btn_click(self, event):
        self.parent.raise_event("x-pick", v=self.item["v"])
