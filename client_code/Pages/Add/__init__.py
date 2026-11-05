import anvil.js
import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import AddTemplate
from ... import fb, router, state

TABS = ["link", "place", "photo", "note"]


class Add(AddTemplate):
    """#add, #add/link/<url>, #add/place, #add/photo, #add/note: save something by hand.
    Link: preview_link reads the page (title, picture, place, schema) and shows the suggested category with reasons;
          pick another category or lists, add a note, save (kept) or save to the inbox. Maps links become places.
    Place: search by name near you (Photon / OpenStreetMap) or drop a pin where you are.
    Photo: many pictures at once; each is shrunk on the device, saved, its text read on the device (Tesseract, free)
           and sorted (save_photo_ocr). Phone photos with GPS become places. AI description with your own key.
    Note / idea: text, sorted like everything else. Also the target of the bookmarklet (#add/link/<url>)."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.tab = args[0] if args and args[0] in TABS else "link"
        prefill = "/".join(args[1:]) if self.tab == "link" else ""
        self.kind = "note"
        self.preview_data: dict = {}
        self.cat = None
        self.chosen = []
        self.rows = []
        self.busy_photos = False
        self.queue = []
        for name, el, part in (("link", self.tab_link, self.link_part), ("place", self.tab_place, self.place_part),
                               ("photo", self.tab_photo, self.photo_part), ("note", self.tab_note, self.note_part)):
            el.classes["on"] = name == self.tab
            part.visible = name == self.tab
            if name == self.tab:
                state.set_attr(el, "aria-current", "page")
        self.preview.visible = self.preview_wait.visible = False
        self.p_picker.add_event_handler("pick", self._cat_pick)
        for panel in (self.p_lists, self.n_lists):
            panel.add_event_handler("x-chip", self._list_pick)
        for box, label in ((self.url_box, "Link to save"), (self.place_box, "Place to search for"), (self.n_title, "Title"),
                           (self.n_note, "Details"), (self.p_note, "Note")):
            state.set_control_attr(box, "aria-label", label)
        state.set_attr(self.bookmarklet, "href", "javascript:(function(){window.open('%s'+encodeURIComponent(location.href),'_blank');})();"
                       % fb.app_url("#add/link/"))
        self.ocr_box.checked = bool(state.store_get("add.ocr", True))
        has_key = bool(window.FB.ai.has())
        self.ai_box.visible, self.ai_nudge.visible = has_key, not has_key
        self.ai_box.checked = has_key and bool(state.store_get("add.ai", False))
        window.FB.dropZone(self.dom_nodes["drop"], anvil.js.report_exceptions(self._files))
        self.dom_nodes["files"].addEventListener("change", anvil.js.report_exceptions(self._picked))
        self.kind_note.classes["on"] = True
        fb.boot()
        ml = state.call_quiet("my_lists") or {"mine": [], "shared": []}
        self.lists = ml["mine"] + [l for l in ml["shared"] if l.get("role") == "editor"]
        self._draw_lists()
        if prefill:
            self.url_box.text = prefill
            self._preview(prefill)

    # ---- lists (chips that toggle)
    def _draw_lists(self):
        items = [{"key": l["id"], "label": "%s %s" % (l.get("emoji") or "⭐", l["name"]), "sm": True, "on": l["id"] in self.chosen}
                 for l in self.lists if l.get("role") != "viewer"]
        self.p_lists.items = self.n_lists.items = items
        self.p_lists_part.visible = self.n_lists_part.visible = bool(items)

    def _list_pick(self, key, **event_args):
        k = state.focus_key()
        if key in self.chosen:
            self.chosen.remove(key)
        else:
            self.chosen.append(key)
        self._draw_lists()
        state.refocus(self.p_lists if self.tab == "link" else self.n_lists, k)

    def _other_lists(self, fave):
        if len(self.chosen) > 1:
            state.call_quiet("update_fave", fave["id"], {"lists": self.chosen})

    # ---- link
    @handle("url_box", "pressed_enter")
    def url_box_pressed_enter(self, **event_args):
        self.preview_button_click()

    @handle("preview_button", "click")
    def preview_button_click(self, **event_args):
        url = (self.url_box.text or "").strip()
        if url:
            self.preview_button.enabled = False
            try:
                self._preview(url)
            finally:
                self.preview_button.enabled = True

    def _preview(self, url):
        self.preview.visible, self.preview_wait.visible = False, True
        self.chosen = []
        r = state.call("preview_link", url)
        self.preview_wait.visible = False
        if not r:
            return
        p, s = r["page"], r["sort"]
        self.preview_data = {"url": url, "page": p, "sort": s}
        self.cat = s["category"]
        title = p.get("title") or p.get("final_url") or url
        self.p_cover.fave = {"id": url, "title": title, "cat": s["category"], "kind": p.get("kind") or "link", "image": p.get("image"),
                             "desc": p.get("description")}
        self.p_title.text = title
        place = p.get("kind") == "place"
        self.p_icon.classes["ic-pin"], self.p_icon.classes["ic-globe"] = place, not place
        self.dom_nodes["p_sub"].textContent = (p.get("address") or ("Pinned on the map" if p.get("lat") is not None else "Place")) if place else (
            p.get("site_name") or url.split("://", 1)[-1].split("/")[0])
        self.p_desc.text = (p.get("description") or "")[:220]
        self.p_desc.visible = bool(p.get("description"))
        self.p_error.visible = bool(r.get("error"))
        self.p_error.text = "Couldn't read the page itself (%s), so this is sorted from the link alone." % r.get("error") if r.get("error") else ""
        self.already.visible = bool(r.get("already"))
        if r.get("already"):
            state.set_attr(self.already_link, "href", router.href("fave", r["already"]))
        if s["category"] != "other":
            self.p_why.text = "%d%% sure because:" % int(round(s["confidence"] * 100))
            self.p_reasons.items = s.get("reasons") or []
        else:
            self.p_why.text = "Not sure: pick a category"
            self.p_reasons.items = []
        self.p_picker.selected = self.cat or ""
        self.p_note.text = ""
        self._draw_lists()
        self.preview.visible = True

    def _cat_pick(self, cat, **event_args):
        self.cat = cat

    def _save_link(self, to_inbox, button):
        d = self.preview_data
        p = d["page"]
        meta_keys = ("description", "image", "site_name", "og_type", "schema", "lang", "read_min", "startDate", "endDate",
                     "priceRange", "servesCuisine", "recipeYield", "totalTime", "entity")
        f = {"url": d["url"], "title": p.get("title") or "", "note": self.p_note.text or "", "enriched": bool(p.get("title")),
             "meta": {k: p.get(k) for k in meta_keys}, "lat": p.get("lat"), "lng": p.get("lng"), "address": p.get("address"),
             "osm": p.get("osm") or {}, "kind": "place" if p.get("kind") == "place" else None,
             "list_id": self.chosen[0] if self.chosen else None, "event_at": p.get("startDate")}
        if to_inbox:
            f["status"] = "inbox"
        else:
            f["category"] = self.cat
        button.enabled = False
        try:
            r = state.call("save_fave", f)
        finally:
            button.enabled = True
        if r:
            self._other_lists(r["fave"])
            label = fb.cat_label(r["fave"]["cat"])
            state.toast(((("Saved in " if not to_inbox else "In your inbox as ")) if r.get("created") else "Already saved: added to ") + label, "ok")
            router.go("fave", r["fave"]["id"])

    @handle("save_link_button", "click")
    def save_link_button_click(self, **event_args):
        self._save_link(False, self.save_link_button)

    @handle("save_inbox_button", "click")
    def save_inbox_button_click(self, **event_args):
        self._save_link(True, self.save_inbox_button)

    def bookmarklet_click(self, event):
        event.preventDefault()
        state.toast("Drag this button to your bookmarks bar, then click it on any page.")

    # ---- place
    @handle("place_box", "pressed_enter")
    def place_box_pressed_enter(self, **event_args):
        self.place_button_click()

    @handle("place_button", "click")
    def place_button_click(self, **event_args):
        q = (self.place_box.text or "").strip()
        if not q:
            return
        g = fb.geo(False)
        self.place_button.enabled = False
        try:
            res = fb.from_js(window.FB.data.photon(q, fb.to_js({"lat": g["lat"], "lng": g["lng"]}) if g else None, 8))
        except Exception:
            state.toast("Place search is unavailable right now.", "error")
            return
        finally:
            self.place_button.enabled = True
        for p in res:
            p["km"] = fb.dist(g, p) if g else None
        self.places.items = res
        self.place_none.visible = not res

    @handle("here_button", "click")
    def here_button_click(self, **event_args):
        self.here_button.enabled = False
        try:
            g = fb.geo(True)
        finally:
            self.here_button.enabled = True
        if not g or g.get("home"):
            state.toast("Location isn't available here. Search for the place instead.", "error")
            return
        r = state.call("save_fave", {"title": "", "lat": g["lat"], "lng": g["lng"], "kind": "place"})
        if r:
            state.toast("Pinned: " + r["fave"]["title"], "ok")
            router.go("fave", r["fave"]["id"])

    # ---- pictures
    @handle("ocr_box", "change")
    def ocr_box_change(self, **event_args):
        state.store_set("add.ocr", bool(self.ocr_box.checked))

    @handle("ai_box", "change")
    def ai_box_change(self, **event_args):
        state.store_set("add.ai", bool(self.ai_box.checked))

    def _picked(self, event):
        self._files(event.target.files)
        event.target.value = ""

    def _files(self, files):
        imgs = window.FB.imagesOf(files)
        for i in range(imgs.length):
            f = imgs[i]
            row = {"key": "p%d%d" % (window.Date.now(), i), "name": f.name, "status": "Waiting its turn…", "pct": 0, "file": f}
            self.rows.insert(0, row)
            self.queue.append(row)
        self.photos.items = self.rows
        if not self.busy_photos:
            self._work()

    def _show(self, row, **changes):
        row.update(changes)
        form = row.get("_form")
        if form is not None:
            form.draw()

    def _work(self):
        self.busy_photos = True
        try:
            while self.queue:
                row = self.queue.pop(0)
                try:
                    self._one(row)
                except Exception as e:
                    self._show(row, status=str(getattr(e, "message", None) or e) or "That didn't work.", pct=None)
        finally:
            self.busy_photos = False

    def _progress(self, row, lo, span):
        def step(status, p):
            self._show(row, pct=lo + (p or 0) * span,
                       status="Reading the text…" if status == "recognizing text" else "Getting the reader ready…")
        return anvil.js.report_exceptions(step)

    def _one(self, row):
        file = row.pop("file")
        name = file.name
        title = " ".join(name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").split()) or "Picture"
        self._show(row, status="Shrinking…", pct=5)
        shot = window.FB.media.shrink(file, 1600)
        ex = fb.from_js(window.FB.media.exif(file))
        self._show(row, img=shot.dataUrl, status="Saving…", pct=15)
        f = {"title": title, "kind": "photo", "photo": shot.dataUrl, "source": "app"}
        if ex and ex.get("lat") is not None:
            f["lat"], f["lng"] = ex["lat"], ex["lng"]
        r = anvil.server.call_s("save_fave", f)
        if not r.get("ok"):
            raise Exception(r.get("error") or "Couldn't save that one.")
        fave = r["fave"]
        if ex:
            fave = anvil.server.call_s("save_photo_ocr", fave["id"], None, None, None, ex)["fave"]
        if self.ocr_box.checked:
            self._show(row, status="Reading the text…", pct=20)
            text = window.FB.media.ocr(shot.dataUrl, self._progress(row, 20, 60))
            fave = anvil.server.call_s("save_photo_ocr", fave["id"], text, fb.from_js(window.FB.media.extract(text)))["fave"]
        if self.ai_box.visible and self.ai_box.checked:
            self._show(row, status="Asking the AI…", pct=85)
            try:
                a = fb.from_js(window.FB.ai.analyseImage(shot.dataUrl, (fave.get("meta") or {}).get("ocr") or ""))
                fave = anvil.server.call_s("save_photo_ocr", fave["id"], None, None, a)["fave"]
            except Exception as e:
                state.toast(str(getattr(e, "message", None) or e), "error")
        from ...Components.Found import count
        found = count((fave.get("meta") or {}).get("found"))
        status = "In your inbox as " + fb.cat_label(fave["cat"])
        if found:
            status += " · found " + state.plural(found, "useful bit")
        if fave.get("lat") is not None:
            status += " · 📍 on the map"
        self._show(row, fave=fave, status=status, why=" · ".join((fave.get("reasons") or [])[:2]), pct=100)

    # ---- note
    def kind_click(self, event):
        self.kind = event.currentTarget.getAttribute("data-kind")
        self.kind_note.classes["on"] = self.kind == "note"
        self.kind_idea.classes["on"] = self.kind == "idea"

    @handle("note_button", "click")
    def note_button_click(self, **event_args):
        title = (self.n_title.text or "").strip()
        if not title:
            state.toast("Give it a title.", "error")
            return
        self.note_button.enabled = False
        try:
            r = state.call("save_fave", {"title": title, "note": self.n_note.text or "", "kind": self.kind,
                                         "list_id": self.chosen[0] if self.chosen else None})
        finally:
            self.note_button.enabled = True
        if r:
            self._other_lists(r["fave"])
            state.toast("Saved to your inbox as " + fb.cat_label(r["fave"]["cat"]), "ok")
            router.go("fave", r["fave"]["id"])
