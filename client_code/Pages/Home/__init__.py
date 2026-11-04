import re

import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import HomeTemplate
from ... import fb, router, state

KINDS = [("Everything", ""), ("Places", "place"), ("Links", "link"), ("Pictures", "photo"), ("Notes", "note"), ("Ideas", "idea")]
STATUSES = [("Kept", "kept"), ("Kept + inbox", "all"), ("Archived", "archived")]
SORTS = [("Newest first", "new"), ("Oldest first", "old"), ("A to Z", "az"), ("Most loved", "loved"), ("Coming up", "soon")]
LINK = re.compile(r"^(https?://|www\.)\S+$|^[\w-]+(\.[\w-]+)+/\S*$", re.I)


class Home(HomeTemplate):
    """#home (also #home/cat/<id>, #home/tag/<t>): the library. Quick add, the inbox nudge, what's coming up, the top
    faves around you, one fave to rediscover, your lists, then every kept fave with filters (search, kind, status,
    sort, category, tag) and "Show more". Server: faves_home(filters), list_faves(filters, offset), save_fave,
    load_samples, top_faves."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.f: dict = state.store_get("home.filters", None) or {"status": "kept"}
        if len(args) > 1 and args[0] == "cat":
            self.f = dict(status="kept", cat=args[1])
        elif len(args) > 1 and args[0] == "tag":
            self.f = dict(status="kept", tag=args[1])
        self.offset = 0
        self.here = None
        self._qtimer = None
        state.heading(self.hello, 1)
        self.kind_box.items = KINDS
        self.status_box.items = STATUSES
        self.sort_box.items = SORTS
        state.set_control_attr(self.kind_box, "aria-label", "Kind")
        state.set_control_attr(self.status_box, "aria-label", "Status")
        state.set_control_attr(self.sort_box, "aria-label", "Sort")
        state.set_control_attr(self.quick_box, "aria-label", "Save something")
        state.set_control_attr(self.search_box, "aria-label", "Search your faves")
        if window.innerWidth < 520:
            self.quick_box.placeholder = "Link, Maps pin or idea…"
        for panel in (self.grid, self.soon_panel):
            panel.add_event_handler("x-loved", self._loved)
        self.cat_chips.add_event_handler("x-chip", self._cat_picked)
        self.tag_chips.add_event_handler("x-chip", self._tag_picked)
        self._load()

    # ---- data
    def _load(self):
        fb.boot()
        self.here = fb.geo(False)
        d = state.call("faves_home", self.f)
        if d is None:
            return
        self.d = d
        fb.set_inbox(d["inbox"])
        me = state.me() or {}
        self.hello.text = "Hi %s 👋" % ((me.get("name") or "there").split(" ")[0])
        if d["count_all"]:
            s = "%s kept · %s on your map" % (state.plural(d["total_kept"], "fave"), state.plural(d["places"], "place"))
            self.summary.text = s + (" · %d saved this week" % d["week"] if d.get("week") else "")
        else:
            self.summary.text = "Your collection starts here."
        self.inbox_nudge.visible = bool(d["inbox"])
        self.dom_nodes["inbox_n"].textContent = str(d["inbox"])
        self.dom_nodes["inbox_text"].textContent = ("thing is" if d["inbox"] == 1 else "things are") + " waiting in your inbox"
        empty = not d["count_all"]
        self.welcome.visible, self.collection.visible = empty, not empty
        if empty:
            return
        self.soon_part.visible = bool(d["soon"])
        self.soon_panel.items = [dict(x, _from=self.here) for x in d["soon"]]
        r = d.get("rediscover")
        self.redis_part.visible = bool(r)
        if r:
            self.redis_cover.fave = r
            self.redis_title.text = r["title"]
            self.redis_meta.text = "%s · saved %s" % (fb.cat_label(r["cat"]), state.ago(r["created"]))
            self.redis_desc.text = r.get("desc") or ""
            self.redis_desc.visible = bool(r.get("desc"))
            state.set_attr(self.redis_open, "href", router.href("fave", r["id"]))
        self.lists_panel.items = d["lists"][:8] + [{"_new": True}]
        self._filters()
        self._grid(d["faves"], d["total"], d["more"], False)
        self.samples_note.visible = bool(d.get("has_samples"))
        self._top()

    def _top(self):
        """Top faves around you: places other people saved most near you (counted anonymously)."""
        spot = self.here
        r = state.call_quiet("top_faves", spot["lat"] if spot else None, spot["lng"] if spot else None, 5) or {}
        places = r.get("places") or []
        self.top_part.visible = bool(places)
        self.top_panel.items = [dict(p, _from=self.here) for p in places[:10]]
        self.top_note.text = "Saved most by people %s. Counted anonymously: only places at least %d people saved, never who." % (
            r.get("near") or "near you", r.get("min_people") or 2)

    def _filters(self):
        d, f = self.d, self.f
        self.search_box.text = f.get("q") or ""
        self.kind_box.selected_value = f.get("kind") or ""
        self.status_box.selected_value = f.get("status") or "kept"
        self.sort_box.selected_value = f.get("sort") or "new"
        self.cat_chips.items = fb.chip_items(fb.cats(), f.get("cat"), d["counts"], all_label="All", total=d["total_kept"])
        self.tag_chips.items = [{"key": t, "label": "#" + t, "n": n, "on": f.get("tag") == t, "sm": True, "flat": True}
                                for t, n in d["tags"]]
        self.tag_chips.visible = bool(d["tags"])

    def _grid(self, faves, total, more, append):
        self.total_label.text = state.plural(total, "fave")
        cards = [dict(x, _from=self.here) for x in faves]
        self.grid.items = (list(self.grid.items or []) + cards) if append else cards
        self.no_match.visible = not len(list(self.grid.items or []))
        self.more_row.visible = bool(more)

    def _refilter(self):
        state.store_set("home.filters", self.f)
        self.offset = 0
        r = state.call_quiet("list_faves", self.f, 0)
        if r:
            self._grid(r["faves"], r["total"], r["more"], False)

    # ---- filters
    @handle("search_box", "change")
    def search_box_change(self, **event_args):
        if self._qtimer is not None:
            window.clearTimeout(self._qtimer)
        self._qtimer = window.setTimeout(self._search_now, 300)

    def _search_now(self):
        self._qtimer = None
        self.f["q"] = (self.search_box.text or "").strip()
        self._refilter()

    @handle("search_box", "pressed_enter")
    def search_box_pressed_enter(self, **event_args):
        self._search_now()

    @handle("kind_box", "change")
    def kind_box_change(self, **event_args):
        self.f["kind"] = self.kind_box.selected_value or None
        self._refilter()

    @handle("status_box", "change")
    def status_box_change(self, **event_args):
        self.f["status"] = self.status_box.selected_value
        self._refilter()

    @handle("sort_box", "change")
    def sort_box_change(self, **event_args):
        self.f["sort"] = self.sort_box.selected_value
        self._refilter()

    def _cat_picked(self, key, **event_args):
        k = state.focus_key()
        self.f["cat"] = key or None
        self.cat_chips.items = fb.chip_items(fb.cats(), self.f.get("cat"), self.d["counts"], all_label="All", total=self.d["total_kept"])
        state.refocus(self.cat_chips, k)
        self._refilter()

    def _tag_picked(self, key, **event_args):
        k = state.focus_key()
        self.f["tag"] = None if self.f.get("tag") == key else key
        self.tag_chips.items = [{"key": t, "label": "#" + t, "n": n, "on": self.f.get("tag") == t, "sm": True, "flat": True}
                                for t, n in self.d["tags"]]
        state.refocus(self.tag_chips, k)
        self._refilter()

    @handle("more_button", "click")
    def more_button_click(self, **event_args):
        self.offset += 60
        self.more_button.enabled = False
        try:
            r = state.call_quiet("list_faves", self.f, self.offset)
        finally:
            self.more_button.enabled = True
        if r:
            self._grid(r["faves"], r["total"], r["more"], True)

    def _loved(self, fave=None, **event_args):
        pass  # the card already shows it

    # ---- actions
    @handle("quick_box", "pressed_enter")
    def quick_box_pressed_enter(self, **event_args):
        self.quick_button_click()

    @handle("quick_button", "click")
    def quick_button_click(self, **event_args):
        v = (self.quick_box.text or "").strip()
        if not v:
            return
        if LINK.match(v):
            router.go("add", "link", v)
            return
        idea = bool(re.match(r"^idea\s*:", v, re.I))
        text = re.sub(r"^(idea|note)\s*:\s*", "", v, flags=re.I)
        self.quick_button.enabled = False
        try:
            r = state.call("save_fave", {"title": text[:120], "note": text if len(text) > 120 else "", "kind": "idea" if idea else "note"})
        finally:
            self.quick_button.enabled = True
        if r:
            state.toast("Saved to your inbox as " + fb.cat_label(r["fave"]["cat"]), "ok")
            self.quick_box.text = ""
            self._load()

    @handle("samples_button", "click")
    def samples_button_click(self, **event_args):
        r = state.call("load_samples")
        if r:
            state.toast("%d sample faves added. Have a look around!" % r["added"], "ok")
            self._load()

    @handle("redis_archive", "click")
    def redis_archive_click(self, **event_args):
        if state.call("triage", self.d["rediscover"]["id"], "archive"):
            state.toast("Archived", "ok")
            self._load()
