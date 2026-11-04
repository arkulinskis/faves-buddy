from anvil import *

from ._anvil_designer import FoundGroupTemplate


class FoundGroup(FoundGroupTemplate):
    """One group of found bits: item = {label, icon, links: [{text, href, external}]}."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.icon.classes.add("ic-" + self.item["icon"])
        self.dom_nodes["label"].textContent = self.item["label"]
        self.links.items = self.item["links"]
