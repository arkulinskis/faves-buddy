from anvil import *

from ._anvil_designer import PhotoRowTemplate
from ... import router, state


class PhotoRow(PhotoRowTemplate):
    """A picture being saved on the Save page: thumbnail, status line and progress. The page changes item and calls
    draw() (the row puts itself in item["_form"] so the page can find it)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.item["_form"] = self
        self.draw()

    def draw(self):
        i = self.item
        if i.get("img"):
            self.dom_nodes["img"].src = i["img"]
        fave = i.get("fave")
        self.title_link.visible, self.title_plain.visible = bool(fave), not fave
        self.dom_nodes["title_a"].textContent = (fave or {}).get("title") or ""
        self.dom_nodes["title_b"].textContent = i.get("name") or ""
        if fave:
            state.set_attr(self.title_link, "href", router.href("fave", fave["id"]))
        self.dom_nodes["st"].textContent = i.get("status") or ""
        self.dom_nodes["why"].textContent = i.get("why") or ""
        self.bar.visible = i.get("pct") is not None and i.get("pct") < 100
        self.dom_nodes["fill"].style.width = "%d%%" % (i.get("pct") or 0)
