import json

import anvil.js
import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import ToolsTemplate
from ... import fb, router, state

SECS = ["extension", "phone", "import", "export", "ai", "events", "home", "learned", "samples"]
TM_KEY = "favesbuddy.tm"


class Tools(ToolsTemplate):
    """#tools/<section>: the extension (download + connection code), on your phone, import (bookmarks HTML, OneTab,
    Pocket CSV, Google Takeout, a Faves Buddy export, any list of links: parsed in the browser), export (JSON, CSV,
    GeoJSON, bookmarks HTML), AI key (Anthropic, browser only) + the AI-sorting opt-in, events key (Ticketmaster,
    browser only), home spot + Top faves privacy, what the sorter learned, sample faves.
    Server: clip_info, rotate_clip_token, import_items, export_all, set_prefs, learned, forget_learned, load/remove_samples."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.sec = args[0] if args and args[0] in SECS else "extension"
        self.pending = []
        self.home_found = []
        for s in SECS:
            getattr(self, "s_" + s).visible = s == self.sec
            nav = getattr(self, "n_" + s)
            nav.classes["on"] = s == self.sec
            if s == self.sec:
                state.set_attr(nav, "aria-current", "page")
        for box, label in ((self.paste_box, "Links to import"), (self.group_box, "Group name"), (self.ai_key_box, "Anthropic API key"),
                           (self.tm_box, "Ticketmaster consumer key"), (self.home_box, "Search for your home spot")):
            state.set_control_attr(box, "aria-label", label)
        state.set_control_attr(self.ai_key_box, "autocomplete", "off")
        state.set_control_attr(self.tm_box, "autocomplete", "off")
        self.domains.add_event_handler("x-forget", self._forget)
        self.words.add_event_handler("x-forget", self._forget)
        self.home_results.add_event_handler("x-chip", self._home_pick)
        fb.boot()
        getattr(self, "_draw_" + self.sec)()

    # ---- extension + phone
    def _draw_extension(self):
        d = state.call("clip_info") or {}
        self.code.text = d.get("code") or ""
        self.ext_saved.text = state.plural(d.get("saved") or 0, "fave") + " saved from the extension so far"

    @handle("copy_code_button", "click")
    def copy_code_button_click(self, **event_args):
        fb.copy(self.code.text, "Code copied. Paste it in the extension.")

    @handle("rotate_button", "click")
    def rotate_button_click(self, **event_args):
        if confirm("Browsers using the old code will be disconnected until you paste the new one.", title="Make a new code?",
                   buttons=[("Cancel", False), ("New code", True)], role="app-dialog"):
            r = state.call("rotate_clip_token")
            if r:
                self.code.text = r["code"]
                state.toast("New code made", "ok")

    def _draw_phone(self):
        pass

    @handle("copy_link_button", "click")
    def copy_link_button_click(self, **event_args):
        fb.copy(window.location.origin + "/", "Address copied. Open it on your phone.")

    # ---- import
    def _draw_import(self):
        self.import_preview.visible = False
        window.FB.dropZone(self.dom_nodes["drop"], anvil.js.report_exceptions(self._dropped))
        self.dom_nodes["file"].addEventListener("change", anvil.js.report_exceptions(self._file_picked))

    def _dropped(self, files):
        self._read(files[0])

    def _file_picked(self, event):
        f = event.target.files
        if f and f.length:
            self._read(f[0])
        event.target.value = ""

    def _read(self, file):
        try:
            text = window.FB.readText(file)
        except Exception as e:
            state.toast(str(getattr(e, "message", None) or e), "error")
            return
        self._show_import(json.loads(window.FB.detectImport(file.name, text)), file.name)

    @handle("parse_button", "click")
    def parse_button_click(self, **event_args):
        self._show_import(json.loads(window.FB.detectImport("pasted.txt", self.paste_box.text or "")), "Pasted links")

    def _show_import(self, det, name):
        items = det["items"]
        self.pending = items
        self.import_none.visible = not items
        self.import_preview.visible = bool(items)
        if not items:
            return
        places = len([i for i in items if i.get("lat") is not None])
        self.import_note.text = "%s: %s found%s." % (det["kind"], state.plural(len(items), "item"),
                                                     (" (%d with a map location)" % places) if places else "")
        sample = ["• " + (i.get("title") or i.get("url") or "") for i in items[:5]]
        self.import_sample.text = "\n".join(sample + (["…"] if len(items) > 5 else []))
        base = name.rsplit(".", 1)[0] if "." in name else name
        self.group_box.text = base or det["kind"]
        self.import_button.text = "Import %d" % len(items)
        self.import_button.enabled = True

    @handle("import_button", "click")
    def import_button_click(self, **event_args):
        items, total = list(self.pending), len(self.pending)
        group = (self.group_box.text or "").strip() or None
        added = again = 0
        first = True
        self.import_button.enabled = False
        try:
            while items:
                chunk, items = items[:300], items[300:]
                self.import_button.text = "Importing… %d%%" % int(round((total - len(items)) * 100.0 / total))
                r = anvil.server.call_s("import_items", chunk, "import", group if first else ((group + " (cont.)") if group else None))
                first = False
                added += r["added"]
                again += r["again"]
        except Exception as e:
            self.import_button.enabled = True
            self.import_button.text = "Try again"
            state.toast(str(e), "error")
            return
        state.toast("%s imported%s. They're in your inbox." % (state.plural(added, "new fave"), (", %d already saved" % again) if again else ""), "ok")
        self.pending = []
        router.go("inbox")

    # ---- export
    def _draw_export(self):
        pass

    def _export(self, kind, button):
        button.enabled = False
        try:
            d = state.call("export_all")
        finally:
            button.enabled = True
        if d:
            window.FB.exportAs(kind, json.dumps(d))
            state.toast("Downloaded", "ok")

    @handle("exp_json", "click")
    def exp_json_click(self, **event_args):
        self._export("json", self.exp_json)

    @handle("exp_csv", "click")
    def exp_csv_click(self, **event_args):
        self._export("csv", self.exp_csv)

    @handle("exp_geojson", "click")
    def exp_geojson_click(self, **event_args):
        self._export("geojson", self.exp_geojson)

    @handle("exp_html", "click")
    def exp_html_click(self, **event_args):
        self._export("html", self.exp_html)

    # ---- AI
    def _draw_ai(self):
        s = fb.ai_sort()
        self.aisort_box.visible, self.aisort_soon.visible = bool(s.get("available")), not s.get("available")
        self.aisort_box.checked = bool(s.get("on"))
        a = fb.from_js(window.FB.ai.get()) or {}
        self.ai_key_box.text = a.get("key") or ""
        self.ai_model_box.items = [("%s: %s" % (m[1], m[2]), m[0]) for m in fb.from_js(window.FB.ai.MODELS)]
        state.set_control_attr(self.ai_model_box, "aria-label", "Model")
        self.ai_model_box.selected_value = window.FB.ai.model()
        self.ai_clear_button.visible = bool(a.get("key"))

    def _ai_set(self):
        window.FB.ai.set(fb.to_js({"key": (self.ai_key_box.text or "").strip(), "model": self.ai_model_box.selected_value}))

    @handle("aisort_box", "change")
    def aisort_box_change(self, **event_args):
        on = bool(self.aisort_box.checked)
        if state.call("set_prefs", None, {"ai_sort": on}):
            fb.ai_sort()["on"] = on
            state.toast("AI second opinion on. Your inbox will show its suggestions." if on else "AI second opinion off.", "ok")

    @handle("ai_save_button", "click")
    def ai_save_button_click(self, **event_args):
        self._ai_set()
        state.toast("Saved in this browser" if (self.ai_key_box.text or "").strip() else "Key removed", "ok")
        self._draw_ai()

    @handle("ai_test_button", "click")
    def ai_test_button_click(self, **event_args):
        self._ai_set()
        self.ai_test_button.enabled = False
        try:
            r = window.FB.ai.test()
            state.toast("It works: “%s”" % str(r).strip(), "ok")
        except Exception as e:
            state.toast(str(getattr(e, "message", None) or e), "error")
        finally:
            self.ai_test_button.enabled = True

    @handle("ai_clear_button", "click")
    def ai_clear_button_click(self, **event_args):
        window.FB.ai.clear()
        self._draw_ai()
        state.toast("Key removed from this browser", "ok")

    # ---- events key
    def _draw_events(self):
        try:
            k = window.localStorage.getItem(TM_KEY) or ""
        except Exception:
            k = ""
        self.tm_box.text = k
        self.tm_clear_button.visible = bool(k)

    @handle("tm_save_button", "click")
    def tm_save_button_click(self, **event_args):
        try:
            window.localStorage.setItem(TM_KEY, (self.tm_box.text or "").strip())
        except Exception:
            pass
        state.toast("Saved in this browser", "ok")
        self._draw_events()

    @handle("tm_clear_button", "click")
    def tm_clear_button_click(self, **event_args):
        try:
            window.localStorage.removeItem(TM_KEY)
        except Exception:
            pass
        state.toast("Key removed", "ok")
        self._draw_events()

    # ---- home spot + Top faves privacy
    def _draw_home(self):
        h = fb.home()
        self.home_label.text = "%s (%.4f, %.4f)" % (h["label"], h["lat"], h["lng"]) if h else "Not set."
        self.home_clear_button.visible = bool(h)
        settings = (fb.boot() or {}).get("settings") or {}
        self.top_box.checked = settings.get("top_faves") is not False

    def _set_home(self, home, message="Home spot saved"):
        r = state.call("set_prefs", home)
        if r:
            fb.set_home(r.get("home"))
            self._draw_home()
            if message:
                state.toast(message, "ok")

    @handle("home_here_button", "click")
    def home_here_button_click(self, **event_args):
        g = fb.geo(True)
        if not g or g.get("home"):
            state.toast("Location isn't available. Search instead.", "error")
            return
        self._set_home({"lat": g["lat"], "lng": g["lng"], "label": "Home base"})

    @handle("home_clear_button", "click")
    def home_clear_button_click(self, **event_args):
        self._set_home({}, None)

    @handle("home_box", "pressed_enter")
    def home_box_pressed_enter(self, **event_args):
        self.home_search_button_click()

    @handle("home_search_button", "click")
    def home_search_button_click(self, **event_args):
        q = (self.home_box.text or "").strip()
        if not q:
            return
        try:
            res = fb.from_js(window.FB.data.photon(q, None, 6))
        except Exception:
            state.toast("Place search is unavailable right now.", "error")
            return
        self.home_found = res
        self.home_results.items = [{"key": i, "label": p["title"], "n": p.get("address") or "", "icon": "pin"} for i, p in enumerate(res)]
        if not res:
            state.toast("Nothing found.", "error")

    def _home_pick(self, key, **event_args):
        p = self.home_found[key]
        self._set_home({"lat": p["lat"], "lng": p["lng"], "label": p["title"]})

    @handle("top_box", "change")
    def top_box_change(self, **event_args):
        on = bool(self.top_box.checked)
        r = state.call("set_prefs", None, {"top_faves": on})
        if r:
            b = fb.boot()
            b["settings"] = r.get("settings") or {}
            state.toast("Your places count toward Top faves, anonymously." if on else "Your places no longer count toward Top faves.", "ok")

    # ---- learned
    def _draw_learned(self):
        d: dict = state.call("learned") or {}
        d = dict({"lessons": 0, "judged": 0, "right": 0, "domains": [], "words": []}, **d)
        self.lessons.text = str(d["lessons"])
        self.right_part.visible = bool(d.get("judged"))
        if d.get("judged"):
            self.right.text = "%d%%" % int(round(d["right"] * 100.0 / d["judged"]))
            self.right_text.text = "of first guesses you kept as they were (%d of %d)" % (d["right"], d["judged"])
        self.domains.items = [dict(x, _kind="domain") for x in d["domains"]]
        self.words.items = [dict(x, _kind="word") for x in d["words"][:25]]
        self.domains_part.visible = bool(d["domains"])
        self.words_part.visible = bool(d["words"])
        self.learned_none.visible = not d["domains"]
        self.forget_all_button.visible = bool(d["lessons"])

    def _forget(self, kind, key, **event_args):
        if state.call("forget_learned", kind, key) is not None:
            self._draw_learned()

    @handle("forget_all_button", "click")
    def forget_all_button_click(self, **event_args):
        if confirm("Sorting goes back to the built-in rules. Your faves and their categories stay as they are.", title="Forget everything?",
                   buttons=[("Cancel", False), ("Forget", True)], role="app-dialog"):
            if state.call("forget_learned") is not None:
                self._draw_learned()
                state.toast("Forgotten", "ok")

    # ---- samples
    def _draw_samples(self):
        pass

    @handle("samples_load", "click")
    def samples_load_click(self, **event_args):
        r = state.call("load_samples")
        if r:
            state.toast(("%d sample faves added" % r["added"]) if r.get("added") else "Samples are already there", "ok")

    @handle("samples_remove", "click")
    def samples_remove_click(self, **event_args):
        r = state.call("remove_samples")
        if r:
            state.toast(state.plural(r["removed"], "sample") + " removed", "ok")
