#!/usr/bin/env python3
"""Turn a 3D model (OBJ, GLB, STL, PLY, 3DS, DAE) into a NeonPlan 3D furniture item.

A pack item is not a mesh: it is up to 60 boxes, cylinders and lofts in fractions of the item's
size (see packs.py PART_SCHEMA). This tool gets there in four steps:

1. load the model and scale it to the real size of the piece (metres);
2. split it into its building blocks - first by material, then into the pieces that hang
   together (the four legs of a chair are four blocks, not one) - and voxelize each into a
   solid grid. The surface is sampled and the inside filled from three directions, so a model
   that is not watertight still comes out solid while an open shelf stays open;
3. cover every block with the largest axis-aligned boxes that fit, sharing out the parts
   budget by size. Boxes grow evenly in all directions, so a seat comes out as a cushion and
   not as a sheet of paper, and they may overlap, which buys a better likeness per part;
4. give every box the palette role of its material, so imported furniture keeps the look of
   the plan instead of carrying the colours of whoever built the model.

A box whose solid fills it like a circle fills a square becomes a "cyl", and one that tapers
from bottom to top becomes a "loft".

    mesh2pack.py item chair.obj --size 0.45 0.5 0.9 --id chair --name de=Stuhl,en=Chair
    mesh2pack.py pack out/*.json --id local.myhome --name "Eigene Möbel" -o pack.json
    mesh2pack.py preview item.json -o item.png          # see what the parts look like

Then sign it:  fp3dpack.py sign pack.json --key private/....pem -o pack.fp3dpack
"""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

# --- palette ---------------------------------------------------------------
# The roles of the built-in palette (frontend/src/viewer/furniture.ts) with the colour they stand
# for in the plan. Mapping a model's colours onto roles instead of hex keeps imported furniture in
# the look of the plan, and it follows a theme change.
ROLE_RGB: dict[str, tuple[int, int, int]] = {
    "body": (0x17, 0x22, 0x38),
    "fabric": (0x1A, 0x26, 0x44),
    "cushion": (0x24, 0x36, 0x61),
    "wood": (0x19, 0x23, 0x3C),
    "white": (0x1D, 0x29, 0x46),
    "metal": (0x2A, 0x3A, 0x60),
    "dark": (0x0B, 0x11, 0x1F),
    "glass": (0x1C, 0x3A, 0x52),
    "plant": (0x12, 0x30, 0x2E),
    "pot": (0x1D, 0x26, 0x40),
    "accent": (0x2B, 0x8F, 0xB3),
}

# A material name says more than its colour: these win over the colour rules below.
NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("cushion", "cushion"),
    ("pillow", "cushion"),
    ("kissen", "cushion"),
    ("seat", "cushion"),
    ("sitz", "cushion"),
    ("armrest", "cushion"),
    ("backrest", "cushion"),
    ("lehne", "cushion"),
    ("headboard", "cushion"),
    ("mattress", "cushion"),
    ("duvet", "cushion"),
    ("blanket", "cushion"),
    ("sofa", "cushion"),
    ("upholster", "cushion"),
    ("polster", "cushion"),
    ("fabric", "fabric"),
    ("cloth", "fabric"),
    ("textile", "fabric"),
    ("stoff", "fabric"),
    ("curtain", "fabric"),
    ("carpet", "fabric"),
    ("rug", "fabric"),
    ("leather", "fabric"),
    ("wood", "wood"),
    ("holz", "wood"),
    ("oak", "wood"),
    ("pine", "wood"),
    ("beech", "wood"),
    ("walnut", "wood"),
    ("timber", "wood"),
    ("plank", "wood"),
    ("bamboo", "wood"),
    ("metal", "metal"),
    ("steel", "metal"),
    ("stahl", "metal"),
    ("chrome", "metal"),
    ("chrom", "metal"),
    ("alu", "metal"),
    ("iron", "metal"),
    ("brass", "metal"),
    ("inox", "metal"),
    ("leg", "metal"),
    ("feet", "metal"),
    ("foot", "metal"),
    ("bein", "metal"),
    ("frame", "metal"),
    ("rahmen", "metal"),
    ("handle", "metal"),
    ("griff", "metal"),
    ("hinge", "metal"),
    ("faucet", "metal"),
    ("tap", "metal"),
    ("glass", "glass"),
    ("glas", "glass"),
    ("window", "glass"),
    ("mirror", "glass"),
    ("spiegel", "glass"),
    ("screen", "dark"),
    ("display", "dark"),
    ("tv", "dark"),
    ("plant", "plant"),
    ("leaf", "plant"),
    ("leaves", "plant"),
    ("foliage", "plant"),
    ("pflanze", "plant"),
    ("blatt", "plant"),
    ("grass", "plant"),
    ("tree", "plant"),
    ("pot", "pot"),
    ("topf", "pot"),
    ("vase", "pot"),
    ("ceramic", "white"),
    ("porcelain", "white"),
    ("white", "white"),
    ("weiss", "white"),
    ("paper", "white"),
    ("marble", "white"),
    ("rubber", "dark"),
    ("tyre", "dark"),
    ("tire", "dark"),
    ("shoe", "dark"),
    ("black", "dark"),
    ("schwarz", "dark"),
)


