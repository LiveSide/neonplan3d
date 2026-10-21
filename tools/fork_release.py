"""Stamp the fork version into the built frontend and build the release ZIP.

Two jobs, both only needed in this fork (see FORK.md):

1. ``--stamp``: the frontend carries its version as a build-time constant, so the
   bundles shipped by upstream say "1.20.2" while this fork's manifest says
   "1.20.2.1". The panel compares both and would ask the user to reload the page
   forever. Stamping writes the manifest version into the bundle instead of
   building the frontend again.
2. The ZIP: GitHub does not run workflows in a fork until they are enabled by
   hand, so the Release workflow attaches nothing. This packs the integration the
   same way (files of custom_components/neonplan3d, no __pycache__, sorted).

    python tools/fork_release.py --stamp         # write the version into the bundles
    python tools/fork_release.py                 # build neonplan3d.zip
    python tools/fork_release.py --tag v1.2.3.4  # build and upload to that release (needs gh)

After a merge of a new upstream release: take upstream's bundles, then --stamp again.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "neonplan3d"
BUNDLES = COMPONENT / "frontend"
ZIP = ROOT / "neonplan3d.zip"


def version() -> str:
    """The version in the manifest; the release tag has to match it."""
    return json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))["version"]


def upstream_version(own: str) -> str:
    """The version this fork sits on: our version without the fork part."""
    parts = own.split(".")
    return ".".join(parts[:3]) if len(parts) > 3 else own


def stamp() -> int:
    """Write the manifest version into the built bundles; returns the number of places."""
    own = version()
    base = upstream_version(own)
    if own == base:
        print(f"version {own} has no fork part - nothing to stamp")
        return 0
    places = 0
    for path in sorted(BUNDLES.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        count = text.count(f'"{base}"')
        if not count:
            continue
        path.write_text(text.replace(f'"{base}"', f'"{own}"'), encoding="utf-8", newline="")
        print(f"{path.name}: {count}x {base} -> {own}")
        places += count
    if not places:
        already = sum(p.read_text(encoding="utf-8").count(f'"{own}"') for p in BUNDLES.glob("*.js"))
        if already:
            print(f"already stamped ({already} places say {own})")
        else:
            sys.exit(f"found neither {base} nor {own} in the bundles - did the frontend change?")
    return places


def build() -> int:
    """Write the ZIP and return the number of files in it."""
    files = sorted(p for p in COMPONENT.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(COMPONENT).as_posix())
    return len(files)


def main() -> None:
    """Build, and upload when a tag is given."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp", action="store_true", help="write the version into the bundles and stop")
    ap.add_argument("--tag", help="release tag to attach the ZIP to, e.g. v1.20.2.1")
    args = ap.parse_args()

    if args.stamp:
        stamp()
        return

    count = build()
    print(f"{ZIP.name}: {count} files, {ZIP.stat().st_size / 1e6:.1f} MB (version {version()})")

    if not args.tag:
        return
    if args.tag.lstrip("v") != version():
        sys.exit(f"tag {args.tag} does not match the manifest version {version()}")
    subprocess.run(
        ["gh", "release", "upload", args.tag, str(ZIP), "--repo", "d14tk/neonplan3d", "--clobber"],
        check=True,
    )
    print(f"attached to {args.tag}")


if __name__ == "__main__":
    main()
