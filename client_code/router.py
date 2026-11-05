"""Page addresses: #name/arg1/arg2 -> a page Form (open_form), with sign-in rules. Same addresses as the old
JavaScript version, so links people saved or shared keep working.

Links in templates are plain <a href="#home">; code calls router.go("fave", id).

    PAGES[name] = (who may open it, browser-tab title)   who: None = anyone, "guest" = signed out only, "user", "admin"
    NAV = the header menu for signed-in people: (page, label, icon). The phone tab bar is drawn by the Shell.
New page: add it to PAGES and to _form(); a page with a map or document listeners defines leave() (called before the
next page opens) to clean up.
"""
import anvil
import anvil.js
from anvil.js import window

from . import state

PAGES = {
    "landing": (None, "Your favourite things, sorted"),
    "auth": ("guest", "Sign in"),
    "home": ("user", "Your faves"),
    "inbox": ("user", "Inbox"),
    "map": ("user", "Map"),
    "discover": ("user", "Discover"),
    "lists": ("user", "Lists"),
    "list": ("user", "List"),
    "fave": ("user", "Fave"),
    "add": ("user", "Save something"),
    "tabs": ("user", "Tab sets"),
    "tidy": ("user", "Tidy up"),
    "share": ("user", "Shared with Faves Buddy"),
    "tools": ("user", "Tools"),
    "s": (None, "Shared list"),
    "f": (None, "A shared fave"),
    "app": (None, "Get the app"),
    "profile": ("user", "Your profile"),
    "admin": ("admin", "Admin"),
}
NAV = [("home", "Faves", "heart"), ("inbox", "Inbox", "inbox"), ("map", "Map", "map"), ("discover", "Discover", "compass"),
       ("lists", "Lists", "grid")]
APP_NAME = "Faves Buddy"
_r: dict = {"after": "", "listening": False, "page": "", "form": None}


def _form(name):
    """The page's Form class (imported when first needed, so start-up stays quick)."""
    if name == "landing":
        from .Pages.Landing import Landing
        return Landing
    if name == "auth":
        from .Pages.Auth import Auth
        return Auth
    if name == "home":
        from .Pages.Home import Home
        return Home
    if name == "inbox":
        from .Pages.Inbox import Inbox
        return Inbox
    if name == "map":
        from .Pages.MapPage import MapPage
        return MapPage
    if name == "discover":
        from .Pages.Discover import Discover
        return Discover
    if name == "lists":
        from .Pages.Lists import Lists
        return Lists
    if name == "list":
        from .Pages.ListView import ListView
        return ListView
    if name == "fave":
        from .Pages.Fave import Fave
        return Fave
    if name == "add":
        from .Pages.Add import Add
        return Add
    if name == "tabs":
        from .Pages.Tabs import Tabs
        return Tabs
    if name == "tidy":
        from .Pages.Tidy import Tidy
        return Tidy
    if name == "share":
        from .Pages.ShareIn import ShareIn
        return ShareIn
    if name == "tools":
        from .Pages.Tools import Tools
        return Tools
    if name == "s":
        from .Pages.SharedList import SharedList
        return SharedList
    if name == "f":
        from .Pages.SharedFave import SharedFave
        return SharedFave
    if name == "app":
        from .Pages.GetApp import GetApp
        return GetApp
    if name == "profile":
        from .Pages.Profile import Profile
        return Profile
    from .Pages.Admin import Admin
    return Admin


def parse(hash_text):
    h = (hash_text or "").lstrip("#").lstrip("!").lstrip("/").split("?")[0]
    parts = [window.decodeURIComponent(p) for p in h.split("/") if p]
    return (parts[0] if parts else ""), parts[1:]


def href(name, *args):
    """'#name/arg1/arg2' with every part URL-encoded (row ids contain brackets and commas)."""
    return "#" + "/".join([name] + [window.encodeURIComponent(str(a)) for a in args if a not in (None, "")])


def link(component, name, *args):
    """Point an Anvil Link at a page of this app (a Link with a url opens a new tab by default: keep it in this one)."""
    component.url = href(name, *args)
    node = anvil.js.get_dom_node(component)
    node.removeAttribute("target")
    node.removeAttribute("rel")


def home_page():
    return "home" if state.me() else "landing"


def current():
    return _r["page"]


def set_title(text):
    """The browser tab title for a page that learns its name after loading (a fave, a list)."""
    window.document.title = (text + " · " if text else "") + APP_NAME


def _leave_current():
    f = _r["form"]
    _r["form"] = None
    leave = getattr(f, "leave", None) if f is not None else None
    if leave is not None:
        try:
            leave()
        except Exception as e:  # a page that can't clean up must never block the next one
            print("leave failed: %r" % e)


def show():
    """Open the page for the current address."""
    name, args = parse(window.location.hash)
    if name not in PAGES:
        name, args = home_page(), []
    who = PAGES[name][0]
    if who == "guest" and state.me():
        name, args = "home", []
    elif who in ("user", "admin") and not state.me():
        _r["after"] = window.location.hash
        name, args = "auth", []
    elif who == "admin" and not state.is_admin():
        state.toast("That page is for admins only.", "error")
        name, args = "home", []
    _leave_current()
    _r["page"] = name
    set_title(PAGES[name][1])
    window.UI_READY = False
    window.scrollTo(0, 0)
    page = _form(name)(args=args)
    _r["form"] = page
    anvil.open_form(page)
    shell = getattr(page, "layout", None)
    if shell is not None and hasattr(shell, "refresh"):
        shell.refresh(name)  # Anvil reuses the layout between pages: tell it who is signed in and which page is open
    window.UI_READY = True  # tests and screenshots wait for this


def shell():
    """The Shell layout of the page on screen (to update the inbox count), or None."""
    f = _r["form"]
    return getattr(f, "layout", None) if f is not None else None


def go(name, *args):
    """Go to a page. Same address again = reload the page."""
    target = href(name, *args)
    if window.location.hash == target:
        show()
    else:
        window.location.hash = target


def replace(name, *args):
    """Change the address without opening anything (a page that switches its own view)."""
    window.history.replaceState(None, "", href(name, *args))


def after_sign_in():
    """Where to go once someone signs in: the page they were heading for, or home."""
    target = _r["after"]
    _r["after"] = ""
    if target and target != window.location.hash:
        window.location.hash = target
    else:
        go("home")


def remember_after(target):
    _r["after"] = target


def _on_hash(event):
    show()


def _on_click(event):
    """Anvil puts a <base href> in the page, so a plain <a href="#x"> would reload the whole app when the address has a
    query string (?utm_source=...). Keep in-app links in the app."""
    if event.defaultPrevented or event.button != 0 or event.ctrlKey or event.metaKey or event.shiftKey:
        return
    target = event.target
    a = target.closest("a[href^='#']") if target and getattr(target, "closest", None) else None
    if not a or a.getAttribute("target") or a.hasAttribute("download"):
        return
    event.preventDefault()
    h = a.getAttribute("href")
    if window.location.hash == h:
        show()
    else:
        window.location.hash = h


def start():
    if not _r["listening"]:
        window.addEventListener("hashchange", anvil.js.report_exceptions(_on_hash))
        window.document.addEventListener("click", anvil.js.report_exceptions(_on_click))
        _r["listening"] = True
    show()
