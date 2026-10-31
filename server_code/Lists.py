"""Lists and sharing.

A list belongs to its owner. It can be shared two ways:
  - with people, by email: viewer (sees it) or editor (adds their own faves, removes items, ticks places off).
    An invite to an email without an account waits until someone signs up with that email.
  - by link: anyone with the link sees it read-only (#s/<token>), no sign-in needed. Turning the link off
    makes the old link stop working; turning it on again makes a new one.
Shared viewers never see anyone's email except their own; members are shown by display name.
"""
import re

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import DemoData
from . import Store
from . import Taxonomy as T

EMOJIS = ["⭐", "☕", "🍜", "🍸", "🌳", "🏛️", "🛍️", "🧳", "🎟️", "🧑‍🍳", "📖", "🎬", "🎧", "🎓", "🛠️", "🏡", "💪", "🎁", "💼", "💡",
          "❤️", "🗺️", "🌧️", "🌞", "🎉", "👶", "🐶", "🍕", "🥐", "🍦"]
COLORS = ["#5b5bf0", "#ff6f61", "#26a69a", "#ffb300", "#ec407a", "#42a5f5", "#66bb6a", "#8d6e63", "#7e57c2", "#78909c"]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _get(list_id, need="viewer"):
    me = C.require_user()
    lst = C.row_by_id(app_tables.lists, list_id)
    r = Store.role(me, lst)
    order = {"viewer": 1, "editor": 2, "owner": 3}
    if r is None or order[r] < order[need]:
        return me, None, r
    return me, lst, r


def _list(lst, me=None, role=None, full=False):
    items = list(app_tables.list_items.search(tables.order_by("added", ascending=False), list=lst))
    d = {"id": lst.get_id(), "name": lst["name"], "emoji": lst["emoji"] or "⭐", "color": lst["color"] or COLORS[0],
         "description": lst["description"] or "", "public": bool(lst["is_public"]), "count": len(items),
         "owner": C.name_of(lst["owner"]), "role": role, "updated": C.iso(lst["updated"]), "demo": bool(lst["is_demo"])}
    if role == "owner":
        d["token"] = lst["share_token"] if lst["is_public"] else None
    if full:
        d["items"] = []
        for li in items:
            f = li["fave"]
            if f is None:
                continue
            fd = Store.fave(f, me, lists=[], slim=True)
            fd["added_by"] = C.name_of(li["added_by"]) if li["added_by"] is not None and li["added_by"] != me else None
            fd["can_remove"] = role in ("owner", "editor") or (me is not None and li["added_by"] == me)
            fd["item_id"] = li.get_id()
            d["items"].append(fd)
        d["members"] = [{"id": m.get_id(), "name": C.name_of(m["user"]) if m["user"] is not None else None,
                         "email": m["email"] if role == "owner" or (me is not None and m["user"] == me) else None,
                         "role": m["role"], "joined": m["user"] is not None, "me": me is not None and m["user"] == me}
                        for m in app_tables.members.search(list=lst)]
    else:
        d["preview"] = [(li["fave"]["photo_key"] and Store.photo_url(li["fave"])) or (li["fave"]["meta"] or {}).get("image")
                        for li in items[:12] if li["fave"] is not None]
        d["preview"] = [p for p in d["preview"] if p][:4]
        d["cats"] = list({li["fave"]["category"] for li in items[:40] if li["fave"] is not None})[:6]
        d["members_n"] = len(app_tables.members.search(list=lst))
    return d


@anvil.server.callable(require_user=True)
def my_lists():
    me = C.require_user()
    Store.claim_invites(me)
    mine = [_list(l, me, "owner") for l in app_tables.lists.search(tables.order_by("updated", ascending=False), owner=me)]
    shared = []
    for m in app_tables.members.search(user=me):
        if m["list"] is not None:
            shared.append(_list(m["list"], me, m["role"]))
    return {"mine": mine, "shared": shared, "emojis": EMOJIS, "colors": COLORS}


@anvil.server.callable(require_user=True)
def get_list(list_id):
    me, lst, role = _get(list_id)
    if lst is None:
        return C.fail("That list isn't there any more, or it isn't shared with you.")
    d = _list(lst, me, role, full=True)
    my = []
    if role in ("owner", "editor"):
        inside = set(i["id"] for i in d["items"])
        for r in app_tables.faves.search(tables.order_by("created", ascending=False), owner=me):
            if r["status"] != "archived" and r.get_id() not in inside:
                my.append({"id": r.get_id(), "title": r["title"], "cat": r["category"] or "other", "kind": r["kind"]})
    return C.ok(list=d, addable=my[:300], emojis=EMOJIS, colors=COLORS)


