from anvil import *

from ._anvil_designer import ReasonTemplate


class Reason(ReasonTemplate):
    """One reason the sorter gave ("the page is a recipe"). item = the text."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.dom_nodes["t"].textContent = str(self.item)
