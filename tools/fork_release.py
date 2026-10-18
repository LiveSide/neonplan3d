"""Build the release ZIP of this fork, as .github/workflows/release.yml does upstream.

GitHub does not run workflows in a fork until they are enabled by hand, so the
Release workflow builds nothing here. This script packs the integration the same
way (files of custom_components/neonplan3d, no __pycache__, sorted) and can
attach it to a release.

    python tools/fork_release.py                 # build neonplan3d.zip
    python tools/fork_release.py --tag v1.2.3.4  # build and upload to that release (needs gh)

Only in this fork, see FORK.md.
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
ZIP = ROOT / "neonplan3d.zip"


def version() -> str:
    """The version in the manifest; the release tag has to match it."""
    return json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))["version"]


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
    ap.add_argument("--tag", help="release tag to attach the ZIP to, e.g. v1.20.2.1")
    args = ap.parse_args()

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
