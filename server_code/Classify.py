"""First-pass sorting without any AI model: rules + a small per-person learner.

    classify(info, model=None) -> {"category", "confidence", "reasons", "tags", "scores"}

info is a plain dict (all optional): kind ("link" | "place" | "photo" | "note" | "idea" | "event"), title, url,
text (description), note, ocr (text read from a picture), schema (list of schema.org types), og_type,
osm (dict of OpenStreetMap tags), site_name, when (True when it has an event date).

How it decides (weights below): the strongest structured signal usually wins (OSM tags, schema.org types,
the website), keywords break ties and cover notes and screenshots, and what this person confirmed or
corrected before (model) counts for a lot. Every point is explained in "reasons", so the app can say why.

The engine is deliberately pluggable: anything that returns the same dict (an LLM, a remote service)
can sit behind classify() later; the app only reads category, confidence, reasons and tags.
"""
import math
import re
import unicodedata
from urllib.parse import urlparse

try:
    from . import Taxonomy as T
except ImportError:  # run on its own (tools/research)
    import Taxonomy as T

W_OSM, W_OSM_ANY, W_SCHEMA, W_OG, W_DOMAIN, W_PATH = 6.0, 4.0, 6.0, 3.0, 5.0, 2.0
# Many sites mark every page as an Article / CreativeWork, so those only nudge.
W_SCHEMA_GENERIC, W_OG_GENERIC = 3.0, 1.5
GENERIC_SCHEMA = {"Article", "BlogPosting", "CreativeWork", "Organization", "Review", "ProfilePage"}
GENERIC_OG = {"article", "profile"}
W_TITLE_WORD, W_TEXT_WORD, WORD_CAP = 1.4, 0.6, 6.0
W_LEARN_DOMAIN, W_LEARN_WORDS, LEARN_CAP = 7.0, 2.2, 6.0
MIN_SCORE = 1.2
MAX_VOCAB = 2500

STOP = set("""a an and are as at be but by for from has have how i in is it its of on or our so that the their this to was we what
when where which who why will with you your le la les un une des du de et en au aux pour par sur dans avec est sont pas plus que qui
ce cette ces mon ma mes ton ta tes son sa ses nos vos leur leurs il elle ils elles nous vous je tu on www com http https html php
amp quot nbsp new best top all more one two get just like can about after into over out up not no""".split())


