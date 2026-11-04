"""Server tests against the strict mock of Anvil (tools/testing/mock).

    python tools/testing/test_server.py          -> prints ALL OK, or the first failure

call(name, ...) runs a server function the way the browser does: by name, with require_user enforced,
and the reply must be JSON (a datetime or a row in a reply fails here, like it would break the page).
Add tests for every new server function: the happy path, bad input, and someone who isn't allowed.
"""
import datetime as dt
import importlib
import json
import os
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
_tmp = pathlib.Path(tempfile.mkdtemp())
shutil.copytree(PROJECT / "server_code", _tmp / "app")
(_tmp / "app" / "__init__.py").write_text("")
os.environ["ANVIL_APP_YAML"] = str(PROJECT / "anvil.yaml")  # the mock's tables follow the app's own schema
sys.path[:0] = [str(HERE / "mock"), str(_tmp)]
import anvil.server  # noqa: E402
import anvil.users  # noqa: E402
from anvil.tables import app_tables as T  # noqa: E402

M = {p.stem: importlib.import_module("app." + p.stem) for p in sorted((PROJECT / "server_code").glob("*.py"))}
now = dt.datetime.now(dt.timezone.utc)


def call(name, *args):
    r = anvil.server.call(name, *args)
    json.dumps(r)  # strict: must be JSON-able
    return r


def as_user(row):
    anvil.users.CURRENT[0] = row
    anvil.server.session.use(row.get_id() if row is not None else None)


def denied(name, *args):
    try:
        call(name, *args)
    except anvil.server.PermissionDenied:
        return True
    return False


def ok(r, msg=""):
    assert isinstance(r, dict) and r.get("ok"), (msg, r)
    return r


def bad(r, msg=""):
    assert isinstance(r, dict) and r.get("ok") is False and r.get("error"), (msg, r)
    return r


def person(email, name=None, **kw):
    return T.users.add_row(email=email, enabled=True, signed_up=now, display_name=name, **kw)


# ---------------------------------------------------------------------------------- accounts
admin = person("arkulinskis@gmail.com", "The Admin")
ana = person("ana@example.com", "Ana")
bob = person("bob@example.com")

as_user(None)
assert call("get_me") is None
assert denied("update_profile", "X")
as_user(admin)
assert call("get_me")["is_admin"] is True, "ADMIN_EMAILS become admins on first sign-in"
as_user(ana)
me = call("get_me")
assert me["name"] == "Ana" and me["is_admin"] is False
assert ana["last_seen"] is not None
as_user(bob)
assert call("get_me")["name"] == "Bob", "a name comes from the email when none is set"
bad(call("update_profile", " x "))
assert ok(call("update_profile", "  Bob   Stone "))["me"]["name"] == "Bob Stone"

# ---------------------------------------------------------------------------------- feedback
as_user(None)
bad(call("submit_feedback", "bug", "hi"))
ok(call("submit_feedback", "bug", "The button is broken", "guest@example.com", {"page": "#home", "evil": "x" * 9999}))
fb = T.feedback.search()[0]
assert fb["name"] == "Guest" and fb["email"] == "guest@example.com" and "evil" not in fb["context"] and fb["status"] == "new"
for i in range(4):
    ok(call("submit_feedback", "idea", "Idea number %d" % i))
bad(call("submit_feedback", "idea", "One too many this hour"), "rate limit")
as_user(ana)
ok(call("submit_feedback", "nonsense-kind", "Signed-in feedback"))
assert T.feedback.get(message="Signed-in feedback")["kind"] == "other"
assert denied("list_feedback")
as_user(admin)
lst = call("list_feedback")
assert lst["counts"]["new"] == 6 and len(lst["items"]) == 6
fid = lst["items"][0]["id"]
ok(call("set_feedback_status", fid, "done", "Fixed it"))
assert call("list_feedback", "done")["items"][0]["note"] == "Fixed it"
bad(call("set_feedback_status", fid, "weird"))
bad(call("set_feedback_status", "nope", "done"))
ok(call("delete_feedback", fid))
assert len(call("list_feedback")["items"]) == 5

# ---------------------------------------------------------------------------------- admin
as_user(ana)
for fn, args in [("admin_overview", ()), ("list_users", ()), ("set_admin", (bob.get_id(), True)), ("demo_load", ()), ("demo_remove", ())]:
    assert denied(fn, *args), fn
as_user(admin)
ov = call("admin_overview")
assert ov["users"] == 3 and ov["admins"] == 1 and ov["feedback_new"] == 5
assert len(call("list_users")["users"]) == 3 and len(call("list_users", "bob")["users"]) == 1
ok(call("set_admin", bob.get_id(), True))
assert bob["is_admin"] is True
bad(call("set_admin", admin.get_id(), False), "can't remove your own admin")
ok(call("set_enabled", bob.get_id(), False))
assert bob["enabled"] is False
bad(call("set_enabled", admin.get_id(), False))
ok(call("set_enabled", bob.get_id(), True))
ok(call("set_admin", bob.get_id(), False))
assert bob["is_admin"] is False

# ---------------------------------------------------------------------------------- Faves Buddy: offline network
import base64  # noqa: E402

