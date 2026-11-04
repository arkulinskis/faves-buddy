from anvil import *

from ._anvil_designer import PlaceResultTemplate


class PlaceResult(PlaceResultTemplate):
    """A place found by name (Photon): item = {title, address, kind, lat, lng, osm}. Raises x-pick(place)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.dom_nodes["title"].textContent = self.item.get("title") or ""
        self.dom_nodes["info"].textContent = " · ".join(x for x in (self.item.get("kind"), self.item.get("address")) if x)

    def pick_click(self, event):
        self.parent.raise_event("x-pick", place=self.item)
