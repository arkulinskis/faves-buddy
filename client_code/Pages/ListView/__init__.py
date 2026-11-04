import anvil.server
from anvil import *

from ._anvil_designer import ListViewTemplate
from ... import fb, router, state


class ListView(ListViewTemplate):
    """#list/<id>: one list: its faves, a mini map of its places, add faves, edit, share (public link + invite people by
    email as viewer/editor), leave or delete. Server: get_list, save_list, delete_list, list_add, list_remove,
    set_public, invite, set_member, copy_member_item."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.id = args[0] if args else ""
        self.L: dict = {}
        self.extra: dict = {}
        self._map_open = False
        state.heading(self.name, 1)
        self.grid.add_event_handler("x-copy", self._copy)
        self.grid.add_event_handler("x-remove", self._remove)
        fb.boot()
        if self._reload():
            self._draw()

    def leave(self):
        self.map.destroy()

    def _reload(self):
        r = anvil.server.call("get_list", self.id)
        if not r.get("ok"):
            state.toast(r.get("error") or "That list isn't available.", "error")
            router.go("lists")
            return False
        self.L = r["list"]
        self.extra = {"addable": r.get("addable") or [], "emojis": r.get("emojis") or ["⭐"], "colors": r.get("colors") or ["#5b5bf0"]}
        router.set_title(self.L["name"])
        return True

    def _draw(self):
        L = self.L
        own = L["role"] == "owner"
        edit = own or L["role"] == "editor"
        self.dom_nodes["em"].textContent = L.get("emoji") or "⭐"
        self.em.style["background"] = "color-mix(in srgb,%s 20%%,var(--c-bg))" % (L.get("color") or "#5b5bf0")
        self.name.text = L["name"]
        info = state.plural(L.get("count") or 0, "fave")
        if not own:
            info += " · by %s · you can %s" % (L.get("owner") or "", "add and remove" if edit else "view")
        if L.get("public"):
            info += " · 🔗 anyone with the link can view"
        self.info.text = info
        self.desc.text = L.get("description") or ""
        self.desc.visible = bool(L.get("description"))
        self.add_button.visible = edit
        self.share_button.visible = self.edit_button.visible = self.delete_button.visible = own
        self.leave_button.visible = not own
        items = L.get("items") or []
        cards = []
        for f in items:
            acts = []
            if not f.get("mine"):
                acts.append("copy")
            if f.get("can_remove"):
                acts.append("remove")
            cards.append(dict(f, _nostage=True, _actions=acts))
        self.grid.items = cards
        self.grid.visible = bool(items)
        self.empty.visible = not items
        self.empty_text.text = "Add faves to it here, or from any fave's page." if edit else "Nothing here yet."
        places = [f for f in items if f.get("lat") is not None]
        self.map.visible = bool(places)
        if places:
            if not self._map_open:
                self._map_open = True
                self.map.open(center=places[0], zoom=13, cooperative=True)
            self.map.pins(places, "fave")
            self.map.fit(places, 40)

    def _refresh(self):
        if self._reload():
            self._draw()

    @handle("add_button", "click")
    def add_button_click(self, **event_args):
        from ...Dialogs.AddFaves import AddFaves
        n = alert(AddFaves(lst=self.L, addable=self.extra["addable"]), buttons=[], role="app-dialog", dismissible=True)
        if n:
            state.toast(state.plural(n, "fave") + " added", "ok")
            self._refresh()

    @handle("share_button", "click")
    def share_button_click(self, **event_args):
        from ...Dialogs.ShareList import ShareList
        alert(ShareList(lst=self.L), buttons=[], role="app-dialog", large=True, dismissible=True)
        self._refresh()

    @handle("edit_button", "click")
    def edit_button_click(self, **event_args):
        from ...Dialogs.EditList import EditList
        if alert(EditList(lst=self.L, emojis=self.extra["emojis"], colors=self.extra["colors"]), buttons=[], role="app-dialog", dismissible=True):
            self._refresh()

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        if confirm("The faves stay in your collection; only the list goes. People it was shared with lose access.",
                   title="Delete this list?", buttons=[("Cancel", False), ("Delete list", True)], role="app-dialog"):
            if state.call("delete_list", self.L["id"]) is not None:
                state.toast("List deleted", "ok")
                router.go("lists")

    @handle("leave_button", "click")
    def leave_button_click(self, **event_args):
        me_m = next((m for m in self.L.get("members") or [] if m.get("me")), None)
        if confirm("You won't see it any more unless %s shares it again." % (self.L.get("owner") or "the owner"),
                   title="Leave this list?", buttons=[("Cancel", False), ("Leave", True)], role="app-dialog") and me_m:
            if state.call("set_member", self.L["id"], me_m["id"]) is not None:
                router.go("lists")

    def _copy(self, id, button=None, **event_args):
        r = state.call("copy_member_item", self.L["id"], id)
        if r:
            state.toast("Saved to your inbox" if r.get("created") else "Already in your faves", "ok")

    def _remove(self, id, **event_args):
        if state.call("list_remove", self.L["id"], id) is not None:
            state.toast("Removed from the list", "ok")
            self._refresh()
