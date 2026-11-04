from anvil import *

from ._anvil_designer import ListCheckTemplate


class ListCheck(ListCheckTemplate):
    """A list with a tick box (in the Add to lists dialog). item = {id, emoji, name, owner, _on}."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i = self.item
        self.box.text = "%s  %s%s" % (i["emoji"], i["name"], (" · " + i["owner"]) if i.get("owner") else "")