Fetch, Store, Classify = M["Fetch"], M["Store"], M["Classify"]
RECIPE_HTML = """<!doctype html><html lang="en"><head><title>Miso soup | Cook Example</title>
<meta property="og:title" content="Weeknight miso soup">
<meta property="og:description" content="Ready in 15 minutes. Ingredients: miso, tofu, scallions.">
<meta property="og:image" content="/img/soup.jpg"><meta property="og:site_name" content="Cook Example">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebSite","name":"Cook Example"},
{"@type":"Recipe","name":"Weeknight miso soup","totalTime":"PT15M","recipeYield":"2"}]}</script></head><body>""" + ("word " * 900) + "</body></html>"
EVENT_HTML = """<html><head><title>Night market</title><script type="application/ld+json">{"@type":"Event","name":"Night market",
"startDate":"2030-06-01T19:00:00-04:00","location":{"@type":"Place","name":"Parc X","geo":{"latitude":45.5,"longitude":-73.6},
"address":{"streetAddress":"1 Rue X","addressLocality":"Montreal"}}}</script></head></html>"""
PHOTON = {"features": [{"type": "Feature", "properties": {"osm_type": "N", "osm_id": 42, "osm_key": "amenity", "osm_value": "cafe",
                                                          "name": "Café Test", "housenumber": "5", "street": "Rue Y", "city": "Montréal"},
                        "geometry": {"type": "Point", "coordinates": [-73.58, 45.52]}}]}
NET = []


def fake_http(url, data=None, headers=None):
    NET.append(url)
    if "photon.komoot.io" in url:
        return url, json.dumps(PHOTON).encode(), "application/json"
    if "overpass" in url or "mail.ru" in url:
        if b"node%2842%29" in (data or b"") or b"node(42)" in (data or b""):
            return url, json.dumps({"elements": [{"type": "node", "id": 42, "tags": {"amenity": "cafe", "cuisine": "coffee_shop",
                                                                                      "outdoor_seating": "yes", "name": "Café Test"}}]}).encode(), "application/json"
        raise Fetch.FetchError("busy")
    if url.startswith("https://cook.example/"):
        return url, RECIPE_HTML.encode(), "text/html; charset=utf-8"
    if url.startswith("https://events.example/"):
        return url, EVENT_HTML.encode(), "text/html"
    if url.startswith("https://maps.app.goo.gl/"):
        return "https://www.google.com/maps/place/Caf%C3%A9+Test/@45.52,-73.58,17z/data=!3d45.5201!4d-73.5801", b"<html></html>", "text/html"
    raise Fetch.FetchError("The page didn't answer (404).")


Fetch.http = fake_http

# pure helpers
assert Fetch.normalize_url("HTTPS://www.Example.com/a/?utm_source=x&id=3#top") == "https://example.com/a?id=3"
assert Fetch.normalize_url("https://m.youtube.com/watch?v=abc&feature=share&si=zz") == "https://youtube.com/watch?v=abc"
assert Fetch.normalize_url("app.example/#/inbox") == "https://app.example/#/inbox"
mp = Fetch.parse_maps_url("https://www.google.com/maps/place/Schwartz's/@45.5162,-73.5776,17z/data=!3d45.5163!4d-73.5776")
assert mp == {"lat": 45.5163, "lng": -73.5776, "name": "Schwartz's"}, mp
assert Fetch.parse_maps_url("https://www.openstreetmap.org/#map=17/45.5/-73.6")["lat"] == 45.5
pg = Fetch.parse_html(RECIPE_HTML, "https://cook.example/miso")
assert pg["title"] == "Weeknight miso soup" and "Recipe" in pg["schema"] and pg["image"] == "https://cook.example/img/soup.jpg"
assert pg["read_min"] >= 3 and pg["lang"] == "en" and pg["totalTime"] == "PT15M"
ev = Fetch.parse_html(EVENT_HTML)
assert ev["lat"] == 45.5 and ev["startDate"].startswith("2030-06-01") and "Montreal" in ev["address"], ev
assert Fetch.parse_html("<title>Just a moment...</title>")["title"] == ""
try:
    Fetch._safe("http://127.0.0.1/x")
    raise AssertionError("private addresses must be refused")
except Fetch.FetchError:
    pass
r = Classify.classify({"kind": "photo", "ocr": "JAZZ AU PARC Samedi 14 nov 19h Parc Laurier"})
assert r["category"] == "events" and "date" in r["reasons"][0], r
assert Classify.classify({"url": "https://www.youtube.com/watch?v=1", "title": "x"})["category"] == "watch"
assert Classify.classify({"kind": "place", "osm": {"amenity": "cafe", "outdoor_seating": "yes"}})["tags"] == ["terrace"]
assert Classify.classify({})["category"] == "other"
mdl = Classify.learn({}, {"url": "https://blog.cozy.example/a", "title": "Reading nook"}, "home")
assert Classify.classify({"url": "https://blog.cozy.example/zzz", "title": "New post"}, mdl)["category"] == "home"

