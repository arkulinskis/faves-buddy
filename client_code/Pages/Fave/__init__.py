import json

import anvil.js
import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import FaveTemplate
from ... import fb, router, state

SIM_KEYS = ("amenity", "shop", "tourism", "leisure", "craft", "historic")


class Fave(FaveTemplate):
    """#fave/<id>: one fave in full. Picture, title, link, category with the sorter's reasons (changing it teaches the
    sorter), status (want / been / loved) + stars, tags, note, lists, place facts (map, hours, website, phone,
    directions, "more like this nearby"), the event date, and for pictures: read the text on the device (OCR), what was
    found in it, an AI description with your own key. Owners edit and can share a link to it; list members view.
    Server: get_fave, update_fave, triage, delete_fave, resort_fave, opened, save_photo_ocr, set_photo, share_fave."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.id = args[0] if args else ""
        self.F: dict = {}
        self.mine = False
        self.lists = []
        self.similar = []
        self.found_places = []
        self._map_open = False
        state.set_control_attr(self.title_box, "aria-label", "Title")
        state.set_control_attr(self.tag_box, "aria-label", "Add a tag")
        state.set_control_attr(self.tag_box, "maxlength", "30")
        state.set_control_attr(self.note_box, "aria-label", "Note")
        state.set_control_attr(self.locate_box, "aria-label", "Search for the place")
        self.picker.add_event_handler("pick", self._cat_picked)
        self.tags_panel.add_event_handler("x-untag", self._untag)
        self.lists_panel.add_event_handler("x-chip", self._list_chip)
        self.similar_panel.add_event_handler("x-chip", self._save_similar)
        self.locate_panel.add_event_handler("x-chip", self._locate_pick)
        self.dom_nodes["repic"].addEventListener("change", anvil.js.report_exceptions(self._repic))
        self.ocr_progress.visible = False
        self._load()

    def leave(self):
        self.map.destroy()

    # ---- loading + drawing
    def _load(self):
        fb.boot()
        r = anvil.server.call("get_fave", self.id)
        if not r.get("ok"):
            state.toast(r.get("error") or "That fave isn't available.", "error")
            router.go("home")
            return
        self.F, self.mine, self.lists = r["fave"], r["mine"], r.get("lists") or []
        router.set_title(self.F.get("title") or "Fave")
        self._draw()

    def _facts(self):
        F = self.F
        o, md, out = F.get("osm") or {}, F.get("meta") or {}, []
        if F.get("address"):
            out.append({"icon": "pin", "text": F["address"]})
        if o.get("opening_hours"):
            out.append({"icon": "clock", "text": o["opening_hours"], "open": fb.open_state(F)})
        site = o.get("website") or o.get("contact:website")
        if site:
            out.append({"icon": "globe", "text": fb.short_url(site), "href": site, "external": True})
        phone = o.get("phone") or o.get("contact:phone")
        if phone:
            out.append({"icon": "phone", "text": phone, "href": "tel:" + "".join(ch for ch in phone if ch.isdigit() or ch == "+")})
        if o.get("cuisine"):
            out.append({"icon": "tag", "text": "Cuisine: " + o["cuisine"].replace("_", " ").replace(";", ", ")})
        if o.get("wheelchair") == "yes":
            out.append({"icon": "check", "text": "Wheelchair accessible"})
        if F.get("event_at"):
            out.append({"icon": "calendar", "text": "%s · %s" % (fb.when(F["event_at"]), fb.fmt_date(F["event_at"]))})
        if md.get("priceRange"):
            out.append({"icon": "tag", "text": md["priceRange"]})
        if md.get("totalTime"):
            out.append({"icon": "clock", "text": "Total time " + md["totalTime"].replace("PT", "").lower()})
        if F.get("read_min"):
            out.append({"icon": "book", "text": "%d minute read" % F["read_min"]})
        return out

    def _draw(self):
        F, mine = self.F, self.mine
        c = fb.cat(F.get("cat"))
        md = F.get("meta") or {}
        inbox = F.get("status") == "inbox"
        state.set_attr(self.back, "href", "#inbox" if inbox else "#home")
        self.dom_nodes["back_text"].textContent = "Inbox" if inbox else "Your faves"
        self.cover.fave = F
        self.repic_row.visible = mine and F.get("kind") == "photo"
        self.dom_nodes["cat_dot"].style.background = c["color"]
        self.dom_nodes["cat_name"].textContent = "%s %s" % (c["emoji"], c["name"])
        self.status_badge.visible = F.get("status") in ("inbox", "archived")
        self.status_badge.text = "In your inbox" if inbox else "Archived"
        self.status_badge.role = ["badge", "badge-warn"] if inbox else ["badge"]
        self.owner_badge.visible = bool(F.get("owner"))
        self.owner_badge.text = "by " + (F.get("owner") or "")
        lbl = fb.stage_label(F)
        self.stage_badge.visible = bool(lbl)
        self.stage_badge.text = lbl
        self.stage_badge.role = ["badge", "badge-loved" if F.get("stage") == "loved" else "badge-good" if F.get("stage") == "been" else "badge-brand"]
        self.title_box.visible, self.title_label.visible = mine, not mine
        self.title_box.text = F.get("title") or ""
        self.title_label.text = F.get("title") or ""
        state.heading(self.title_box if mine else self.title_label, 1)
        place = F.get("lat") is not None
        self.open_link.visible = bool(F.get("url"))
        if F.get("url"):
            state.set_attr(self.open_link, "href", F["url"])
            self.dom_nodes["open_text"].textContent = "Open " + (F.get("domain") or "link")
        self.dir_link.visible = place
        self.osm_link.visible = place and not F.get("url")
        if place:
            state.set_attr(self.dir_link, "href", fb.directions_url(F))
            state.set_attr(self.osm_link, "href", fb.osm_url(F))
            self.dir_link.classes["primary"] = not F.get("url")
        self.desc.text = F.get("desc") or ""
        self.desc.visible = bool(F.get("desc"))
        facts = self._facts()
        self.facts.items = facts
        self.facts.visible = bool(facts)

        self.owner_part.visible, self.viewer_part.visible = mine, not mine
        if mine:
            st = fb.stages(F)
            for (key, label), btn, node in zip(st, (self.stage_want, self.stage_been, self.stage_loved),
                                               ("stage_want_t", "stage_been_t", "stage_loved_t")):
                self.dom_nodes[node].textContent = label
                btn.classes["on"] = F.get("stage") == key
            for n, b in enumerate((self.star1, self.star2, self.star3, self.star4, self.star5)):
                b.classes["on"] = (F.get("rating") or 0) >= n + 1
            conf = int(round((F.get("conf") or 0) * 100))
            reasons = F.get("reasons") or []
            if F.get("confirmed"):
                self.why_text.text = "You filed it here."
            else:
                self.why_text.text = "Suggested" + (" (%d%% sure)" % conf if F.get("cat") != "other" else "") + (" because:" if reasons else "")
            self.why_panel.items = [] if F.get("confirmed") else reasons
            self.picker.selected = F.get("cat") or ""
            self.resort_button.visible = bool(F.get("confirmed"))
            self.tags_panel.items = F.get("tags") or []
            mine_lists = [l for l in self.lists if l["id"] in (F.get("lists") or [])]
            self.lists_panel.items = [{"key": l["id"], "label": "%s %s" % (l.get("emoji") or "⭐", l["name"]), "sm": True} for l in mine_lists]
            self.lists_button.text = "Change" if mine_lists else "Add to a list"
            self.note_box.text = F.get("note") or ""
            self.keep_part.visible = inbox
            self.keep_button.text = "Keep as " + c["name"]
        else:
            self.viewer_note_part.visible = bool(F.get("note"))
            self.viewer_note.text = F.get("note") or ""

        self.map_part.visible = place
        self.similar_button.visible = mine and place
        self.locate_part.visible = mine and not place and bool(c.get("place"))
        if self.locate_part.visible:
            self.locate_box.placeholder = "Search for the place, e.g. " + (F.get("title") or "")
            if not self.locate_box.text:
                self.locate_box.text = F.get("title") or ""
        self.photo_part.visible = F.get("kind") == "photo" or bool(md.get("ocr"))
        if self.photo_part.visible:
            self._draw_photo()
        self.selection_part.visible = bool(md.get("selection"))
        self.selection_text.text = md.get("selection") or ""
        self.more_part.visible = mine
        archived = F.get("status") == "archived"
        self.archive_button.visible, self.unarchive_button.visible = not archived, archived
        src = fb.SOURCES.get(F.get("source"), F.get("source")) if F.get("source") else ""
        line = "Saved " + state.ago(F.get("created")) + (" from " + src if src else "")
        if (F.get("saves") or 1) > 1:
            line += " · saved %d times" % F["saves"]
        if md.get("fetch_error"):
            line += " · couldn't read the page: " + md["fetch_error"]
        self.meta_line.text = line
        self.tabset_link.visible = bool(F.get("tabset_name"))
        self.dom_nodes["tabset_name"].textContent = "Tab set: " + (F.get("tabset_name") or "")
        if place:
            self._draw_map()

    def _draw_photo(self):
        F, md = self.F, self.F.get("meta") or {}
        self.ocr_part.visible, self.ocr_none.visible = bool(md.get("ocr")), not md.get("ocr")
        self.ocr_text.text = md.get("ocr") or ""
        from ...Components.Found import count
        self.found_part.visible = count(md.get("found")) > 0
        self.found.found = md.get("found") or {}
        self.ai_part.visible = bool(md.get("ai"))
        self.ai_text.text = md.get("ai") or ""
        has_key = bool(window.FB.ai.has())
        self.photo_tools.visible = self.mine and bool(F.get("photo"))
        self.ocr_button.text = "Read the text again" if md.get("ocr") else "Read the text (on this device, free)"
        self.ai_button.visible = has_key
        self.ai_nudge.visible = not has_key

    def _draw_map(self):
        F = self.F
        if not self._map_open:
            self._map_open = True
            self.map.open(center=F, zoom=15, cooperative=True, on_click=self._map_click if self.mine else None)
        self.map.pins([F], "none")
        self.map.jump(F["lat"], F["lng"], 15)

    # ---- saving
    def _save(self, fields, redraw=True):
        r = state.call("update_fave", self.F["id"], fields)
        if r:
            self.F = r["fave"]
            if redraw:
                self._draw()
        return r

    def _map_click(self, lat, lng):
        if confirm("The place's location becomes the spot you clicked.", title="Move the pin here?",
                   buttons=[("Cancel", False), ("Move pin", True)], role="app-dialog"):
            if self._save({"lat": lat, "lng": lng}):
                state.toast("Pin moved", "ok")

    def open_click(self, event):
        state.call_quiet("opened", self.F["id"])

    @handle("title_box", "lost_focus")
    def title_box_lost_focus(self, **event_args):
        t = (self.title_box.text or "").strip()
        if t and t != self.F.get("title"):
            if self._save({"title": t}, False):
                state.toast("Renamed", "ok")
                router.set_title(t)

    @handle("title_box", "pressed_enter")
    def title_box_pressed_enter(self, **event_args):
        self.title_box_lost_focus()

    @handle("note_box", "lost_focus")
    def note_box_lost_focus(self, **event_args):
        n = self.note_box.text or ""
        if n != (self.F.get("note") or ""):
            if self._save({"note": n}, False):
                state.toast("Note saved", "ok")

    def stage_click(self, event):
        v = event.currentTarget.getAttribute("data-stage")
        self._save({"stage": "" if self.F.get("stage") == v else v})

    def star_click(self, event):
        n = int(event.currentTarget.getAttribute("data-star"))
        self._save({"rating": 0 if self.F.get("rating") == n else n})

    def _cat_picked(self, cat, **event_args):
        if self._save({"category": cat}):
            state.toast("Filed under %s. Noted for next time." % fb.cat_label(self.F["cat"]), "ok")

    @handle("resort_button", "click")
    def resort_button_click(self, **event_args):
        r = state.call("resort_fave", self.F["id"])
        if r:
            self.F = r["fave"]
            self._draw()
            state.toast("Sorted again: " + fb.cat(self.F["cat"])["name"], "ok")

    def _untag(self, tag, **event_args):
        self._save({"tags": [t for t in (self.F.get("tags") or []) if t != tag]})

    @handle("tag_box", "pressed_enter")
    def tag_box_pressed_enter(self, **event_args):
        tag = (self.tag_box.text or "").strip().lstrip("#").lower()
        if tag and self._save({"tags": (self.F.get("tags") or []) + [tag]}):
            self.tag_box.text = ""
            self.tag_box.focus()

    def _list_chip(self, key, **event_args):
        router.go("list", key)

    @handle("lists_button", "click")
    def lists_button_click(self, **event_args):
        from ...Dialogs.ListsPicker import ListsPicker
        nf = alert(ListsPicker(fave=self.F, lists=self.lists, current=self.F.get("lists") or []), buttons=[],
                   role="app-dialog", dismissible=True)
        if nf:
            self.F = nf
            self._draw()

    def _triage(self, action, message):
        if state.call("triage", self.F["id"], action) is not None:
            state.toast(message, "ok")
            self._load()

    @handle("keep_button", "click")
    def keep_button_click(self, **event_args):
        self._triage("keep", "Kept")

    @handle("archive_button", "click")
    def archive_button_click(self, **event_args):
        self._triage("archive", "Archived")

    @handle("unarchive_button", "click")
    def unarchive_button_click(self, **event_args):
        self._triage("inbox", "Back in your inbox")

    @handle("snooze_button", "click")
    def snooze_button_click(self, **event_args):
        from ...Dialogs.Snooze import Snooze
        if alert(Snooze(fave_id=self.F["id"]), buttons=[], role="app-dialog", dismissible=True):
            self._load()

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        if confirm("It disappears from your lists too. This can't be undone.", title="Delete this fave?",
                   buttons=[("Cancel", False), ("Delete", True)], role="app-dialog"):
            if state.call("delete_fave", self.F["id"]) is not None:
                state.toast("Deleted", "ok")
                router.go("home")

    @handle("share_button", "click")
    def share_button_click(self, **event_args):
        from ...Dialogs.ShareFave import ShareFave
        alert(ShareFave(fave=self.F), buttons=[], role="app-dialog", dismissible=True)

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        lid = (self.F.get("lists") or [None])[0]
        r = state.call("copy_member_item", lid, self.F["id"])
        if r:
            state.toast("Saved to your inbox" if r.get("created") else "Already in your faves", "ok")

    # ---- picture: replace, read the text, describe
    def _repic(self, event):
        files = event.target.files
        if not files or not files.length:
            return
        shot = window.FB.media.shrink(files[0], 1600)
        r = state.call("set_photo", self.F["id"], shot.dataUrl)
        event.target.value = ""
        if r:
            self.F = r["fave"]
            self._draw()
            state.toast("Picture replaced", "ok")

    def _ocr_step(self, status, p):
        self.ocr_status.text = "Reading the text…" if status == "recognizing text" else "Getting ready…"
        self.dom_nodes["ocr_fill"].style.width = "%d%%" % int(round((p or 0) * 100))

    @handle("ocr_button", "click")
    def ocr_button_click(self, **event_args):
        self.ocr_progress.visible = True
        self.ocr_status.text = "Loading the text reader (first time: about 10 MB)…"
        self.ocr_button.enabled = False
        try:
            text = window.FB.media.ocr(self.F["image"], anvil.js.report_exceptions(self._ocr_step))
            found = fb.from_js(window.FB.media.extract(text))
            r = state.call("save_photo_ocr", self.F["id"], text, found)
        finally:
            self.ocr_button.enabled = True
            self.ocr_progress.visible = False
        if r:
            self.F = r["fave"]
            self._draw()
            state.toast("Text read. Category: " + fb.cat_label(self.F["cat"]), "ok")

    @handle("ai_button", "click")
    def ai_button_click(self, **event_args):
        self.ai_button.enabled = False
        try:
            blob = window.FB.tidy.blobOf(self.F["image"])
            shot = window.FB.media.shrink(blob, 1200)
            md = self.F.get("meta") or {}
            try:
                a = fb.from_js(window.FB.ai.analyseImage(shot.dataUrl, md.get("ocr") or ""))
            except Exception as e:
                state.toast(str(getattr(e, "message", None) or e), "error")
                return
            found = dict(md.get("found") or {})
            places = [p.get("address") or p.get("name") for p in (a.get("places") or []) if p.get("address") or p.get("name")]
            if places:
                found["addresses"] = (found.get("addresses") or []) + places
            if a.get("when"):
                found["dates"] = (found.get("dates") or []) + [a["when"]]
            r = state.call("save_photo_ocr", self.F["id"], md.get("ocr") or a.get("text") or None, found, a)
        finally:
            self.ai_button.enabled = True
        if r:
            self.F = r["fave"]
            self._draw()
            state.toast("Described by AI", "ok")

    # ---- the map: more like this nearby, find the place
    @handle("similar_button", "click")
    def similar_button_click(self, **event_args):
        o = self.F.get("osm") or {}
        key = next((k for k in SIM_KEYS if o.get(k)), None)
        if not key:
            state.toast("We don't know this place's type yet. Try Discover instead.", "error")
            return
        filters = [[key, o[key]]] + ([["cuisine", o["cuisine"].split(";")[0]]] if o.get("cuisine") else [])
        recipe = {"filters": filters, "prefer": [], "cat": self.F["cat"], "label": "Similar places"}
        self.similar_button.enabled = False
        try:
            t = state.call_quiet("taste") or {}
            found = fb.from_js(window.FB.data.findPlaces(fb.to_js(recipe), fb.to_js({"lat": self.F["lat"], "lng": self.F["lng"]}),
                                                          1.5, fb.to_js(t.get("saved") or [])))
        except Exception:
            state.toast("OpenStreetMap search is busy right now. Try again in a minute.", "error")
            return
        finally:
            self.similar_button.enabled = True
        places = (found.get("places") or [])[:12]
        self.similar = places
        self.similar_note.text = "%s with %s within 1.5 km (OpenStreetMap):" % (
            state.plural(len(places), "place"), " + ".join("%s=%s" % (a, b) for a, b in filters))
        self.similar_panel.items = [{"key": i, "label": p["title"], "n": fb.fmt_dist(p.get("km")), "icon": "plus"} for i, p in enumerate(places)]
        self.map.sugs([dict(p, cat=self.F["cat"]) for p in places])
        if places:
            self.map.fit([self.F] + places, 40)

    def _save_similar(self, key, **event_args):
        p = self.similar[key]
        r = state.call("save_fave", {"kind": "place", "source": "suggested", "title": p["title"], "lat": p["lat"], "lng": p["lng"],
                                     "address": p.get("address") or "", "osm": p.get("osm") or {}})
        if r:
            state.toast(("Saved: " if r.get("created") else "Already saved: ") + p["title"], "ok")
            items = list(self.similar_panel.items)
            items[key] = dict(items[key], icon="check", disabled=True)
            self.similar_panel.items = items

    @handle("locate_box", "pressed_enter")
    def locate_box_pressed_enter(self, **event_args):
        self.locate_button_click()

    @handle("locate_button", "click")
    def locate_button_click(self, **event_args):
        q = (self.locate_box.text or "").strip()
        if not q:
            return
        near = fb.geo(False) or fb.DEFAULT_CENTER
        self.locate_button.enabled = False
        try:
            res = fb.from_js(window.FB.data.photonJson(q, fb.to_js({"lat": near["lat"], "lng": near["lng"]}), 6))
        except Exception:
            state.toast("Place search is unavailable right now.", "error")
            return
        finally:
            self.locate_button.enabled = True
        self.found_places = res
        self.locate_none.visible = not res
        self.locate_panel.items = [{"key": i, "label": p["title"], "n": p.get("address") or "", "icon": "pin"} for i, p in enumerate(res)]

    def _locate_pick(self, key, **event_args):
        p = self.found_places[key]
        if self._save({"lat": p["lat"], "lng": p["lng"], "address": p.get("address") or "", "osm": p.get("osm") or {}}):
            state.toast("Pinned on your map", "ok")
