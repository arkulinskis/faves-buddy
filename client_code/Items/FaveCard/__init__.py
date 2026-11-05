from anvil import *

from ._anvil_designer import FaveCardTemplate
from ... import fb, router, state


class FaveCard(FaveCardTemplate):
    """A fave as a card: picture or category tile with pills, title, place or website, distance, open now, tags,
    and the heart (Loved). item = a fave dict plus optional extras:
        _from      {lat, lng}: show the distance from there
        _href      where the card links ("" = no link; default #fave/<id>)
        _nostage   no heart
        _actions   any of "copy" (Save to mine), "remove", "open" (the link), "go" (directions)
    Raises on the RepeatingPanel: x-loved(fave), x-copy(id, button), x-remove(id)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self._draw()

    def _draw(self):
        f = self.item
        self.cover.fave = f
        self.dom_nodes["title"].textContent = f.get("title") or "Untitled"
        if f.get("kind") == "place" or (f.get("lat") is not None and not f.get("url")):
            icon, sub = "pin", f.get("address") or "On the map"
        elif f.get("domain"):
            icon, sub = "globe", f["domain"]
        elif f.get("kind") == "photo":
            icon, sub = "image", "Picture"
        else:
            icon, sub = fb.KIND_ICON.get(f.get("kind"), "note"), ("Idea" if f.get("kind") == "idea" else "Note")
        self.sub_icon.classes.add("ic-" + icon)
        self.dom_nodes["sub"].textContent = sub
        d = fb.dist(f.get("_from"), f) if f.get("_from") else None
        o = fb.open_state(f)
        rest = []
        if f.get("owner"):
            rest.append("from " + f["owner"])
        if (f.get("saves") or 1) > 1:
            rest.append("saved %s×" % f["saves"])
        lead = fb.fmt_dist(d) if d is not None else ""
        self.dom_nodes["m_lead"].textContent = lead + (" · " if lead and o else "")
        self.m_open.visible, self.m_closed.visible = o == "open", o == "closed"
        self.dom_nodes["m_rest"].textContent = ((" · " if (lead or o) and rest else "") + " · ".join(rest))
        self.meta.visible = bool(lead or o or rest)
        self.tags.items = (f.get("tags") or [])[:3]
        self.tags.visible = bool(f.get("tags"))
        mine = f.get("mine") is not False
        self.love.visible = not f.get("_nostage") and mine
        loved = f.get("stage") == "loved"
        self.love.classes["loved"] = loved
        state.set_attr(self.love, "aria-pressed", "true" if loved else "false")
        state.set_attr(self.love, "aria-label", "Loved: " + (f.get("title") or "") if loved else "Love " + (f.get("title") or "it"))
        href = f.get("_href")
        if href is None:
            href = router.href("fave", f["id"])
        state.set_attr(self.link, "href", href or None)
        acts = f.get("_actions") or []
        self.copy_button.visible = "copy" in acts
        self.remove_button.visible = "remove" in acts
        self.open_link.visible = "open" in acts and bool(f.get("url"))
        self.go_link.visible = "go" in acts and f.get("lat") is not None
        if f.get("url"):
            state.set_attr(self.open_link, "href", f["url"])
        if f.get("lat") is not None:
            state.set_attr(self.go_link, "href", fb.directions_url(f))
        self.actions.visible = self.copy_button.visible or self.remove_button.visible or self.open_link.visible or self.go_link.visible

    def love_click(self, event):
        event.preventDefault()
        f = self.item
        loved = f.get("stage") == "loved"
        self.love.classes["loved"] = not loved
        r = state.call_quiet("update_fave", f["id"], {"stage": "" if loved else "loved"})
        if not r or not r.get("ok"):
            self.love.classes["loved"] = loved
            state.toast((r or {}).get("error") or "That didn't work.", "error")
            return
        state.toast("Unloved" if loved else "Loved it ♥", "ok")
        f["stage"] = "" if loved else "loved"
        self._draw()
        if self.parent is not None:
            self.parent.raise_event("x-loved", fave=r.get("fave"))

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        self.parent.raise_event("x-copy", id=self.item["id"], button=self.copy_button)

    @handle("remove_button", "click")
    def remove_button_click(self, **event_args):
        self.parent.raise_event("x-remove", id=self.item["id"])