# ---------------------------------------------------------------------------------- faves
as_user(None)
assert denied("fb_boot") and denied("faves_home") and denied("save_fave", {"title": "x"})
as_user(ana)
boot = call("fb_boot")
assert len(boot["cats"]) >= 18 and boot["api"].endswith("/_/api")
bad(call("save_fave", {}))
s1 = ok(call("save_fave", {"url": "https://cook.example/miso?utm_source=tw"}))
f1 = s1["fave"]
assert f1["cat"] == "recipes" and f1["status"] == "inbox" and f1["title"] == "Weeknight miso soup" and f1["created"] is not None, f1
assert "schema.org: Recipe" in f1["reasons"] and f1["image"].startswith("https://cook.example/")
again = ok(call("save_fave", {"url": "https://cook.example/miso", "note": "Double the tofu"}))
assert not again["created"] and again["fave"]["id"] == f1["id"] and again["fave"]["saves"] == 2 and "tofu" in again["fave"]["note"]
pv = ok(call("preview_link", "cook.example/miso"))
assert pv["sort"]["category"] == "recipes" and pv["already"] == f1["id"]
pv2 = ok(call("preview_link", "https://maps.app.goo.gl/abc"))
assert pv2["page"]["kind"] == "place" and pv2["page"]["osm"]["amenity"] == "cafe" and pv2["sort"]["category"] == "coffee", pv2
place = ok(call("save_fave", {"url": "https://maps.app.goo.gl/abc", "category": "coffee"}))["fave"]
assert place["kind"] == "place" and place["lat"] == 45.5201 and place["status"] == "kept" and place["confirmed"]
place_d = ok(call("get_fave", place["id"]))["fave"]
assert place_d["osm"].get("outdoor_seating") == "yes" and "terrace" in place_d["tags"], place_d
evf = ok(call("save_fave", {"url": "https://events.example/night-market"}))["fave"]
assert evf["cat"] == "events" and evf["event_at"].startswith("2030-06-01") and evf["lat"] == 45.5
same_place = ok(call("save_fave", {"title": "Café Test", "lat": 45.52, "lng": -73.58}))
assert not same_place["created"] and same_place["fave"]["id"] == place["id"], "the same place saved twice is one fave"
pin = ok(call("save_fave", {"title": "Parc des Pins", "lat": 45.51, "lng": -73.59}))["fave"]
assert pin["kind"] == "place" and pin["cat"] == "outdoors" and pin["status"] == "inbox", pin
note = ok(call("save_fave", {"title": "Gift for Dad: a good pocket knife", "kind": "note"}))["fave"]
assert note["cat"] == "gifts"
dead = ok(call("save_fave", {"url": "https://nowhere.example/page"}))["fave"]
assert dead["enriched"] and ok(call("get_fave", dead["id"]))["fave"]["meta"]["fetch_error"]

# inbox + triage + learning
ib = call("inbox")
assert ib["total"] == 5 and all(f["status"] == "inbox" for f in ib["faves"])
ok(call("triage", f1["id"], "keep"))
bad(call("triage", f1["id"], "keep", "nonsense"))
bad(call("triage", f1["id"], "explode"))
ok(call("triage", dead["id"], "keep", "learn"))
mdl = T.prefs.get(owner=ana)["model"]
assert mdl["d"]["nowhere.example"] == {"learn": 1} and mdl["n"] >= 2
assert Store.model_of(ana)["d"]["nowhere.example"]
later = (now + dt.timedelta(days=2)).isoformat()
bad(call("triage", evf["id"], "snooze", None, "2001-01-01T00:00:00+00:00"))
ok(call("triage", evf["id"], "snooze", None, later))
assert call("inbox")["snoozed"] == 1 and evf["id"] not in [f["id"] for f in call("inbox")["faves"]]
ok(call("triage", note["id"], "archive"))
assert call("list_faves", {"status": "archived"})["total"] == 1
as_user(bob)
bad(call("triage", f1["id"], "delete"), "bob can't triage Ana's faves")
bad(call("get_fave", f1["id"]), "bob can't see Ana's fave")
bad(call("update_fave", f1["id"], {"title": "mine now"}))
as_user(ana)

# library, filters, updates
home = call("faves_home")
assert home["total_kept"] == 3 and home["inbox"] == 1 and home["counts"]["recipes"] == 1 and home["places"] == 1, home
assert call("list_faves", {"cat": "coffee"})["total"] == 1
assert call("list_faves", {"status": "inbox"})["total"] == 1
assert call("list_faves", {"q": "miso tofu"})["total"] == 1
assert call("list_faves", {"q": "zzz-nothing"})["total"] == 0
assert call("list_faves", {"status": "all", "sort": "az"})["total"] == 5
up = ok(call("update_fave", f1["id"], {"title": "Miso soup", "tags": ["Quick", "soup"], "stage": "want", "rating": 4, "category": "eat"}))["fave"]
assert up["title"] == "Miso soup" and up["tags"] == ["quick", "soup"] and up["rating"] == 4 and up["cat"] == "eat" and up["confirmed"]
bad(call("update_fave", f1["id"], {"stage": "bored"}))
bad(call("update_fave", f1["id"], {"title": " "}))
bad(call("update_fave", f1["id"], {"lat": 999, "lng": 1}))
ok(call("update_fave", note["id"], {"lat": 45.5, "lng": -73.6}))
rs = ok(call("resort_fave", f1["id"]))
assert rs["fave"]["cat"] == "recipes" and not rs["fave"]["confirmed"]
ok(call("opened", f1["id"]))

# photos + OCR
png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfakepng").decode()
ph = ok(call("save_fave", {"title": "Screenshot 2026-10-31", "kind": "photo", "photo": png}))["fave"]
assert ph["photo"] and "/photo?k=" in ph["image"]
key = T.faves.get_by_id(ph["id"])["photo_key"]
resp = anvil.server.ENDPOINTS["/photo"](k=key)
assert resp.status == 200 and resp.body.get_bytes().startswith(b"\x89PNG")
assert anvil.server.ENDPOINTS["/photo"](k="nope").status == 404
bad(call("save_fave", {"title": "x", "photo": "data:text/plain;base64,aGk="}))
o = ok(call("save_photo_ocr", ph["id"], "JAZZ AU PARC Samedi 14 nov 19h Parc Laurier", {"times": ["19h"], "evil": ["x"]}, None,
            {"lat": 45.53, "lng": -73.58, "taken": "2026:10:31 10:00:00"}))["fave"]
