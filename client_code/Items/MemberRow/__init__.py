from anvil import *

from ._anvil_designer import MemberRowTemplate
from ... import state


class MemberRow(MemberRowTemplate):
    """Someone a list is shared with: their role (view / add) and Remove. Raises x-changed after a removal."""

    def __init__(self, **properties):
        super().__init__(**properties)
        m = self.item
        who = m.get("name") or m.get("email") or "?"
        self.dom_nodes["initials"].textContent = state.initials(who)
        self.dom_nodes["name"].textContent = who
        self.dom_nodes["email"].textContent = (m.get("email") or "") + ("" if m.get("joined") else " · hasn't signed up yet")
        self.role_box.items = [("Can view", "viewer"), ("Can add", "editor")]
        self.role_box.selected_value = m.get("role") or "viewer"
        state.set_control_attr(self.role_box, "aria-label", "What %s can do" % who)
        state.set_control_attr(self.remove_button, "aria-label", "Remove " + who)

    @handle("role_box", "change")
    def role_box_change(self, **event_args):
        if state.call("set_member", self.item["_list"], self.item["id"], self.role_box.selected_value) is not None:
            state.toast("Updated", "ok")

    @handle("remove_button", "click")
    def remove_button_click(self, **event_args):
        if state.call("set_member", self.item["_list"], self.item["id"]) is not None:
            self.parent.raise_event("x-changed")
