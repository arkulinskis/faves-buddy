from anvil import *

from ._anvil_designer import SortRowTemplate


class SortRow(SortRowTemplate):
    """A row of an admin table with up to three cells: item = {a, b, c}."""

    def __init__(self, **properties):
        super().__init__(**properties)
        for k in ("a", "b", "c"):
            self.dom_nodes[k].textContent = str(self.item.get(k, ""))
