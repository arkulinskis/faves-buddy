from anvil import *

from ._anvil_designer import LinkRowTemplate
from ... import fb, router, state

WAYBACK = "https://web.archive.org/web/"


class LinkRow(LinkRowTemplate):
    """Tools -> Link health: one gone or moved link. item = fave (slim) + link {state, code, moved_to, checked}.
    Gone: "Saved copy" (the Wayback Machine's copy, opened by the person; the app sends nothing there), It works, Archive.
    Moved: the new address, Use new address (link_fix use_new), It works (keep the old one). Raises x-fixed(fave_id, state)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        f = self.item
        ln = f.get("link") or {}
        gone = ln.get("state") == "gone"
        state.set_attr(self.title_link, "href", router.href("fave", f["id"]))
        self.dom_nodes["title"].textContent = f.get("title") or f.get("domain") or "Untitled"
        code = ln.get("code")
        why = ("Page not found (%s)" % code if code in (404, 410) else "The website no longer answers") if gone else "Moved to a new address"
        self.dom_nodes["info"].textContent = "%s · %s · checked %s" % (f.get("domain") or "", why, state.ago(ln.get("checked")))
        self.new_part.visible = not gone and bool(ln.get("moved_to"))
        self.dom_nodes["new_url"].textContent = fb.short_url(ln.get("moved_to") or "")
        self.copy_link.visible = gone and bool(f.get("url"))
        if f.get("url"):
            state.set_attr(self.copy_link, "href", WAYBACK + (f.get("url") or ""))
            state.set_attr(self.copy_link, "aria-label", "Look for a saved copy of " + (f.get("title") or "this page") + " on the Wayback Machine")
        self.use_button.visible = not gone
        self.works_button.text = "It works" if gone else "Keep the old one"
        self.archive_button.visible = gone

    def _done(self, new_state):
        self.row.visible = False
        if self.parent is not None:
            self.parent.raise_event("x-fixed", fave_id=self.item["id"], link_state=new_state)

    @handle("use_button", "click")
    def use_button_click(self, **event_args):
        if state.call("link_fix", self.item["id"], "use_new") is not None:
            state.toast("Updated to the new address", "ok")
            self._done("ok")

    @handle("works_button", "click")
    def works_button_click(self, **event_args):
        if state.call("link_fix", self.item["id"], "works") is not None:
            self._done("ok")

    @handle("archive_button", "click")
    def archive_button_click(self, **event_args):
        if state.call("triage", self.item["id"], "archive") is not None:
            state.toast("Archived", "ok")
            self._done("archived")
