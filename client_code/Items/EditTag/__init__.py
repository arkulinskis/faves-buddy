from anvil import *

from ._anvil_designer import EditTagTemplate
from ... import state


class EditTag(EditTagTemplate):
    """A #tag with a remove button (the fave page). Raises x-untag(tag)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.dom_nodes["t"].textContent = "#" + str(self.item)
        state.set_attr(self.x, "aria-label", "Remove the tag " + str(self.item))

    def x_click(self, event):
        self.parent.raise_event("x-untag", tag=self.item)
