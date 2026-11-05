from anvil import *

from ._anvil_designer import ListsTemplate
from ... import router, state


class Lists(ListsTemplate):
    """#lists, #lists/new: your lists and the ones shared with you, as tiles with picture previews."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.mine.add_event_handler("x-new", self._new)
        self.d = state.call("my_lists") or {"mine": [], "shared": [], "emojis": ["⭐"], "colors": ["#5b5bf0"]}
        self.mine.items = self.d["mine"] + [{"_new": True}]
        self.shared.items = self.d["shared"]
        self.shared_part.visible = bool(self.d["shared"])
        self._open_new = bool(args) and args[0] == "new"

    @handle("", "show")
    def form_show(self, **event_args):
        if self._open_new:
            self._open_new = False
            self._new()

    def _new(self, **event_args):
        from ...Dialogs.EditList import EditList
        l = alert(EditList(lst=None, emojis=self.d["emojis"], colors=self.d["colors"]), buttons=[], role="app-dialog", dismissible=True)
        if l:
            router.go("list", l["id"])

    @handle("new_button", "click")
    def new_button_click(self, **event_args):
        self._new()
