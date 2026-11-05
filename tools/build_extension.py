"""Build the Chrome extension download: icons from theme/assets/icon.svg, a syntax check, and the zip the app serves.

    python -I tools/build_extension.py

Writes extension/icons/icon-{16,32,48,128}.png and theme/assets/faves-buddy-extension.zip (served by Anvil at
_/theme/faves-buddy-extension.zip; Tools -> Browser extension links to it). Run it after any change in extension/.
The zip is deterministic (fixed timestamps), so an unchanged extension doesn't create a new deploy diff.
"""
import json
import pathlib
import subprocess
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
PROJECT = HERE.parent
EXT = PROJECT / "extension"
OUT = PROJECT / "theme" / "assets" / "faves-buddy-extension.zip"
sys.path.insert(0, str(HERE))
import make_icons  # noqa: E402


def main():
    (EXT / "icons").mkdir(exist_ok=True)
    for size in (16, 32, 48, 128):
        make_icons.render(size, EXT / "icons" / ("icon-%d.png" % size))
    for js in sorted(EXT.glob("*.js")):
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        if r.returncode:
            sys.exit("%s: %s" % (js.name, r.stderr.strip()))
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    for f in [manifest["background"]["service_worker"], manifest["action"]["default_popup"]] + list(manifest["icons"].values()):
        if not (EXT / f).exists():
            sys.exit("manifest points at a missing file: %s" % f)
    files = sorted(p for p in EXT.rglob("*") if p.is_file() and p.name != ".DS_Store")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo("faves-buddy-extension/" + p.relative_to(EXT).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    print("built %s (%d files, %d KB), extension v%s" % (OUT.name, len(files), OUT.stat().st_size // 1024, manifest["version"]))


if __name__ == "__main__":
    main()
