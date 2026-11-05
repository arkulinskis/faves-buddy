from anvil import *

from ._anvil_designer import InboxItemTemplate
from ... import fb, router, state


class InboxItem(InboxItemTemplate):
    """One thing waiting in the inbox: its suggested category with a confidence bar and the reasons, an AI suggestion
    when there is one, and Keep / Change / lists / snooze / archive / delete. Raises x-act(id, action, cat, button) on
    the RepeatingPanel (actions: keep, archive, snooze, delete, lists, ai)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.picker.add_event_handler("pick", self._picked)
        self.picker_part.visible = False
        self.draw()

    def draw(self):
        f = self.item
        c = fb.cat(f.get("cat"))
        self.cover.fave = f
        state.set_attr(self.box, "data-id", f["id"])
        self.dom_nodes["title"].textContent = f.get("title") or "Untitled"
        state.set_attr(self.title_link, "href", router.href("fave", f["id"]))
        if f.get("domain"):
            icon, sub = "globe", f["domain"]
        elif f.get("address"):
            icon, sub = "pin", f["address"]
        else:
            icon, sub = fb.KIND_ICON.get(f.get("kind"), "note"), f.get("kind") or ""
        for k in ("globe", "pin", "link", "image", "note", "bulb", "calendar"):
            self.sub_icon.classes["ic-" + k] = k == icon
        self.dom_nodes["sub"].textContent = sub
        self.tabset_part.visible = bool(f.get("tabset_name"))
        self.dom_nodes["tabset"].textContent = f.get("tabset_name") or ""
        self.dom_nodes["saves"].textContent = (" · saved %d×" % f["saves"]) if (f.get("saves") or 1) > 1 else ""
        enriched = bool(f.get("enriched"))
        self.sorted_part.visible, self.reading_part.visible = enriched, not enriched
        conf = int(round((f.get("conf") or 0) * 100))
        self.dom_nodes["sug"].textContent = "%s %s" % (c["emoji"], c["name"])
        other = f.get("cat") == "other"
        self.conf_bar.visible = not other
        self.dom_nodes["conf_fill"].style.width = "%d%%" % conf
        state.set_attr(self.conf_bar, "title", "How sure: %d%%" % conf)
        self.dom_nodes["conf_text"].textContent = "Not sure yet: pick one" if other else (
            "Pretty sure" if conf >= 70 else "Likely" if conf >= 45 else "A guess")
        reasons = (f.get("reasons") or [])[:3]
        self.why_part.visible = bool(reasons)
        self.why_panel.items = reasons
        a = (f.get("meta") or {}).get("ai_sort") or {}
        show_ai = bool(a.get("cat")) and a.get("cat") != f.get("cat")
        self.ai_part.visible = show_ai
        if show_ai:
            self.dom_nodes["ai_cat"].textContent = "AI suggests " + fb.cat_label(a["cat"])
            self.dom_nodes["ai_why"].textContent = (": " + a["why"]) if a.get("why") else ""
        self.tags.items = (f.get("tags") or [])[:5]
        self.tags.visible = bool(f.get("tags"))
        self.keep_button.text = "Keep" if other else "Keep as " + c["name"]
        self.open_link.visible = bool(f.get("url"))
        if f.get("url"):
            state.set_attr(self.open_link, "href", f["url"])
        self.picker.selected = f.get("cat") or ""

    def set_focus(self, on):
        self.box.classes["focus"] = bool(on)

    def gone(self):
        self.box.classes["gone"] = True

    def _act(self, action, cat=None, button=None):
        self.parent.raise_event("x-act", id=self.item["id"], action=action, cat=cat, button=button)

    @handle("keep_button", "click")
    def keep_button_click(self, **event_args):
        self._act("keep", button=self.keep_button)

    @handle("change_button", "click")
    def change_button_click(self, **event_args):
        self.picker_part.visible = not self.picker_part.visible

    def _picked(self, cat, **event_args):
        self._act("keep", cat=cat)

    @handle("lists_button", "click")
    def lists_button_click(self, **event_args):
        self._act("lists")

    @handle("snooze_button", "click")
    def snooze_button_click(self, **event_args):
        self._act("snooze")

    @handle("archive_button", "click")
    def archive_button_click(self, **event_args):
        self._act("archive")

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        self._act("delete")

    @handle("ai_button", "click")
    def ai_button_click(self, **event_args):
        self._act("ai", button=self.ai_button)