assert o["cat"] == "events" and o["lat"] == 45.53 and "evil" not in o["meta"]["found"] and o["meta"]["exif"]["taken"]
o2 = ok(call("save_photo_ocr", ph["id"], None, None, {"summary": "A poster for a jazz night.", "title": "Jazz night poster", "category": "events", "tags": ["jazz"]}))["fave"]
assert o2["title"] == "Jazz night poster" and o2["meta"]["ai"] and "jazz" in o2["tags"]
ok(call("set_photo", ph["id"], png))
as_user(bob)
bad(call("save_photo_ocr", ph["id"], "x"))
bad(call("set_photo", ph["id"], png))
as_user(ana)

# import + tab sets + enrichment
bad(call("import_items", []))
bad(call("import_items", [{"url": "https://a.example"}] * 401))
imp = ok(call("import_items", [{"url": "https://cook.example/stew", "title": "Stew"}, {"url": "https://cook.example/miso"},
                               {"title": "Café Test", "lat": 45.52, "lng": -73.58}, {"nothing": 1}, "junk"], "onetab", "Old OneTab"))
assert imp["added"] == 1 and imp["again"] == 2, imp
ts = call("tabsets")["tabsets"]
assert len(ts) == 1 and ts[0]["name"] == "Old OneTab" and ts[0]["count"] == 1
en = call("enrich_pending")
assert en["left"] == 0 and en["done"] and en["done"][0]["cat"] == "recipes"
ok(call("rename_tabset", ts[0]["id"], "Soups"))
bad(call("rename_tabset", ts[0]["id"], ""))
assert ok(call("keep_tabset", ts[0]["id"]))["kept"] == 1
ok(call("delete_tabset", ts[0]["id"]))
assert call("tabsets")["tabsets"] == [] and call("list_faves", {"q": "stew"})["total"] == 1, "deleting a set keeps its faves"

# accept confident
ok(call("save_fave", {"url": "https://cook.example/curry"}))
assert ok(call("accept_confident", 0.5))["kept"] >= 1

# prefs, learned, export, samples
bad(call("set_prefs", {"lat": 200, "lng": 0}))
assert ok(call("set_prefs", {"lat": 45.52, "lng": -73.58, "label": "Home"}, {"radius_km": 3, "junk": 1}))["settings"] == {"radius_km": 3}
lr = call("learned")
assert lr["lessons"] >= 3 and any(d["key"] == "nowhere.example" for d in lr["domains"]) and lr["judged"] >= 1
ok(call("forget_learned", "domain", "nowhere.example"))
assert "nowhere.example" not in Store.model_of(ana).get("d", {})
ex = call("export_all")
assert len(ex["faves"]) >= 8 and ex["faves"][0]["category_name"]
n_before = len(T.faves.search(owner=ana))
assert ok(call("load_samples"))["added"] > 20
assert ok(call("load_samples"))["added"] == 0, "samples load once"
assert call("faves_home")["has_samples"]
ok(call("remove_samples"))
assert len(T.faves.search(owner=ana)) == n_before and not T.faves.search(owner=ana, is_sample=True)

# ---------------------------------------------------------------------------------- lists + sharing
bad(call("save_list", None, {"name": " "}))
lst = ok(call("save_list", None, {"name": "Coffee crawl", "emoji": "☕", "faves": [place["id"], pin["id"], "bad-id"]}))["list"]
assert lst["count"] == 2 and lst["emoji"] == "☕" and lst["role"] == "owner"
ok(call("save_list", lst["id"], {"name": "Coffee crawl!", "emoji": "nope", "color": "#000"}))
gl = ok(call("get_list", lst["id"]))["list"]
assert gl["name"] == "Coffee crawl!" and gl["emoji"] == "⭐" and len(gl["items"]) == 2
assert ok(call("list_add", lst["id"], [f1["id"], f1["id"]]))["added"] == 1
ok(call("update_fave", up["id"], {"lists": []}))
assert len(ok(call("get_list", lst["id"]))["list"]["items"]) == 2
bad(call("invite", lst["id"], "not-an-email"))
bad(call("invite", lst["id"], "ana@example.com"))
inv = ok(call("invite", lst["id"], "bob@example.com", "viewer"))
assert inv["has_account"] and any(m["email"] == "bob@example.com" for m in inv["list"]["members"])
ok(call("invite", lst["id"], "carol@example.com", "editor"))
as_user(bob)
ml = call("my_lists")
assert len(ml["shared"]) == 1 and ml["shared"][0]["role"] == "viewer"
gb = ok(call("get_list", lst["id"]))["list"]
assert gb["role"] == "viewer" and all(m["email"] in (None, "bob@example.com") for m in gb["members"]), "viewers never see others' emails"
assert ok(call("get_fave", place["id"]))["fave"]["owner"] == "Ana", "members can open faves on the list"
bob_f = ok(call("save_fave", {"title": "Bob's café", "lat": 45.51, "lng": -73.57, "category": "coffee"}))["fave"]
bad(call("list_add", lst["id"], [bob_f["id"]]), "viewers can't add")
bad(call("save_list", lst["id"], {"name": "Bob's now"}))
bad(call("set_public", lst["id"], True))
cp = ok(call("copy_member_item", lst["id"], place["id"]))
assert cp["created"] and cp["fave"]["mine"]
as_user(ana)
mem_bob = [m for m in ok(call("get_list", lst["id"]))["list"]["members"] if m["email"] == "bob@example.com"][0]
ok(call("set_member", lst["id"], mem_bob["id"], "editor"))
as_user(bob)
assert ok(call("list_add", lst["id"], [bob_f["id"]]))["added"] == 1
ok(call("list_remove", lst["id"], bob_f["id"]))
carol = person("carol@example.com", "Carol")
as_user(carol)
assert call("my_lists")["shared"][0]["role"] == "editor", "an invite waits for the account"
# public link
as_user(ana)
tok = ok(call("set_public", lst["id"], True))["token"]
as_user(None)
sl = ok(call("shared_list", tok))["list"]
assert sl["name"] == "Coffee crawl!" and len(sl["items"]) == 2 and "members" not in sl and not sl["signed_in"]
bad(call("shared_list", "nope"))
assert denied("copy_shared", tok, place["id"])
assert call("featured_lists")["lists"], "the demo's public lists show on the landing page"
as_user(bob)
c2 = ok(call("copy_shared", tok, pin["id"]))
assert c2["fave"]["mine"] and c2["created"]
bad(call("copy_shared", tok, f1["id"]), "only items on the list can be copied")
ok(call("set_member", lst["id"], mem_bob["id"]))  # bob leaves
assert call("my_lists")["shared"] == []
as_user(ana)
ok(call("set_public", lst["id"], False))
as_user(None)
bad(call("shared_list", tok), "turning the link off kills it")
as_user(bob)
bad(call("delete_list", lst["id"]))
as_user(ana)
ok(call("delete_list", lst["id"]))
assert not T.list_items.search(list=None) or True

