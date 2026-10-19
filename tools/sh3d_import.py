#!/usr/bin/env python3
"""Turn a Sweet Home 3D furniture library (.sh3f) into NeonPlan 3D furniture packs.

Sweet Home 3D publishes free furniture libraries at sweethome3d.com/importModels: hundreds of
models with the one thing a 3D model from the web almost never carries - the real size of the
piece, its category, and a name in twenty languages. That is what makes them worth importing:
mesh2pack.py can shape any model, but only a catalogue knows that this one is a 1.40 m bed.

    sh3d_import.py BlendSwap-CC-0.sh3f --out packs/ --id local.blendswap --name "Blend Swap"

What it does per model: read the size and category from the catalogue, hand the mesh to
mesh2pack.py, and turn the category into what NeonPlan 3D needs to place the piece - a lamp gets
its light kind, a table carries things on top, a staircase cuts its stairwell, a car parks.
Doors and windows are skipped: NeonPlan 3D has its own, and they belong to the wall, not the room.

Licences are kept: every item records its creator and licence, and --credits writes the list.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mesh2pack import build_item

# the integration's own schema, so a bad item is caught here and not when Home Assistant refuses
# the whole pack
_spec = importlib.util.spec_from_file_location(
    "fp3d_packs", Path(__file__).resolve().parent.parent / "custom_components" / "neonplan3d" / "packs.py"
)
assert _spec and _spec.loader
packs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(packs)

# Categories we do not take over. NeonPlan 3D draws doors and windows itself, as part of the wall.
SKIP_CATEGORIES = {"Doors and windows"}

# Catalogue category -> the pack it goes into: one pack per room reads far better in the picker
# than one pack per library.
ROOMS: dict[str, tuple[str, str]] = {
    "Living room": ("wohnen", "Wohnen"),
    "Bedroom": ("schlafen", "Schlafen"),
    "Kitchen": ("kueche", "Küche"),
    "Bathroom": ("bad", "Bad"),
    "Office": ("buero", "Büro"),
    "Lights": ("licht", "Licht"),
    "Exterior": ("aussen", "Außen"),
    "Staircases": ("treppen", "Treppen"),
    "Vehicles": ("aussen", "Außen"),
    "Miscellaneous": ("diverses", "Diverses"),
}

# category -> what the piece is in NeonPlan 3D
SURFACE_CATEGORIES = {"Kitchen", "Living room", "Office", "Bedroom", "Bathroom", "Miscellaneous"}

LIGHT_KINDS: tuple[tuple[str, str], ...] = (
    ("ceiling", "ceiling"),
    ("decken", "ceiling"),
    ("chandelier", "pendant"),
    ("kronleuchter", "pendant"),
    ("pendant", "pendant"),
    ("hange", "pendant"),
    ("hänge", "pendant"),
    ("suspension", "pendant"),
    ("spot", "spot"),
    ("downlight", "downlight"),
    ("panel", "panel"),
    ("strip", "strip"),
    ("led", "strip"),
    ("wall", "wall"),
    ("wand", "wall"),
    ("applique", "wall"),
    ("sconce", "wall"),
    ("floor", "floor"),
    ("steh", "floor"),
    ("uplight", "uplight"),
    ("torch", "uplight"),
    ("lampadaire", "floor"),
    ("desk", "table"),
    ("table", "table"),
    ("tisch", "table"),
    ("bedside", "table"),
    ("nacht", "table"),
    ("bollard", "bollard"),
    ("garden", "garden"),
    ("street", "bollard"),
    ("lantern", "garden"),
    ("laterne", "garden"),
)

PLANT_WORDS = (
    "plant",
    "pflanze",
    "tree",
    "baum",
    "flower",
    "blume",
    "bush",
    "busch",
    "hedge",
    "hecke",
    "grass",
    "gras",
    "palm",
    "cactus",
    "kaktus",
    "fern",
    "bamboo",
    "shrub",
    "ficus",
    "garden",
)


def decode_properties(raw: bytes) -> str:
    """A Sweet Home 3D catalogue file as text.

    Java property files are ISO-8859-1 by specification, and that is what the Sweet Home 3D
    libraries ship; reading them as UTF-8 turned every umlaut into U+FFFD. Some third-party
    libraries do use UTF-8, so try that first and fall back to Latin-1, which never fails.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("iso-8859-1")


