import anvil.server
from anvil import *

from ._anvil_designer import EditListTemplate
from ... import state


class EditList(EditListTemplate):
    """Create or edit a list: name, emoji, colour, description. Closes with the saved list, or None."""

    def __init__(self, lst, emojis, colors, **properties):
        super().__init__(**properties)
        self.lst = lst or {}
        self.emoji = self.lst.get("emoji") or emojis[0]
        self.color = self.lst.get("color") or colors[0]
        self.all_emojis, self.all_colors = emojis, colors
        self.heading.text = "Edit list" if self.lst.get("id") else "New list"
        self.save_button.text = "Save" if self.lst.get("id") else "Create list"
        self.name_box.text = self.lst.get("name") or ""
        self.desc_box.text = self.lst.get("description") or ""
        state.set_control_attr(self.name_box, "maxlength", "60")
        state.set_control_attr(self.desc_box, "maxlength", "400")
        self.emojis.add_event_handler("x-pick", self._emoji)
        self.colors.add_event_handler("x-pick", self._color)
        self._draw()

    def _draw(self):
        self.emojis.items = [{"v": e, "on": e == self.emoji} for e in self.all_emojis]
        self.colors.items = [{"v": c, "on": c == self.color} for c in self.all_colors]

    @handle("", "show")
    def form_show(self, **event_args):
        self.name_box.focus()

    def _emoji(self, v, **event_args):
        k = state.focus_key()
        self.emoji = v
        self._draw()
        state.refocus(self.emojis, k)

    def _color(self, v, **event_args):
        k = state.focus_key()
        self.color = v
        self._draw()
        state.refocus(self.colors, k)

    @handle("cancel_button", "click")
    def cancel_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=None)

    @handle("name_box", "pressed_enter")
    def name_box_pressed_enter(self, **event_args):
        self.save_button_click()

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        name = (self.name_box.text or "").strip()
        if not name:
            self.message.text, self.message.visible = "Give the list a name.", True
            return
        self.save_button.enabled = False
        try:
            r = anvil.server.call("save_list", self.lst.get("id"), {"name": name, "description": self.desc_box.text or "",
                                                                    "emoji": self.emoji, "color": self.color})
        finally:
            self.save_button.enabled = True
        if not r.get("ok"):
            self.message.text, self.message.visible = r.get("error") or "That didn't work.", True
            return
        self.raise_event("x-close-alert", value=r["list"])