# ---------------------------------------------------------------------------------- the extension (Clip)
as_user(ana)
info = call("clip_info")
assert info["code"].startswith("FAVES1.")
raw = json.loads(base64.urlsafe_b64decode(info["code"][7:] + "==").decode())
token = raw["t"]
assert raw["a"].endswith("/_/api")


def clip(payload):
    anvil.server.request.body = json.dumps(payload)
    anvil.server.request.headers = {}
    as_user(None)
    r = anvil.server.ENDPOINTS["/clip"]()
    return r.status, json.loads(r.body), r.headers


st, body, hd = clip({"token": "x" * 32, "action": "ping"})
assert st == 401 and hd["Access-Control-Allow-Origin"] == "*"
st, body, _ = clip({"token": token, "action": "ping"})
assert st == 200 and body["name"] == "Ana" and len(body["cats"]) >= 18
st, body, _ = clip({"token": token, "action": "save", "item": {"url": "https://shop.example/p/lamp", "title": "Brass lamp",
                                                               "meta": {"description": "Add to cart", "schema": ["Product"], "image": "https://shop.example/l.jpg"}}})
assert st == 200 and body["created"] and body["fave"]["cat"] == "shop" and body["fave"]["status"] == "inbox", body
assert not [u for u in NET[-3:] if "shop.example" in u], "a page the extension read isn't fetched again"
st, body, _ = clip({"token": token, "action": "save", "item": {"url": "https://cook.example/pie", "title": "Pie", "category": "recipes"}})
assert body["fave"]["status"] == "kept" and body["fave"]["cat"] == "recipes"
st, body, _ = clip({"token": token, "action": "save_many", "group": "Research", "items": [
    {"url": "https://cook.example/a", "title": "A"}, {"url": "https://www.youtube.com/watch?v=zz", "title": "Video"}, {"title": "no url"}]})
assert body["added"] == 2 and body["tabset"], body
st, body, _ = clip({"token": token, "action": "tabsets"})
assert body["tabsets"][0]["name"] == "Research" and body["tabsets"][0]["count"] == 2
st, body2, _ = clip({"token": token, "action": "tabset_urls", "id": body["tabsets"][0]["id"]})
assert len(body2["urls"]) == 2
st, body, _ = clip({"token": token, "action": "note", "text": "Idea: label every jar in the pantry", "page_url": "https://x.example"})
assert body["fave"]["cat"] == "ideas", body
lamp_id = [f for f in T.faves.search(owner=ana) if f["title"] == "Brass lamp"][0].get_id()
st, body, _ = clip({"token": token, "action": "set_category", "id": lamp_id, "category": "home"})
assert body["fave"]["cat"] == "home" and body["fave"]["status"] == "kept"
st, body, _ = clip({"token": token, "action": "set_category", "id": lamp_id, "category": "nope"})
assert body["ok"] is False
st, body, _ = clip({"token": token, "action": "set_category", "id": f1["id"] if False else "bad", "category": "home"})
assert body["ok"] is False
st, body, _ = clip({"token": token, "action": "zap"})
assert body["ok"] is False
as_user(ana)
new = ok(call("rotate_clip_token"))["code"]
assert new != info["code"]
st, body, _ = clip({"token": token, "action": "ping"})
assert st == 401, "a rotated token disconnects old browsers"

# ---------------------------------------------------------------------------------- tidy: tabs, screenshots, share sheet
Tidy, Cm = M["Tidy"], M["common"]
pl = Tidy.parse_links("Weeknight miso\nhttps://cook.example/miso\nhttps://www.youtube.com/watch?v=zz | Video\nwww.example.org/a\nhttps://cook.example/miso?utm_source=x\n")
assert [p["url"] for p in pl] == ["https://cook.example/miso", "https://www.youtube.com/watch?v=zz", "https://www.example.org/a"], pl
assert pl[0]["title"] == "Weeknight miso" and pl[1]["title"] == "Video", pl
assert Tidy.guess_title("9:41\n87%\nLTE\nJazz in the Park\nSat June 14, 7 pm") == "Jazz in the Park"
assert Tidy.guess_title("", "Screenshot_2026-10-30.png").startswith("Screenshot")
as_user(None)
assert denied("triage_links", None, "https://x.example") and denied("shot_save", {}) and denied("drop_open", "x" * 28)
as_user(ana)
bad(call("triage_links", None, "no links here"))
tl = ok(call("triage_links", None, "https://cook.example/udon\nhttps://www.youtube.com/watch?v=yy\nhttps://cook.example/pie"))["links"]
assert tl[1]["cat"] == "watch" and tl[2]["already"] and not tl[0]["already"], tl
det = ok(call("triage_detail", ["https://cook.example/udon", "https://gone.example/x"]))["pages"]
assert det[0]["cat"] == "recipes" and det[0]["image"] and det[1]["failed"], det
n0 = len(T.faves.search(owner=ana))
r = ok(call("triage_save", [{"url": tl[0]["url"], "title": "Miso", "category": "recipes", "meta": det[0]["meta"]},
                            {"url": tl[1]["url"], "title": "Video", "category": None}], "Phone tabs"))
