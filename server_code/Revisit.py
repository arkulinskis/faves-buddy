"""Revisit (#revisit): a short, kind review of the things you kept but never opened ("Still want this?"), plus
"On this day" (what you saved a month, months or years ago today).

A fave waits for a revisit when it is kept, was never opened, is at least MIN_AGE_DAYS old and wasn't reviewed in the
last REVIEW_DAYS. "Keep" stamps meta["revisited"] (no new columns), so it isn't asked about again for REVIEW_DAYS.
Open marks it opened (opened_at), Let go archives it, Remind me snoozes it back into the inbox (Faves.triage).
"""
import datetime as dt

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import Store

MIN_AGE_DAYS = 3
REVIEW_DAYS = 60
MAX = 30
MINS = (0, 5, 15, 30)


def _reviewed(r, now):
    t = Store.parse_when((r["meta"] or {}).get("revisited"))
    return t is not None and t > now - dt.timedelta(days=REVIEW_DAYS)


def waiting(r, now):
    return (r["status"] == "kept" and r["opened_at"] is None and r["created"] is not None
            and r["created"] < now - dt.timedelta(days=MIN_AGE_DAYS) and not _reviewed(r, now))


def stats_for(rows, now):
    """For the home page: how many wait for a revisit, and how many kept faves were ever opened."""
    kept = [r for r in rows if r["status"] == "kept"]
    return {"waiting": len([r for r in kept if waiting(r, now)]), "opened": len([r for r in kept if r["opened_at"] is not None]),
            "total": len(kept)}


def _ago_label(created, today):
    """'1 year ago today' / '3 months ago today', or None when the day doesn't line up."""
    d = created.date()
    if d >= today or (d.day != today.day):
        return None
    months = (today.year - d.year) * 12 + (today.month - d.month)
    if months <= 0:
        return None
    if d.month == today.month:
        years = today.year - d.year
        return "%d year%s ago today" % (years, "" if years == 1 else "s")
    return "%d month%s ago today" % (months, "" if months == 1 else "s")


def on_this_day(rows, me, now):
    today = now.date()
    out = []
    for r in rows:
        if r["status"] == "archived" or r["created"] is None or r["is_sample"]:
            continue
        label = _ago_label(r["created"], today)
        if label:
            out.append(dict(Store.fave(r, me, lists=[], slim=True), ago=label))
    return out[:8]


@anvil.server.callable(require_user=True)
def revisit_queue(filters=None):
    """The deck: up to MAX faves waiting for a revisit, filtered by reading time (5/15/30 = reads that fit) and category,
    oldest or newest first. Also the counts per category, the stats line and On this day."""
    me = C.require_user()
    f = filters if isinstance(filters, dict) else {}
    try:
        mins = int(f.get("mins") or 0)
    except (TypeError, ValueError):
        mins = 0
    mins = mins if mins in MINS else 0
    cat = f.get("cat") or None
    order = "new" if f.get("order") == "new" else "old"
    now = C.now()
    rows = list(app_tables.faves.search(tables.order_by("created", ascending=order != "new"), owner=me))
    pool = [r for r in rows if waiting(r, now)]
    cats = {}
    for r in pool:
        cats[r["category"] or "other"] = cats.get(r["category"] or "other", 0) + 1
    picked = []
    for r in pool:
        if cat and (r["category"] or "other") != cat:
            continue
        rm = (r["meta"] or {}).get("read_min") or 0
        if mins and not (rm and rm <= mins):
            continue
        picked.append(r)
    fits = {m: len([r for r in pool if (r["meta"] or {}).get("read_min") and (r["meta"] or {}).get("read_min") <= m]) for m in MINS if m}
    return C.ok(items=[Store.fave(r, me, lists=[], slim=True) for r in picked[:MAX]], left=len(picked),
                cats=cats, fits={str(k): v for k, v in fits.items()}, stats=stats_for(rows, now),
                on_this_day=on_this_day(rows, me, now))


@anvil.server.callable(require_user=True)
def revisit_decide(fave_id, action):
    """open (marks it opened) | keep (still want it: not asked again for 60 days) | archive (let it go) |
    undo (back to how it was before the revisit: kept, unopened, not reviewed). Remind me uses triage(..., "snooze")."""
    me = C.require_user()
    r = C.row_by_id(app_tables.faves, fave_id)
    if r is None or r["owner"] != me:
        return C.fail("That fave isn't yours or no longer exists.")
    now = C.now()
    if action == "open":
        r["opened_at"] = now
    elif action == "keep":
        r["meta"] = dict(r["meta"] or {}, revisited=C.iso(now))
    elif action == "archive":
        r.update(status="archived", remind_at=None, updated=now)
    elif action == "undo":
        m = dict(r["meta"] or {})
        m.pop("revisited", None)
        r.update(status="kept", remind_at=None, opened_at=None, meta=m)
    else:
        return C.fail("Unknown action.")
    return C.ok(fave=Store.fave(r, me, lists=[], slim=True))
