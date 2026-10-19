"""Fork feature: the tools that shape furniture out of 3D models (see FORK.md).

tools/mesh2pack.py turns a model into the boxes and cylinders a pack item is made of, and
tools/sh3d_import.py reads a Sweet Home 3D library. Both only produce data for packs.py, so
these tests pin what matters: that a shape comes out as the solid it stands for, that an item
passes the real ITEM_SCHEMA, and that a catalogue entry becomes the right kind of item.

numpy and scipy are not part of requirements_test.txt, so the tests that need them skip when
they are missing; the ones that do not need them always run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from custom_components.neonplan3d import packs

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _tool(name: str):
    """Load a tool module by path (tools/ is not a package)."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(f"fp3d_{name}", TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- colours: no model data needed ----------------------------------------


def test_material_name_beats_colour() -> None:
    """A part called "seat" is a cushion whatever colour the model gave it."""
    m2p = _tool("mesh2pack")
    assert m2p.role_of((0.1, 0.9, 0.2), "seat") == "cushion"
    assert m2p.role_of((0.9, 0.9, 0.9), "wooden_leg") == "wood"
    assert m2p.role_of((0.5, 0.5, 0.5), "chrome_frame") == "metal"


def test_green_is_not_a_plant_unless_asked() -> None:
    """Whoever built the model picked its colours freely: a green armchair is not a shrub."""
    m2p = _tool("mesh2pack")
    assert m2p.role_of((0.33, 0.76, 0.29)) != "plant"
    assert m2p.role_of((0.33, 0.76, 0.29), plantish=True) == "plant"


def test_every_role_is_one_the_schema_knows() -> None:
    """Whatever colour a model carries, the role must pass _COLOR of PART_SCHEMA."""
    m2p = _tool("mesh2pack")
    probes = [(0, 0, 0), (1, 1, 1), (0.5, 0.5, 0.5), (0.8, 0.1, 0.1), (0.1, 0.1, 0.8), (0.6, 0.4, 0.2)]
    for rgb in probes:
        for alpha in (1.0, 0.3):
            role = m2p.role_of(rgb, alpha=alpha)
            packs.PART_SCHEMA({"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": role})


def test_roles_and_palette_agree() -> None:
    """Every role the tool can produce has a colour for the preview, and none is invented."""
    m2p = _tool("mesh2pack")
    hinted = {role for _, role in m2p.NAME_HINTS}
    assert hinted <= set(m2p.ROLE_RGB)
    for role in m2p.ROLE_RGB:
        packs.PART_SCHEMA({"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": role})


# --- the shapes: these need numpy -----------------------------------------


def test_a_hollow_shell_becomes_solid() -> None:
    """Models of furniture are hollow. The inside has to come out solid, or every part is a sheet."""
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shell = np.zeros((10, 10, 10), dtype=bool)
    shell[0, :, :] = shell[-1, :, :] = True
    shell[:, 0, :] = shell[:, -1, :] = True
    shell[:, :, 0] = shell[:, :, -1] = True
    solid = m2p.solidify(shell)
    assert solid.all()


def test_an_open_bay_stays_open() -> None:
    """A shelf is open at the front, and filling it up would make it a cupboard."""
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shell = np.zeros((10, 10, 10), dtype=bool)
    shell[:, 0, :] = shell[:, -1, :] = True  # bottom and top shelf
    shell[0, :, :] = shell[-1, :, :] = True  # the two sides
    shell[:, :, 0] = True  # the back, nothing at the front
    solid = m2p.solidify(shell)
    assert not solid[5, 5, 8], "the bay in front of the back panel must stay empty"


def test_a_box_is_covered_by_one_part() -> None:
    """A solid block needs one box, not a staircase of slivers."""
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((12, 12, 12), dtype=bool)
    solid[2:10, 2:10, 2:10] = True
    boxes = m2p.cover(solid, 20)
    assert len(boxes) == 1
    assert boxes[0] == [2, 2, 2, 10, 10, 10]


def test_a_part_grows_in_every_direction() -> None:
    """The seat of a chair is a cushion, not a sheet of paper: a box must not eat one axis first."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((16, 16, 16), dtype=bool)
    solid[3:13, 3:13, 3:13] = True
    box = m2p.cover(solid, 4)[0]
    sides = (box[3] - box[0], box[4] - box[1], box[5] - box[2])
    assert min(sides) >= 8, f"the part came out flat: {sides}"


def test_quality_sees_a_bad_cover() -> None:
    """The likeness measure has to tell a fitting part from one that misses the model."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((10, 10, 10), dtype=bool)
    solid[0:5, 0:10, 0:10] = True
    good = [{"shape": "box", "x": -0.25, "z": 0, "w": 0.5, "d": 1, "y": 0, "h": 1, "color": "body"}]
    bad = [{"shape": "box", "x": 0.4, "z": 0, "w": 0.2, "d": 0.2, "y": 0, "h": 0.2, "color": "body"}]
    assert m2p.quality(good, solid) > 0.9
    assert m2p.quality(bad, solid) < 0.2