@anvil.server.callable(require_user=True)
def save_list(list_id, fields):
    """Create (list_id None) or edit a list's name, emoji, colour and description."""
    me = C.require_user()
    f = fields or {}
    name = C.text(f.get("name"), 60)
    if not name:
        return C.fail("Give the list a name.")
    emoji = f.get("emoji") if f.get("emoji") in EMOJIS else "⭐"
    color = f.get("color") if f.get("color") in COLORS else COLORS[0]
    desc = C.text(f.get("description"), 400, multiline=True)
    if list_id:
        me, lst, role = _get(list_id, "owner")
        if lst is None:
            return C.fail("Only the list's owner can change it.")
        lst.update(name=name, emoji=emoji, color=color, description=desc or None, updated=C.now())
    else:
        if len(app_tables.lists.search(owner=me)) >= 200:
            return C.fail("That's 200 lists already. Tidy up a few first.")
        lst = app_tables.lists.add_row(owner=me, name=name, emoji=emoji, color=color, description=desc or None, share_token=None,
                                       is_public=False, created=C.now(), updated=C.now(), is_demo=False)
        for fid in (f.get("faves") or [])[:200]:
            fv = C.row_by_id(app_tables.faves, fid)
            if fv is not None and fv["owner"] == me:
                Store._add_to_list(me, fv, lst.get_id())
    return C.ok(list=_list(lst, me, "owner"))


@anvil.server.callable(require_user=True)
def delete_list(list_id):
    me, lst, role = _get(list_id, "owner")
    if lst is None:
        return C.fail("Only the list's owner can delete it.")
    for li in app_tables.list_items.search(list=lst):
        li.delete()
    for m in app_tables.members.search(list=lst):
        m.delete()
    lst.delete()
    return C.ok()


@anvil.server.callable(require_user=True)
def list_add(list_id, fave_ids):
    me, lst, role = _get(list_id, "editor")
    if lst is None:
        return C.fail("You can't add to that list.")
    n = 0
    for fid in (fave_ids or [])[:200]:
        fv = C.row_by_id(app_tables.faves, fid)
        if fv is not None and fv["owner"] == me and app_tables.list_items.get(list=lst, fave=fv) is None:
            Store._add_to_list(me, fv, lst.get_id())
            n += 1
    return C.ok(added=n)


@anvil.server.callable(require_user=True)
def list_remove(list_id, fave_id):
    me = C.require_user()
    lst = C.row_by_id(app_tables.lists, list_id)
    fv = C.row_by_id(app_tables.faves, fave_id)
    role = Store.role(me, lst)
    if lst is None or fv is None or role is None:
        return C.ok()
    li = app_tables.list_items.get(list=lst, fave=fv)
    if li is None:
        return C.ok()
    if role not in ("owner", "editor") and li["added_by"] != me:
        return C.fail("Only editors can remove things from this list.")
    li.delete()
    lst["updated"] = C.now()
    return C.ok()


@anvil.server.callable(require_user=True)
def set_public(list_id, on):
    me, lst, role = _get(list_id, "owner")
    if lst is None:
        return C.fail("Only the list's owner can share it by link.")
    if on:
        lst.update(is_public=True, share_token=lst["share_token"] or Store.token(22))
    else:
        lst.update(is_public=False, share_token=None)
    return C.ok(token=lst["share_token"])


@anvil.server.callable(require_user=True)
def invite(list_id, email, role="viewer"):
    me, lst, r = _get(list_id, "owner")
    if lst is None:
        return C.fail("Only the list's owner can invite people.")
    email = C.text(email, 120).lower()
    if not EMAIL.match(email):
        return C.fail("That email doesn't look right.")
    if email == (me["email"] or "").lower():
        return C.fail("That's you! You already own this list.")
    if role not in ("viewer", "editor"):
        role = "viewer"
    if len(app_tables.members.search(list=lst)) >= 50:
        return C.fail("A list can be shared with up to 50 people.")
    if C.rate_limited("invite", 60, 3600):
        return C.fail("That's a lot of invites this hour. Try again later.")
    m = app_tables.members.get(list=lst, email=email)
    user = app_tables.users.get(email=email)
    if m is None:
        app_tables.members.add_row(list=lst, user=user, email=email, role=role, invited_by=me, created=C.now(), is_demo=False)
    else:
        m.update(role=role)
    return C.ok(list=_list(lst, me, "owner", full=True), has_account=user is not None)


