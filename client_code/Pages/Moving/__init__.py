from anvil import *

from ._anvil_designer import MovingTemplate
from ... import state


class Moving(MovingTemplate):
    """#moving (anyone): a welcome page for people leaving Pocket, Raindrop.io or Instapaper. Where to find each export
    and what comes along (dates, tags, folders, archived), then why Faves Buddy is more than another pile. The button
    opens Tools -> Import (signed-out visitors sign up first and land there afterwards)."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        signed_in = bool(state.me())
        self.dom_nodes["cta_text"].textContent = "Import my saves" if signed_in else "Start free, then import"
        self.tour_link.visible = not signed_in