def role_of(rgb: tuple[float, float, float], name: str = "", alpha: float = 1.0, plantish: bool = False) -> str:
    """The palette role that best stands for a model colour.

    `plantish` allows green to mean a plant. It is off by default: whoever built the model picked
    its colours freely, and a green armchair is an armchair, not a shrub. Only a model we know to
    be greenery (a plant, a tree, the garden) turns it on.
    """
    low = name.lower()
    for needle, role in NAME_HINTS:
        if needle in low:
            return role
    if alpha < 0.65:
        return "glass"
    r, g, b = (max(0.0, min(1.0, c)) for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    deg = h * 360.0
    if plantish and s > 0.22 and 70 <= deg <= 165:
        return "plant"
    if v < 0.13:
        return "dark"
    if s > 0.28 and 170 <= deg <= 265:
        return "accent"
    if s > 0.18 and (deg <= 52 or deg >= 345):
        # warm: wood for the dark half, fabric for a bright red or orange
        return "wood" if v < 0.62 else "fabric"
    if s < 0.13:
        if v > 0.74:
            return "white"
        if v > 0.3:
            return "metal"
        return "body"
    if s > 0.3:
        return "fabric"
    return "body"


# --- loading ---------------------------------------------------------------


def load_faces(path: Path, plantish: bool = False) -> tuple[Any, list[tuple[int, int, str]]]:
    """The model as one mesh plus its material groups as (first face, last face + 1, palette role).

    Groups are what the model was built from - a chair's seat, legs and armrests are separate
    materials - and they carry the colour, so every part comes out in one clean role.
    """
    import trimesh
    import trimesh.util

    loaded = trimesh.load(str(path), process=False)
    parts = []
    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise SystemExit(f"{path.name}: no geometry")
        # bake the scene graph, so a model whose parts sit in nodes comes out in place
        for node in loaded.graph.nodes_geometry:
            transform, geom_name = loaded.graph[node]
            geom = loaded.geometry.get(geom_name)
            if geom is None or not hasattr(geom, "faces") or len(geom.faces) == 0:
                continue
            geom = geom.copy()
            geom.apply_transform(transform)
            parts.append(geom)
    elif hasattr(loaded, "faces"):
        parts.append(loaded)
    if not parts:
        raise SystemExit(f"{path.name}: no faces")

    groups: list[tuple[int, int, str]] = []
    at = 0
    for geom in parts:
        material = getattr(geom.visual, "material", None)
        name = str(getattr(material, "name", "") or "")
        rgba = np.array([0.6, 0.6, 0.6, 1.0])
        main = getattr(material, "main_color", None) if material is not None else None
        if main is not None and len(main) >= 3:
            rgba = np.asarray(main, dtype=float)[:4] / 255.0
            if len(main) == 3:
                rgba = np.append(rgba, 1.0)
        else:
            try:  # vertex or face colours, when the model carries no material
                face_col = geom.visual.face_colors
                if face_col is not None and len(face_col):
                    rgba = np.asarray(face_col, dtype=float).mean(axis=0)[:4] / 255.0
            except Exception:
                pass
        role = role_of((rgba[0], rgba[1], rgba[2]), name, float(rgba[3]), plantish=plantish)
        groups.append((at, at + len(geom.faces), role))
        at += len(geom.faces)

    return trimesh.util.concatenate(parts), groups


def normalise(mesh: Any, size: tuple[float, float, float] | None) -> tuple[Any, tuple[float, float, float]]:
    """Scale the model to `size` (w, d, h in metres), centre it in x/z and put its bottom at y=0.

    Model axes are the same as the item's: x across, y up, z depth. Without a size the model's own
    extent is taken as metres.
    """
    mesh = mesh.copy()
    lo, hi = mesh.bounds
    extent = np.maximum(hi - lo, 1e-9)
    own = np.array([extent[0], extent[2], extent[1]], dtype=float)
    if own.max() > 25:  # a model in centimetres
        own = own / 100.0
    if size is None:
        target = own
    else:
        # a catalogue entry may give 0 for a flat piece (a rug, a picture): take the model's own
        target = np.array([s if s and s > 0 else o for s, o in zip(size, own, strict=True)], dtype=float)
    # the schema allows 1 cm to 10 m per side
    target = np.clip(target, 0.01, 10.0)
    scale = np.array([target[0] / extent[0], target[2] / extent[1], target[1] / extent[2]])
    mesh.apply_translation(-lo)
    mesh.apply_scale(scale)
    mesh.apply_translation([-target[0] / 2.0, 0.0, -target[1] / 2.0])
    return mesh, (float(target[0]), float(target[1]), float(target[2]))


# --- voxels ----------------------------------------------------------------


def between(surface: np.ndarray, axis: int) -> np.ndarray:
    """Cells that lie between the first and the last hit of the surface along `axis`."""
    moved = np.moveaxis(surface, axis, -1)
    depth = moved.shape[-1]
    hit = moved.any(axis=-1)
    first = np.where(hit, np.argmax(moved, axis=-1), depth)
    last = np.where(hit, depth - 1 - np.argmax(moved[..., ::-1], axis=-1), -1)
    line = np.arange(depth)
    inside = (line >= first[..., None]) & (line <= last[..., None])
    return np.moveaxis(inside, -1, axis)


def solidify(surface: np.ndarray) -> np.ndarray:
    """A surface shell as a solid body: a cell is inside when it is inside along all three axes.

    Models of furniture are hollow shells, often not even watertight, so filling enclosed holes
    finds almost nothing. Looking from all three sides instead turns a shell into the block it
    stands for, while the gap under a seat (nothing above or below it) and the empty bay of a
    shelf (open at the front) stay empty, because there one of the three says no.
    """
    inside = between(surface, 0) & between(surface, 1) & between(surface, 2)
    return inside | surface


def blocks(
    mesh: Any,
    groups: list[tuple[int, int, str]],
    grid: tuple[int, int, int],
    samples: int = 300_000,
    crumb: float = 0.004,
) -> list[tuple[np.ndarray, str]]:
    """The model's building blocks: for every material, the pieces of it that hang together.

    A chair comes back as its seat, its back and its four legs, each with its own palette role,
    instead of one blob - that is what makes the parts land where the eye expects them.
    """
    from scipy.ndimage import label
    import trimesh

    nx, ny, nz = grid
    lo, hi = mesh.bounds
    span = np.maximum(hi - lo, 1e-9)
    points, face_index = trimesh.sample.sample_surface(mesh, samples)
    rel = (points - lo) / span
    cells = np.stack(
        [
            np.clip((rel[:, 0] * nx).astype(int), 0, nx - 1),
            np.clip((rel[:, 1] * ny).astype(int), 0, ny - 1),
            np.clip((rel[:, 2] * nz).astype(int), 0, nz - 1),
        ],
        axis=1,
    )

    whole = np.zeros(grid, dtype=bool)
    whole[cells[:, 0], cells[:, 1], cells[:, 2]] = True
    total = max(int(solidify(whole).sum()), 1)

    neighbourhood = np.ones((3, 3, 3), dtype=bool)
    found: list[tuple[np.ndarray, str]] = []
    for first, last, role in groups:
        take = (face_index >= first) & (face_index < last)
        if not take.any():
            continue
        shell = np.zeros(grid, dtype=bool)
        sub = cells[take]
        shell[sub[:, 0], sub[:, 1], sub[:, 2]] = True
        solid = solidify(shell)
        tagged, count = label(solid, structure=neighbourhood)
        for piece in range(1, count + 1):
            mask = tagged == piece
            if int(mask.sum()) < crumb * total:  # a screw, a trim strip: not worth a part
                continue
            found.append((mask, role))
    if not found:  # a model without usable materials: take it as one block
        found = [(solidify(whole), groups[0][2] if groups else "body")]
    found.sort(key=lambda b: -int(b[0].sum()))
    return found


# --- covering a block with boxes -------------------------------------------


def grow(solid: np.ndarray, box: list[int], tol: float, limit: tuple[int, int, int]) -> None:
    """Grow `box` (x0, y0, z0, x1, y1, z1, half-open) as far as the solid carries it.

    Each round weighs all six directions and takes the one that adds the most solid cells. Without
    that, the order of the directions decides: a box eats one axis to the end before it tries the
    others, and a seat cushion comes out a sheet of paper. A slice must be solid enough (`tol`) to
    be taken at all, so a box never grows out into thin air.
    """
    while True:
        best: tuple[float, int, int] | None = None
        for axis in range(3):
            for direction in (1, -1):
                lo_i, hi_i = axis, axis + 3
                probe = list(box)
                if direction > 0:
                    if probe[hi_i] >= limit[axis]:
                        continue
                    probe[lo_i], probe[hi_i] = box[hi_i], box[hi_i] + 1
                else:
                    if probe[lo_i] <= 0:
                        continue
                    probe[hi_i], probe[lo_i] = box[lo_i], box[lo_i] - 1
                slab = solid[probe[0] : probe[3], probe[1] : probe[4], probe[2] : probe[5]]
                if not slab.size:
                    continue
                if float(slab.mean()) < tol:
                    continue
                score = float(slab.sum())
                if best is None or score > best[0]:
                    best = (score, axis, direction)
        if best is None:
            return
        _, axis, direction = best
        box[axis + 3 if direction > 0 else axis] += direction


def cover(solid: np.ndarray, max_parts: int, tol: float = 0.7, rest_stop: float = 0.06) -> list[list[int]]:
    """Cover a block with at most `max_parts` boxes, the thickest places first.

    Boxes grow against the block, not against what is still uncovered, so they may overlap. For a
    drawing that costs nothing and buys a better likeness per part: a round table top becomes one
    slab instead of a staircase of slivers.
    """
    from scipy.ndimage import distance_transform_edt

    total = int(solid.sum())
    if not total:
        return []
    limit = solid.shape
    rest = solid.copy()
    boxes: list[list[int]] = []
    while len(boxes) < max_parts:
        if int(rest.sum()) <= rest_stop * total:
            break
        # start where the uncovered rest is thickest: that is a real part of the piece, not a crumb
        dist = distance_transform_edt(rest)
        seed = np.unravel_index(int(np.argmax(dist)), dist.shape)
        sx, sy, sz = (int(v) for v in seed)
        box = [sx, sy, sz, sx + 1, sy + 1, sz + 1]
        grow(solid, box, tol, limit)
        before = int(rest.sum())
        rest[box[0] : box[3], box[1] : box[4], box[2] : box[5]] = False
        if int(rest.sum()) == before:  # no progress: drop the seed cell and carry on
            rest[sx, sy, sz] = False
            continue
        boxes.append(box)
    boxes.sort(key=lambda b: -((b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2])))
    return boxes