@anvil.server.callable(require_user=True)
def set_member(list_id, member_id, role=None):
    """Owner: change someone's role, or remove them (role None). A member can remove themselves (leave)."""
    me = C.require_user()
    lst = C.row_by_id(app_tables.lists, list_id)
    m = C.row_by_id(app_tables.members, member_id)
    if lst is None or m is None or m["list"] != lst:
        return C.ok()
    if lst["owner"] != me and m["user"] != me:
        return C.fail("Only the list's owner can change who it's shared with.")
    if role in ("viewer", "editor") and lst["owner"] == me:
        m["role"] = role
    else:
        m.delete()
    return C.ok()


# ------------------------------------------------------------------------------------------- public link
@anvil.server.callable
def shared_list(token):
    """A list someone shared by link. Anyone with the link; no emails, no private notes on other people's faves."""
    DemoData.ensure_loaded()
    token = C.text(token, 40)
    lst = app_tables.lists.get(share_token=token, is_public=True) if token else None
    if lst is None:
        return C.fail("This link doesn't work any more. Ask whoever shared it for a new one.")
    me = C.me()
    d = _list(lst, me, Store.role(me, lst), full=True)
    for it in d["items"]:
        it.pop("item_id", None)
        it["can_remove"] = False
    d.pop("members", None)
    d.pop("token", None)
    d["signed_in"] = me is not None
    return C.ok(list=d, cats=T.public())


@anvil.server.callable
def featured_lists():
    """Public demo lists for the landing page ("peek at a shared list")."""
    DemoData.ensure_loaded()
    out = []
    for lst in app_tables.lists.search(is_public=True, is_demo=True):
        d = _list(lst)
        d["token"] = lst["share_token"]
        out.append(d)
    return {"lists": out[:3], "cats": T.public()}


@anvil.server.callable(require_user=True)
def copy_shared(token, fave_id):
    """Save a fave from a shared list into your own collection."""
    me = C.require_user()
    lst = app_tables.lists.get(share_token=C.text(token, 40), is_public=True) if token else None
    fv = C.row_by_id(app_tables.faves, fave_id)
    if lst is None or fv is None or app_tables.list_items.get(list=lst, fave=fv) is None:
        return C.fail("That isn't on this shared list any more.")
    f = {"url": fv["url"], "title": fv["title"], "lat": fv["lat"], "lng": fv["lng"], "address": fv["address"], "osm": fv["osm"],
         "kind": fv["kind"], "tags": fv["tags"], "event_at": C.iso(fv["event_at"]), "enriched": True,
         "meta": {k: v for k, v in (fv["meta"] or {}).items() if k in ("description", "image", "site_name", "og_type", "schema", "read_min")},
         "note": "From %s's list \"%s\"" % (C.name_of(lst["owner"]), lst["name"])}
    row, created = Store.create(me, f, source="shared")
    if created and fv["photo"] is not None:
        row.update(photo=fv["photo"], photo_key=Store.token(28))
    return C.ok(fave=Store.fave(row, me, slim=True), created=created)


@anvil.server.callable(require_user=True)
def copy_member_item(list_id, fave_id):
    """Save someone else's fave from a list shared with you into your own collection."""
    me, lst, role = _get(list_id)
    fv = C.row_by_id(app_tables.faves, fave_id)
    if lst is None or fv is None or app_tables.list_items.get(list=lst, fave=fv) is None:
        return C.fail("That isn't on this list any more.")
    if fv["owner"] == me:
        return C.ok(fave=Store.fave(fv, me, slim=True), created=False)
    f = {"url": fv["url"], "title": fv["title"], "lat": fv["lat"], "lng": fv["lng"], "address": fv["address"], "osm": fv["osm"],
         "kind": fv["kind"], "tags": fv["tags"], "event_at": C.iso(fv["event_at"]), "enriched": True,
         "meta": {k: v for k, v in (fv["meta"] or {}).items() if k in ("description", "image", "site_name", "og_type", "schema", "read_min")},
         "note": "From %s's list \"%s\"" % (C.name_of(lst["owner"]), lst["name"])}
    row, created = Store.create(me, f, source="shared")
    return C.ok(fave=Store.fave(row, me, slim=True), created=created)
