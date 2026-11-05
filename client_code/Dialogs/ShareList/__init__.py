from anvil import *

from ._anvil_designer import ShareListTemplate
from ... import fb, router, state


class ShareList(ShareListTemplate):
    """Share a list: a public link (on/off, copy) and people invited by email as viewers or editors."""

    def __init__(self, lst, **properties):
        super().__init__(**properties)
        self.L = lst
        self.heading.text = "Share “%s”" % lst["name"]
        self.role_box.items = [("Can view", "viewer"), ("Can add", "editor")]
        state.set_control_attr(self.role_box, "aria-label", "What they can do")
        state.set_control_attr(self.email_box, "aria-label", "Their email")
        state.set_control_attr(self.link_box, "aria-label", "Public link")
        state.set_control_attr(self.link_box, "readonly", "")
        self.members.add_event_handler("x-changed", self._reload)
        self._draw()

    def _link(self):
        return fb.app_url(router.href("s", self.L["token"])) if self.L.get("public") and self.L.get("token") else ""

    def _draw(self):
        self.public_box.checked = bool(self.L.get("public"))
        link = self._link()
        self.link_row.visible = bool(link)
        self.link_box.text = link
        ms = self.L.get("members") or []
        self.members.items = [dict(m, _list=self.L["id"]) for m in ms]
        self.no_members.visible = not ms

    def _reload(self, **event_args):
        r = state.call("get_list", self.L["id"])
        if r:
            self.L = r["list"]
            self._draw()

    @handle("public_box", "change")
    def public_box_change(self, **event_args):
        r = state.call("set_public", self.L["id"], bool(self.public_box.checked))
        if r is None:
            self.public_box.checked = not self.public_box.checked
            return
        self.L["public"], self.L["token"] = bool(r.get("token")), r.get("token")
        self._draw()
        if r.get("token"):
            fb.copy(self._link(), "Link copied")

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        fb.copy(self._link(), "Link copied")

    @handle("email_box", "pressed_enter")
    def email_box_pressed_enter(self, **event_args):
        self.invite_button_click()

    @handle("invite_button", "click")
    def invite_button_click(self, **event_args):
        email = (self.email_box.text or "").strip()
        if not email:
            return
        self.invite_button.enabled = False
        try:
            r = state.call("invite", self.L["id"], email, self.role_box.selected_value)
        finally:
            self.invite_button.enabled = True
        if r:
            self.L["members"] = r["list"]["members"]
            self.email_box.text = ""
            self._draw()
            state.toast("Shared. They'll see it in their lists." if r.get("has_account") else
                        "Invite saved. Tell them to sign up with %s." % email, "ok")

    @handle("done_button", "click")
    def done_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=True)