def test_parts_fit_the_schema_and_the_item_is_valid(tmp_path: Path) -> None:
    """A built item must pass the integration's own schema, or the whole pack is refused."""
    pytest.importorskip("scipy")
    trimesh = pytest.importorskip("trimesh")
    m2p = _tool("mesh2pack")
    path = tmp_path / "box.ply"
    trimesh.creation.box(extents=(1.0, 0.5, 0.8)).export(path)
    item = m2p.build_item(path, "block", {"de": "Block", "en": "Block"}, size=(1.0, 0.8, 0.5))
    packs.ITEM_SCHEMA(item)
    assert 1 <= len(item["parts"]) <= 60
    assert item["size"] == [1.0, 0.8, 0.5]


def test_share_out_gives_every_block_a_part() -> None:
    """A small block still gets one part, so the legs of a chair do not vanish."""
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shares = m2p.share_out([1000, 10, 10, 10, 10], 12)
    assert len(shares) == 5
    assert min(shares) >= 1
    assert sum(shares) == 12
    assert shares[0] == max(shares)


def test_share_out_never_promises_more_than_the_budget() -> None:
    """More blocks than parts: the budget still holds, the smallest blocks drop out."""
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shares = m2p.share_out([10] * 20, 5)
    assert sum(shares) == 5


# --- the catalogue ---------------------------------------------------------


def test_a_lamp_becomes_a_lamp() -> None:
    """The catalogue's category decides the light kind, mount and whether it draws power."""
    sh3d = _tool("sh3d_import")
    out = sh3d.traits({"category": "Lights", "name": "Ceiling lamp", "_names": {"de": "Deckenlampe"}, "height": "30"})
    assert out["light"] == "ceiling"
    assert out["mount"] == "ceiling"
    assert out["electric"] is True


def test_a_wall_lamp_hangs_at_its_height() -> None:
    """A piece the catalogue puts above the floor belongs on the wall, at that height."""
    sh3d = _tool("sh3d_import")
    out = sh3d.traits(
        {"category": "Lights", "name": "Wall light", "_names": {"en": "Wall light"}, "height": "25", "elevation": "180"}
    )
    assert out["light"] == "wall"
    assert out["mount"] == "wall"
    assert out["wall_y"] == pytest.approx(1.8)


def test_stairs_cut_a_hole_and_cars_park() -> None:
    """Stairs and vehicles carry the flags NeonPlan 3D needs to place them."""
    sh3d = _tool("sh3d_import")
    assert sh3d.traits({"category": "Staircases", "name": "Stairs", "_names": {}, "height": "250"})["hole"] is True
    assert sh3d.traits({"category": "Vehicles", "name": "Car", "_names": {}, "height": "150"})["vehicle"] is True


def test_a_table_carries_things() -> None:
    """A piece whose catalogue entry drops things on its top is a surface."""
    sh3d = _tool("sh3d_import")
    out = sh3d.traits(
        {"category": "Living room", "name": "Table", "_names": {}, "height": "75", "dropOnTopElevation": "75"}
    )
    assert out.get("surface") is True


def test_traits_pass_the_item_schema() -> None:
    """Whatever the catalogue says, the fields have to be ones ITEM_SCHEMA accepts."""
    sh3d = _tool("sh3d_import")
    entries = [
        {"category": "Lights", "name": "Pendant", "_names": {}, "height": "40", "elevation": "200"},
        {"category": "Staircases", "name": "Stairs", "_names": {}, "height": "250"},
        {"category": "Kitchen", "name": "Fridge", "_names": {}, "height": "180", "dropOnTopElevation": "180"},
        {"category": "Miscellaneous", "name": "Mirror", "_names": {}, "height": "60", "elevation": "120"},
    ]
    part = {"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": "body"}
    for entry in entries:
        item = {"id": "x", "name": {"en": "X"}, "size": [1, 1, 1], "parts": [part], **sh3d.traits(entry)}
        packs.ITEM_SCHEMA(item)


def test_doors_and_windows_are_left_to_neonplan() -> None:
    """NeonPlan 3D draws doors and windows itself, as part of the wall."""
    sh3d = _tool("sh3d_import")
    assert "Doors and windows" in sh3d.SKIP_CATEGORIES


def test_item_ids_stay_unique_and_legal() -> None:
    """Two pieces of the same name must not collide, and an id has to match the schema."""
    sh3d = _tool("sh3d_import")
    used: set[str] = set()
    ids = [sh3d.slug(name, used) for name in ("Chair", "Chair", "Chair", "Ärmchair!", "")]
    assert len(set(ids)) == len(ids)
    part = {"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": "body"}
    for item_id in ids:
        packs.ITEM_SCHEMA({"id": item_id, "name": {"en": "X"}, "size": [1, 1, 1], "parts": [part]})
