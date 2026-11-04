from anvil import *

from ._anvil_designer import AdminTemplate
from ... import state

TABS = ["overview", "feedback", "users", "sorting", "ai", "demo"]


class Admin(AdminTemplate):
    """#admin/<tab>: overview numbers, the old feedback inbox, users (admin / active switches), Sorting (how often the
    first guess was kept, the most common corrections, a tester), AI sorting (in progress: the app's own key in App
    Secrets, the switch, model, threshold, a test run) and the demo data. Each tab is its own address."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        self.tab = args[0] if args and args[0] in TABS else "overview"
        self._filter = "new"
        for name in TABS:
            getattr(self, name + "_part").visible = name == self.tab
            tab = getattr(self, "tab_" + name)
            tab.classes["on"] = name == self.tab
            if name == self.tab:
                state.set_attr(tab, "aria-current", "page")
        self.feedback_panel.add_event_handler("x-changed", self._feedback_changed)
        state.set_control_attr(self.search_box, "aria-label", "Search people")
        state.set_control_attr(self.try_box, "aria-label", "Something to sort")
        getattr(self, "_" + self.tab)()

    # ---- overview
    def _overview(self):
        d = state.call("admin_overview")
        if not d:
            return
        self.s_users.text, self.s_admins.text = str(d["users"]), str(d["admins"])
        self.s_admins_label.text = "admin" if d["admins"] == 1 else "admins"
        self.s_feedback.text = str(d["feedback_new"])
        self.s_faves.text = str(d.get("faves", 0))
        self.s_faves_label.text = "faves saved (%d this week)" % d.get("faves_week", 0)
        self.s_ext.text = str(d.get("from_extension", 0))
        self.s_connected.text = str(d.get("connected", 0))
        self.s_lists.text = str(d.get("lists", 0))
        self.s_lists_label.text = "lists (%d public)" % d.get("shared", 0)
        self.demo_line.text = "Demo data is %s (%d demo people). Manage it in the Demo data tab." % (
            d["demo"]["state"], d["demo"]["counts"].get("users", 0))

    # ---- feedback
    def _feedback(self):
        d = state.call("list_feedback", None)
        if not d:
            return
        items = [i for i in d["items"] if self._filter == "all" or i["status"] == self._filter]
        self.feedback_panel.items = items
        self.no_feedback.visible = not items
        labels = {"new": "New", "read": "Read", "done": "Done", "all": "All"}
        for key, el in (("new", self.f_new), ("read", self.f_read), ("done", self.f_done), ("all", self.f_all)):
            n = len(d["items"]) if key == "all" else d["counts"].get(key, 0)
            el.text = "%s (%d)" % (labels[key], n)
            el.role = ["seg", "on"] if key == self._filter else ["seg"]

    def _set_filter(self, value):
        self._filter = value
        self._feedback()

    @handle("f_new", "click")
    def f_new_click(self, **event_args):
        self._set_filter("new")

    @handle("f_read", "click")
    def f_read_click(self, **event_args):
        self._set_filter("read")

    @handle("f_done", "click")
    def f_done_click(self, **event_args):
        self._set_filter("done")

    @handle("f_all", "click")
    def f_all_click(self, **event_args):
        self._set_filter("all")

    def _feedback_changed(self, **event_args):
        self._feedback()

    # ---- users
    def _users(self, query=None):
        d = state.call("list_users", query or None)
        if d:
            self.users_panel.items = d["users"]
            self.users_count.text = state.plural(d["total"], "person", "people")

    @handle("search_box", "pressed_enter")
    def search_box_pressed_enter(self, **event_args):
        self._users(self.search_box.text)

    @handle("search_button", "click")
    def search_button_click(self, **event_args):
        self._users(self.search_box.text)

    # ---- sorting
    def _sorting(self):
        d = state.call("admin_sorting")
        if not d:
            return
        total = d.get("total") or 0
        self.so_pct.text = ("%d%%" % int(round(d["right"] * 100.0 / total))) if total else "–"
        self.so_pct_label.text = "first guesses people kept (%d of %d)" % (d.get("right") or 0, total)
        self.so_cats.text = str(d.get("categories") or 0)
        per = d.get("per") or []
        self.per_panel.items = [{"a": r["name"], "b": "%d / %d" % (r["right"], r["total"]),
                                 "c": "%d%%" % int(round(r["right"] * 100.0 / r["total"])) if r["total"] else ""} for r in per]
        self.per_none.visible = not per
        fixes = d.get("fixes") or []
        self.fix_panel.items = [{"a": f[0], "b": f[1], "c": ""} for f in fixes]
        self.fix_none.visible = not fixes

    @handle("try_button", "click")
    def try_button_click(self, **event_args):
        r = state.call("admin_classify", self.try_box.text or "", bool(self.try_fetch.checked))
        if not r:
            return
        x = r["result"]
        lines = ["%s (%d%% sure)" % (x["category"], int(round(x["confidence"] * 100))),
                 "Why: " + (" · ".join(x.get("reasons") or []) or "nothing matched"),
                 "Scores: " + ", ".join("%s %s" % (k, v) for k, v in (x.get("scores") or {}).items())]
        if x.get("tags"):
            lines.append("Tags: " + ", ".join(x["tags"]))
        if (r.get("page") or {}).get("title"):
            lines.append("Page title: " + r["page"]["title"])
        self.try_out.text = "\n".join(lines)

    # ---- AI sorting
    def _ai(self):
        d = state.call("admin_ai_status")
        if not d:
            return
        c = d["config"]
        self.ai_key_line.text = ("1. Key: found in App Secrets ✓" if d.get("has_key") else
                                 "1. Key: not added yet. In the Anvil editor, open App Secrets and add a secret named %s holding your Anthropic API key." % d.get("secret"))
        self.ai_switch_line.text = "2. Switch: %s · %d people opted in · %d suggestions in inboxes" % (
            "on" if d.get("available") else "off", d.get("opted_in") or 0, d.get("suggestions_waiting") or 0)
        self.ai_enabled.checked = bool(c.get("enabled"))
        self.ai_enabled.enabled = bool(d.get("has_key"))
        self.ai_model.items = [("%s: %s" % (m[1], m[2]), m[0]) for m in d.get("models") or []]
        state.set_control_attr(self.ai_model, "aria-label", "Model")
        self.ai_model.selected_value = c.get("model")
        self.ai_threshold.text = str(c.get("threshold"))
        self.ai_daily.text = str(c.get("daily"))
        self.ai_test.enabled = bool(d.get("has_key"))

    @handle("ai_save", "click")
    def ai_save_click(self, **event_args):
        if state.call("admin_ai_save", {"enabled": bool(self.ai_enabled.checked), "model": self.ai_model.selected_value,
                                        "threshold": self.ai_threshold.text, "daily": self.ai_daily.text}):
            state.toast("Saved", "ok")
            self._ai()

    @handle("ai_test", "click")
    def ai_test_click(self, **event_args):
        self.ai_test.enabled = False
        try:
            r = state.call("admin_ai_test", self.ai_model.selected_value)
        finally:
            self.ai_test.enabled = True
        if not r:
            return
        u = r.get("usage") or {}
        self.ai_test_line.text = "%s · %d ms%s" % (r.get("model"), r.get("ms") or 0,
                                                    (" · %d tokens in, %d out" % (u["input_tokens"], u.get("output_tokens") or 0)) if u.get("input_tokens") else "")
        self.ai_rows.items = [{"a": x["title"], "b": "%s (%d%%) → %s %s" % (x["rules"], int(round(x["rules_conf"] * 100)), x.get("ai") or "-", x.get("sure") or ""),
                               "c": x.get("why") or ""} for x in r.get("rows") or []]

    # ---- demo data
    def _demo(self):
        d = state.call("admin_overview")
        if not d:
            return
        d = d["demo"]
        counts = ", ".join("%s %s" % (v, k) for k, v in d["counts"].items())
        self.demo_status.text = "Status: %s · %s" % (d["state"], counts)
        self.demo_load_button.text = "Reload demo data" if d["state"] == "loaded" else "Load demo data"

    @handle("demo_load_button", "click")
    def demo_load_button_click(self, **event_args):
        if confirm("Demo people and content are added (any old demo rows are replaced).", title="Load the demo data?",
                   buttons=[("Cancel", False), ("Load", True)], role="app-dialog"):
            if state.call("demo_load"):
                state.toast("Done", "ok")
                self._demo()

    @handle("demo_remove_button", "click")
    def demo_remove_button_click(self, **event_args):
        if confirm("Every demo row is deleted. Real data stays.", title="Remove the demo data?",
                   buttons=[("Cancel", False), ("Remove", True)], role="app-dialog"):
            if state.call("demo_remove"):
                state.toast("Done", "ok")
                self._demo()
