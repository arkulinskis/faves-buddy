"""Admin page callables: overview, users (make admin, disable), demo data, and the sorter's report card.
Admins only. Feedback admin calls live in Feedback.py."""
import datetime as dt

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import Classify
from . import DemoData, Feedback
from . import Fetch
from . import Taxonomy as T


@anvil.server.callable(require_user=True)
def admin_overview():
    C.require_admin()
    faves = [f for f in app_tables.faves.search() if not f["is_demo"] and f["status"] != "drop"]
    week = C.now() - dt.timedelta(days=7)
    return {"users": len([u for u in app_tables.users.search() if not u["is_demo"]]),
            "admins": len(app_tables.users.search(is_admin=True)),
            "feedback_new": Feedback.new_count(),
            "faves": len(faves), "faves_week": len([f for f in faves if f["created"] and f["created"] > week]),
            "from_extension": len([f for f in faves if f["source"] == "extension"]),
            "lists": len([l for l in app_tables.lists.search() if not l["is_demo"]]),
            "shared": len([l for l in app_tables.lists.search(is_public=True) if not l["is_demo"]]),
            "connected": len([p for p in app_tables.prefs.search() if p["owner"] is not None and
                              len(app_tables.faves.search(owner=p["owner"], source="extension")) > 0]),
            "demo": {"state": DemoData.state(), "counts": DemoData.counts()}}


def _user(u):
    return {"id": u.get_id(), "email": u["email"], "name": C.name_of(u), "is_admin": C.is_admin(u),
            "enabled": u["enabled"] is not False, "joined": C.iso(u["signed_up"]), "last_seen": C.iso(u["last_seen"])}


@anvil.server.callable(require_user=True)
def list_users(query=None):
    C.require_admin()
    query = C.text(query, 80).lower()
    rows = [u for u in app_tables.users.search(tables.order_by("signed_up", ascending=False)) if not u["is_demo"]]
    if query:
        rows = [u for u in rows if query in (u["email"] or "").lower() or query in (u["display_name"] or "").lower()]
    return {"users": [_user(u) for u in rows[:200]], "total": len(rows)}


@anvil.server.callable(require_user=True)
def set_admin(user_id, flag):
    me = C.require_admin()
    u = C.row_by_id(app_tables.users, user_id)
    if u is None:
        return C.fail("That account no longer exists.")
    if u == me and not flag:
        return C.fail("You can't remove your own admin rights.")
    u["is_admin"] = bool(flag)
    return C.ok(user=_user(u))


@anvil.server.callable(require_user=True)
def set_enabled(user_id, flag):
    me = C.require_admin()
    u = C.row_by_id(app_tables.users, user_id)
    if u is None:
        return C.fail("That account no longer exists.")
    if u == me:
        return C.fail("You can't disable your own account.")
    u["enabled"] = bool(flag)
    return C.ok(user=_user(u))


@anvil.server.callable(require_user=True)
def demo_load():
    C.require_admin()
    DemoData.load()
    return C.ok(demo={"state": DemoData.state(), "counts": DemoData.counts()})


@anvil.server.callable(require_user=True)
def demo_remove():
    C.require_admin()
    DemoData.remove()
    return C.ok(demo={"state": DemoData.state(), "counts": DemoData.counts()})


# ------------------------------------------------------------------------------------------- the sorter
@anvil.server.callable(require_user=True)
def admin_sorting():
    """How well first-pass sorting does: of the faves people sorted themselves, how often the suggestion was
    already right, per category, plus the most common corrections (what to improve in Taxonomy.py)."""
    C.require_admin()
    judged = [f for f in app_tables.faves.search(confirmed=True) if f["suggested"] and not f["is_demo"] and not f["is_sample"]]
    per, fixes = {}, {}
    for f in judged:
        s, c = f["suggested"], f["category"]
        p = per.setdefault(s, [0, 0])
        p[1] += 1
        if s == c:
            p[0] += 1
        else:
            key = "%s -> %s" % (s, c)
            fixes[key] = fixes.get(key, 0) + 1
    rows = [{"cat": k, "name": T.BY_ID.get(k, {}).get("name", k), "right": v[0], "total": v[1]} for k, v in per.items()]
    rows.sort(key=lambda r: -r["total"])
    return {"total": len(judged), "right": sum(r["right"] for r in rows), "per": rows,
            "fixes": sorted(fixes.items(), key=lambda kv: -kv[1])[:15], "categories": len(T.CATEGORIES)}


@anvil.server.callable(require_user=True)
def admin_classify(text, fetch=False):
    """Try the sorter: a link (optionally read live) or any text. Shows every category's score and why."""
    C.require_admin()
    text = C.text(text, 2000, multiline=True)
    if not text:
        return C.fail("Paste a link or some text.")
    info = {"kind": "note", "title": text}
    page = None
    if text.lower().startswith(("http://", "https://")):
        info = {"kind": "link", "url": text, "title": ""}
        if fetch:
            try:
                page = Fetch.read_page(text)
            except Exception as e:
                page = {"error": str(e)}
            info.update({"title": page.get("title") or "", "text": page.get("description"), "schema": page.get("schema"),
                         "og_type": page.get("og_type"), "site_name": page.get("site_name"), "kind": page.get("kind") or "link"})
    res = Classify.classify(info)
    return C.ok(result=res, page=page)
