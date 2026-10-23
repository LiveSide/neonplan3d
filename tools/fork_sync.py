"""Follow the original: merge each new release of Mastershort/neonplan3d into this fork and publish it.

Runs in the workflow ``.github/workflows/fork-sync.yml`` (every few hours) and by hand:

    python tools/fork_sync.py            # merge the newest upstream release, build, tag and release it
    python tools/fork_sync.py --dry-run  # only tell what would happen

What it does, in order (see FORK.md, "Automatisch dem Original folgen"):

1. Fetch the original's tags and pick the newest stable one (``vX.Y.Z``).
2. Nothing to do when this fork already sits on it (manifest ``X.Y.Z.n``).
3. Merge the tag. Files the build writes (the bundles, the language files) and the original's own
   workflows are taken from the original and built again; the language files keep the fork's extra
   keys. A conflict anywhere else stops here: the merge is undone, an issue says which files, and no
   release is made, so HACS keeps offering the last good version.
4. Version ``X.Y.Z.1``, the fork's own manifest fields, tests, type check and build. A failure stops the
   same way.
5. Commit, tag ``vX.Y.Z.1``, push, and a release with ``neonplan3d.zip`` for HACS.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "neonplan3d" / "manifest.json"
UPSTREAM = "https://github.com/Mastershort/neonplan3d.git"
REPO = os.environ.get("GITHUB_REPOSITORY", "LiveSide/neonplan3d")
# the fork's own manifest fields (the original's would send users to the wrong issue tracker)
FORK_FIELDS = {
    "codeowners": ["@LiveSide"],
    "documentation": f"https://github.com/{REPO}#readme",
    "issue_tracker": f"https://github.com/{REPO}/issues",
}
# written by the build, or the original's own: taken from the original on a conflict
GENERATED = (
    "custom_components/neonplan3d/frontend/",
    "site/import/",
    ".github/workflows/",
)


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True).stdout.strip()


def run(cmd: list[str], cwd: Path) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def vkey(tag: str) -> tuple[int, ...]:
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def newest_upstream() -> str | None:
    if "upstream" not in git("remote").split():
        git("remote", "add", "upstream", UPSTREAM)
    git("fetch", "--quiet", "--tags", "upstream")
    tags = [t for t in git("tag", "--list", "v*").split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    return max(tags, key=vkey) if tags else None


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def write_manifest(data: dict) -> None:
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def union_lang(path: str, tag: str) -> None:
    """The original's texts, plus the keys only the fork has (its own fields)."""
    theirs = json.loads(git("show", f"{tag}:{path}"))
    ours = json.loads(git("show", f"HEAD:{path}"))
    theirs.update({k: v for k, v in ours.items() if k not in theirs})
    (ROOT / path).write_text(json.dumps(theirs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    git("add", path)


def report(title: str, body: str) -> None:
    """An issue in the fork (one per title), so a stop does not go unnoticed."""
    print(f"::error::{title}\n{body}")
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    found = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", "open", "--search", f'"{title}" in:title', "--json", "number"],
        capture_output=True, text=True,
    ).stdout
    if json.loads(found or "[]"):
        return
    subprocess.run(["gh", "issue", "create", "--repo", REPO, "--title", title, "--body", body], check=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", action="store_true", help="test: merge and commit, but no build, push or release")
    args = ap.parse_args()

    tag = newest_upstream()
    own = manifest()["version"]
    base = ".".join(own.split(".")[:3])
    if not tag or vkey(tag) <= vkey(base):
        print(f"up to date: fork {own} on original {base}, newest original {tag}")
        return 0
    target = f"{tag.lstrip('v')}.1"
    print(f"original {tag} is new: fork {own} -> {target}")
    if args.dry_run:
        return 0

    merged = subprocess.run(["git", "merge", "--no-commit", "--no-ff", tag], cwd=ROOT, capture_output=True, text=True)
    conflicts = git("diff", "--name-only", "--diff-filter=U").split()
    left = []
    for path in conflicts:
        if path.startswith(GENERATED):
            git("checkout", "--theirs", "--", path)
            git("add", path)
        elif re.fullmatch(r"(frontend|custom_components/neonplan3d/frontend)/lang/[\w-]+\.json", path):
            union_lang(path, tag)
        elif path == "custom_components/neonplan3d/manifest.json":
            git("checkout", "--theirs", "--", path)
            git("add", path)
        else:
            left.append(path)
    if merged.returncode and not conflicts:
        git("merge", "--abort", check=False)
        report(f"Original {tag}: Merge fehlgeschlagen", f"```\n{merged.stdout}\n{merged.stderr}\n```")
        return 1
    if left:
        git("merge", "--abort", check=False)
        files = "\n".join(f"- `{p}`" for p in left)
        report(
            f"Original {tag}: Konflikt, von Hand zusammenführen",
            f"Diese Dateien haben Änderungen des Forks und des Originals an denselben Stellen:\n\n{files}\n\n"
            "Bis das gelöst ist, gibt es kein neues Release, HACS bleibt beim letzten Fork-Release.",
        )
        return 1

    data = manifest()
    data.update(FORK_FIELDS)
    data["version"] = target
    write_manifest(data)

    front = ROOT / "frontend"
    if args.local:
        git("add", "-A")
        git("commit", "-m", f"Merge original {tag}; {target} (local test)")
        print(f"local: merged {tag} as {target}, not built, not pushed")
        return 0
    try:
        run(["npm", "ci", "--no-audit", "--no-fund"], front)
        run(["npm", "test"], front)
        run(["npm", "run", "typecheck"], front)
        run(["npm", "run", "build"], front)
    except subprocess.CalledProcessError as err:
        git("merge", "--abort", check=False)
        git("reset", "--hard", "HEAD", check=False)
        report(f"Original {tag}: Build oder Tests schlagen fehl", f"`{' '.join(err.cmd)}` endete mit {err.returncode}. Details im Workflow-Lauf.")
        return 1

    git("add", "-A")
    git("commit", "-m", f"Merge original {tag}; {target}")
    git("tag", f"v{target}")
    git("push", "origin", "HEAD", f"v{target}")
    run([sys.executable, "tools/fork_release.py"], ROOT)
    run(
        [
            "gh", "release", "create", f"v{target}", "neonplan3d.zip", "--repo", REPO, "--title", target,
            "--notes", f"Original {tag} (Mastershort) mit den Fork-Ergänzungen (siehe FORK.md). Gebaut von fork-sync.",
        ],
        ROOT,
    )
    print(f"released v{target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
