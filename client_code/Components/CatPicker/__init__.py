from anvil import *

from ._anvil_designer import CatPickerTemplate
from ... import fb, state


class CatPicker(CatPickerTemplate):
    """Category chips. selected = the pressed one; "pick" event when someone picks one (the keyboard focus stays on it)."""

    def __init__(self, **properties):
        self._selected, self._small, self._scroll, self._ready = "", False, False, False
        super().__init__(**properties)
        self.chips.add_event_handler("x-chip", self._picked)
        self._ready = True
        self._draw()

    def _draw(self):
        if not self._ready:
            return
        self.host.classes["scroll"] = self._scroll
        self.chips.items = fb.chip_items(fb.cats(), self._selected, sm=self._small)

    def _picked(self, key, **event_args):
        k = state.focus_key()
        self._selected = key
        self._draw()
        state.refocus(self.chips, k)
        self.raise_event("pick", cat=key)

    @property
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, value):
        self._selected = value or ""
        self._draw()

    @property
    def small(self):
        return self._small

    @small.setter
    def small(self, value):
        self._small = bool(value)
        self._draw()

    @property
    def scroll(self):
        return self._scroll

    @scroll.setter
    def scroll(self, value):
        self._scroll = bool(value)
        self._draw()
