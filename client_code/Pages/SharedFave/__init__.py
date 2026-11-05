import anvil.server
from anvil import *

from ._anvil_designer import SharedFaveTemplate
from ... import fb, router, state

PENDING = "pending.fave"


class SharedFave(SharedFaveTemplate):
    """#f/<token>: one fave someone shared by link. Anyone can see it (no account needed): picture, title, link or
    place on a map. Saving it needs an account: visitors sign up (or in) and come straight back here, where it is
    saved for them (the token waits in this browser's storage meanwhile). Server: shared_fave (public),
    copy_shared_fave."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.token = args[0] if args else ""
        self._map_open = False
        self.F: dict = {}
        state.heading(self.title, 1)
        self._load()

    def _load(self):
        r = anvil.server.call("shared_fave", self.token)
        ok = bool(r.get("ok"))
        self.found_part.visible, self.missing.visible = ok, not ok
        if not ok:
            self.missing_text.text = r.get("error") or ""
            return
        fb.set_cats(r.get("cats"))
        F = self.F = r["fave"]
        router.set_title(F.get("title") or "A shared fave")
        c = fb.cat(F.get("cat"))
        self.cover.fave = F
        self.dom_nodes["by"].textContent = "Shared by " + (F.get("owner") or "someone")
        self.dom_nodes["cat_dot"].style.background = c["color"]
        self.dom_nodes["cat_name"].textContent = "%s %s" % (c["emoji"], c["name"])
        self.title.text = F.get("title") or "Untitled"
        self.desc.text = F.get("desc") or ""
        self.desc.visible = bool(F.get("desc"))
        facts = []
        if F.get("address"):
            facts.append({"icon": "pin", "text": F["address"]})
        o = F.get("osm") or {}
        if o.get("opening_hours"):
            facts.append({"icon": "clock", "text": o["opening_hours"], "open": fb.open_state(F)})
        if F.get("event_at"):
            facts.append({"icon": "calendar", "text": "%s · %s" % (fb.when(F["event_at"]), fb.fmt_date(F["event_at"]))})
        self.facts.items = facts
        self.facts.visible = bool(facts)
        self.open_link.visible = bool(F.get("url"))
        if F.get("url"):
            state.set_attr(self.open_link, "href", F["url"])
            self.dom_nodes["open_text"].textContent = "Open " + (F.get("domain") or "link")
        place = F.get("lat") is not None
        self.dir_link.visible = place
        if place:
            state.set_attr(self.dir_link, "href", fb.directions_url(F))
        self.map_part.visible = place
        signed_in = bool(r.get("signed_in"))
        yours = r.get("yours")
        self.guest_part.visible = not signed_in
        self.cta.visible = not signed_in
        self.save_button.visible = signed_in and not yours
        self.yours_link.visible = bool(yours)
        if yours:
            state.set_attr(self.yours_link, "href", router.href("fave", yours))
        if signed_in and not yours and state.store_get(PENDING, "") == self.token:
            state.store_set(PENDING, "")
            self.save_button_click()

    @handle("", "show")
    def form_show(self, **event_args):
        F = self.F
        if F.get("lat") is not None and not self._map_open:
            self._map_open = True
            self.map.open(center=F, zoom=15, cooperative=True)
            self.map.pins([F], "go")

    def leave(self):
        self.map.destroy()

    def _remember(self):
        state.store_set(PENDING, self.token)
        router.remember_after(router.href("f", self.token))

    @handle("signup_button", "click")
    def signup_button_click(self, **event_args):
        self._remember()
        router.go("auth", "signup")

    def signin_click(self, event):
        event.preventDefault()
        self._remember()
        router.go("auth")

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        self.save_button.enabled = False
        try:
            r = state.call("copy_shared_fave", self.token)
        finally:
            self.save_button.enabled = True
        if r:
            state.toast(("Saved to your inbox as " if r.get("created") else "Already in your faves as ") + fb.cat_label(r["fave"]["cat"]), "ok")
            self.save_button.visible = False
            self.yours_link.visible = True
            state.set_attr(self.yours_link, "href", router.href("fave", r["fave"]["id"]))