def read_properties(text: str) -> dict[int, dict[str, str]]:
    """A Sweet Home 3D catalogue file as {index: {key: value}}."""
    out: dict[int, dict[str, str]] = {}
    for key, index, value in re.findall(r"^([A-Za-z]+)#(\d+)=(.*)$", text, re.M):
        out.setdefault(int(index), {})[key] = value.strip()
    return out


def catalogue(sh3f: Path, languages: tuple[str, ...] = ("de", "en")) -> list[dict[str, Any]]:
    """Every piece of a .sh3f library, with its names in `languages`."""
    archive = zipfile.ZipFile(sh3f)
    names = archive.namelist()
    base_name = next((n for n in names if n.endswith("PluginFurnitureCatalog.properties")), None)
    if base_name is None:
        raise SystemExit(f"{sh3f.name}: no PluginFurnitureCatalog.properties")
    root = base_name[: -len("PluginFurnitureCatalog.properties")]
    base = read_properties(decode_properties(archive.read(base_name)))

    translated: dict[str, dict[int, dict[str, str]]] = {}
    for lang in languages:
        member = f"{root}PluginFurnitureCatalog_{lang}.properties"
        if member in names:
            translated[lang] = read_properties(decode_properties(archive.read(member)))

    pieces = []
    for index, entry in sorted(base.items()):
        if "model" not in entry or "width" not in entry:
            continue
        item = dict(entry)
        item["_index"] = index
        item["_names"] = {}
        for lang in languages:
            name = translated.get(lang, {}).get(index, {}).get("name") or entry.get("name")
            if name:
                item["_names"][lang] = name[:80]
        if "en" not in item["_names"] and entry.get("name"):
            item["_names"]["en"] = entry["name"][:80]
        pieces.append(item)
    return pieces


def slug(text: str, used: set[str]) -> str:
    """A pack item id: lower case, unique inside the pack."""
    base = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:36] or "item"
    if not base[0].isalnum():
        base = f"i{base}"
    name = base
    n = 2
    while name in used:
        name = f"{base}_{n}"[:40]
        n += 1
    used.add(name)
    return name


def traits(entry: dict[str, Any]) -> dict[str, Any]:
    """What the catalogue says the piece is, as NeonPlan 3D item fields."""
    category = entry.get("category", "")
    label = f"{entry.get('name', '')} {' '.join(entry['_names'].values())} {entry.get('tags', '')}".lower()
    height = float(entry.get("height", 100)) / 100.0
    elevation = float(entry.get("elevation", 0) or 0) / 100.0
    out: dict[str, Any] = {}

    if category == "Lights" or "lamp" in label or "light" in label or "leuchte" in label:
        kind = next((k for needle, k in LIGHT_KINDS if needle in label), None)
        if kind is None:
            kind = "table" if height < 0.75 else ("floor" if height > 1.1 else "ceiling")
        out["light"] = kind
        out["electric"] = True
        if kind in {"ceiling", "pendant", "downlight", "panel"}:
            out["mount"] = "ceiling"
        elif kind == "wall":
            out["mount"] = "wall"
            out["wall_y"] = round(min(2.5, max(0.3, elevation or 1.8)), 2)
    elif category == "Staircases":
        out["hole"] = True
    elif category == "Vehicles":
        out["vehicle"] = True

    if "mount" not in out and elevation > 0.35 and height < 1.2:
        # the catalogue hangs it on the wall (a shelf, a mirror, a TV)
        out["mount"] = "wall"
        out["wall_y"] = round(min(2.5, elevation), 2)

    if "mount" not in out and category in SURFACE_CATEGORIES:
        drop = entry.get("dropOnTopElevation")
        if drop is not None:
            try:
                if float(drop) / 100.0 >= 0.95 * height:
                    out["surface"] = True
            except ValueError:
                pass

    if any(word in label for word in ("tv", "television", "monitor", "screen", "fernseher", "bildschirm")):
        out["electric"] = True
    if category in {"Kitchen"} and any(
        word in label for word in ("fridge", "oven", "dishwasher", "washer", "kuhl", "kühl", "herd", "ofen")
    ):
        out["electric"] = True
    return out


