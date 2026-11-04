import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import ShareInTemplate
from ... import fb, router, state


class ShareIn(ShareInTemplate):
    """#share/<code>: where Android's share sheet lands (the share target POSTs to /_/api/share, which parks the pile
    under a code). drop_open claims it: links go to the tab deck, pictures to the screenshot sweep, a lone text gets a
    quick "save as a note" form."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.code = args[0] if args else ""
        self.note_part.visible = self.gone_part.visible = False
        state.set_control_attr(self.title_box, "maxlength", "200")
        r = anvil.server.call_s("drop_open", self.code)
        if not r.get("ok"):
            self.gone_part.visible = True
            self.gone_text.text = r.get("error") or "That share has already been tidied, or it expired."
            return
        fb._cache["incoming"] = r
        if r.get("links"):
            state.store_set("tidy.tabs", None)
            window.setTimeout(lambda: router.go("tidy", "tabs"), 0)
            return
        if r.get("photos"):
            window.setTimeout(lambda: router.go("tidy", "shots"), 0)
            return
        lines = (r.get("note") or "").split("\n")
        self.title_box.text = lines[0][:200]
        self.note_box.text = "\n".join(lines[1:]).strip()
        self.note_part.visible = True

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        title = (self.title_box.text or "").strip()
        if not title:
            state.toast("Give it a title.", "error")
            return
        s = state.call("save_fave", {"title": title, "note": self.note_box.text or "", "kind": "note", "source": "share"})
        if s:
            state.call_quiet("drop_discard", self.code)
            state.toast("Saved as " + fb.cat_label(s["fave"]["cat"]), "ok")
            router.go("fave", s["fave"]["id"])

    @handle("no_button", "click")
    def no_button_click(self, **event_args):
        state.call_quiet("drop_discard", self.code)
        router.go("tidy")
