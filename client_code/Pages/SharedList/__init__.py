import anvil.server
from anvil import *

from ._anvil_designer import SharedListTemplate
from ... import fb, router, state


class SharedList(SharedListTemplate):
    """#s/<token>: a list someone shared by link. Anyone can open it (no account): the list, its places on a map, its
    faves. Signed-in visitors can save any of them into their own collection (copy_shared)."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.token = args[0] if args else ""
        self._map_open = False
        state.heading(self.name, 1)
        self.grid.add_event_handler("x-copy", self._copy)
        r = anvil.server.call("shared_list", self.token)
        ok = bool(r.get("ok"))
        self.found_part.visible, self.missing.visible = ok, not ok
        if not ok:
            self.missing_text.text = r.get("error") or "This link doesn't work any more."
            return
        fb.set_cats(r.get("cats"))
        self.L = r["list"]
        L = self.L
        router.set_title(L["name"])
        self.dom_nodes["em"].textContent = L.get("emoji") or "⭐"
        self.em.style["background"] = "color-mix(in srgb,%s 20%%,var(--c-bg))" % (L.get("color") or "#5b5bf0")
        self.dom_nodes["by"].textContent = "A list shared by " + (L.get("owner") or "someone")
        self.name.text = L["name"]
        self.desc.text = L.get("description") or ""
        self.desc.visible = bool(L.get("description"))
        self.places = [f for f in L["items"] if f.get("lat") is not None]
        self.counts.text = state.plural(L.get("count") or 0, "fave") + (
            " · %s on the map" % state.plural(len(self.places), "place") if self.places else "")
        acts = (["copy"] if L.get("signed_in") else []) + ["open", "go"]
        self.grid.items = [dict(f, _nostage=True, _href="", _actions=acts) for f in L["items"]]
        self.cta.visible = not L.get("signed_in")
        self.map.visible = bool(self.places)

    @handle("", "show")
    def form_show(self, **event_args):
        if getattr(self, "places", None) and not self._map_open:
            self._map_open = True
            self.map.open(center=self.places[0], zoom=13, cooperative=True)
            self.map.pins(self.places, "go")
            self.map.fit(self.places, 40)

    def leave(self):
        self.map.destroy()

    def _copy(self, id, button=None, **event_args):
        r = state.call("copy_shared", self.token, id)
        if r:
            if button is not None:
                button.text, button.enabled = "Saved", False
            state.toast("Saved to your inbox" if r.get("created") else "Already in your faves", "ok")
