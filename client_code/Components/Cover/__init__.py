import json

from anvil import *
from anvil.js import window

from ._anvil_designer import CoverTemplate


class Cover(CoverTemplate):
    """A fave's picture or its category tile (see FB.drawCover). Redraws when fave or pills change."""

    def __init__(self, **properties):
        self._fave, self._pills, self._ready = {}, False, False
        super().__init__(**properties)
        self._ready = True
        self._draw()

    def _draw(self):
        if self._ready:
            window.FB.drawCover(self.dom_nodes["box"], json.dumps(self._fave or {}), json.dumps({"pills": self._pills}))

    @property
    def fave(self):
        return self._fave

    @fave.setter
    def fave(self, value):
        self._fave = value or {}
        self._draw()

    @property
    def pills(self):
        return self._pills

    @pills.setter
    def pills(self, value):
        self._pills = bool(value)
        self._draw()
