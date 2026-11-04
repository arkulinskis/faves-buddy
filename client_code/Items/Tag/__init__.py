from anvil import *

from ._anvil_designer import TagTemplate


class Tag(TagTemplate):
    """A #tag pill. item = the tag text."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.dom_nodes["t"].textContent = "#" + str(self.item)