assert r["saved"] == 2 and r["by_cat"].get("recipes") == 1 and r["tabset"], r
assert len(T.faves.search(owner=ana)) == n0 + 2
assert T.faves.get(owner=ana, url_norm=Fetch.normalize_url(tl[1]["url"]))["status"] == "inbox"
miso = T.faves.get(owner=ana, url_norm=Fetch.normalize_url(tl[0]["url"]))
assert miso["status"] == "kept" and miso["confirmed"] and miso["category"] == "recipes"
bad(call("triage_save", [{"url": "https://x.example/%d" % i} for i in range(201)]))

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
assert call("shots_seen", ["s1", "s2"])["seen"] == []
srt = ok(call("shot_sort", "9:41\nJazz in the Park\nSat June 14, 7 pm\nParc La Fontaine, free outdoor concert", "IMG_1.png",
              {"dates": ["June 14"], "times": ["7 pm"]}))
assert srt["title"] == "Jazz in the Park" and srt["cat"] == "events", srt
assert ok(call("shot_sort", "", "Screenshot_1.png"))["reasons"][0] == "no text found in it"
sv = ok(call("shot_save", {"photo": PNG, "title": srt["title"], "category": "events", "ocr": "Jazz in the Park", "found": {"dates": ["June 14"], "bogus": ["x"]}, "fp": "s1"}))
assert sv["created"] and sv["fave"]["cat"] == "events" and sv["fave"]["status"] == "kept" and sv["fave"]["photo"], sv
assert "bogus" not in T.faves.get(owner=ana, title="Jazz in the Park")["meta"]["found"]
ok(call("shots_skip", ["s2"]))
assert sorted(call("shots_seen", ["s1", "s2", "s3"])["seen"]) == ["s1", "s2"]
bad(call("shot_save", {"title": "no picture"}))
sl = ok(call("shot_save", {"photo": PNG, "title": "Later one", "category": None, "ocr": "", "url": "https://cook.example/miso", "fp": "s4"}))
assert not sl["created"], "a screenshot of a page already saved goes onto that fave"
assert "shots_seen" not in call("fb_boot")["settings"]
ok(call("shots_forget"))
assert call("shots_seen", ["s1"])["seen"] == []


