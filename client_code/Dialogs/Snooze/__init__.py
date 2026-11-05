from anvil import *

from ._anvil_designer import SnoozeTemplate
from ... import fb, state


class Snooze(SnoozeTemplate):
    """Tonight / This weekend / Next week / In a month. Closes with the triage reply, or None."""

    def __init__(self, fave_id, **properties):
        super().__init__(**properties)
        self.fave_id = fave_id
        self.choices.items = [{"label": c[0], "iso": c[1], "date": c[2]} for c in fb.snooze_choices()]
        self.choices.add_event_handler("x-pick", self._pick)

    def _pick(self, choice, **event_args):
        r = state.call("triage", self.fave_id, "snooze", None, choice["iso"])
        if r is not None:
            state.toast("Snoozed until " + choice["date"], "ok")
            self.raise_event("x-close-alert", value=r)

    @handle("cancel_button", "click")
    def cancel_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=None)
