import anvil.js
from anvil import *
from anvil.js import window

from ._anvil_designer import InboxTemplate
from ... import fb, state


class Inbox(InboxTemplate):
    """#inbox: everything new waits here, already sorted with a suggested category, a confidence bar and the reasons.
    Keep it (picking another category teaches the sorter), add to lists, snooze, archive or delete. Links saved in bulk
    (tab sets, imports) are read a few at a time in the background (enrich_pending). With AI sorting on, unsure items
    get a second opinion (ai_second_opinion). Keys: J/K move, Enter keep, A archive, S snooze, Delete delete."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        state.live(self.progress_text)
        self.items = []
        self.lists = []
        self.focus = 0
        self.pending = 0
        self.start_pending = 0
        self.alive = True
        self.items_panel.add_event_handler("x-act", self._act)
        self._off_keys = window.FB.onKeys(anvil.js.report_exceptions(self._key))
        self._load()

    def leave(self):
        self.alive = False
        self._off_keys()

    # ---- drawing
    def _load(self):
        fb.boot()
        d = state.call("inbox")
        if d is None:
            return
        self.items, self.lists = d["faves"], d.get("lists") or []
        self.pending = d["pending"]
        self.start_pending = max(self.start_pending, d["pending"])
        fb.set_inbox(d["total"])
        sure = len([f for f in self.items if f.get("enriched") and (f.get("conf") or 0) >= 0.6 and f.get("cat") != "other"])
        self.summary.text = (state.plural(d["total"], "thing") + " to sort" if d["total"] else "Nothing to sort") + (
            " · %d snoozed" % d["snoozed"] if d.get("snoozed") else "")
        self.accept_button.visible = sure > 1
        self.accept_button.text = "Keep the %d sure ones" % sure
        self._draw_items()
        self._progress()
        if self.pending:
            window.setTimeout(self._enrich, 300)
        else:
            self._ask_ai()

    def _draw_items(self):
        self.items_panel.items = self.items
        self.zero.visible = not self.items
        self.keys.visible = bool(self.items)
        self._set_focus(min(self.focus, max(0, len(self.items) - 1)), quiet=True)

    def _progress(self):
        self.progress.visible = bool(self.pending)
        if self.pending:
            done = self.start_pending - self.pending
            pct = int(round(done * 100.0 / self.start_pending)) if self.start_pending else 0
            self.progress_text.text = "Reading %s…" % state.plural(self.pending, "saved page")
            self.dom_nodes["progress_fill"].style.width = "%d%%" % pct

    def _replace(self, faves):
        """Put fresh copies of some faves in place (after enriching or an AI opinion) without redrawing the rest."""
        by_id = {f["id"]: f for f in faves}
        self.items = [by_id.get(x["id"], x) for x in self.items]
        for c in self.items_panel.get_components():
            f = by_id.get(getattr(c, "item")["id"])
            if f is not None:
                setattr(c, "item", f)
                getattr(c, "draw")()

    def _enrich(self):
        if not self.alive or not self.pending:
            return
        r = state.call_quiet("enrich_pending", 4)
        if not self.alive:
            return
        if not r:
            self.pending = 0
            self._progress()
            return
        self.pending = r["left"]
        self._replace(r["done"])
        self._progress()
        if self.pending:
            window.setTimeout(self._enrich, 300)
        else:
            self._ask_ai()

    def _ask_ai(self):
        a = fb.ai_sort()
        if not self.alive or not (a.get("available") and a.get("on")) or self.pending:
            return
        unsure = [f for f in self.items if f.get("enriched") and not f.get("confirmed") and (f.get("conf") or 0) < 0.55
                  and not (f.get("meta") or {}).get("ai_sort")]
        if not unsure:
            return
        try:
            r = state.call_quiet("ai_second_opinion")
        except Exception as e:
            print("AI second opinion: %r" % e)
            return
        if r and self.alive:
            self._replace(r.get("faves") or [])

    # ---- focus + keys
    def _set_focus(self, i, quiet=False):
        comps = self.items_panel.get_components()
        if not comps:
            return
        self.focus = max(0, min(len(comps) - 1, i))
        for j, c in enumerate(comps):
            getattr(c, "set_focus")(j == self.focus and not quiet)
        if not quiet:
            node = anvil.js.get_dom_node(comps[self.focus])
            el = node.querySelector(".ib-item") or node
            getattr(el, "focus")({"preventScroll": True})
            window.FB.scrollIntoView(el)

    def _key(self, key, ctrl):
        if not self.items:
            return False
        fid = self.items[self.focus]["id"] if self.focus < len(self.items) else None
        if key in ("j", "arrowdown"):
            self._set_focus(self.focus + 1)
            return True
        if key in ("k", "arrowup"):
            self._set_focus(self.focus - 1)
            return True
        if fid is None:
            return False
        if key == "enter":
            self._do(fid, "keep")
            return True
        if key == "a":
            self._do(fid, "archive")
        elif key == "s":
            self._do(fid, "snooze")
        elif key in ("delete", "backspace"):
            self._do(fid, "delete")
        return False

    # ---- actions
    def _act(self, id, action, cat=None, button=None, **event_args):
        for i, f in enumerate(self.items):
            if f["id"] == id:
                self.focus = i
        if button is not None:
            button.enabled = False
        try:
            self._do(id, action, cat)
        finally:
            if button is not None:
                button.enabled = True

    def _do(self, id, action, cat=None):
        f = next((x for x in self.items if x["id"] == id), None)
        if f is None:
            return
        if action == "keep":
            if state.call("triage", id, "keep", cat or None) is not None:
                self._remove(id, "Kept in " + fb.cat_label(cat or f["cat"]))
        elif action == "archive":
            if state.call("triage", id, "archive") is not None:
                self._remove(id, "Archived")
        elif action == "delete":
            if state.call("triage", id, "delete") is not None:
                self._remove(id, "Deleted")
        elif action == "snooze":
            from ...Dialogs.Snooze import Snooze
            if alert(Snooze(fave_id=id), buttons=[], role="app-dialog", dismissible=True):
                self._remove(id)
        elif action == "lists":
            from ...Dialogs.ListsPicker import ListsPicker
            nf = alert(ListsPicker(fave=f, lists=self.lists, current=[]), buttons=[], role="app-dialog", dismissible=True)
            if nf and nf.get("status") == "kept":
                self._remove(id)
        elif action == "ai":
            r = state.call("ai_use", id)
            if r:
                self._remove(id, "Kept in " + fb.cat_label(r["fave"]["cat"]))

    def _remove(self, id, message=None):
        self.items = [x for x in self.items if x["id"] != id]
        fb.set_inbox(len(self.items))
        if message:
            state.toast(message, "ok")
        for c in self.items_panel.get_components():
            if getattr(c, "item")["id"] == id:
                getattr(c, "gone")()
        window.setTimeout(self._after_remove, 260)

    def _after_remove(self):
        if not self.alive:
            return
        if not self.items:
            window.FB.confetti()
            self._load()
        else:
            self._draw_items()

    @handle("accept_button", "click")
    def accept_button_click(self, **event_args):
        self.accept_button.enabled = False
        try:
            r = state.call("accept_confident", 0.6)
        finally:
            self.accept_button.enabled = True
        if r:
            state.toast(state.plural(r["kept"], "fave") + " kept with their suggested category", "ok")
            if r["kept"]:
                window.FB.confetti()
            self._load()
