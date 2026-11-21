import anvil.js
import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import RevisitTemplate
from ... import fb, router, state

TIMES = [(0, "Any time", "sparkle"), (5, "5 min reads", "clock"), (15, "15 min", "clock"), (30, "30 min", "clock")]
WORDS = {"keep": "kept", "archive": "let go", "remind": "for later", "open": "opened"}


class Revisit(RevisitTemplate):
    """#revisit: "Still want this?" for the faves you kept but never opened (server Revisit.revisit_queue).
    A meter (opened X of Y), On this day, filters (time you have: reads that fit 5/15/30 min; category; oldest or
    newest first), then one card at a time: Still want it (not asked again for 60 days), Let go (archive), Remind me
    (snooze to the inbox), Open it now (opens the link, counts as a keep). Swipe right/left, arrow keys, Undo.
    The finish screen tallies what happened."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.f: dict = state.store_get("revisit.filters", None) or {"mins": 0, "cat": "", "order": "old"}
        self.items: list = []
        self.idx = 0
        self.history: list = []
        self.tally: dict = {}
        self.d: dict = {}
        self._off_keys = None
        fb.boot()
        window.FB.tidy.swipe(self.dom_nodes["card"], anvil.js.report_exceptions(self._swiped))
        self._off_keys = window.FB.onKeys(anvil.js.report_exceptions(self._key))
        self.time_chips.add_event_handler("x-chip", self._time_pick)
        self.cat_chips.add_event_handler("x-chip", self._cat_pick)
        self._load()

    def leave(self):
        if self._off_keys is not None:
            self._off_keys()
            self._off_keys = None

    # ---- data
    def _load(self):
        d = state.call("revisit_queue", self.f)
        if d is None:
            return
        self.d = d
        self.items, self.idx, self.history, self.tally = list(d["items"]), 0, [], {}
        self._meter()
        otd = d.get("on_this_day") or []
        self.otd_part.visible = bool(otd)
        self.otd_panel.items = otd
        self._filters()
        self._render()

    def _meter(self):
        s = self.d.get("stats") or {}
        total, opened, waiting = s.get("total") or 0, s.get("opened") or 0, s.get("waiting") or 0
        self.meter_part.visible = bool(total)
        pct = int(round(opened * 100.0 / total)) if total else 0
        self.dom_nodes["meter_text"].textContent = "You opened %d of %s" % (opened, state.plural(total, "kept fave"))
        self.dom_nodes["meter_sub"].textContent = ("%s never opened, waiting for a look" % state.plural(waiting, "save")) if waiting else "Nothing waiting. Nice."
        self.dom_nodes["meter_bar"].style.width = "%d%%" % max(2, pct)
        self.dom_nodes["meter_wrap"].setAttribute("aria-label", "%d%% opened" % pct)

    def _filters(self):
        d, f = self.d, self.f
        fits = d.get("fits") or {}
        self.time_chips.items = [{"key": m, "label": label, "icon": icon, "sm": True, "on": (f.get("mins") or 0) == m,
                                  "n": fits.get(str(m)) if m else None} for m, label, icon in TIMES]
        cats = d.get("cats") or {}
        self.cat_chips.items = fb.chip_items(fb.cats(), f.get("cat") or None, cats, all_label="Every category", total=sum(cats.values()), sm=True)
        self.filters_part.visible = bool(cats)
        for name, btn in (("old", self.order_old), ("new", self.order_new)):
            btn.classes["on"] = (f.get("order") or "old") == name
            state.set_attr(btn, "aria-pressed", "true" if (f.get("order") or "old") == name else "false")

    def _refilter(self):
        state.store_set("revisit.filters", self.f)
        self._load()

    def _time_pick(self, key, **event_args):
        self.f["mins"] = key or 0
        self._refilter()

    def _cat_pick(self, key, **event_args):
        self.f["cat"] = key or ""
        self._refilter()

    def order_click(self, event):
        self.f["order"] = event.currentTarget.getAttribute("data-order") or "old"
        self._refilter()

    # ---- the deck
    def _render(self):
        left = len(self.items) - self.idx
        done = bool(self.history) and left <= 0
        self.deck_part.visible = left > 0
        self.done_part.visible = done
        self.empty_part.visible = not done and left <= 0
        if self.empty_part.visible:
            waiting = (self.d.get("stats") or {}).get("waiting") or 0
            if waiting and (self.f.get("mins") or self.f.get("cat")):
                self.dom_nodes["empty_title"].textContent = "Nothing fits these filters"
                self.dom_nodes["empty_text"].textContent = "Try Any time or Every category: %s still wait." % state.plural(waiting, "save")
            else:
                self.dom_nodes["empty_title"].textContent = "Nothing to revisit"
                self.dom_nodes["empty_text"].textContent = ("Things you keep but don't open show up here after a few days. "
                                                            "Everything else you kept was opened or looked at recently.")
        if done:
            self._finish()
            return
        if left <= 0:
            return
        it = self.items[self.idx]
        self.count_label.text = "%d of %d" % (self.idx + 1, len(self.items))
        more = (self.d.get("left") or 0) - len(self.items)
        self.tally_label.text = (" · %d more after these" % more) if more > 0 else ""
        self.card_cover.fave = it
        self.dom_nodes["card_title"].textContent = it.get("title") or it.get("domain") or "Untitled"
        c = fb.cat(it.get("cat"))
        self.dom_nodes["card_site"].textContent = "%s %s · %s" % (c["emoji"], c["name"], it.get("domain") or it.get("address") or {"note": "a note", "idea": "an idea", "photo": "a picture", "place": "a place"}.get(it.get("kind") or "", "a note"))
        self.card_desc.visible = bool(it.get("desc"))
        self.dom_nodes["card_desc_t"].textContent = it.get("desc") or ""
        bits = ["Saved " + state.ago(it.get("created"))]
        if it.get("read_min"):
            bits.append("%d minute read" % it["read_min"])
        if it.get("link_state") == "gone":
            bits.append("the page seems to be gone")
        self.dom_nodes["card_age"].textContent = " · ".join(bits)
        has_url = bool(it.get("url"))
        self.open_link.visible = has_url
        if has_url:
            state.set_attr(self.open_link, "href", it["url"])
        state.set_attr(self.fave_link, "href", router.href("fave", it["id"]))
        self.undo_button.enabled = bool(self.history)

    def _finish(self):
        n = len(self.history)
        self.done_title.text = "You looked at %s" % state.plural(n, "save")
        kept = self.tally.get("keep", 0) + self.tally.get("open", 0)
        gone = self.tally.get("archive", 0)
        self.done_text.text = ("Kept %d, let go of %d. Your collection is a little lighter and a lot more yours." % (kept, gone)) if gone else \
            "Everything you looked at still matters to you. They won't be asked about again for two months."
        self.done_tally.items = [{"key": k, "label": WORDS[k], "n": v, "sm": True, "flat": True} for k, v in self.tally.items() if v]
        more = (self.d.get("left") or 0) - len(self.items)
        self.more_button.visible = more > 0 or bool(self.items)
        if gone >= 3:
            try:
                window.FB.confetti()
            except Exception:
                pass

    def _decide(self, act, server_act=None):
        if self.idx >= len(self.items):
            return
        it = self.items[self.idx]
        r = state.call("revisit_decide", it["id"], server_act or act)
        if r is None:
            return
        self._advance(it, act)

    def _advance(self, it, act):
        self.history.append((it, act))
        self.tally[act] = self.tally.get(act, 0) + 1
        self.idx += 1
        window.FB.tidy.fling(self.dom_nodes["card"], "skip" if act == "archive" else "keep" if act in ("keep", "open") else "later")
        self._render()

    def _swiped(self, act):
        self._decide("keep" if act == "keep" else "archive")

    @handle("keep_button", "click")
    def keep_button_click(self, **event_args):
        self._decide("keep")

    @handle("letgo_button", "click")
    def letgo_button_click(self, **event_args):
        self._decide("archive")

    @handle("remind_button", "click")
    def remind_button_click(self, **event_args):
        if self.idx >= len(self.items):
            return
        it = self.items[self.idx]
        from ...Dialogs.Snooze import Snooze
        if alert(Snooze(fave_id=it["id"]), buttons=[], role="app-dialog", dismissible=True):
            self._advance(it, "remind")

    def open_click(self, event):
        """The link opens in a new tab (the anchor does that); here it counts as opened and the deck moves on."""
        if self.idx >= len(self.items):
            return
        it = self.items[self.idx]
        state.call_quiet("revisit_decide", it["id"], "open")
        window.setTimeout(anvil.js.report_exceptions(lambda: self._advance(it, "open")), 120)

    @handle("undo_button", "click")
    def undo_button_click(self, **event_args):
        self._undo()

    def _undo(self):
        if not self.history:
            return
        it, act = self.history.pop()
        if state.call("revisit_decide", it["id"], "undo") is None:
            self.history.append((it, act))
            return
        self.tally[act] = max(0, self.tally.get(act, 1) - 1)
        self.idx = max(0, self.idx - 1)
        self._render()

    @handle("more_button", "click")
    def more_button_click(self, **event_args):
        self._load()

    def _key(self, key, ctrl):
        if not self.deck_part.visible:
            return False
        if key == "arrowright":
            self._decide("keep")
        elif key == "arrowleft":
            self._decide("archive")
        elif key == "arrowdown":
            self.remind_button_click()
        elif (key == "z" and ctrl) or key == "backspace":
            self._undo()
        else:
            return False
        return True
