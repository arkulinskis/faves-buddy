from anvil import *
from anvil.js import window

from ._anvil_designer import ShareFaveTemplate
from ... import fb, router, state


class ShareFave(ShareFaveTemplate):
    """Share one fave by link (share_fave). Copy the link, use the phone's share sheet, email or text it, or turn it
    off. The person who opens it sees the fave and can save it once they have an account (#f/<token>)."""

    def __init__(self, fave, **properties):
        super().__init__(**properties)
        self.F = fave
        self.token = None
        self.heading.text = "Share “%s”" % (fave.get("title") or "this fave")
        state.set_control_attr(self.link_box, "aria-label", "Link to this fave")
        state.set_control_attr(self.link_box, "readonly", "")
        self.native_button.visible = bool(window.FB.canShare())
        r = state.call("share_fave", fave["id"], True)
        self.token = (r or {}).get("token")
        self._draw()

    def _url(self):
        return fb.app_url(router.href("f", self.token)) if self.token else ""

    def _draw(self):
        on = bool(self.token)
        self.on_box.checked = on
        self.link_part.visible = on
        url = self._url()
        self.link_box.text = url
        title = self.F.get("title") or "this"
        msg = "I saved %s on Faves Buddy: %s" % (title, url)
        state.set_attr(self.mail_link, "href", "mailto:?subject=%s&body=%s" % (
            window.encodeURIComponent("Have a look: " + title), window.encodeURIComponent(msg)))
        state.set_attr(self.sms_link, "href", "sms:?&body=" + window.encodeURIComponent(msg))

    @handle("on_box", "change")
    def on_box_change(self, **event_args):
        r = state.call("share_fave", self.F["id"], bool(self.on_box.checked))
        if r is None:
            self.on_box.checked = not self.on_box.checked
            return
        self.token = r.get("token")
        self._draw()
        state.toast("Link on" if self.token else "Link off: it doesn't work any more", "ok")

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        fb.copy(self._url(), "Link copied. Paste it anywhere.")

    @handle("native_button", "click")
    def native_button_click(self, **event_args):
        window.FB.share(self.F.get("title") or "Faves Buddy", "I saved this on Faves Buddy", self._url())

    @handle("done_button", "click")
    def done_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=bool(self.token))
