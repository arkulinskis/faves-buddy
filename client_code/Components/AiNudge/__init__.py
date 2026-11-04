from anvil import *

from ._anvil_designer import AiNudgeTemplate


class AiNudge(AiNudgeTemplate):
    """"Bring your own AI key to ..." with a link to Tools → AI."""

    def __init__(self, **properties):
        self._what, self._ready = "describe pictures", False
        super().__init__(**properties)
        self._ready = True
        self.dom_nodes["what"].textContent = self._what

    @property
    def what(self):
        return self._what

    @what.setter
    def what(self, value):
        self._what = value or ""
        if self._ready:
            self.dom_nodes["what"].textContent = self._what