def strip_accents(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def stem(w):
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(s):
    s = re.sub(r"[^a-z0-9]+", " ", strip_accents(s).lower())
    return [stem(w) for w in s.split()]


def padded(s):
    """' tok tok tok ' for whole-phrase matching."""
    return " " + " ".join(tokens(s)) + " "


def _compile():
    out = {}
    for c in T.CATEGORIES:
        phrases = []
        for p in c["words"]:
            strong = p.startswith("!")
            p = p.lstrip("!")
            t = " ".join(tokens(p))
            if t:
                phrases.append((p, " " + t + " ", 2.2 if strong else 1.0))
        out[c["id"]] = phrases
    tags = {}
    for tag, ps in T.TAGS.items():
        tags[tag] = [" " + " ".join(tokens(p)) + " " for p in ps if tokens(p)]
    return out, tags


PHRASES, TAG_PHRASES = _compile()


def domain_of(url):
    try:
        host = urlparse(url if "//" in (url or "") else "https://" + (url or "")).netloc.lower()
    except Exception:
        return ""
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _domain_hit(url, dom, pattern):
    """'youtube.com' matches youtube.com and m.youtube.com; 'google.com/travel' also needs the path."""
    if "/" in pattern:
        d, path = pattern.split("/", 1)
        return (dom == d or dom.endswith("." + d)) and ("/" + path) in (urlparse(url).path or "")
    return dom == pattern or dom.endswith("." + pattern)


def _osm_hits(osm, rules):
    best, why = 0.0, None
    for r in rules:
        k, v = r.split("=", 1)
        if k not in osm:
            continue
        val = str(osm.get(k) or "")
        if v == "*" and val and val != "no":
            if W_OSM_ANY > best:
                best, why = W_OSM_ANY, "%s=%s" % (k, val)
        elif v in [x.strip() for x in val.split(";")]:
            if W_OSM > best:
                best, why = W_OSM, r
    return best, why


def classify(info, model=None):
    info = info or {}
    url = info.get("url") or ""
    dom = domain_of(url) if url else ""
    path = (urlparse(url).path or "").lower() if url else ""
    title = info.get("title") or ""
    body = " ".join(x for x in [info.get("text"), info.get("note"), info.get("ocr"), info.get("site_name")] if x)
    kind0 = info.get("kind") or "link"
    if kind0 in ("note", "idea") and info.get("text"):
        # a note's own words matter as much as its first line
        title, body = title + " " + (info.get("text") or ""), " ".join(x for x in [info.get("note"), info.get("ocr")] if x)
    t_title, t_body = padded(title), padded(body)
    osm = info.get("osm") or {}
    schema = [s.split("/")[-1] for s in (info.get("schema") or []) if s]
    og = (info.get("og_type") or "").lower()
    kind = info.get("kind") or "link"

    scores, reasons = {}, {}

    def add(cat, pts, why):
        scores[cat] = scores.get(cat, 0.0) + pts
        reasons.setdefault(cat, []).append((pts, why))

    for c in T.CATEGORIES:
        cid = c["id"]
        if cid == "other":
            continue
        if osm and c["osm"]:
            pts, why = _osm_hits(osm, c["osm"])
            if pts:
                add(cid, pts, "OpenStreetMap: " + why)
        hit = [s for s in schema if s in c["schema"]]
        if hit:
            specific = [s for s in hit if s not in GENERIC_SCHEMA]
            add(cid, W_SCHEMA if specific else W_SCHEMA_GENERIC, "schema.org: " + ", ".join(sorted(set(specific or hit))[:2]))
        if og and any(og == o or (o.endswith(".") and og.startswith(o)) for o in c["og"]):
            add(cid, W_OG_GENERIC if og in GENERIC_OG else W_OG, "page type: " + og)
        if dom:
            d = [p for p in c["domains"] if _domain_hit(url, dom, p)]
            if d:
                add(cid, W_DOMAIN, "site: " + d[0])
            pth = [p for p in c["paths"] if p in path]
            if pth:
                add(cid, W_PATH, "link looks like " + pth[0])
        words, pts = [], 0.0
        for raw, ph, mult in PHRASES[cid]:
            if ph in t_title:
                pts += W_TITLE_WORD * mult
                words.append(raw)
            elif ph in t_body:
                pts += W_TEXT_WORD * mult
                words.append(raw)
        if pts:
            add(cid, min(pts, WORD_CAP), "words: " + ", ".join(_uniq(words)[:4]))

    if kind in ("note", "idea") and not dom:
        add("ideas", 1.0 if kind == "note" else 3.0, "it's a note" if kind == "note" else "you called it an idea")
    if kind == "event" or info.get("when"):
        # a picture with a date and a time on it is usually a poster, a ticket or an invite
        add("events", 4.5 if kind == "photo" else 3.5, "it has a date")
    elif when_mentioned(title + " " + body):
        add("events", 2.5, "it mentions a date and time")

    if model:
        _learned(model, dom, title, add)

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] < MIN_SCORE:
        top, conf = "other", 0.0
    else:
        top = ranked[0][0]
        s1, s2 = ranked[0][1], (ranked[1][1] if len(ranked) > 1 else 0.0)
        conf = round(min(0.99, s1 / (s1 + s2 + 2.0) + (0.12 if s1 >= 6 else 0)), 2)
    why = [w for _, w in sorted(reasons.get(top, []), key=lambda x: -x[0])]
    return {"category": top, "confidence": conf, "reasons": why[:4], "tags": tags_for(title + " " + body, osm),
            "scores": {k: round(v, 2) for k, v in ranked[:5]}}


MONTHS = ("jan|january|janvier|feb|february|fevrier|mar|march|mars|apr|april|avril|may|mai|jun|june|juin|jul|july|juillet|aug|august|"
          "aout|sep|sept|september|septembre|oct|october|octobre|nov|november|novembre|dec|december|decembre")
