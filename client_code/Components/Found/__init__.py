from anvil import *

from ._anvil_designer import FoundTemplate

GROUPS = [("urls", "link", "Links"), ("emails", "mail", "Emails"), ("phones", "phone", "Phone numbers"),
          ("dates", "calendar", "Dates"), ("times", "clock", "Times"), ("addresses", "pin", "Addresses"),
          ("handles", "user", "Handles"), ("prices", "tag", "Prices")]


def count(found):
    return sum(len((found or {}).get(k) or []) for k, _, _ in GROUPS)


def _href(kind, x):
    if kind == "urls":
        return x if x.lower().startswith(("http://", "https://")) else "https://" + x
    if kind == "addresses":
        from ... import router
        return router.href("map", "find", x)
    if kind == "phones":
        return "tel:" + "".join(ch for ch in x if ch.isdigit() or ch == "+")
    if kind == "emails":
        return "mailto:" + x
    return ""


class Found(FoundTemplate):
    """What was found in a picture, grouped (Links, Dates, Addresses...). Addresses open the map, phones call."""

    def __init__(self, **properties):
        self._found, self._ready = {}, False
        super().__init__(**properties)
        self._ready = True
        self._draw()

    def _draw(self):
        if not self._ready:
            return
        f = self._found or {}
        self.groups.items = [{"label": label, "icon": icon,
                              "links": [{"text": x, "href": _href(k, x), "external": k == "urls"} for x in f[k]]}
                             for k, icon, label in GROUPS if f.get(k)]

    @property
    def found(self):
        return self._found

    @found.setter
    def found(self, value):
        self._found = value or {}
        self._draw()
