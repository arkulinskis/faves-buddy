from anvil import *

from ._anvil_designer import TabsTemplate
from ... import fb, state


class Tabs(TabsTemplate):
    """#tabs: tab sets: groups of tabs saved together ("Save all tabs in this window" in the extension, or an
    import). Server: tabsets, rename_tabset, keep_tabset, delete_tabset."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.sets.add_event_handler("x-reload", self._load)
        self._load()

    def _load(self, **event_args):
        fb.boot()
        r = state.call("tabsets") or {"tabsets": []}
        self.sets.items = r["tabsets"]
        self.empty.visible = not r["tabsets"]
