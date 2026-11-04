from anvil import *
from anvil.js import window

from ._anvil_designer import GetAppTemplate
from ... import fb, state


class GetApp(GetAppTemplate):
    """#app: how to install Faves Buddy on Android, iPhone/iPad and a computer (it's a web app: no store needed).
    The card for this device comes first and is marked; the Install button shows when the browser offers it."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        p = window.FB.tidy.platform()
        inst = bool(window.FB.tidy.installed())
        can = bool(window.FB.tidy.canInstall())
        self.installed_note.visible = inst
        self.here_android.visible, self.here_ios.visible, self.here_desktop.visible = p == "android", p == "ios", p == "desktop"
        for name, card in (("android", self.card_android), ("ios", self.card_ios), ("desktop", self.card_desktop)):
            card.classes["here"] = name == p
        self.install_button.visible = p == "android" and can and not inst
        self.install_desktop_button.visible = p == "desktop" and can and not inst
        url = window.location.origin + "/"
        self.url = url
        msg = "Faves Buddy: open this on your phone and add it to your home screen: " + url
        state.set_attr(self.mail_link, "href", "mailto:%s?subject=%s&body=%s" % (
            window.encodeURIComponent((state.me() or {}).get("email") or ""), window.encodeURIComponent("Faves Buddy on my phone"),
            window.encodeURIComponent(msg)))
        state.set_attr(self.sms_link, "href", "sms:?&body=" + window.encodeURIComponent(msg))

    def _install(self, button):
        outcome = window.FB.tidy.install()
        if outcome == "accepted":
            state.toast("Installed. Find Faves Buddy on your home screen.", "ok")
            button.visible = False
        elif outcome == "unavailable":
            state.toast("Use your browser's menu: Add to Home screen (or Install).")

    @handle("install_button", "click")
    def install_button_click(self, **event_args):
        self._install(self.install_button)

    @handle("install_desktop_button", "click")
    def install_desktop_button_click(self, **event_args):
        self._install(self.install_desktop_button)

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        fb.copy(self.url, "Link copied. Open it on your phone.")
