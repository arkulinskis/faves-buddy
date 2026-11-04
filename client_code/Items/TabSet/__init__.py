from anvil import *
from anvil.js import window

from ._anvil_designer import TabSetTemplate
from ... import fb, state


class TabSet(TabSetTemplate):
    """A saved tab set: rename it, open every tab again, copy the links, keep everything still in the inbox, delete it
    (with or without its faves). Raises x-reload after Keep all / Delete."""

    def __init__(self, **properties):
        super().__init__(**properties)
        s = self.item
        self.name_box.text = s["name"]
        state.set_control_attr(self.name_box, "aria-label", "Tab set name")
        self.info.text = "%s · saved %s · %s" % (state.plural(s["count"], "tab"), state.ago(s["created"]),
                                                  ("%d still in your inbox" % s["inbox"]) if s.get("inbox") else "all sorted ✓")
        self.keep_button.visible = bool(s.get("inbox"))
        self.cats.items = [{"key": c[0], "label": fb.cat_label(c[0]), "n": c[1], "sm": True, "flat": True} for c in s.get("cats") or []]
        self.links.items = s.get("faves") or []

    def _urls(self):
        return [f["url"] for f in self.item.get("faves") or [] if f.get("url")]

    @handle("name_box", "lost_focus")
    def name_box_lost_focus(self, **event_args):
        name = (self.name_box.text or "").strip()
        if name and name != self.item["name"]:
            if state.call("rename_tabset", self.item["id"], name) is not None:
                self.item["name"] = name
                state.toast("Renamed", "ok")

    @handle("name_box", "pressed_enter")
    def name_box_pressed_enter(self, **event_args):
        self.name_box_lost_focus()

    @handle("open_button", "click")
    def open_button_click(self, **event_args):
        urls = self._urls()
        opened = 0
        for u in urls:
            if window.open(u, "_blank", "noopener"):
                opened += 1
        if opened < len(urls):
            state.toast("Your browser blocked some tabs. Allow pop-ups for this site, or use the extension's “Reopen a tab set”.", "error")

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        urls = self._urls()
        fb.copy("\n".join(urls), state.plural(len(urls), "link") + " copied")

    @handle("keep_button", "click")
    def keep_button_click(self, **event_args):
        r = state.call("keep_tabset", self.item["id"])
        if r:
            state.toast(state.plural(r["kept"], "tab") + " kept", "ok")
            self.parent.raise_event("x-reload")

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        choice = alert("Keep the tabs as faves and only remove the group, or delete the tabs too.",
                       title="Delete “%s”?" % self.item["name"], role="app-dialog",
                       buttons=[("Cancel", None), ("Remove the group", "only"), ("Delete the tabs too", "all")])
        if choice:
            if state.call("delete_tabset", self.item["id"], choice == "all") is not None:
                state.toast("Done", "ok")
                self.parent.raise_event("x-reload")
