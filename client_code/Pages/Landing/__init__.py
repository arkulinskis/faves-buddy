from anvil import *
from anvil.js import window

from ._anvil_designer import LandingTemplate
from ... import fb, state


class Landing(LandingTemplate):
    """What visitors see first (also #landing = "About" for members): the promise with a live-map hero, the video,
    how it works, features, a peek at the public demo lists (featured_lists) and the FAQ."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        me = state.me()
        self.cta_guest.visible, self.cta_member.visible = not me, bool(me)
        self.band_guest.visible, self.band_member.visible = not me, bool(me)
        d = state.call_quiet("featured_lists") or {}
        fb.set_cats(d.get("cats"))
        lists = d.get("lists") or []
        self.peek.visible = bool(lists)
        self.peek_panel.items = lists

    def play_click(self, event):
        """Swap the cover for YouTube's privacy-enhanced player only when it's pressed."""
        frame = self.dom_nodes["yt_frame"]
        f = window.document.createElement("iframe")
        for k, v in (("src", "https://www.youtube-nocookie.com/embed/LKq6NHGjgdc?autoplay=1&rel=0&playsinline=1"),
                     ("title", "Faves Buddy video"), ("allow", "autoplay; encrypted-media; picture-in-picture; fullscreen"),
                     ("allowfullscreen", ""), ("referrerpolicy", "strict-origin-when-cross-origin")):
            f.setAttribute(k, v)
        frame.innerHTML = ""
        frame.appendChild(f)
