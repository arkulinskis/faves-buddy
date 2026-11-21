"""Link health: are your saved links still there? (Tools -> Link health, the fave page's banner, Home's "Broken links".)

Each check stores meta["link"] = {state, code, moved_to, checked} on the fave (no new columns):
  ok      the page answers
  moved   it now redirects to a different page (moved_to): "Use the new address" swaps it in one tap
  gone    404 / 410, the website no longer exists, or a deep link now lands on the site's home page
  unsure  blocked us (403, 429), a server error, or no answer in time. Never called gone: plenty of sites refuse robots.
Gone links get "Look for a saved copy", a plain link to the Wayback Machine that the person opens themselves (the app
sends nothing to archive.org). Checks run a few at a time (check_links, parallel, ~6 s each at most) so a big
collection is checked in batches from the browser; a link is checked again after RECHECK_DAYS.
"""
import concurrent.futures
import datetime as dt
import urllib.parse

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import Classify
from . import Fetch
from . import Store

RECHECK_DAYS = 30
BATCH = 8
BAD = ("gone", "moved")


def link_of(r):
    """The stored check for a fave ({} when never checked)."""
    m = r["meta"] or {}
    v = m.get("link")
    return v if isinstance(v, dict) else {}


def is_broken(r):
    return link_of(r).get("state") == "gone"


def _checkable(r):
    return bool(r["url"]) and r["kind"] != "place" and not Fetch.is_maps_url(r["url"]) and not r["is_sample"] and not r["is_demo"]


def _due(r, now):
    ln = link_of(r)
    if not ln.get("checked"):
        return True
    t = Store.parse_when(ln.get("checked"))
    return t is None or t < now - dt.timedelta(days=RECHECK_DAYS)


def _path(u):
    try:
        p = urllib.parse.urlparse(u).path or "/"
    except Exception:
        return "/"
    return p.rstrip("/") or "/"


def judge(url, code, final, problem):
    """(state, moved_to) from what the website answered."""
    if problem == "dns":
        return "gone", None
    if problem:
        return "unsure", None
    if code in (404, 410):
        return "gone", None
    if code is None or code >= 400:
        return "unsure", None
    final = final or url
    a, b = Fetch.normalize_url(url), Fetch.normalize_url(final)
    if a == b or a.replace("http://", "https://") == b:
        return "ok", None
    if _path(url) != "/" and _path(final) == "/":
        return "gone", None  # a deep link that now lands on the home page: the page itself is gone
    if Classify.domain_of(url) == Classify.domain_of(final) and _path(url) == _path(final):
        return "ok", None  # only the query or the protocol changed
    return "moved", final


def _check_one(url):
    try:
        code, final, problem = Fetch.status(url)
    except Exception:
        code, final, problem = None, url, "error"
    return judge(url, code, final, problem) + (code,)


def _store(r, state, moved_to, code):
    m = dict(r["meta"] or {})
    m["link"] = {"state": state, "code": code, "moved_to": (moved_to or "")[:1000] or None, "checked": C.iso(C.now())}
    r["meta"] = m


def _counts(rows, now):
    c = {"ok": 0, "moved": 0, "gone": 0, "unsure": 0, "unchecked": 0, "total": 0}
    due = 0
    for r in rows:
        c["total"] += 1
        st = link_of(r).get("state")
        if st in c:
            c[st] += 1
        else:
            c["unchecked"] += 1
        if _due(r, now):
            due += 1
    c["due"] = due
    return c


def _mine(me):
    return [r for r in app_tables.faves.search(tables.order_by("created", ascending=False), owner=me) if _checkable(r)]


def _item(r, me):
    d = Store.fave(r, me, lists=[], slim=True)
    ln = link_of(r)
    d["link"] = {"state": ln.get("state"), "code": ln.get("code"), "moved_to": ln.get("moved_to"), "checked": ln.get("checked")}
    return d


@anvil.server.callable(require_user=True)
def link_report():
    """Counts (ok, moved, gone, unsure, not checked yet, due for a check) and the gone and moved faves."""
    me = C.require_user()
    rows = _mine(me)
    now = C.now()
    bad = [r for r in rows if link_of(r).get("state") in BAD and r["status"] != "archived"]
    return C.ok(counts=_counts(rows, now),
                gone=[_item(r, me) for r in bad if link_of(r).get("state") == "gone"][:150],
                moved=[_item(r, me) for r in bad if link_of(r).get("state") == "moved"][:150])


@anvil.server.callable(require_user=True)
def check_links(limit=BATCH):
    """Check the next few links that were never checked (or not for a month), in parallel. The page calls this again
    until `due` is 0. Returns how many were checked and what was found."""
    me = C.require_user()
    if C.rate_limited("linkcheck", 150, 3600):
        return C.fail("That's a lot of checking for one hour. Try again a bit later.")
    try:
        limit = max(1, min(BATCH, int(limit)))
    except (TypeError, ValueError):
        limit = BATCH
    now = C.now()
    rows = _mine(me)
    todo = [r for r in rows if not link_of(r).get("checked")][:limit]
    if len(todo) < limit:
        todo += [r for r in rows if link_of(r).get("checked") and _due(r, now)][:limit - len(todo)]
    found = {"ok": 0, "moved": 0, "gone": 0, "unsure": 0}
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(todo)) as pool:
            results = list(pool.map(_check_one, [r["url"] for r in todo]))
        for r, (state, moved_to, code) in zip(todo, results):
            _store(r, state, moved_to, code)
            found[state] += 1
    return C.ok(checked=len(todo), found=found, counts=_counts(rows, now))


@anvil.server.callable(require_user=True)
def link_fix(fave_id, action):
    """use_new: swap in the address it moved to | works: the person says the link is fine (stops the warning) |
    recheck: check this one link again now."""
    me = C.require_user()
    r = C.row_by_id(app_tables.faves, fave_id)
    if r is None or r["owner"] != me:
        return C.fail("That fave isn't yours or no longer exists.")
    ln = link_of(r)
    if action == "use_new":
        new = ln.get("moved_to")
        if not new:
            return C.fail("There's no new address for this one.")
        r.update(url=new, url_norm=Fetch.normalize_url(new), domain=Classify.domain_of(new), updated=C.now())
        _store(r, "ok", None, 200)
    elif action == "works":
        _store(r, "ok", None, ln.get("code"))
    elif action == "recheck":
        if not _checkable(r):
            return C.fail("Only web links can be checked.")
        if C.rate_limited("linkcheck1", 40, 3600):
            return C.fail("Try again a bit later.")
        state, moved_to, code = _check_one(r["url"])
        _store(r, state, moved_to, code)
    else:
        return C.fail("Unknown action.")
    return C.ok(fave=_item(r, me))