DAYS = "mon|monday|lundi|tue|tuesday|mardi|wed|wednesday|mercredi|thu|thursday|jeudi|fri|friday|vendredi|sat|saturday|samedi|sun|sunday|dimanche"
_DATE = re.compile(r"\b((%s)\s+\d{1,2}|\d{1,2}(er)?\s+(%s))\b" % (MONTHS, MONTHS))
_DAY = re.compile(r"\b(%s)\b" % DAYS)
_TIME = re.compile(r"\b(\d{1,2}\s?h(\d{2})?|\d{1,2}(:\d{2})?\s?(am|pm)|\d{1,2}:\d{2})\b")


def when_mentioned(text):
    """A date (14 nov, Nov 14) or a weekday, together with a time (19h, 7pm, 19:30): poster / invite text."""
    t = strip_accents(text or "").lower()
    return bool((_DATE.search(t) or _DAY.search(t)) and _TIME.search(t))


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def tags_for(text, osm=None):
    t = padded(text)
    out = [tag for tag, ps in TAG_PHRASES.items() if any(p in t for p in ps)]
    osm = osm or {}
    for c in str(osm.get("cuisine") or "").split(";"):
        c = c.strip().lower()
        if c:
            out.append(T.CUISINE_TAGS.get(c, c.replace("_", " ")))
    for k, tag in (("diet:vegan", "vegan"), ("diet:vegetarian", "vegetarian"), ("diet:gluten_free", "gluten-free")):
        if osm.get(k) in ("yes", "only"):
            out.append(tag)
    if osm.get("outdoor_seating") == "yes":
        out.append("terrace")
    if osm.get("wheelchair") == "yes":
        out.append("accessible")
    if osm.get("internet_access") in ("wlan", "yes"):
        out.append("wifi")
    if osm.get("dog") == "yes":
        out.append("dog-friendly")
    if osm.get("fee") == "no":
        out.append("free")
    return _uniq(out)[:6]


# ------------------------------------------------------------------------------------------- the learner
def title_tokens(title):
    return _uniq([w for w in tokens(title) if len(w) >= 3 and w not in STOP and not w.isdigit()])[:20]


def _learned(model, dom, title, add):
    dm = (model.get("d") or {}).get(dom) if dom else None
    if dm:
        total = float(sum(dm.values()))
        best = max(dm.items(), key=lambda kv: kv[1])
        if total >= 1:
            add(best[0], W_LEARN_DOMAIN * best[1] / total, "you filed %s under %s before" % (dom, T.BY_ID.get(best[0], {}).get("name", best[0])))
    words = model.get("w") or {}
    per: dict = {}
    for w in title_tokens(title):
        wc = words.get(w)
        if not wc:
            continue
        total = float(sum(wc.values()))
        if total < 2:
            continue
        for cat, n in wc.items():
            share = n / total
            if share >= 0.6:
                per.setdefault(cat, [0.0, []])
                per[cat][0] += W_LEARN_WORDS * share * min(1.0, math.log(1 + n) / math.log(4))
                per[cat][1].append(w)
    for cat, (pts, ws) in per.items():
        add(cat, min(pts, LEARN_CAP), "like your other faves with: " + ", ".join(ws[:3]))


def learn(model, info, category, forget=None):
    """Teach the model that this fave belongs in `category` (and, if `forget` is given, not in that one).
    Returns the updated model (a plain dict, stored per person)."""
    model = dict(model or {})
    d, w = dict(model.get("d") or {}), dict(model.get("w") or {})
    dom = domain_of(info.get("url") or "") if info.get("url") else ""

    def bump(table, key, cat, n):
        row = dict(table.get(key) or {})
        row[cat] = max(0, row.get(cat, 0) + n)
        if not row[cat]:
            row.pop(cat)
        if row:
            table[key] = row
        else:
            table.pop(key, None)

    if dom:
        bump(d, dom, category, 1)
        if forget and forget != category:
            bump(d, dom, forget, -1)
    for tok in title_tokens(info.get("title") or ""):
        bump(w, tok, category, 1)
        if forget and forget != category:
            bump(w, tok, forget, -1)
    if len(w) > MAX_VOCAB:
        keep = sorted(w.items(), key=lambda kv: -sum(kv[1].values()))[:MAX_VOCAB]
        w = dict(keep)
    model["d"], model["w"], model["n"] = d, w, int(model.get("n") or 0) + 1
    return model