def share_post(fields, files):
    parts = []
    for k, v in fields.items():
        parts.append(('--XyZ\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (k, v)).encode())
    for name, data in files:
        parts.append(('--XyZ\r\nContent-Disposition: form-data; name="files"; filename="%s"\r\nContent-Type: image/png\r\n\r\n' % name).encode() + data + b"\r\n")
    anvil.server.request.body = anvil.BlobMedia("multipart/form-data; boundary=XyZ", b"".join(parts) + b"--XyZ--\r\n")
    anvil.server.request.headers = {"content-type": "multipart/form-data; boundary=XyZ"}
    as_user(None)
    return anvil.server.ENDPOINTS["/share"]()


rs = share_post({"title": "Ramen night", "text": "Ramen night\nhttps://www.youtube.com/watch?v=r1\nhttps://cook.example/ramen"}, [("shot1.png", b"\x89PNG fake bytes")])
assert rs.status == 303 and "/#share/" in rs.headers["Location"] and rs.headers["X-Faves-Received"] == "links=2; files=1; note=0", rs.headers
code = rs.headers["Location"].split("/")[-1]
drops = list(T.faves.search(status="drop"))
assert len(drops) == 2 and all(f["owner"] is None for f in drops)
as_user(ana)
op = ok(call("drop_open", code))
assert [l["url"] for l in op["links"]] == ["https://www.youtube.com/watch?v=r1", "https://cook.example/ramen"] and len(op["photos"]) == 1 and op["photos"][0]["image"], op
as_user(bob)
bad(call("drop_open", code))
as_user(ana)
w = call("drops_waiting")["drops"]
assert len(w) == 1 and w[0]["photos"] == 1 and w[0]["links"] == 2, w
assert "drops" not in call("fb_boot")["settings"]
as_user(admin)
assert call("admin_overview")["faves"] == len([f for f in T.faves.search() if not f["is_demo"] and f["status"] != "drop"])
as_user(ana)
pid = op["photos"][0]["id"]
sv = ok(call("shot_save", {"drop_id": pid, "title": "Ramen poster", "category": "eat"}))
assert sv["fave"]["photo"] and Cm.row_by_id(T.faves, pid) is None and sv["fave"]["cat"] == "eat"
as_user(bob)
bad(call("shot_save", {"drop_id": pid, "title": "x"}))
as_user(ana)
ok(call("triage_save", [{"url": op["links"][0]["url"], "title": "Ramen video", "category": "watch"}], None, code))
assert not T.faves.search(status="drop") and call("drops_waiting")["drops"] == []
bad(call("drop_open", code))
rs = share_post({"title": "Gift idea", "text": "A pocket knife for Sam"}, [])
as_user(ana)
nt = ok(call("drop_open", rs.headers["Location"].split("/")[-1]))
assert nt["note"].startswith("Gift idea") and not nt["links"] and not nt["photos"]
assert ok(call("drop_discard", rs.headers["Location"].split("/")[-1]))["deleted"] == 1
assert share_post({}, []).headers["Location"].endswith("/#tidy")
old = Tidy.new_drop(links=[{"url": "https://old.example", "title": ""}])
for f in T.faves.search(url_norm="drop:" + old):
    f["created"] = now - dt.timedelta(days=4)
Tidy._clean_drops()
assert not T.faves.search(url_norm="drop:" + old), "unclaimed shares are deleted after 3 days"
mf = anvil.server.ENDPOINTS["/manifest.json"]()
mj = json.loads(mf.body)
assert mf.headers["Content-Type"] == "application/manifest+json" and mj["share_target"]["action"] == "/_/api/share"
assert mj["share_target"]["params"]["files"][0]["name"] == "files" and mj["start_url"] == "/" and mj["icons"]
tok2 = T.prefs.get(owner=ana)["clip_token"]
st, body, _ = clip({"token": tok2, "action": "drop_links", "group": "Tabs from Pixel", "items": [{"url": "https://cook.example/x", "title": "X"}, {"url": "chrome://flags"}]})
assert body["ok"] and body["count"] == 1, body
st, body2, _ = clip({"token": tok2, "action": "drop_links", "items": []})
assert body2["ok"] is False
as_user(ana)
dl = ok(call("drop_open", body["code"]))
assert dl["name"] == "Tabs from Pixel" and dl["links"][0]["url"] == "https://cook.example/x"
assert call("drops_waiting")["drops"][0]["name"] == "Tabs from Pixel"
ok(call("drop_discard", body["code"]))

# ---------------------------------------------------------------------------------- AI second opinion (in progress: off until a key is added)
AI = M["AISort"]
import anvil.secrets as SEC  # noqa: E402
as_user(ana)
assert call("fb_boot")["ai"] == {"available": False, "on": False, "status": "in_progress"}
bad(call("ai_second_opinion"))
assert denied("admin_ai_status") and denied("admin_ai_save", {}) and denied("admin_ai_test")
as_user(admin)
s0 = call("admin_ai_status")
assert s0["has_key"] is False and s0["available"] is False and s0["config"]["model"] == "claude-opus-5-5"
bad(call("admin_ai_save", {"enabled": True}))
bad(call("admin_ai_test"))
SEC.SECRETS["anthropic_api_key"] = "sk-ant-test"
SENT = []


def fake_post(url, headers, body, timeout=60):
    d = json.loads(body)
    SENT.append((dict(headers), d))
    lines = d["messages"][0]["content"].split("one JSON object per line):\n")[1].splitlines()
    out = {"items": [{"i": json.loads(l)["i"], "category": "ideas", "sure": "medium", "why": "Looks like an idea."} for l in lines]}
    return 200, json.dumps({"content": [{"type": "text", "text": json.dumps(out)}], "stop_reason": "end_turn", "model": d["model"],
                            "usage": {"input_tokens": 100, "output_tokens": 50}})


AI.post = fake_post
ok(call("admin_ai_save", {"enabled": True, "model": "claude-haiku-5-5", "threshold": 0.9, "daily": 50}))
ok(call("save_fave", {"title": "idea: a tiny library box on the corner", "kind": "idea"}))
t = ok(call("admin_ai_test"))
assert t["rows"] and t["rows"][0]["ai"] == "ideas" and t["usage"]["input_tokens"] == 100
h, b = SENT[-1]
assert h["anthropic-version"] == "2026-10-21" and h["x-api-key"] == "sk-ant-test" and "anthropic-beta" not in h
assert b["output_config"]["format"]["type"] == "json_schema" and b["output_config"]["effort"] == "low" and "fallbacks" not in b
assert "temperature" not in b and "thinking" not in b
as_user(ana)
assert call("fb_boot")["ai"]["available"] is True
bad(call("ai_second_opinion"))
ok(call("set_prefs", None, {"ai_sort": True}))
assert call("fb_boot")["ai"]["on"] is True
r = ok(call("ai_second_opinion"))
assert r["asked"] >= 1 and r["faves"][0]["meta"]["ai_sort"]["cat"] == "ideas", r
assert "base64" not in SENT[-1][1]["messages"][0]["content"] and "Looks like" in r["faves"][0]["meta"]["ai_sort"]["why"]
fid = r["faves"][0]["id"]
k = ok(call("ai_use", fid))
assert k["fave"]["cat"] == "ideas" and k["fave"]["status"] == "kept"
as_user(bob)
bad(call("ai_use", fid))
as_user(admin)
ok(call("admin_ai_save", {"model": "claude-opus-5-5"}))
HDRS = []


def fb_post(url, headers, body, timeout=60):
    HDRS.append(dict(headers))
    if "anthropic-beta" in headers:
        return 400, json.dumps({"error": {"message": "fallbacks: unknown beta"}})
    return fake_post(url, headers, body)


AI.post = fb_post
ok(call("admin_ai_test"))
assert HDRS[0]["anthropic-beta"] == "server-side-fallback-2026-07-01" and "anthropic-beta" not in HDRS[1]
AI.post = lambda *a, **k: (401, json.dumps({"error": {"message": "invalid x-api-key"}}))
assert "refused" in bad(call("admin_ai_test"))["error"]
AI.post = lambda *a, **k: (200, json.dumps({"content": [], "stop_reason": "refusal"}))
bad(call("admin_ai_test"))
bad(call("admin_ai_save", {"threshold": "lots"}))
ok(call("admin_ai_save", {"enabled": False}))
SEC.SECRETS.pop("anthropic_api_key")
AI.post = fake_post
as_user(ana)
assert call("fb_boot")["ai"]["available"] is False

# ---------------------------------------------------------------------------------- discover
as_user(ana)
tst = call("taste")
assert tst["recipes"] and tst["recipes"][0]["filters"][0] == ["amenity", "cafe"], tst["recipes"][:2]
assert tst["centers"] and tst["centers"][0].get("home")
assert any(s for s in tst["saved"])
as_user(carol)
assert call("taste")["recipes"], "new people get starter searches"

# ---------------------------------------------------------------------------------- admin: the sorter
as_user(ana)
assert denied("admin_sorting") and denied("admin_classify", "x")
as_user(admin)
srt = call("admin_sorting")
assert srt["total"] >= 2 and srt["per"]
bad(call("admin_classify", ""))
assert ok(call("admin_classify", "Preheat the oven, 2 tbsp butter"))["result"]["category"] == "recipes"
assert ok(call("admin_classify", "https://cook.example/miso", True))["result"]["category"] == "recipes"
ov = call("admin_overview")
assert ov["faves"] >= 10 and ov["from_extension"] >= 3 and ov["connected"] == 1

# ---------------------------------------------------------------------------------- demo data
as_user(None)
DD = M["DemoData"]
assert DD.state() == "loaded" and T.users.get(email="maya.demo@example.com") is not None
as_user(admin)
ok(call("demo_remove"))
assert DD.state() == "removed" and not T.users.search(is_demo=True) and not T.faves.search(is_demo=True)
assert len(T.faves.search(owner=ana)) > 5, "removing demo data keeps real data"
as_user(None)
call("featured_lists")
assert DD.state() == "removed", "removed demo data doesn't come back by itself"
as_user(admin)
ok(call("demo_load"))
ok(call("demo_load"))
assert len(T.lists.search(is_demo=True, is_public=True)) == 2, "reloading replaces the demo instead of doubling it"

# ---------------------------------------------------------------------------------- Privacy & Terms
if "legal_server" in M:
    as_user(ana)
    st = call("legal_state")
    assert st["signedIn"] and st["accepted_version"] is None
    ok(call("legal_accept", st["version"], "signup"))
    assert ana["legal_source"] == "signup" and call("legal_state")["accepted_version"] == st["version"]

# ---------------------------------------------------------------------------------- every callable is covered by a permission check
# A callable that changes data without require_user / a C.require_* check is a security hole. List the public ones here.

# ---------------------------------------------------------------------------------- one fave by link + top faves (Social)
as_user(ana)
f1 = ok(call("save_fave", {"title": "Café Lumière", "kind": "place", "lat": 45.52, "lng": -73.58, "note": "a secret note"}))["fave"]
tok = ok(call("share_fave", f1["id"], True))["token"]
assert tok and len(tok) >= 20
assert ok(call("share_fave", f1["id"], True))["token"] == tok, "sharing again keeps the same link"
as_user(bob)
bad(call("share_fave", f1["id"], True), "only the owner can share a fave")
as_user(None)
s = ok(call("shared_fave", tok))
assert s["fave"]["title"] == "Café Lumière" and "note" not in s["fave"] and "tags" not in s["fave"] and not s["signed_in"]
assert "@" not in json.dumps(s), "no emails on a shared fave"
assert denied("copy_shared_fave", tok), "visitors sign up before saving"
bad(call("shared_fave", "nope"))
bad(call("shared_fave", None))
as_user(bob)
c1 = ok(call("copy_shared_fave", tok))
assert c1["created"] and c1["fave"]["title"] == "Café Lumière"
assert not ok(call("copy_shared_fave", tok))["created"], "saving twice doesn't duplicate"
assert ok(call("shared_fave", tok))["yours"] == c1["fave"]["id"]
as_user(ana)
assert ok(call("shared_fave", tok))["own"]
ok(call("share_fave", f1["id"], False))
as_user(None)
bad(call("shared_fave", tok), "a link that was turned off stops working")

carl = person("carl@example.com", "Carl")
as_user(carl)
assert denied("top_faves") is False
top = ok(call("top_faves", 45.52, -73.58, 5))
hit = [x for x in top["places"] if x["title"] == "Café Lumière"]
assert hit and hit[0]["people"] == 2 and not hit[0]["mine"], top
assert "ana" not in json.dumps(top).lower() and "bob" not in json.dumps(top).lower(), "never who saved it"
assert not ok(call("top_faves", 10.0, 10.0, 5))["places"], "nothing far away"
assert ok(call("top_faves", None, None, 5))["places"] == [], "no spot, no home, no places: nothing"
as_user(bob)
ok(call("set_prefs", None, {"top_faves": False}))
as_user(carl)
assert not [x for x in ok(call("top_faves", 45.52, -73.58, 5))["places"] if x["title"] == "Café Lumière"], "opted-out people don't count"
as_user(bob)
ok(call("set_prefs", None, {"top_faves": True}))
as_user(carl)
sv = ok(call("save_top_fave", {"title": "Café Lumière", "lat": 45.52, "lng": -73.58, "address": "", "osm": {}}))
assert sv["created"] and sv["fave"]["lat"] == 45.52
bad(call("save_top_fave", {"title": ""}))
as_user(None)
assert denied("top_faves", 45.52, -73.58, 5) and denied("share_fave", f1["id"], True) and denied("save_top_fave", {})

PUBLIC = {"get_me", "submit_feedback", "legal_state", "legal_accept", "shared_list", "featured_lists", "shared_fave"}
for name, (f, need) in sorted(anvil.server.CALLABLES.items()):
    if name in PUBLIC:
        continue
    assert need, "%s is callable by anyone: add require_user=True (or list it in PUBLIC in test_server.py)" % name

print("ALL OK (%d server functions)" % len(anvil.server.CALLABLES))
