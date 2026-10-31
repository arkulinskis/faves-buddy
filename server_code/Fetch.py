"""Reading links: what a saved web page is about, where a Google Maps link points, and what OpenStreetMap
knows about a place. Used when something is saved, and by the "enrich" pass for tabs saved in bulk.

Network goes through http(url, data=None, headers=None) -> (final_url, bytes, content_type) so tests can
swap it (Fetch.http = fake). Pure parsing functions have no network at all.

Safety: only http(s), no private/loopback addresses (no reaching into Anvil's network), 1.5 MB cap,
8 second timeout, a polite User-Agent.
"""
import html as htmllib
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request

UA = "FavesBuddy/1.0 (+https://github.com/arkulinskis/faves-buddy; link previews)"
MAX_BYTES = 1500000
TIMEOUT = 8
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|igshid|igsh|si|ref|ref_src|ref_url|_hsenc|_hsmi|mkt_tok|"
                      r"yclid|spm|feature|_ga|_gl|wt\.mc_id|cmpid|smid)$", re.I)
KEEP_SHORT = {"youtube.com": {"v", "list", "t"}, "youtu.be": {"t"}, "google.com": {"q", "cid", "query", "api", "ll"}}


class FetchError(Exception):
    pass


def _safe(url):
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise FetchError("Only web links (http or https) can be read.")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except Exception:
        raise FetchError("That website couldn't be found.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("That address isn't on the public internet.")


class _NoRedirectToPrivate(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _safe(newurl)
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def _real_http(url, data=None, headers=None):
    _safe(url)
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5",
         "Accept-Language": "en-CA,en;q=0.9,fr-CA;q=0.8"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    opener = urllib.request.build_opener(_NoRedirectToPrivate())
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            body = r.read(MAX_BYTES)
            return r.geturl(), body, r.headers.get("Content-Type") or ""
    except FetchError:
        raise
    except Exception as e:
        raise FetchError("The page didn't answer (%s)." % (getattr(e, "code", None) or type(e).__name__))


http = _real_http  # tests replace this


# ------------------------------------------------------------------------------------------- URLs
def normalize_url(url):
    """The same page saved twice should match: no tracking params, no fragment, no www., no trailing slash."""
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
        url = "https://" + url
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return url[:1000]
    host = (u.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    if host.startswith("m.") and host.count(".") >= 2:
        host = host[2:]
    keep = None
    for d, ks in KEEP_SHORT.items():
        if host == d or host.endswith("." + d):
            keep = ks
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=False)
         if (keep is not None and k in keep) or (keep is None and not TRACKING.match(k))]
    path = u.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    frag = u.fragment if u.fragment.startswith(("/", "!")) else ""  # keep hash-routed apps (#/page)
    out = "https://" + host + (":" + str(u.port) if u.port and u.port not in (80, 443) else "") + path
    if q:
        out += "?" + urllib.parse.urlencode(sorted(q))
    if frag:
        out += "#" + frag
    return out[:1000]


def is_maps_url(url):
    d = (urllib.parse.urlparse(url).hostname or "").lower()
    return ("google." in d and "/maps" in url) or d in ("maps.app.goo.gl", "goo.gl", "maps.google.com") or \
        d.endswith("openstreetmap.org") or d == "maps.apple.com" or d == "maps.apple"


def parse_maps_url(url):
    """{lat, lng, name} from a Google Maps / Apple Maps / OpenStreetMap link (whatever it contains)."""
    out = {}
    u = urllib.parse.unquote(url or "")
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", u)  # the place's own pin
    if not m:
        m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", u)  # the map's centre
    if not m:
        m = re.search(r"[?&](?:q|ll|query|center|daddr|destination|mlat)=(-?\d+\.\d+)[, ](-?\d+\.\d+)", u.replace("&mlon=", ","))
    if not m:
        m = re.search(r"#map=\d+/(-?\d+\.\d+)/(-?\d+\.\d+)", u)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            out["lat"], out["lng"] = round(lat, 6), round(lng, 6)
    m = re.search(r"/maps/place/([^/@?]+)", u)
    if m:
        out["name"] = m.group(1).replace("+", " ").strip()
    else:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        for k in ("q", "query", "name"):
            v = (q.get(k) or [""])[0]
            if v and not re.match(r"^-?\d+\.\d+[, ]", v):
                out["name"] = v.split(",")[0].strip()
                break
    return out


# ------------------------------------------------------------------------------------------- pages
_META = re.compile(r"<meta\s+([^>]+?)/?>", re.I | re.S)
_ATTR = re.compile(r"""([a-zA-Z_:.-]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.S)
_LD = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.I | re.S)


def _attrs(tag):
    return {m.group(1).lower(): htmllib.unescape(m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else m.group(5)))
            for m in _ATTR.finditer(tag)}


def _clean(s, n=300):
    s = re.sub(r"\s+", " ", htmllib.unescape(s or "")).strip()
    return s[:n]


def _walk_ld(node, out):
    if isinstance(node, list):
        for x in node:
            _walk_ld(x, out)
        return
    if not isinstance(node, dict):
        return
    t = node.get("@type")
    types = t if isinstance(t, list) else [t] if t else []
    for typ in types:
        if isinstance(typ, str):
            out["types"].append(typ.split("/")[-1])
    if types:
        main = out["main"]
        if not main.get("name") and isinstance(node.get("name"), str) and not any(x in ("WebSite", "Organization", "BreadcrumbList", "WebPage", "ImageObject", "Person")
                                                                                   for x in types if isinstance(x, str)):
            main["name"] = node.get("name")
        geo = node.get("geo")
        if isinstance(geo, dict) and "lat" not in main:
            try:
                main["lat"], main["lng"] = float(geo.get("latitude")), float(geo.get("longitude"))
            except Exception:
                pass
        addr = node.get("address")
        if addr and "address" not in main:
            if isinstance(addr, dict):
                main["address"] = ", ".join(str(addr.get(k)) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode") if addr.get(k))
            elif isinstance(addr, str):
                main["address"] = addr
        for k in ("startDate", "endDate", "priceRange", "servesCuisine", "recipeYield", "totalTime"):
            if node.get(k) and k not in main:
                v = node.get(k)
                main[k] = v if isinstance(v, str) else ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
        loc = node.get("location")
        if isinstance(loc, dict):
            _walk_ld(loc, out)
    for k in ("@graph", "mainEntity", "itemListElement"):
        if k in node:
            _walk_ld(node[k], out)


def parse_html(html, url=""):
    """Everything useful in a page's <head> and JSON-LD: title, description, image, site, og:type,
    schema.org types, language, reading time, and a place or event when the page describes one."""
    head = html[:400000]
    meta = {}
    for m in _META.finditer(head):
        a = _attrs(m.group(1))
        k = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
        if k and a.get("content") and k not in meta:
            meta[k] = a["content"]
    tm = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
    ld = {"types": [], "main": {}}
    for block in _LD.findall(html[:1500000]):
        try:
            _walk_ld(json.loads(block.strip().strip(";")), ld)
        except Exception:
            continue
    lang = re.search(r"<html[^>]*\slang=[\"']?([a-zA-Z-]+)", head, re.I)
    body = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html[:1500000])
    words = len(re.sub(r"<[^>]+>", " ", body).split())
    title = meta.get("og:title") or meta.get("twitter:title") or (tm and tm.group(1)) or ld["main"].get("name") or ""
    image = meta.get("og:image") or meta.get("og:image:url") or meta.get("twitter:image") or meta.get("twitter:image:src") or ""
    if image and url:
        image = urllib.parse.urljoin(url, image)
    if re.match(r"^\s*(just a moment|client challenge|attention required|access denied|please wait|are you a robot|403 forbidden|"
                r"verify you are human|one moment|security check|captcha)", title or "", re.I):
        title = ""
    out = {
        "title": _clean(title, 200),
        "description": _clean(meta.get("og:description") or meta.get("description") or meta.get("twitter:description"), 500),
        "image": image[:600] if image.startswith("http") else "",
        "site_name": _clean(meta.get("og:site_name") or meta.get("application-name"), 80),
        "og_type": _clean(meta.get("og:type"), 40).lower(),
        "schema": sorted(set(ld["types"]))[:12],
        "lang": (lang.group(1).lower() if lang else "")[:8],
        "words": words,
        "read_min": max(1, round(words / 230)) if words > 350 else 0,
    }
    main = ld["main"]
    lat = main.get("lat")
    if lat is None:
        for a, b in (("place:location:latitude", "place:location:longitude"), ("og:latitude", "og:longitude"), ("geo.position", None)):
            if a in meta:
                try:
                    if b:
                        lat, lng = float(meta[a]), float(meta[b])
                    else:
                        lat, lng = [float(x) for x in re.split(r"[;,]", meta[a])[:2]]
                    main["lat"], main["lng"] = lat, lng
                    break
                except Exception:
                    pass
    if main.get("lat") is not None and -90 <= main["lat"] <= 90 and -180 <= main.get("lng", 999) <= 180:
        out["lat"], out["lng"] = round(main["lat"], 6), round(main["lng"], 6)
    for k in ("address", "startDate", "endDate", "priceRange", "servesCuisine", "recipeYield", "totalTime"):
        if main.get(k):
            out[k] = _clean(main[k], 160)
    if main.get("name"):
        out["entity"] = _clean(main["name"], 160)
    return out


def read_page(url):
    """Fetch a link and describe it. Maps links become places (and get OSM tags when we can match them)."""
    final, body, ctype = http(url)
    final = final or url
    host = (urllib.parse.urlparse(final).hostname or "")
    if "consent.google" in host or "consent.youtube" in host:
        cont = urllib.parse.parse_qs(urllib.parse.urlparse(final).query).get("continue")
        if cont:
            final = cont[0]
    info = {"final_url": final}
    if is_maps_url(final) or is_maps_url(url):
        place = parse_maps_url(final)
        if not place.get("lat"):
            place.update({k: v for k, v in parse_maps_url(url).items() if k not in place})
        info.update(place)
        info["kind"] = "place"
        if place.get("name"):
            info["title"] = place["name"]
        return info
    if "html" in ctype or body[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        text = body.decode(_charset(ctype, body), errors="replace")
        info.update(parse_html(text, final))
    elif ctype.startswith("image/"):
        info["kind"] = "photo"
        info["image"] = final
    elif "pdf" in ctype:
        info["schema"] = ["Report"]
        info["title"] = urllib.parse.unquote(final.rsplit("/", 1)[-1])[:150]
    return info


def _charset(ctype, body):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:3000], re.I)
    cs = m.group(1) if m else "utf-8"
    cs = cs.decode() if isinstance(cs, bytes) else cs
    try:
        "".encode(cs)
        return cs
    except Exception:
        return "utf-8"


# ------------------------------------------------------------------------------------------- OpenStreetMap
KEEP_OSM = ("amenity", "shop", "tourism", "leisure", "natural", "historic", "cuisine", "craft", "sport", "office", "boundary",
            "diet:vegan", "diet:vegetarian", "diet:gluten_free", "outdoor_seating", "wheelchair", "internet_access", "dog", "fee",
            "opening_hours", "website", "contact:website", "phone", "contact:phone", "addr:housenumber", "addr:street", "addr:city",
            "brand", "takeaway", "delivery", "name", "wikidata", "wikipedia", "description", "level", "smoking")


def slim_tags(tags):
    return {k: str(v)[:200] for k, v in (tags or {}).items() if k in KEEP_OSM}


PHOTON = "https://photon.komoot.io"


def _photon(path, params):
    url = PHOTON + path + "?" + urllib.parse.urlencode(params)
    _, body, _ = http(url)
    return json.loads(body.decode("utf-8")).get("features") or []


def _feature(f):
    p, g = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or [None, None]
    addr = " ".join(x for x in [p.get("housenumber"), p.get("street")] if x)
    addr = ", ".join(x for x in [addr, p.get("city") or p.get("district"), p.get("state")] if x)
    return {"name": p.get("name") or "", "lat": g[1], "lng": g[0], "address": addr, "country": p.get("countrycode") or "",
            "osm": {p.get("osm_key"): p.get("osm_value")} if p.get("osm_key") else {},
            "ref": "%s/%s" % ({"N": "node", "W": "way", "R": "relation"}.get(p.get("osm_type"), "node"), p.get("osm_id")) if p.get("osm_id") else None}


def _dist_m(a_lat, a_lng, b_lat, b_lng):
    import math
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def place_search(q, lat=None, lng=None, limit=6):
    """Places by name (Photon, OpenStreetMap data), nearest first when a location is given."""
    params = {"q": q, "limit": limit}
    if lat is not None and lng is not None:
        params.update({"lat": lat, "lon": lng})
    try:
        return [_feature(f) for f in _photon("/api/", params)]
    except Exception:
        return []


def osm_full_tags(ref):
    """All of a feature's OSM tags (cuisine, diets, hours...) from Overpass. Overpass is often busy:
    one quick try per server, and None when neither answers."""
    if not ref or "/" not in ref:
        return None
    typ, oid = ref.split("/", 1)
    q = "[out:json][timeout:6];%s(%s);out tags;" % (typ, int(oid))
    data = urllib.parse.urlencode({"data": q}).encode()
    for server in OVERPASS:
        try:
            _, body, _ = http(server, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
            els = json.loads(body.decode("utf-8")).get("elements") or []
            if els:
                return slim_tags(els[0].get("tags"))
        except Exception:
            continue
    return None


def osm_match(lat, lng, name=None):
    """The OpenStreetMap feature for a saved place: {osm tags, ref, address, name} or None.
    Photon (fast, reliable) finds it by name near the pin, or the nearest feature for a bare pin; Overpass
    then adds the full tags when it has capacity. Failing is fine: the place still saves with fewer clues."""
    if lat is None or lng is None:
        return None
    try:
        if name:
            feats = [_feature(f) for f in _photon("/api/", {"q": name, "lat": lat, "lon": lng, "limit": 5})]
            want = set(_name_tokens(name))
            feats = [f for f in feats if f["lat"] is not None and _dist_m(lat, lng, f["lat"], f["lng"]) < 400
                     and (not want or want & set(_name_tokens(f["name"])))]
        else:
            feats = [_feature(f) for f in _photon("/reverse", {"lat": lat, "lon": lng, "limit": 3, "radius": 0.08})]
            feats = [f for f in feats if f["osm"]]
    except Exception:
        return None
    if not feats:
        return None
    best = feats[0]
    full = osm_full_tags(best["ref"])
    if full:
        best["osm"] = full
    return best


def _name_tokens(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return [w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 1 and w not in ("the", "le", "la", "les", "de", "du", "des", "cafe", "restaurant")]
