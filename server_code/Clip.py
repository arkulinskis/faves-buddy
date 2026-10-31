"""The Chrome extension's door into Faves Buddy: POST <app>/_/api/clip.

The extension holds a connection code (Tools -> Browser extension): the app's API address + this person's
private clip token. Requests are JSON sent as text/plain (a "simple" cross-origin request, so no CORS
preflight), with the token in the body. Answers carry Access-Control-Allow-Origin: * so the extension can
read them. Rotating the token (Tools) disconnects every browser that had the old code.

Actions: ping | save (one tab, with what the extension read from the page) | save_many (a window's tabs,
as a tab set) | note (selected text) | set_category (re-file what was just saved; keeps it and teaches the sorter)
| tabsets | tabset_urls (to reopen a set).
"""
import base64
import json

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import Store
from . import Taxonomy as T

MAX_TABS = 150


def _reply(data, status=200):
    return anvil.server.HttpResponse(status, json.dumps(data), headers={
        "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})


def _body():
    b = anvil.server.request.body
    if b is None:
        return {}
    if hasattr(b, "get_bytes"):
        b = b.get_bytes()
    if isinstance(b, bytes):
        b = b.decode("utf-8", errors="replace")
    try:
        d = json.loads(b or "{}")
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _user_for(token):
    if not isinstance(token, str) or len(token) < 20:
        return None
    p = app_tables.prefs.get(clip_token=token)
    if p is None or p["owner"] is None or p["owner"]["enabled"] is False:
        return None
    return p["owner"]


def _short(row):
    c = T.BY_ID.get(row["category"] or "other", T.BY_ID["other"])
    return {"id": row.get_id(), "title": row["title"], "cat": c["id"], "cat_name": c["name"], "emoji": c["emoji"],
            "conf": row["confidence"] or 0, "reasons": (row["reasons"] or [])[:3], "status": row["status"]}


@anvil.server.http_endpoint("/clip", methods=["POST"])
def clip(**kw):
    d = _body()
    me = _user_for(d.get("token") or (anvil.server.request.headers.get("authorization") or "").replace("Bearer ", ""))
    if me is None:
        return _reply({"ok": False, "error": "This browser isn't connected any more. Paste a fresh code from Faves Buddy → Tools."}, 401)
    action = d.get("action")
    try:
        return _reply(_do(me, action, d))
    except Exception as e:
        print("clip %s failed: %r" % (action, e))
        return _reply({"ok": False, "error": "Something went wrong saving that. Try again."}, 500)


def _do(me, action, d):
    if action == "ping":
        lists = [{"id": l.get_id(), "name": l["name"], "emoji": l["emoji"] or "⭐"}
                 for l in app_tables.lists.search(tables.order_by("updated", ascending=False), owner=me)]
        for m in app_tables.members.search(user=me, role="editor"):
            if m["list"] is not None:
                lists.append({"id": m["list"].get_id(), "name": m["list"]["name"], "emoji": m["list"]["emoji"] or "⭐"})
        return {"ok": True, "name": C.name_of(me), "lists": lists[:60],
                "cats": [{"id": c["id"], "name": c["name"], "emoji": c["emoji"]} for c in T.CATEGORIES]}
    if action == "save":
        it = d.get("item") or {}
        if not (it.get("url") or it.get("title")):
            return {"ok": False, "error": "Nothing to save on this page."}
        meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        f = {"url": it.get("url"), "title": it.get("title"), "note": it.get("note"), "list_id": it.get("list_id"),
             "category": it.get("category") if it.get("category") in T.BY_ID else None, "meta": meta,
             "lat": meta.get("lat"), "lng": meta.get("lng"), "address": meta.get("address"),
             "enriched": bool(meta.get("description") or meta.get("schema") or meta.get("og_type")),
             "kind": "photo" if it.get("kind") == "image" else None, "event_at": meta.get("startDate")}
        if it.get("kind") == "image":
            f["meta"] = dict(meta, image=it.get("url"))
            f["url"] = it.get("page_url") or it.get("url")
        row, created = Store.create(me, f, source="extension", enrich_now=not f["enriched"])
        return {"ok": True, "created": created, "fave": _short(row)}
    if action == "note":
        text = C.text(d.get("text"), 4000, multiline=True)
        if not text:
            return {"ok": False, "error": "Select some text first."}
        first = text.split("\n")[0][:120]
        row, created = Store.create(me, {"title": first, "note": text, "kind": "note",
                                         "meta": {"selection": C.text(d.get("page_title"), 200)},
                                         "url": None}, source="extension")
        if d.get("page_url"):
            row["note"] = (text + "\n\nFrom: " + C.text(d.get("page_url"), 600))[:4000]
            Store.sort_row(row)
        return {"ok": True, "created": created, "fave": _short(row)}
    if action == "save_many":
        items = [i for i in (d.get("items") or []) if isinstance(i, dict) and i.get("url")][:MAX_TABS]
        if not items:
            return {"ok": False, "error": "No tabs to save."}
        name = C.text(d.get("group"), 80) or "Tabs from %s" % C.now().strftime("%b %d")
        ts = app_tables.tabsets.add_row(owner=me, name=name, count=0, created=C.now(), is_demo=False)
        model = Store.model_of(me)
        added = again = 0
        for i in items:
            row, created = Store.create(me, {"url": i.get("url"), "title": i.get("title"),
                                             "meta": {"favicon": i.get("favicon")} if i.get("favicon") else {}},
                                        source="extension", tabset=ts, model=model)
            if not created and row["tabset"] is None:
                row["tabset"] = ts
            added += created
            again += not created
        ts["count"] = len(app_tables.faves.search(tabset=ts))
        if not ts["count"]:
            ts.delete()
            return {"ok": True, "added": 0, "again": again}
        return {"ok": True, "added": added, "again": again, "tabset": ts.get_id(), "name": name}
    if action == "set_category":
        row = C.row_by_id(app_tables.faves, d.get("id"))
        if row is None or row["owner"] != me:
            return {"ok": False, "error": "That fave isn't there any more."}
        if d.get("category") not in T.BY_ID:
            return {"ok": False, "error": "Unknown category."}
        Store.confirm(row, d["category"])
        row.update(status="kept", updated=C.now())
        return {"ok": True, "fave": _short(row)}
    if action == "tabsets":
        out = [{"id": t.get_id(), "name": t["name"], "count": t["count"] or 0, "created": C.iso(t["created"])}
               for t in app_tables.tabsets.search(tables.order_by("created", ascending=False), owner=me)]
        return {"ok": True, "tabsets": out[:30]}
    if action == "tabset_urls":
        ts = C.row_by_id(app_tables.tabsets, d.get("id"))
        if ts is None or ts["owner"] != me:
            return {"ok": False, "error": "That tab set isn't there any more."}
        return {"ok": True, "urls": [r["url"] for r in app_tables.faves.search(tabset=ts) if r["url"]][:MAX_TABS]}
    return {"ok": False, "error": "Unknown request."}


# ------------------------------------------------------------------------------------------- in the app (Tools)
def _code(token):
    raw = json.dumps({"a": Store.api_origin(), "t": token}, separators=(",", ":"))
    return "FAVES1." + base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


@anvil.server.callable(require_user=True)
def clip_info():
    me = C.require_user()
    p = Store.prefs_for(me)
    if not p["clip_token"]:
        p["clip_token"] = Store.token(32)
    return {"code": _code(p["clip_token"]), "api": Store.api_origin(),
            "saved": len(app_tables.faves.search(owner=me, source="extension"))}


@anvil.server.callable(require_user=True)
def rotate_clip_token():
    me = C.require_user()
    p = Store.prefs_for(me)
    p["clip_token"] = Store.token(32)
    return C.ok(code=_code(p["clip_token"]))
