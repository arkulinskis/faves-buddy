from anvil import *

from ._anvil_designer import SnoozeChoiceTemplate


class SnoozeChoice(SnoozeChoiceTemplate):
    """One "remind me" choice: item = {label, iso, date}. Raises x-pick(choice)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.dom_nodes["label"].textContent = self.item["label"]
        self.dom_nodes["date"].textContent = self.item["date"]

    def pick_click(self, event):
        self.parent.raise_event("x-pick", choice=self.item)