def share_out(sizes: list[int], budget: int) -> list[int]:
    """How many parts each block gets: one each, the rest by size (damped, so small blocks count)."""
    if not sizes:
        return []
    count = min(len(sizes), budget)
    sizes = sizes[:count]
    shares = [1] * count
    left = budget - count
    if left > 0:
        weight = np.array(sizes, dtype=float) ** 0.55
        weight /= weight.sum()
        extra = np.floor(weight * left).astype(int)
        for i in np.argsort(-(weight * left - extra))[: left - int(extra.sum())]:
            extra[i] += 1
        shares = [s + int(e) for s, e in zip(shares, extra, strict=True)]
    return shares


def shape_of(solid: np.ndarray, box: list[int]) -> tuple[str, dict[str, float]]:
    """ "box", "cyl" or "loft" for the solid inside `box`, plus the extra loft fields."""
    x0, y0, z0, x1, y1, z1 = box
    inside = solid[x0:x1, y0:y1, z0:z1]
    nx, ny, nz = inside.shape
    extra: dict[str, float] = {}
    if inside.size == 0:
        return "box", extra
    fill = float(inside.mean())

    # a cylinder: square footprint, round in plan, same from bottom to top
    if nx >= 4 and nz >= 4 and 0.55 <= fill <= 0.93 and 0.6 <= nx / nz <= 1.667:
        plan = inside.any(axis=1)
        yy, xx = np.mgrid[0:nx, 0:nz]
        cx, cz = (nx - 1) / 2.0, (nz - 1) / 2.0
        radius = min(nx, nz) / 2.0
        circle = ((yy - cx) / max(radius, 1e-9)) ** 2 + ((xx - cz) / max(radius, 1e-9)) ** 2 <= 1.0
        agree = float((plan == circle).mean())
        corners = float(plan[:: max(nx - 1, 1), :: max(nz - 1, 1)].mean())
        if agree >= 0.86 and corners <= 0.3:
            return "cyl", extra

    # a loft: the footprint at the top is clearly smaller or larger than at the bottom
    if ny >= 4:
        third = max(1, ny // 3)
        bottom = inside[:, :third, :].any(axis=1)
        top = inside[:, -third:, :].any(axis=1)
        if bottom.any() and top.any():

            def span(plan: np.ndarray) -> tuple[float, float, float, float]:
                xs = np.where(plan.any(axis=1))[0]
                zs = np.where(plan.any(axis=0))[0]
                return (
                    (xs[-1] + 1 - xs[0]) / nx,
                    (zs[-1] + 1 - zs[0]) / nz,
                    (xs[-1] + 1 + xs[0]) / 2.0 / nx - 0.5,
                    (zs[-1] + 1 + zs[0]) / 2.0 / nz - 0.5,
                )

            bw, bd, bcx, bcz = span(bottom)
            tw, td, tcx, tcz = span(top)
            if (min(tw / max(bw, 1e-9), td / max(bd, 1e-9)) < 0.72) or (
                max(tw / max(bw, 1e-9), td / max(bd, 1e-9)) > 1.38
            ):
                extra = {
                    "tw": max(0.05, min(1.0, tw / max(bw, 1e-9))),
                    "td": max(0.05, min(1.0, td / max(bd, 1e-9))),
                }
                if abs(tcx - bcx) > 0.06:
                    extra["tx"] = tcx - bcx
                if abs(tcz - bcz) > 0.06:
                    extra["tz"] = tcz - bcz
                return "loft", extra
    return "box", extra


# --- how good is it --------------------------------------------------------


def parts_solid(parts: list[dict[str, Any]], shape: tuple[int, int, int]) -> np.ndarray:
    """Draw an item's parts back into a voxel grid, to compare them with the model."""
    nx, ny, nz = shape
    grid = np.zeros(shape, dtype=bool)
    gx, gy, gz = np.mgrid[0:nx, 0:ny, 0:nz]
    fx = (gx + 0.5) / nx - 0.5
    fy = (gy + 0.5) / ny
    fz = (gz + 0.5) / nz - 0.5
    for part in parts:
        y0, y1 = part["y"], part["y"] + part["h"]
        level = (fy >= y0) & (fy < y1)
        if not level.any():
            continue
        if part["shape"] == "loft":
            # the cross-section tapers with height
            t = np.clip((fy - y0) / max(part["h"], 1e-9), 0, 1)
            half_w = part["w"] / 2 * (1 + t * (part.get("tw", 1.0) - 1))
            half_d = part["d"] / 2 * (1 + t * (part.get("td", 1.0) - 1))
            cx = part["x"] + t * part.get("tx", 0.0)
            cz = part["z"] + t * part.get("tz", 0.0)
        else:
            half_w = np.full(shape, part["w"] / 2)
            half_d = np.full(shape, part["d"] / 2)
            cx = np.full(shape, part["x"])
            cz = np.full(shape, part["z"])
        dx = np.abs(fx - cx)
        dz = np.abs(fz - cz)
        if part["shape"] == "cyl":
            inside = (dx / np.maximum(half_w, 1e-9)) ** 2 + (dz / np.maximum(half_d, 1e-9)) ** 2 <= 1.0
        else:
            inside = (dx <= half_w) & (dz <= half_d)
        grid |= level & inside
    return grid


def quality(parts: list[dict[str, Any]], solid: np.ndarray) -> float:
    """How much of the model the parts hit, as intersection over union (1 = perfect)."""
    drawn = parts_solid(parts, solid.shape)  # type: ignore[arg-type]
    union = int((drawn | solid).sum())
    return float((drawn & solid).sum()) / union if union else 0.0


# --- the item --------------------------------------------------------------


def _round(value: float, digits: int = 4) -> float:
    out = round(float(value), digits)
    return 0.0 if out == 0 else out


def build_item(
    path: Path,
    item_id: str,
    names: dict[str, str],
    size: tuple[float, float, float] | None = None,
    max_parts: int = 28,
    grid: int = 30,
    tol: float = 0.7,
    plantish: bool = False,
    extras: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A pack item for the model at `path`; `report` collects how well it came out."""
    mesh, groups = load_faces(path, plantish=plantish)
    mesh, real = normalise(mesh, size)
    span = mesh.bounds[1] - mesh.bounds[0]
    longest = max(float(span.max()), 1e-9)
    shape = (
        max(3, round(grid * float(span[0]) / longest)),
        max(3, round(grid * float(span[1]) / longest)),
        max(3, round(grid * float(span[2]) / longest)),
    )
    found = blocks(mesh, groups, shape)
    shares = share_out([int(mask.sum()) for mask, _ in found], max_parts)

    nx, ny, nz = shape
    parts: list[dict[str, Any]] = []
    for (mask, role), budget in zip(found, shares, strict=False):
        for box in cover(mask, budget, tol=tol):
            x0, y0, z0, x1, y1, z1 = box
            kind, extra = shape_of(mask, box)
            width = max(0.004, (x1 - x0) / nx)
            depth = max(0.004, (z1 - z0) / nz)
            if kind == "cyl":
                # the viewer takes the smaller of the two as the diameter, so say what we mean
                width = depth = min(width, depth)
            part: dict[str, Any] = {
                "shape": kind,
                "x": _round((x0 + x1) / 2.0 / nx - 0.5),
                "z": _round((z0 + z1) / 2.0 / nz - 0.5),
                "w": _round(width),
                "d": _round(depth),
                "y": _round(y0 / ny),
                "h": _round(max(0.004, (y1 - y0) / ny)),
                "color": role,
            }
            for key, value in extra.items():
                part[key] = _round(value)
            parts.append(part)
    if not parts:  # a model we could not voxelize: one block, so the item still works
        parts = [{"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": "body"}]

    # biggest first, and that one carries the outline so the piece reads as one body in the plan
    parts.sort(key=lambda p: -(p["w"] * p["d"] * p["h"]))
    parts[0]["edges"] = True

    item: dict[str, Any] = {
        "id": item_id,
        "name": names,
        "size": [_round(real[0], 3), _round(real[1], 3), _round(real[2], 3)],
        "parts": parts,
    }
    if extras:
        item.update(extras)
    if report is not None:
        whole = np.zeros(shape, dtype=bool)
        for mask, _ in found:
            whole |= mask
        report["iou"] = round(quality(parts, whole), 3)
        report["blocks"] = len(found)
        report["cells"] = int(whole.sum())
    return item


# --- preview ---------------------------------------------------------------


def render_parts(item: dict[str, Any], width: int = 320) -> Any:
    """A small picture of an item's parts from the front-left, to see what was made."""
    from PIL import Image

    sw, sd, sh = item["size"]
    tris: list[tuple[np.ndarray, str]] = []
    for part in item["parts"]:
        cx, cz = part["x"] * sw, part["z"] * sd
        w, d = part["w"] * sw, part["d"] * sd
        y0, h = part["y"] * sh, part["h"] * sh
        tw = part.get("tw", 1.0) * w
        td = part.get("td", 1.0) * d
        tx = cx + part.get("tx", 0.0) * sw
        tz = cz + part.get("tz", 0.0) * sd
        if part["shape"] == "cyl":
            steps = 16
            ang = np.linspace(0, 2 * np.pi, steps, endpoint=False)
            rx, rz = w / 2, d / 2
            ring_lo = np.stack([cx + rx * np.cos(ang), np.full(steps, y0), cz + rz * np.sin(ang)], axis=1)
            ring_hi = np.stack([cx + rx * np.cos(ang), np.full(steps, y0 + h), cz + rz * np.sin(ang)], axis=1)
        else:
            corners = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]])
            ring_lo = np.stack([cx + corners[:, 0] * w, np.full(4, y0), cz + corners[:, 1] * d], axis=1)
            ring_hi = np.stack([tx + corners[:, 0] * tw, np.full(4, y0 + h), tz + corners[:, 1] * td], axis=1)
        n = len(ring_lo)
        for i in range(n):
            j = (i + 1) % n
            tris.append((np.array([ring_lo[i], ring_lo[j], ring_hi[j]]), part["color"]))
            tris.append((np.array([ring_lo[i], ring_hi[j], ring_hi[i]]), part["color"]))
        for ring in (ring_lo, ring_hi):
            for i in range(1, n - 1):
                tris.append((np.array([ring[0], ring[i], ring[i + 1]]), part["color"]))

    # look from the front-left and slightly above
    yaw, pitch = np.radians(-35), np.radians(22)
    right = np.array([np.cos(yaw), 0, -np.sin(yaw)])
    up_dir = np.array([-np.sin(yaw) * np.sin(pitch), np.cos(pitch), -np.cos(yaw) * np.sin(pitch)])
    view = np.cross(right, up_dir)

    all_pts = np.vstack([t[0] for t in tris]) if tris else np.zeros((1, 3))
    proj = np.stack([all_pts @ right, all_pts @ up_dir], axis=1)
    lo, hi = proj.min(axis=0), proj.max(axis=0)
    scale = 0.86 * width / max((hi - lo).max(), 1e-9)
    height = int(width * 1.1)
    off = np.array([width / 2, height * 0.56]) - (lo + hi) / 2 * scale * np.array([1, -1])

    img = np.zeros((height, width, 3), dtype=np.float32)
    zbuf = np.full((height, width), -1e9, dtype=np.float32)
    light = np.array([0.4, 0.85, 0.35])
    light = light / np.linalg.norm(light)
    yy, xx = np.mgrid[0:height, 0:width]
    for tri, role in tris:
        screen = np.stack([tri @ right * scale, -(tri @ up_dir) * scale], axis=1) + off
        depth = tri @ view
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        norm = np.linalg.norm(normal)
        if norm < 1e-12:
            continue
        normal = normal / norm
        x_lo = max(int(np.floor(screen[:, 0].min())), 0)
        x_hi = min(int(np.ceil(screen[:, 0].max())) + 1, width)
        y_lo = max(int(np.floor(screen[:, 1].min())), 0)
        y_hi = min(int(np.ceil(screen[:, 1].max())) + 1, height)
        if x_hi <= x_lo or y_hi <= y_lo:
            continue
        px, py = xx[y_lo:y_hi, x_lo:x_hi], yy[y_lo:y_hi, x_lo:x_hi]
        (ax, ay), (bx, by), (cx_, cy) = screen
        den = (by - cy) * (ax - cx_) + (cx - cy * 0 - cx_) * 0 + (cx_ - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        wa = ((by - cy) * (px - cx_) + (cx_ - bx) * (py - cy)) / den
        wb = ((cy - ay) * (px - cx_) + (ax - cx_) * (py - cy)) / den
        wc = 1 - wa - wb
        inside = (wa >= -0.002) & (wb >= -0.002) & (wc >= -0.002)
        if not inside.any():
            continue
        zz = wa * depth[0] + wb * depth[1] + wc * depth[2]
        hit = inside & (zz > zbuf[y_lo:y_hi, x_lo:x_hi])
        if not hit.any():
            continue
        base = np.array(ROLE_RGB[role], dtype=np.float32) / 255.0
        shade = 0.45 + 0.9 * abs(float(normal @ light))
        colour = np.clip(base * shade * 3.1, 0, 1)
        block = img[y_lo:y_hi, x_lo:x_hi]
        block[hit] = colour
        img[y_lo:y_hi, x_lo:x_hi] = block
        zb = zbuf[y_lo:y_hi, x_lo:x_hi]
        zb[hit] = zz[hit]
        zbuf[y_lo:y_hi, x_lo:x_hi] = zb

    back = np.array([0.03, 0.05, 0.09], dtype=np.float32)
    img[zbuf <= -1e8] = back
    return Image.fromarray((img * 255).astype(np.uint8))


# --- command line ----------------------------------------------------------


def parse_names(text: str) -> dict[str, str]:
    """ "de=Stuhl,en=Chair" as the item's name map."""
    out: dict[str, str] = {}
    for chunk in text.split(","):
        if "=" in chunk:
            lang, name = chunk.split("=", 1)
            out[lang.strip()] = name.strip()
        elif chunk.strip():
            out["en"] = chunk.strip()
    return out or {"en": "Item"}


def main(argv: list[str] | None = None) -> int:
    """Run the tool."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    one = sub.add_parser("item", help="turn one model into an item")
    one.add_argument("model", type=Path)
    one.add_argument("--id", required=True)
    one.add_argument("--name", required=True, help='"de=Stuhl,en=Chair"')
    one.add_argument("--size", nargs=3, type=float, metavar=("W", "D", "H"), help="real size in metres")
    one.add_argument("--parts", type=int, default=28, help="most parts to use (max 60)")
    one.add_argument("--grid", type=int, default=30, help="voxels along the longest side")
    one.add_argument("--tol", type=float, default=0.7, help="how solid an added slice must be")
    one.add_argument("--plant", action="store_true", help="greenery: green may become the plant colour")
    one.add_argument("--surface", action="store_true", help="its top carries other items")
    one.add_argument("--mount", choices=["floor", "surface", "wall", "ceiling"])
    one.add_argument("--light", help="lamp kind (ceiling, pendant, table, …)")
    one.add_argument("--electric", action="store_true")
    one.add_argument("-o", "--out", type=Path)

    group = sub.add_parser("pack", help="collect items into a pack payload")
    group.add_argument("items", nargs="+", type=Path)
    group.add_argument("--id", required=True, help='pack id, "local.…" for an own key')
    group.add_argument("--name", required=True)
    group.add_argument("--publisher", default="Eigenbau")
    group.add_argument("--description", default="")
    group.add_argument("--release", type=int, default=1)
    group.add_argument("-o", "--out", type=Path)

    shot = sub.add_parser("preview", help="draw an item's parts")
    shot.add_argument("item", type=Path)
    shot.add_argument("-o", "--out", type=Path, required=True)
    shot.add_argument("--width", type=int, default=320)
    shot.add_argument("--columns", type=int, default=6, help="items per row on a pack sheet")

    args = parser.parse_args(argv)

    if args.cmd == "item":
        extras: dict[str, Any] = {}
        if args.surface:
            extras["surface"] = True
        if args.mount:
            extras["mount"] = args.mount
        if args.light:
            extras["light"] = args.light
        if args.electric or args.light:
            extras["electric"] = True
        item = build_item(
            args.model,
            args.id,
            parse_names(args.name),
            tuple(args.size) if args.size else None,
            max_parts=min(args.parts, 60),
            grid=args.grid,
            tol=args.tol,
            plantish=args.plant,
            extras=extras,
        )
        text = json.dumps(item, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
            print(f"{args.id}: {len(item['parts'])} parts -> {args.out}", file=sys.stderr)
        else:
            print(text)
        return 0

    if args.cmd == "pack":
        items = []
        for path in args.items:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.extend(data if isinstance(data, list) else [data])
        payload = {
            "format": "fp3dpack",
            "version": 1,
            "id": args.id,
            "name": args.name,
            "publisher": args.publisher,
            "description": args.description,
            "release": args.release,
            "items": items,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
            print(f"{args.id}: {len(items)} items, {len(text)} chars -> {args.out}", file=sys.stderr)
        else:
            print(text)
        return 0

    data = json.loads(args.item.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "items" in data:
        from PIL import Image, ImageDraw, ImageFont

        items = data["items"]
        if not items:
            raise SystemExit("the pack has no items")
        try:
            font = ImageFont.truetype("arial.ttf", 11)
        except OSError:
            font = ImageFont.load_default()
        label_height = 15
        shots = [render_parts(it, args.width) for it in items]
        columns = min(args.columns, len(shots))
        rows = (len(shots) + columns - 1) // columns
        cell_w, cell_h = shots[0].width, shots[0].height + label_height
        sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), (7, 11, 19))
        draw = ImageDraw.Draw(sheet)
        for i, (shot_img, item) in enumerate(zip(shots, items, strict=True)):
            x, y = (i % columns) * cell_w, (i // columns) * cell_h
            sheet.paste(shot_img, (x, y))
            name = item["name"].get("de") or next(iter(item["name"].values()), "")
            draw.text((x + 4, y + shot_img.height + 2), name[:26], fill=(150, 190, 255), font=font)
        sheet.save(args.out)
    else:
        render_parts(data if isinstance(data, dict) else data[0], args.width).save(args.out)
    print(f"-> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
