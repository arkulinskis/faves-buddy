import json

import anvil.js
import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import TidyTemplate
from ... import fb, router, state


def _date_label():
    return anvil.js.new(window.Date).toLocaleDateString(fb.to_js([]), fb.to_js({"month": "short", "day": "numeric"}))


class Tidy(TidyTemplate):
    """#tidy (hub), #tidy/tabs, #tidy/shots: clear a pile in a few minutes, made for phones.
    Hub    the two jobs, piles shared in but not finished (drops_waiting), and how to get tabs and screenshots in from
           Android, iPhone and the Chrome extension (with an Install button when the browser offers one).
    Tabs   paste links (rich "Copy links" keeps titles) or arrive from a share -> triage_links sorts them all at once
           without AI. Then one card at a time: Keep (in the suggested or picked category), Later (inbox) or Skip; swipe
           right/left, arrow keys, Undo. triage_detail reads the next pages for pictures and better titles. "List" view
           ticks many at once. The finish screen saves (triage_save), optionally as one tab set. Progress is kept in this
           browser (tidy.tabs), so a pile can be finished later.
    Shots  choose screenshots or, on a computer, a folder (remembered). Ones looked at before are hidden (shots_seen).
           Each is shrunk, read on the device, sorted (shot_sort) and shown for Keep / Later / Skip (shot_save, shots_skip)."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.mode = args[0] if args and args[0] in ("tabs", "shots") else "hub"
        self.alive = True
        self._off_keys = None
        self.st: dict = {}
        self.hub_part.visible = self.mode == "hub"
        self.tabs_part.visible = self.mode == "tabs"
        self.shots_part.visible = self.mode == "shots"
        fb.boot()
        getattr(self, "_start_" + self.mode)()

    def leave(self):
        self.alive = False
        if self._off_keys is not None:
            self._off_keys()

    # ======================================================================== hub
    def _start_hub(self):
        saved = state.store_get("tidy.tabs", None) or {}
        left = len(saved.get("items") or []) - (saved.get("idx") or 0) if saved.get("items") else 0
        self.tabs_job_text.text = ("You have %s left from last time. Pick up where you left off." % state.plural(left, "tab")) if left > 0 else \
            "Share or paste a pile of tabs, then swipe: keep, move or skip."
        p = window.FB.tidy.platform()
        for name, el in (("android", self.h_android), ("ios", self.h_ios), ("desktop", self.h_desktop)):
            if name == p:
                state.set_attr(el, "open", "")
        inst = bool(window.FB.tidy.installed())
        self.installed_note.visible = inst
        self.install_button.visible = not inst and bool(window.FB.tidy.canInstall())
        self.drops.add_event_handler("x-discarded", self._load_drops)
        self._load_drops()

    def _load_drops(self, **event_args):
        r = state.call_quiet("drops_waiting") or {}
        self.drops.items = r.get("drops") or []
        self.waiting_part.visible = bool(r.get("drops"))

    @handle("install_button", "click")
    def install_button_click(self, **event_args):
        if window.FB.tidy.install() == "accepted":
            state.toast("Installed. Faves Buddy is now in your share menu.", "ok")
            self.install_button.visible = False

    # ======================================================================== tabs
    def _start_tabs(self):
        self.st = {}
        self.view = state.store_get("tidy.view", "deck")
        self.fetching = set()
        window.FB.tidy.richPaste(state.control(self.paste_box))
        window.FB.tidy.swipe(self.dom_nodes["card"], anvil.js.report_exceptions(self._decide))
        self.card_picker.add_event_handler("pick", self._card_pick)
        self.done_tally.add_event_handler("x-chip", self._done_chip)
        self._off_keys = window.FB.onKeys(anvil.js.report_exceptions(self._key))
        state.set_control_attr(self.paste_box, "aria-label", "Your tabs, one link per line")
        state.set_control_attr(self.group_name, "aria-label", "Tab set name")
        p = window.FB.tidy.platform()
        self.i_android.visible, self.i_ios.visible, self.i_desktop.visible = p == "android", p == "ios", p == "desktop"
        incoming = fb._cache.get("incoming")
        if incoming and incoming.get("links") and not incoming.get("linksTaken"):
            incoming["linksTaken"] = True
            r = state.call("triage_links", incoming["links"])
            if r:
                self._begin(r["links"], incoming.get("code"), incoming.get("name") or "")
                return
        st = state.store_get("tidy.tabs", None)
        if st and st.get("items"):
            st.setdefault("history", [])
            self.st = st
            self._render()
            if st["idx"] < len(st["items"]):
                state.toast("Picking up where you left off. %s to go." % state.plural(len(st["items"]) - st["idx"], "tab"))
        else:
            self._render()

    def _save(self):
        state.store_set("tidy.tabs", self.st)

    def _clear(self):
        self.st = {}
        state.store_set("tidy.tabs", None)

    def _begin(self, links, drop, name):
        self.st = {"items": [dict(l) for l in links], "idx": 0, "dec": {}, "drop": drop, "name": name, "history": []}
        self._save()
        self._render()

    def _show_parts(self, which):
        for name in ("input", "deck", "list", "finish", "done"):
            getattr(self, name + "_part").visible = name == which
        self.top_part.visible = which in ("deck", "list")

    def _render(self):
        st = self.st
        if not st:
            self._show_parts("input")
            return
        if st["idx"] >= len(st["items"]):
            self._finish()
            return
        self._top()
        if self.view == "list":
            self._list_view()
        else:
            self._deck_view()

    def _decided(self, act):
        return len([1 for it in self.st["items"] if (self.st["dec"].get(it["url"]) or {}).get("act") == act])

    def _cat_of(self, it):
        return (self.st["dec"].get(it["url"]) or {}).get("cat") or it.get("pick") or it.get("cat") or "other"

    def _top(self):
        st, n = self.st, len(self.st["items"])
        self.count_label.text = ("Tab %d of %d" % (min(st["idx"] + 1, n), n)) if self.view == "deck" else "%d tabs" % n
        self.tally_label.text = "· %d kept · %d later · %d skipped" % (self._decided("keep"), self._decided("later"), self._decided("skip"))
        self.view_deck.classes["on"] = self.view == "deck"
        self.view_list.classes["on"] = self.view == "list"
        self.dom_nodes["bar"].style.width = "%d%%" % int(st["idx"] * 100.0 / max(1, n))

    def _sure_left(self):
        st = self.st
        return [it for it in st["items"][st["idx"]:] if it["url"] not in st["dec"] and (it.get("conf") or 0) >= 0.6
                and it.get("cat") != "other" and not it.get("already")]

    def _deck_view(self):
        self._show_parts("deck")
        it = self.st["items"][self.st["idx"]]
        cat = self._cat_of(it)
        sure = self._sure_left()
        self.sure_part.visible = len(sure) > 2
        self.dom_nodes["sure_n"].textContent = str(len(sure))
        self.card_cover.fave = {"id": it["url"], "title": it.get("title"), "cat": cat, "kind": "place" if it.get("kind") == "place" else "link",
                                "image": it.get("image")}
        self.dom_nodes["card_title"].textContent = it.get("title") or it.get("domain") or ""
        self.dom_nodes["card_site"].textContent = it.get("site") or it.get("domain") or ""
        self.card_desc.visible = bool(it.get("desc"))
        self.dom_nodes["card_desc_t"].textContent = it.get("desc") or ""
        self.card_already.visible = bool(it.get("already"))
        self.dom_nodes["card_already_t"].textContent = "Already saved, in " + fb.cat_label(it.get("already_cat")) if it.get("already") else ""
        if it.get("cat") != "other":
            self.dom_nodes["card_why"].textContent = "%s %d%% sure: " % (fb.cat_label(it["cat"]), int(round((it.get("conf") or 0) * 100)))
            self.card_reasons.items = it.get("reasons") or []
        else:
            self.dom_nodes["card_why"].textContent = "Not sure where this goes: pick one."
            self.card_reasons.items = []
        self.card_picker.selected = cat
        c = fb.cat(cat)
        self.keep_button.text = "Keep" if cat == "other" else "Keep in %s %s" % (c["emoji"], c["name"])
        self.undo_button.enabled = bool(self.st["history"])
        state.set_attr(self.card_open, "href", it["url"])
        window.setTimeout(self._prefetch, 50)

    def _card_pick(self, cat, **event_args):
        it = self.st["items"][self.st["idx"]]
        it["pick"] = cat
        self._save()
        self._deck_view()

    def _list_view(self):
        self._show_parts("list")
        rest = self.st["items"][self.st["idx"]:]
        rows = []
        for it in rest:
            d = self.st["dec"].get(it["url"])
            on = (d["act"] != "skip") if d else ((it.get("conf") or 0) >= 0.5 and not it.get("already"))
            rows.append(dict(it, _on=on, _cat=self._cat_of(it)))
        self.list_rows.items = rows

    def view_click(self, event):
        self.view = event.currentTarget.getAttribute("data-view")
        state.store_set("tidy.view", self.view)
        self._render()

    def _decide(self, act, cat=None):
        st = self.st
        if not st or st["idx"] >= len(st["items"]):
            return
        it = st["items"][st["idx"]]
        st["dec"][it["url"]] = {"act": act, "cat": cat or self._cat_of(it)}
        st["history"].append(it["url"])
        st["idx"] += 1
        self._save()
        window.FB.tidy.fling(self.dom_nodes["card"], act)
        self._render()

    @handle("keep_button", "click")
    def keep_button_click(self, **event_args):
        self._decide("keep")

    @handle("later_button", "click")
    def later_button_click(self, **event_args):
        self._decide("later")

    @handle("skip_button", "click")
    def skip_button_click(self, **event_args):
        self._decide("skip")

    @handle("undo_button", "click")
    def undo_button_click(self, **event_args):
        self._undo()

    def _undo(self):
        st = self.st
        if not st or not st["history"]:
            return
        url = st["history"].pop()
        st["dec"].pop(url, None)
        st["idx"] = max(0, next((i for i, it in enumerate(st["items"]) if it["url"] == url), 0))
        self._save()
        self._render()

    def _key(self, key, ctrl):
        if self.mode != "tabs" or not self.st or self.view != "deck" or not self.deck_part.visible:
            return False
        if key == "arrowright":
            self._decide("keep")
        elif key == "arrowleft":
            self._decide("skip")
        elif key == "arrowdown":
            self._decide("later")
        elif (key == "z" and ctrl) or key == "backspace":
            self._undo()
        else:
            return False
        return True

    @handle("sure_button", "click")
    def sure_button_click(self, **event_args):
        st = self.st
        for x in self._sure_left():
            st["dec"][x["url"]] = {"act": "keep", "cat": x["cat"]}
        rest = st["items"][st["idx"]:]
        done = [x for x in rest if x["url"] in st["dec"]]
        open_ = [x for x in rest if x["url"] not in st["dec"]]
        st["items"] = st["items"][:st["idx"]] + done + open_
        st["idx"] += len(done)
        self._save()
        state.toast(state.plural(len(done), "tab") + " kept as sorted.", "ok")
        self._render()

    @handle("finish_now_button", "click")
    def finish_now_button_click(self, **event_args):
        self.st["idx"] = len(self.st["items"])
        self._save()
        self._finish()

    @handle("list_done_button", "click")
    def list_done_button_click(self, **event_args):
        for row in self.list_rows.items:
            self.st["dec"][row["url"]] = {"act": "keep" if row.get("_on") else "skip", "cat": row.get("_cat") or "other"}
        self.st["idx"] = len(self.st["items"])
        self._save()
        self._finish()

    def _prefetch(self):
        st = self.st
        if not self.alive or not st:
            return
        want = [it for it in st["items"][st["idx"]:st["idx"] + 4] if not it.get("detail") and it["url"] not in self.fetching]
        if not want:
            return
        for it in want:
            self.fetching.add(it["url"])
        try:
            r = anvil.server.call_s("triage_detail", [it["url"] for it in want])
        except Exception:
            for it in want:
                it["detail"] = True
            return
        if not self.alive or not self.st:
            return
        cur = self.st["items"][self.st["idx"]] if self.st["idx"] < len(self.st["items"]) else None
        redraw = False
        for p in (r or {}).get("pages") or []:
            it = next((x for x in self.st["items"] if x["url"] == p["url"]), None)
            if it is None:
                continue
            it["detail"] = True
            if p.get("failed"):
                continue
            if p.get("title") and (not it.get("title") or it.get("title") == it.get("domain")):
                it["title"] = p["title"]
            it["image"] = p.get("image") or it.get("image")
            it["desc"] = p.get("desc") or it.get("desc")
            it["site"] = p.get("site") or it.get("site")
            it["meta"] = p.get("meta")
            if p.get("kind") == "place":
                it.update(kind="place", lat=p.get("lat"), lng=p.get("lng"), address=p.get("address"))
            if not it.get("pick") and it["url"] not in self.st["dec"] and (p.get("conf") or 0) >= (it.get("conf") or 0):
                it.update(cat=p.get("cat"), conf=p.get("conf"), reasons=p.get("reasons"))
            if it is cur:
                redraw = True
        self._save()
        if redraw and self.view == "deck" and self.deck_part.visible:
            self._deck_view()

    def _finish(self):
        self._show_parts("finish")
        st = self.st
        keep = [it for it in st["items"] if (st["dec"].get(it["url"]) or {}).get("act") == "keep"]
        later = [it for it in st["items"] if (st["dec"].get(it["url"]) or {}).get("act") == "later"]
        skip = len(st["items"]) - len(keep) - len(later)
        tally = {}
        for it in keep:
            c = st["dec"][it["url"]]["cat"]
            tally[c] = tally.get(c, 0) + 1
        n = len(keep) + len(later)
        self.finish_title.text = "Ready to save" if n else "All skipped"
        self.finish_text.text = "%s to keep, %d for later (inbox), %d skipped." % (state.plural(len(keep), "tab"), len(later), skip)
        self.finish_tally.items = [{"key": k, "label": fb.cat_label(k), "n": v, "sm": True, "on": True} for k, v in tally.items()]
        self.group_part.visible = n > 1
        self.group_box.checked = n >= 5
        self.group_name.text = st.get("name") or "Tidied tabs, " + _date_label()
        self.save_button.text = ("Save %d" % n) if n else "Done"

    @handle("back_button", "click")
    def back_button_click(self, **event_args):
        st = self.st
        i = next((k for k, x in enumerate(st["items"]) if x["url"] not in st["dec"]), len(st["items"]) - 1)
        st["idx"] = max(0, min(i, len(st["items"]) - 1))
        self._save()
        self._render()

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        st = self.st
        items = []
        for it in st["items"]:
            d = st["dec"].get(it["url"])
            if not d or d["act"] == "skip":
                continue
            items.append({"url": it["url"], "title": it.get("title"), "category": d["cat"] if d["act"] == "keep" and d["cat"] != "other" else None,
                          "meta": it.get("meta") or {}, "kind": it.get("kind"), "lat": it.get("lat"), "lng": it.get("lng"), "address": it.get("address")})
        group = (self.group_name.text or "").strip() if (self.group_part.visible and self.group_box.checked) else None
        drop = st.get("drop")
        incoming = fb._cache.get("incoming") or {}
        other = len(incoming.get("photos") or []) if incoming.get("code") == drop and drop else 0
        self.save_button.enabled = False
        try:
            r = state.call("triage_save", items, group, drop)
        finally:
            self.save_button.enabled = True
        if not r:
            return
        self._clear()
        self._show_parts("done")
        self.done_text.text = (state.plural(r["saved"], "new fave") + " saved" if r.get("saved") else "Nothing new saved") + (
            ", %d were already there" % r["again"] if r.get("again") else "") + "."
        self.done_tally.items = [{"key": k, "label": fb.cat_label(k), "n": v, "sm": True} for k, v in (r.get("by_cat") or {}).items()]
        self.sweep_link.visible = bool(other)
        self.dom_nodes["sweep_t"].textContent = "Now sweep the %s you shared" % state.plural(other, "picture")
        self.tabset_link.visible = bool(r.get("tabset"))

    def _done_chip(self, key, **event_args):
        router.go("home", "cat", key)

    @handle("clip_button", "click")
    def clip_button_click(self, **event_args):
        try:
            text = window.FB.tidy.readClipboard()
        except Exception:
            self.paste_box.focus()
            state.toast("Long-press the box and choose Paste.")
            return
        cur = self.paste_box.text or ""
        self.paste_box.text = (cur.rstrip() + "\n" if cur.strip() else "") + str(text)

    @handle("sort_button", "click")
    def sort_button_click(self, **event_args):
        t = self.paste_box.text or ""
        if not t.strip():
            state.toast("Paste some links first.", "error")
            return
        self.sort_button.enabled = False
        try:
            r = state.call("triage_links", None, t)
        finally:
            self.sort_button.enabled = True
        if r:
            if not r["links"]:
                state.toast("No links found there.", "error")
                return
            self._begin(r["links"], None, "")

    # ======================================================================== screenshots
    def _start_shots(self):
        self.list = []
        self.hidden = []
        self.queue = []
        self.busy = False
        self.shot_ocr_box.checked = bool(state.store_get("tidy.ocr", True))
        self.shots.add_event_handler("x-shot", self._shot_act)
        self.dom_nodes["shot_files"].addEventListener("change", anvil.js.report_exceptions(self._shot_picked))
        can_folder = bool(window.FB.tidy.canFolder())
        self.folder_button.visible = can_folder
        self.recheck_button.visible = False
        if can_folder:
            name = window.FB.tidy.folderName()
            self.recheck_button.visible = bool(name)
            self.recheck_button.text = "Check “%s” for new ones" % name
        phone = bool(window.FB.tidy.isPhone())
        self.shot_tip.visible = phone
        self.shot_tip.text = ("Tip: in the picker, open Albums → Screenshots and select a batch." if window.FB.tidy.platform() == "ios" else
                              "Tip: in the picker, open the Screenshots album and select a batch, or share them from Photos to Faves Buddy.")
        r = state.call_quiet("shots_seen", []) or {}
        self._seen_line(r.get("total_seen") or 0)
        self._summary()
        incoming = fb._cache.get("incoming")
        if incoming and incoming.get("photos") and not incoming.get("photosTaken"):
            incoming["photosTaken"] = True
            for p in incoming["photos"]:
                self._enqueue({"name": p.get("name") or "Shared picture", "drop_id": p["id"], "fp": None, "url": p["image"]})
            self._kick()

    def _seen_line(self, n):
        self.seen_part.visible = bool(n)
        self.seen_label.text = "%s looked at before will be skipped." % state.plural(n, "screenshot")

    @handle("shot_ocr_box", "change")
    def shot_ocr_box_change(self, **event_args):
        state.store_set("tidy.ocr", bool(self.shot_ocr_box.checked))

    def _summary(self):
        def n(s):
            return len([1 for x in self.list if x["status"] == s])
        ready, busy = n("ready"), n("queued") + n("reading")
        kept, skipped = n("kept") + n("later"), n("skipped")
        self.summary.visible = bool(self.list or self.hidden)
        bits = [x for x in ("%d ready" % ready if ready else "", "%d reading" % busy if busy else "", "%d kept" % kept if kept else "",
                            "%d skipped" % skipped if skipped else "") if x]
        if self.hidden:
            bits.append("%d seen before, hidden" % len(self.hidden))
        self.summary_text.text = " · ".join(bits)
        self.show_hidden_button.visible = bool(self.hidden)
        self.keep_all_button.visible = ready > 1
        self.keep_all_button.text = "Keep all %d as sorted" % ready

    def _shot_picked(self, event):
        files = window.FB.imagesOf(event.target.files)
        entries = [{"file": files[i], "name": files[i].name, "fp": window.FB.tidy.fpOf(files[i])} for i in range(files.length)]
        event.target.value = ""
        self._add(entries)

    @handle("folder_button", "click")
    def folder_button_click(self, **event_args):
        self._from_folder(True)

    @handle("recheck_button", "click")
    def recheck_button_click(self, **event_args):
        self._from_folder(False)

    def _from_folder(self, pick):
        try:
            files = window.FB.tidy.folderFiles(pick)
        except Exception as e:
            state.toast(str(getattr(e, "message", None) or e) or "Couldn't open that folder.", "error")
            return
        name = window.FB.tidy.folderName()
        self.recheck_button.visible = bool(name)
        self.recheck_button.text = "Check “%s” for new ones" % name
        if files.length:
            state.toast("%s in “%s”. Showing the newest ones you haven't looked at." % (state.plural(files.length, "picture"), name))
        self._add([{"file": files[i], "name": files[i].name, "fp": window.FB.tidy.fpOf(files[i])} for i in range(files.length)])

    def _add(self, entries):
        if not entries:
            return
        fps = [e["fp"] for e in entries if e.get("fp")]
        seen = (state.call_quiet("shots_seen", fps) or {}).get("seen") or [] if fps else []
        for e in entries:
            if e.get("fp") and e["fp"] in seen:
                self.hidden.append(e)
            elif not any(x.get("fp") and x["fp"] == e.get("fp") for x in self.list):
                self._enqueue(e)
        if not self.list and self.hidden:
            state.toast("You looked at all of these before. Tap Show to see them again.")
        elif not self.list:
            state.toast("No pictures in that choice.")
        self._summary()
        self._kick()

    def _enqueue(self, e):
        e["key"] = "k%d" % len(self.list)
        e["status"] = "queued"
        self.list.append(e)
        self.queue.append(e)
        self.shots.items = self.list

    def _show(self, e, **changes):
        e.update(changes)
        f = e.get("_form")
        if f is not None:
            f.draw()

    def _kick(self):
        if self.busy:
            return
        self.busy = True
        try:
            while self.queue and self.alive:
                e = self.queue.pop(0)
                try:
                    self._read(e)
                except Exception as err:
                    self._show(e, status="error", err=str(getattr(err, "message", None) or err) or "That one didn't work.")
                self._summary()
        finally:
            self.busy = False

    def _ocr_step(self, e):
        def step(status, p):
            self._show(e, pct=int((p or 0) * 100), step="Reading the text…" if status == "recognizing text" else "Getting the reader ready (first time only)…")
        return anvil.js.report_exceptions(step)

    def _read(self, e):
        self._show(e, status="reading", step="Getting it ready…", pct=0)
        file = e.pop("file", None)
        if file is None and e.get("url"):
            file = window.FB.tidy.blobOf(e["url"])
        shot = window.FB.media.shrink(file, 1600)
        ex = fb.from_js(window.FB.media.exif(file))
        self._show(e, shot=shot.dataUrl, exif=ex)
        text = ""
        if self.shot_ocr_box.checked:
            text = window.FB.media.ocr(shot.dataUrl, self._ocr_step(e)) or ""
        found = fb.from_js(window.FB.media.extract(text))
        s = anvil.server.call_s("shot_sort", text, e.get("name"), found)
        self._show(e, text=text, found=found, sort=s, title=s.get("title"), pick=None, useUrl=bool(s.get("url")), status="ready")

    def _shot_act(self, key, action, button=None, **event_args):
        e = next((x for x in self.list if x["key"] == key), None)
        if e is None:
            return
        if action == "skip":
            self._show(e, status="skipped")
            self._summary()
            state.call_quiet("shots_skip", [e["fp"]] if e.get("fp") else [], [e["drop_id"]] if e.get("drop_id") else [])
            return
        if button is not None:
            button.enabled = False
        try:
            self._keep(e, action == "later")
        finally:
            if button is not None:
                button.enabled = True

    def _keep(self, e, later):
        cat = e.get("pick") or (e.get("sort") or {}).get("cat") or "other"
        f = {"photo": None if e.get("drop_id") else e.get("shot"), "drop_id": e.get("drop_id"), "title": e.get("title"),
             "category": None if later or cat == "other" else cat, "ocr": e.get("text"), "found": e.get("found"),
             "exif": e.get("exif") or {}, "url": (e.get("sort") or {}).get("url") if e.get("useUrl") else None, "fp": e.get("fp"),
             "source": "share" if e.get("drop_id") else "screenshot"}
        r = state.call_quiet("shot_save", f)
        if not r or not r.get("ok"):
            state.toast((r or {}).get("error") or "Couldn't save that one.", "error")
            return
        self._show(e, fave=r["fave"], saved_before=not r.get("created"), status="later" if (later or cat == "other") else "kept")
        self._summary()

    @handle("keep_all_button", "click")
    def keep_all_button_click(self, **event_args):
        ready = [x for x in self.list if x["status"] == "ready"]
        self.keep_all_button.enabled = False
        try:
            for x in ready:
                self._keep(x, False)
        finally:
            self.keep_all_button.enabled = True
        state.toast(state.plural(len(ready), "screenshot") + " kept.", "ok")

    @handle("show_hidden_button", "click")
    def show_hidden_button_click(self, **event_args):
        h, self.hidden = self.hidden, []
        for e in h:
            self._enqueue(e)
        self._summary()
        self._kick()

    @handle("forget_button", "click")
    def forget_button_click(self, **event_args):
        if state.call("shots_forget") is not None:
            self._seen_line(0)
            state.toast("Next time, every screenshot shows again.", "ok")
