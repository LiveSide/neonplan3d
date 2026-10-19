"""Install signed furniture packs into the NeonPlan 3D store of a Home Assistant, over SSH.

    python tools/packs_store.py list
    python tools/packs_store.py install packs/*.fp3dpack [--restart]
    python tools/packs_store.py remove local.furniture.bath [--restart]

The usual way is the panel: NeonPlan 3D, edit, furniture, import a furniture pack, pick the file.
This is the way for many packs at once, and for a machine reached over SSH.

Every pack is checked exactly as Home Assistant checks it on import: the signature against the
keys this repository knows (PACK_PUBLIC_KEYS, plus own ones from neonplan3d_publishers.json or
NEONPLAN3D_PUBLISHERS, see own-furniture/README.md), the payload against the real schema, and a
pack bound to one installation against that installation's fingerprint. What is refused here
would not have arrived there either. --dry-run stops before anything is written.

Home Assistant reads .storage only at start-up, so a written store takes effect on the next
restart; --restart triggers one. The store as it was is saved to a file first.

Needs "cryptography" and "voluptuous", and an ssh client that reaches the machine without a
password (a key in the agent, or --ssh-key). The SSH user is root on a Home Assistant OS add-on;
with another user add --sudo.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fp3d_packs", ROOT / "custom_components" / "neonplan3d" / "packs.py")
assert _spec and _spec.loader
packs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(packs)

STORE = "/config/.storage/neonplan3d.packs"
UUID = "/config/.storage/core.uuid"
# what an empty store looks like; an existing one keeps its own version fields
EMPTY: dict[str, Any] = {"version": 1, "minor_version": 1, "key": "neonplan3d.packs", "data": {"packs": []}}


def ssh(args: argparse.Namespace, command: str, stdin: bytes | None = None) -> bytes:
    """Runs a command on the Home Assistant and returns its output."""
    target = f"{args.user}@{args.host}"
    call = ["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes"]
    if args.ssh_key:
        call += ["-i", args.ssh_key]
    if args.port:
        call += ["-p", str(args.port)]
    done = subprocess.run([*call, target, command], input=stdin, capture_output=True, check=False)
    if done.returncode != 0:
        sys.exit(f"ssh failed ({done.returncode}): {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def privileged(args: argparse.Namespace, command: str) -> str:
    """The command as sudo, where the SSH user is not root."""
    return f"sudo {command}" if args.sudo else command


def read_store(args: argparse.Namespace) -> dict[str, Any]:
    """The pack store as it lies on the machine now; the empty one when there is none yet."""
    raw = ssh(args, privileged(args, f"cat {shlex.quote(args.store)} 2>/dev/null"))
    if not raw.strip():
        return json.loads(json.dumps(EMPTY))
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as err:
        sys.exit(f"{args.store} is no readable JSON: {err}")


def write_store(args: argparse.Namespace, store: dict[str, Any]) -> int:
    """Writes the store back and checks that it arrived whole. SFTP is often off, so tee it in."""
    text = json.dumps(store, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path = shlex.quote(args.store)
    ssh(args, privileged(args, f"tee {path} >/dev/null"), stdin=text)
    written = ssh(args, privileged(args, f"wc -c < {path}")).decode().strip()
    if written != str(len(text)):
        sys.exit(f"written size differs: {written} instead of {len(text)} bytes - check {args.store}")
    return len(text)


def save_copy(store: dict[str, Any], directory: Path) -> Path:
    """Puts the store as it was into a file, named after the moment it was taken."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"packs-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def fingerprint(args: argparse.Namespace) -> str | None:
    """The installation's fingerprint, as a bound pack carries it; None when core.uuid is unreadable."""
    raw = ssh(args, privileged(args, f"cat {shlex.quote(args.uuid)} 2>/dev/null"))
    if not raw.strip():
        return None
    try:
        return packs.fingerprint(json.loads(raw.decode("utf-8"))["data"]["uuid"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def entry_of(path: Path, instance: str | None) -> dict[str, Any]:
    """The store entry of a pack file, checked as Home Assistant checks it. Raises PackError."""
    text = path.read_text(encoding="utf-8")
    payload = packs.verify_pack(text, instance=instance)
    source, signature = packs.parts_of(text)
    return {**payload, "source": source, "signature": signature, "imported_at": time.time()}


def installed(store: dict[str, Any]) -> list[dict[str, Any]]:
    return store.setdefault("data", {}).setdefault("packs", [])


def show(store: dict[str, Any]) -> None:
    """Prints what is installed."""
    rows = installed(store)
    if not rows:
        print("No pack installed.")
        return
    print(f"{'ID':<30}{'ITEMS':>6}  {'PUBLISHER':<22}NAME")
    for pack in rows:
        items = len(pack.get("items", []))
        print(f"{pack.get('id', '?'):<30}{items:>6}  {(pack.get('publisher') or '')[:22]:<22}{pack.get('name', '')}")
    print(f"\n{len(rows)} packs, {sum(len(p.get('items', [])) for p in rows)} items")


def files_of(patterns: list[str]) -> list[Path]:
    """The pack files behind the given paths or globs, without duplicates."""
    out: list[Path] = []
    for pattern in patterns:
        hits = sorted(glob.glob(pattern)) or ([pattern] if Path(pattern).exists() else [])
        if not hits:
            sys.exit(f"no file for {pattern}")
        out += [Path(h) for h in hits if Path(h) not in out]
    return out


def merge(store: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    """Puts the entries into the store, each replacing an installed pack of the same id."""
    by_id = {pack["id"]: pack for pack in installed(store)}
    for entry in entries:
        by_id[entry["id"]] = entry
    store["data"]["packs"] = list(by_id.values())


def drop(store: dict[str, Any], ids: list[str]) -> int:
    """Removes the named packs and says how many went."""
    rows = installed(store)
    keep = [pack for pack in rows if pack.get("id") not in ids]
    gone = len(rows) - len(keep)
    store["data"]["packs"] = keep
    return gone


def restart(args: argparse.Namespace) -> None:
    """Restarts Home Assistant. The call cuts the connection it arrives on, so its exit code says nothing."""
    print("restarting Home Assistant ...")
    ssh(args, privileged(args, "ha core restart || true"))
    print("restart triggered; the panel is back after about a minute")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="homeassistant.local")
    parser.add_argument("--user", default="root")
    parser.add_argument("--port", type=int, default=None, help="SSH port, e.g. 22222 for the official add-on")
    parser.add_argument("--ssh-key", default=None, help="private key file; without it ssh uses its own config")
    parser.add_argument("--sudo", action="store_true", help="the SSH user is not root")
    parser.add_argument("--store", default=STORE)
    parser.add_argument("--uuid", default=UUID, help="core.uuid, for the fingerprint of a bound pack")
    parser.add_argument("--backups", default="backups", help="where the store as it was is saved")
    parser.add_argument("--restart", action="store_true", help="restart Home Assistant afterwards")
    parser.add_argument("--dry-run", action="store_true", help="check and print, write nothing")
    jobs = parser.add_subparsers(dest="job", required=True)
    jobs.add_parser("list", help="show the installed packs")
    install = jobs.add_parser("install", help="check signed .fp3dpack files and put them in")
    install.add_argument("files", nargs="+", metavar="FILE")
    remove = jobs.add_parser("remove", help="take packs out by id")
    remove.add_argument("ids", nargs="+", metavar="ID")
    args = parser.parse_args()

    store = read_store(args)
    if args.job == "list":
        show(store)
        return

    changed = False
    if args.job == "install":
        instance = fingerprint(args)
        if instance is None:
            print("note: no fingerprint read, a pack bound to another installation would pass here")
        known = {pack["id"] for pack in installed(store)}
        entries, refused = [], []
        for path in files_of(args.files):
            try:
                entry = entry_of(path, instance)
            except packs.PackError as err:
                refused.append(f"{path.name}: {err.code} {err.detail}".rstrip())
                continue
            print(f"  {entry['id']:<30}{len(entry['items']):>4} items  {'replaces' if entry['id'] in known else 'new'}")
            entries.append(entry)
        if refused:
            for line in refused:
                print(f"  REFUSED {line}")
            sys.exit(f"{len(refused)} pack(s) not valid, nothing written.")
        merge(store, entries)
        changed = bool(entries)
    elif args.job == "remove":
        gone = drop(store, args.ids)
        print(f"removed: {gone} pack(s)")
        changed = gone > 0

    if not changed:
        print("nothing to do.")
        return
    if args.dry_run:
        show(store)
        print("dry run: nothing written.")
        return

    print(f"saved the store as it was: {save_copy(read_store(args), Path(args.backups))}")
    size = write_store(args, store)
    rows = installed(store)
    print(f"written: {len(rows)} packs, {sum(len(p.get('items', [])) for p in rows)} items, {size / 1000:.0f} kB")
    if args.restart:
        restart(args)
    else:
        print("takes effect on the next restart of Home Assistant (--restart does it now)")


if __name__ == "__main__":
    main()
