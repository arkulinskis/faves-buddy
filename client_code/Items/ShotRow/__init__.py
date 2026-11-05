from anvil import *

from ._anvil_designer import ShotRowTemplate
from ... import fb, router, state


class ShotRow(ShotRowTemplate):
    """A screenshot in the sweep: waiting / being read / ready (title, suggested category, found bits, Keep / Later /
    Skip) / kept / skipped. item keeps the state; the page calls draw() (the row puts itself in item["_form"]).
    Raises x-shot(key, action) for keep, later, skip."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.item["_form"] = self
        self.picker.add_event_handler("pick", self._picked)
        self.draw()

    def draw(self):
        e = self.item
        s = e.get("status")
        has_img = bool(e.get("shot"))
        self.img.visible, self.ph.visible = has_img, not has_img
        if has_img and self.dom_nodes["img"].src != e["shot"]:
            self.dom_nodes["img"].src = e["shot"]
        done = s in ("kept", "later")
        self.box.classes["done"] = done or s == "skipped"
        self.box.classes["skipped"] = s == "skipped"
        self.busy_part.visible = s in ("queued", "reading", "error")
        self.done_part.visible = done
        self.skipped_part.visible = s == "skipped"
        self.ready_part.visible = s == "ready"
        if self.busy_part.visible:
            self.dom_nodes["busy_name"].textContent = e.get("name") or ""
            self.dom_nodes["busy_st"].textContent = e.get("err") if s == "error" else ("Waiting its turn…" if s == "queued" else e.get("step") or "")
            self.bar.visible = s == "reading"
            self.dom_nodes["fill"].style.width = "%d%%" % int(e.get("pct") or 0)
        elif done:
            f = e["fave"]
            self.dom_nodes["done_a"].textContent = f.get("title") or ""
            state.set_attr(self.done_link, "href", router.href("fave", f["id"]))
            info = ("kept in " + fb.cat_label(f["cat"])) if s == "kept" else "in your inbox"
            if e.get("saved_before"):
                info += " (already saved: added the screenshot)"
            self.dom_nodes["done_info"].textContent = info
        elif s == "skipped":
            self.dom_nodes["skipped_t"].textContent = "Skipped " + (e.get("title") or e.get("name") or "")
        elif s == "ready":
            so = e.get("sort") or {}
            cat = e.get("pick") or so.get("cat") or "other"
            self.title_box.text = e.get("title") or ""
            state.set_control_attr(self.title_box, "aria-label", "Title")
            state.set_control_attr(self.title_box, "maxlength", "200")
            self.dom_nodes["why"].textContent = ("%s %d%% sure: " % (fb.cat_label(so["cat"]), int(round((so.get("conf") or 0) * 100)))) if so.get("cat") not in (None, "other") else ""
            self.reasons.items = so.get("reasons") or []
            self.picker.selected = cat
            self.url_box.visible = bool(so.get("url"))
            self.url_box.text = "Link it to %s (found in it)" % fb.short_url(so.get("url") or "")[:60]
            self.url_box.checked = bool(e.get("useUrl"))
            from ...Components.Found import count
            n = count(e.get("found"))
            self.found_part.visible = n > 0
            self.dom_nodes["found_sum"].textContent = "Found " + state.plural(n, "useful bit")
            self.found.found = e.get("found") or {}
            self.ocr.text = (e.get("text") or "")[:400]
            self.ocr.visible = bool(e.get("text"))
            self.keep_button.text = "Keep" if cat == "other" else "Keep in " + fb.cat_label(cat)

    def _picked(self, cat, **event_args):
        self.item["pick"] = cat
        self.item["title"] = self.title_box.text or self.item.get("title")
        self.keep_button.text = "Keep" if cat == "other" else "Keep in " + fb.cat_label(cat)

    @handle("title_box", "change")
    def title_box_change(self, **event_args):
        self.item["title"] = self.title_box.text

    @handle("url_box", "change")
    def url_box_change(self, **event_args):
        self.item["useUrl"] = bool(self.url_box.checked)

    def _act(self, action, button):
        self.item["title"] = (self.title_box.text or "").strip() or self.item.get("title")
        self.parent.raise_event("x-shot", key=self.item["key"], action=action, button=button)

    @handle("keep_button", "click")
    def keep_button_click(self, **event_args):
        self._act("keep", self.keep_button)

    @handle("later_button", "click")
    def later_button_click(self, **event_args):
        self._act("later", self.later_button)

    @handle("skip_button", "click")
    def skip_button_click(self, **event_args):
        self._act("skip", self.skip_button)