def one(job: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a single model; runs in a worker process."""
    try:
        entry = job["entry"]
        label = " ".join(entry["_names"].values()).lower() + " " + entry.get("name", "").lower()
        report: dict[str, Any] = {}
        item = build_item(
            Path(job["model"]),
            job["id"],
            entry["_names"],
            size=tuple(
                value / 100.0 if 1.0 <= value <= 1000.0 else 0.0
                for value in (
                    float(entry.get("width") or 0),
                    float(entry.get("depth") or 0),
                    float(entry.get("height") or 0),
                )
            ),
            max_parts=job["parts"],
            grid=job["grid"],
            cell=job["cell"],
            tol=job["tol"],
            plantish=any(word in label for word in PLANT_WORDS),
            extras=traits(entry),
            report=report,
        )
        packs.ITEM_SCHEMA(item)  # refuse it here, not when Home Assistant reads the pack
        return {
            "item": item,
            "report": report,
            "creator": entry.get("creator", ""),
            "license": entry.get("license", ""),
            "category": entry.get("category", ""),
        }
    except Exception as err:
        return {"error": f"{job['id']}: {type(err).__name__}: {err}"}


def main(argv: list[str] | None = None) -> int:
    """Run the import."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("library", type=Path, nargs="+", help="one or more .sh3f furniture libraries")
    parser.add_argument("--out", type=Path, required=True, help="directory for the pack payloads")
    parser.add_argument("--id", required=True, help='pack id base, "local.…" for an own key')
    parser.add_argument("--name", required=True, help="pack name")
    parser.add_argument("--by-room", action="store_true", help="one pack per room instead of one big one")
    parser.add_argument("--publisher", default="Eigenbau")
    parser.add_argument("--parts", type=int, default=46, help="most parts per item")
    parser.add_argument("--grid", type=int, default=24, help="fewest voxels along the longest side")
    parser.add_argument("--cell", type=float, default=0.045, help="voxel edge in metres (what sets the detail)")
    parser.add_argument("--tol", type=float, default=0.8, help="how solid an added slice must be")
    parser.add_argument("--max-items", type=int, default=120, help="most items per pack")
    parser.add_argument("--sample", type=int, default=0, help="only convert this many (to try it out)")
    parser.add_argument(
        "--min-iou", type=float, default=0.45, help="drop items whose shape is this far off the model (0 = keep all)"
    )
    parser.add_argument("--only", help="regular expression on the model name")
    parser.add_argument("--jobs", type=int, default=0, help="worker processes (0 = all cores)")
    parser.add_argument("--credits", type=Path, help="write the list of creators and licences here")
    args = parser.parse_args(argv)

    jobs: list[dict[str, Any]] = []
    used: set[str] = set()
    work = Path(tempfile.mkdtemp(prefix="sh3d-"))
    try:
        for library in args.library:
            pieces = [p for p in catalogue(library) if p.get("category") not in SKIP_CATEGORIES]
            if args.only:
                pattern = re.compile(args.only, re.I)
                pieces = [p for p in pieces if pattern.search(" ".join(p["_names"].values()) + " " + p.get("name", ""))]
            if args.sample:
                step = max(1, len(pieces) // args.sample)
                pieces = pieces[::step][: args.sample]
            room = work / library.stem
            zipfile.ZipFile(library).extractall(room)
            for entry in pieces:
                model = room / entry["model"].lstrip("/")
                if not model.exists():
                    continue
                jobs.append(
                    {
                        "entry": entry,
                        "model": str(model),
                        "id": slug(entry["_names"].get("en") or entry.get("name", "item"), used),
                        "parts": args.parts,
                        "grid": args.grid,
                        "cell": args.cell,
                        "tol": args.tol,
                        "library": library.name,
                    }
                )
        if not jobs:
            raise SystemExit("nothing to convert")

        print(f"{len(jobs)} models", file=sys.stderr)
        results: list[dict[str, Any]] = []
        with ProcessPoolExecutor(max_workers=args.jobs or None) as pool:
            for n, result in enumerate(pool.map(one, jobs), 1):
                if result is None:
                    continue
                if "error" in result:
                    print(f"  ! {result['error']}", file=sys.stderr)
                    continue
                results.append(result)
                if n % 50 == 0:
                    print(f"  {n}/{len(jobs)}", file=sys.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if args.min_iou > 0:
        keep = [r for r in results if r["report"].get("iou", 1.0) >= args.min_iou]
        dropped = len(results) - len(keep)
        if dropped:
            worst = sorted(results, key=lambda r: r["report"].get("iou", 1.0))[:dropped]
            print(
                f"dropped {dropped} items below IoU {args.min_iou}: " + ", ".join(r["item"]["id"] for r in worst[:10]),
                file=sys.stderr,
            )
        results = keep

    args.out.mkdir(parents=True, exist_ok=True)
    if args.by_room:
        buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for result in results:
            key = ROOMS.get(result["category"], ("diverses", "Diverses"))
            buckets.setdefault(key, []).append(result)
        groups = [
            (f"{args.id}.{slug_id}", f"{args.name} - {label}", rows)
            for (slug_id, label), rows in sorted(buckets.items())
        ]
    else:
        groups = [(args.id, args.name, results)]

    written = []
    for pack_id, pack_name, rows in groups:
        count = max(1, -(-len(rows) // args.max_items))  # as few packs as fit
        per = -(-len(rows) // count)  # and then evenly, so no pack holds a single item
        chunks = [rows[i : i + per] for i in range(0, len(rows), per)]
        for n, chunk in enumerate(chunks, 1):
            this_id = pack_id if len(chunks) == 1 else f"{pack_id}{n}"
            payload = {
                "format": "fp3dpack",
                "version": 1,
                "id": this_id,
                "name": (pack_name if len(chunks) == 1 else f"{pack_name} {n}")[:80],
                "publisher": args.publisher,
                "description": f"{len(chunk)} Möbel aus Sweet-Home-3D-Bibliotheken"[:400],
                "release": 1,
                "items": [r["item"] for r in chunk],
            }
            out = args.out / f"{this_id}.json"
            text = json.dumps(payload, ensure_ascii=False, indent=1)
            out.write_text(text + "\n", encoding="utf-8")
            written.append((this_id, len(chunk), len(text)))
            print(f"{this_id}: {len(chunk)} items, {len(text) / 1000:.0f} kB -> {out}", file=sys.stderr)

    scores = sorted((r["report"].get("iou", 0.0), r["item"]["id"]) for r in results)
    if scores:
        values = [s for s, _ in scores]
        median = values[len(values) // 2]
        print(
            f"likeness (IoU): median {median:.2f}, worst {values[0]:.2f}, best {values[-1]:.2f}; "
            f"under 0.5: {sum(1 for v in values if v < 0.5)}",
            file=sys.stderr,
        )
        print("  weakest: " + ", ".join(f"{i} {s:.2f}" for s, i in scores[:8]), file=sys.stderr)

    if args.credits:
        lines = [f"# Quellen: {', '.join(p.name for p in args.library)}", ""]
        for result in sorted(results, key=lambda r: r["item"]["id"]):
            name = result["item"]["name"].get("de") or result["item"]["name"].get("en", "")
            lines.append(f"- {name} ({result['item']['id']}) - {result['creator']}, {result['license']}")
        args.credits.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"credits -> {args.credits}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
